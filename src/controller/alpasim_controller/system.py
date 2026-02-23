# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-2026 NVIDIA Corporation

"""
Vehicle simulation system with pluggable MPC controller.

This module provides the System class which handles:
- Trajectory management and coordinate transforms
- Vehicle model simulation
- DDS request/response handling
- Logging
"""

import logging

import numpy as np
from alpasim_controller.mpc_controller import (
    ControllerInput,
    MPCController,
    MPCImplementation,
)
from alpasim_controller.vehicle_model import VehicleModel
from alpasim_dds.types.common import DynamicState, StateAtTime, Vec3
from alpasim_dds.types.controller import (
    RunControllerAndVehicleModelRequest,
    RunControllerAndVehicleModelResponse,
)
from alpasim_utils import trajectory

__all__ = ["System", "VehicleModel", "create_system"]


class System:
    """Vehicle simulation system vehicle model and controller."""

    def __init__(
        self,
        log_file: str,
        initial_state: StateAtTime,
        controller: MPCController,
    ):
        self._timestamp_us = initial_state.timestamp_us
        self._reference_trajectory = None
        self._trajectory = trajectory.Trajectory.create_empty()
        self._trajectory.update_absolute(
            initial_state.timestamp_us,
            trajectory.QVec.from_dds_pose(initial_state.pose),
        )

        self._vehicle_model = VehicleModel(
            initial_velocity=np.array(
                [
                    initial_state.state.linear_velocity.x,
                    initial_state.state.linear_velocity.y,
                ]
            ),
            initial_yaw_rate=initial_state.state.angular_velocity.z,
        )
        self._controller = controller

        self._log_file_handle = open(log_file, "w", encoding="utf-8")
        self._log_header()

        self._first_reference_pose_rig: trajectory.QVec = trajectory.QVec(
            vec3=np.array([0, 0, 0]), quat=np.array([0, 0, 0, 1])
        )
        self.control_input: np.ndarray = np.array([0.0, 0.0])
        self._solve_time_ms: float = 0.0

    def _dynamic_state_to_cg_velocity(
        self, dynamic_state: DynamicState
    ) -> np.ndarray:
        """Convert rig frame velocity to CG frame velocity."""
        return np.array(
            [
                dynamic_state.linear_velocity.x,
                dynamic_state.linear_velocity.y
                + self._vehicle_model.parameters.l_rig_to_cg
                * dynamic_state.angular_velocity.z,
            ]
        )

    def run_controller_and_vehicle_model(
        self, request: RunControllerAndVehicleModelRequest
    ) -> RunControllerAndVehicleModelResponse:
        """Run the controller and vehicle model for the given request."""
        logging.debug(
            "run_controller_and_vehicle_model: %s: %s -> %s",
            request.session_uuid,
            request.state.timestamp_us,
            request.future_time_us,
        )

        # Input sanity checks
        if request.state.timestamp_us != self._timestamp_us:
            raise ValueError(
                f"Timestamp mismatch: expected {self._timestamp_us}, "
                f"got {request.state.timestamp_us}"
            )
        if len(request.planned_trajectory_in_rig.poses) == 0:
            raise ValueError("Planned trajectory is empty")
        if request.future_time_us <= request.state.timestamp_us:
            raise ValueError(
                f"future_time_us ({request.future_time_us}) must be greater than "
                f"current timestamp ({request.state.timestamp_us})"
            )

        if request.state.timestamp_us != self._trajectory.timestamps_us[-1]:
            raise ValueError(
                f"Timestamp mismatch: expected {self._trajectory.timestamps_us[-1]}, "
                f"got {request.state.timestamp_us}"
            )
        logging.debug(
            "overriding pose at timestamp %s with %s",
            request.state.timestamp_us,
            request.state.pose,
        )
        self._trajectory.poses.vec3[-1] = trajectory.QVec.from_dds_pose(
            request.state.pose
        ).vec3
        self._trajectory.poses.quat[-1] = trajectory.QVec.from_dds_pose(
            request.state.pose
        ).quat

        self._reference_trajectory = trajectory.Trajectory.from_dds(
            request.planned_trajectory_in_rig
        )

        if request.coerce_dynamic_state:
            velocity_cg = self._dynamic_state_to_cg_velocity(request.state.state)
            self._vehicle_model.set_velocity(velocity_cg[0], velocity_cg[1])

        dt_request_us = request.future_time_us - self._timestamp_us
        dt_mpc_us = int(1e6 * self._controller.DT_MPC)
        n_steps = dt_request_us // dt_mpc_us
        if (dt_request_us % dt_mpc_us) / dt_mpc_us > 0.1:
            n_steps += 1
        n_steps = max(1, n_steps)

        for i in range(n_steps):
            if i == n_steps - 1:
                dt_us = request.future_time_us - self._timestamp_us
            else:
                dt_us = int(1e6 * self._controller.DT_MPC)
            self._step(dt_us)

        current_pose_local_to_rig = self._trajectory.last_pose.to_dds_pose_at_time(
            self._timestamp_us
        )

        dynamic_state = self._build_dynamic_state_in_rig_frame()

        return RunControllerAndVehicleModelResponse(
            pose_local_to_rig=current_pose_local_to_rig,
            pose_local_to_rig_estimated=current_pose_local_to_rig,
            dynamic_state=dynamic_state,
            dynamic_state_estimated=dynamic_state,
        )

    def _build_dynamic_state_in_rig_frame(self) -> DynamicState:
        """Build DynamicState with velocities and accelerations in rig frame."""
        l_rig_to_cg = self._vehicle_model.parameters.l_rig_to_cg
        state = self._vehicle_model.state
        accels = self._vehicle_model.accelerations

        v_cg_x = state[3]
        v_cg_y = state[4]
        yaw_rate = state[5]

        a_cg_x = accels[0]
        a_cg_y = accels[1]
        d_yaw_rate = accels[2]

        v_rig_x = v_cg_x
        v_rig_y = v_cg_y - yaw_rate * l_rig_to_cg

        a_rig_x = a_cg_x + yaw_rate * yaw_rate * l_rig_to_cg
        a_rig_y = a_cg_y - d_yaw_rate * l_rig_to_cg

        return DynamicState(
            linear_velocity=Vec3(x=v_rig_x, y=v_rig_y, z=0.0),
            angular_velocity=Vec3(x=0.0, y=0.0, z=yaw_rate),
            linear_acceleration=Vec3(x=a_rig_x, y=a_rig_y, z=0.0),
            angular_acceleration=Vec3(x=0.0, y=0.0, z=d_yaw_rate),
        )

    def _step(self, dt_us: int) -> None:
        """Execute one MPC step."""
        self._vehicle_model.reset_origin()

        ref_in_rig = self._get_reference_in_rig_frame()
        if ref_in_rig is None:
            raise ValueError("Cannot step controller: no reference trajectory set. ")

        ctrl_input = ControllerInput(
            state=self._vehicle_model.state.copy(),
            reference_trajectory=ref_in_rig,
            timestamp_us=self._timestamp_us,
        )

        ctrl_output = self._controller.compute_control(ctrl_input)
        self.control_input = ctrl_output.control

        self._solve_time_ms = ctrl_output.solve_time_ms
        if ref_in_rig is not None and len(ref_in_rig.poses) > 0:
            self._first_reference_pose_rig = ref_in_rig.poses[0]

        pose_rig_t0_to_rig_t1 = self._vehicle_model.advance(
            self.control_input, dt_us * 1e-6
        )
        self._timestamp_us += dt_us

        logging.debug(
            "pose_rig_t0_to_rig_t1: %s, %s",
            pose_rig_t0_to_rig_t1.vec3,
            pose_rig_t0_to_rig_t1.quat,
        )
        self._trajectory.update_relative(self._timestamp_us, pose_rig_t0_to_rig_t1)
        logging.debug(
            "current pose local to rig: %s, %s",
            self._trajectory.last_pose.vec3,
            self._trajectory.last_pose.quat,
        )

        self._log()

    def _get_reference_in_rig_frame(self) -> trajectory.Trajectory | None:
        """Transform reference trajectory to current rig frame."""
        if self._reference_trajectory is None:
            return None

        pose_local_to_rig_at_ref_start = self._trajectory.interpolate_pose(
            self._reference_trajectory.timestamps_us[0]
        )
        pose_local_to_rig_now = self._trajectory.last_pose
        pose_rig_now_to_rig_at_traj_time = (
            pose_local_to_rig_now.inverse() @ pose_local_to_rig_at_ref_start
        )

        transformed_poses = []
        for pose in self._reference_trajectory.poses:
            transformed_poses.append(pose_rig_now_to_rig_at_traj_time @ pose)

        return trajectory.Trajectory(
            timestamps_us=self._reference_trajectory.timestamps_us.copy(),
            poses=trajectory.QVec.stack(transformed_poses),
        )

    def _log_header(self) -> None:
        """Write CSV header."""
        self._log_file_handle.write("timestamp_us,")
        self._log_file_handle.write("x,y,z,")
        self._log_file_handle.write("qx,qy,qz,qw,")
        self._log_file_handle.write("vx,vy,wz,")
        self._log_file_handle.write("u_steering_angle,")
        self._log_file_handle.write("u_longitudinal_actuation,")
        self._log_file_handle.write("ref_traj_0_x,ref_traj_0_y,")
        self._log_file_handle.write("front_steering_angle,")
        self._log_file_handle.write("acceleration,")
        self._log_file_handle.write("x_ref_0,y_ref_0,")
        self._log_file_handle.write("yaw_ref_0\n")

    def _log(self) -> None:
        """Write CSV row."""
        self._log_file_handle.write(f"{self._timestamp_us},")
        for i in range(3):
            self._log_file_handle.write(f"{self._trajectory.last_pose.vec3[i]},")
        for i in range(4):
            self._log_file_handle.write(f"{self._trajectory.last_pose.quat[i]},")
        for i in range(3):
            self._log_file_handle.write(f"{self._vehicle_model.state[i + 3]},")
        for i in range(2):
            self._log_file_handle.write(f"{self.control_input[i]},")
        if self._reference_trajectory is not None:
            for i in range(2):
                self._log_file_handle.write(
                    f"{self._reference_trajectory.poses[0].vec3[i]},"
                )
        else:
            self._log_file_handle.write("0.0,0.0,")
        self._log_file_handle.write(f"{self._vehicle_model.front_steering_angle},")
        self._log_file_handle.write(f"{self._vehicle_model.state[7]},")
        for i in range(2):
            self._log_file_handle.write(f"{self._first_reference_pose_rig.vec3[i]},")
        self._log_file_handle.write(f"{self._first_reference_pose_rig.yaw}\n")


def create_system(
    log_file: str,
    initial_state: StateAtTime,
    mpc_implementation: MPCImplementation = MPCImplementation.LINEAR,
) -> System:
    """Create a System with the specified MPC implementation."""
    vehicle_model = VehicleModel(
        initial_velocity=np.array(
            [
                initial_state.state.linear_velocity.x,
                initial_state.state.linear_velocity.y,
            ]
        ),
        initial_yaw_rate=initial_state.state.angular_velocity.z,
    )

    if mpc_implementation == "linear":
        from alpasim_controller.mpc_impl import LinearMPC

        controller = LinearMPC(vehicle_model.parameters)
    elif mpc_implementation == "nonlinear":
        from alpasim_controller.mpc_impl import NonlinearMPC

        controller = NonlinearMPC(vehicle_model.parameters)
    else:
        raise ValueError(
            f"Unknown mpc_implementation: {mpc_implementation}. "
            "Use 'linear' or 'nonlinear'."
        )

    return System(
        log_file=log_file,
        initial_state=initial_state,
        controller=controller,
    )
