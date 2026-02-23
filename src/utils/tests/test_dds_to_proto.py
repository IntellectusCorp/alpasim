"""Unit tests for alpasim_utils.dds_to_proto conversion functions."""

import pytest
from alpasim_dds.types.common import (
    AABB,
    DynamicState,
    Pose,
    PoseAtTime,
    Quat,
    StateAtTime,
    Trajectory,
    Vec3,
)
from alpasim_dds.types.controller import (
    RunControllerAndVehicleModelRequest,
    RunControllerAndVehicleModelResponse,
)
from alpasim_dds.types.egodriver import (
    CameraImage,
    DebugInfo,
    DriveRequest,
    DriveResponse,
    DriveResponseDebugInfo,
    DriveSessionRequest,
    GroundTruth,
    GroundTruthRequest,
    RolloutCameraImage,
    RolloutEgoTrajectory,
    RolloutSpec,
    Route,
    RouteRequest,
    VehicleDefinition,
)
from alpasim_dds.types.physics import (
    EgoData,
    GroundIntersectionStatus,
    OtherObject,
    PhysicsGroundIntersectionRequest,
    PhysicsGroundIntersectionReturn,
    PosePair,
    ReturnPose,
)
from alpasim_utils.dds_to_proto import (
    aabb_to_proto,
    drive_request_to_proto,
    drive_response_to_proto,
    drive_session_request_to_proto,
    dynamic_state_to_proto,
    ground_truth_request_to_proto,
    physics_request_to_proto,
    physics_response_to_proto,
    pose_at_time_to_proto,
    pose_to_proto,
    quat_to_proto,
    rollout_camera_image_to_proto,
    rollout_ego_trajectory_to_proto,
    route_request_to_proto,
    run_controller_request_to_proto,
    run_controller_response_to_proto,
    state_at_time_to_proto,
    trajectory_to_proto,
    vec3_to_proto,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_vec3():
    return Vec3(x=1.0, y=2.0, z=3.0)


@pytest.fixture
def sample_quat():
    return Quat(w=1.0, x=0.0, y=0.0, z=0.0)


@pytest.fixture
def sample_pose(sample_vec3, sample_quat):
    return Pose(vec=sample_vec3, quat=sample_quat)


@pytest.fixture
def sample_dynamic_state():
    return DynamicState(
        angular_velocity=Vec3(x=0.1, y=0.2, z=0.3),
        linear_velocity=Vec3(x=1.0, y=2.0, z=3.0),
        linear_acceleration=Vec3(x=0.01, y=0.02, z=0.03),
        angular_acceleration=Vec3(x=0.001, y=0.002, z=0.003),
    )


@pytest.fixture
def sample_pose_at_time(sample_pose):
    return PoseAtTime(pose=sample_pose, timestamp_us=123456)


@pytest.fixture
def sample_trajectory(sample_pose):
    return Trajectory(
        poses=[
            PoseAtTime(pose=sample_pose, timestamp_us=100),
            PoseAtTime(pose=sample_pose, timestamp_us=200),
        ]
    )


# ---------------------------------------------------------------------------
# Layer 1: common types
# ---------------------------------------------------------------------------


class TestCommonTypes:
    def test_vec3(self, sample_vec3):
        proto = vec3_to_proto(sample_vec3)
        assert proto.x == pytest.approx(1.0)
        assert proto.y == pytest.approx(2.0)
        assert proto.z == pytest.approx(3.0)

    def test_quat(self, sample_quat):
        proto = quat_to_proto(sample_quat)
        assert proto.w == pytest.approx(1.0)
        assert proto.x == pytest.approx(0.0)
        assert proto.y == pytest.approx(0.0)
        assert proto.z == pytest.approx(0.0)

    def test_pose(self, sample_pose):
        proto = pose_to_proto(sample_pose)
        assert proto.vec.x == pytest.approx(1.0)
        assert proto.quat.w == pytest.approx(1.0)

    def test_dynamic_state(self, sample_dynamic_state):
        proto = dynamic_state_to_proto(sample_dynamic_state)
        assert proto.angular_velocity.x == pytest.approx(0.1)
        assert proto.linear_velocity.y == pytest.approx(2.0)
        assert proto.linear_acceleration.z == pytest.approx(0.03)
        assert proto.angular_acceleration.x == pytest.approx(0.001)

    def test_dynamic_state_partial(self):
        ds = DynamicState(linear_velocity=Vec3(x=1.0, y=0.0, z=0.0))
        proto = dynamic_state_to_proto(ds)
        assert proto.linear_velocity.x == pytest.approx(1.0)
        assert not proto.HasField("angular_velocity")

    def test_pose_at_time(self, sample_pose_at_time):
        proto = pose_at_time_to_proto(sample_pose_at_time)
        assert proto.timestamp_us == 123456
        assert proto.pose.vec.x == pytest.approx(1.0)

    def test_state_at_time(self, sample_pose, sample_dynamic_state):
        sat = StateAtTime(
            timestamp_us=999, pose=sample_pose, state=sample_dynamic_state
        )
        proto = state_at_time_to_proto(sat)
        assert proto.timestamp_us == 999
        assert proto.pose.vec.x == pytest.approx(1.0)
        assert proto.state.linear_velocity.x == pytest.approx(1.0)

    def test_trajectory(self, sample_trajectory):
        proto = trajectory_to_proto(sample_trajectory)
        assert len(proto.poses) == 2
        assert proto.poses[0].timestamp_us == 100
        assert proto.poses[1].timestamp_us == 200

    def test_trajectory_empty(self):
        proto = trajectory_to_proto(Trajectory(poses=[]))
        assert len(proto.poses) == 0

    def test_aabb(self):
        aabb = AABB(size_x=1.5, size_y=2.5, size_z=3.5)
        proto = aabb_to_proto(aabb)
        assert proto.size_x == pytest.approx(1.5)
        assert proto.size_y == pytest.approx(2.5)
        assert proto.size_z == pytest.approx(3.5)


# ---------------------------------------------------------------------------
# Layer 2: egodriver types
# ---------------------------------------------------------------------------


class TestEgodriverTypes:
    def test_drive_request(self):
        req = DriveRequest(
            session_uuid="test-uuid",
            time_now_us=100,
            time_query_us=200,
            renderer_data=b"some_data",
        )
        proto = drive_request_to_proto(req)
        assert proto.session_uuid == "test-uuid"
        assert proto.time_now_us == 100
        assert proto.time_query_us == 200
        assert proto.renderer_data == b"some_data"

    def test_drive_response(self, sample_trajectory):
        resp = DriveResponse(
            trajectory=sample_trajectory,
            debug_info=DriveResponseDebugInfo(
                unstructured_debug_info=b"debug",
                sampled_trajectories=[sample_trajectory],
            ),
        )
        proto = drive_response_to_proto(resp)
        assert len(proto.trajectory.poses) == 2
        assert proto.debug_info.unstructured_debug_info == b"debug"
        assert len(proto.debug_info.sampled_trajectories) == 1

    def test_drive_response_no_debug(self, sample_trajectory):
        resp = DriveResponse(trajectory=sample_trajectory)
        proto = drive_response_to_proto(resp)
        assert len(proto.trajectory.poses) == 2

    def test_drive_session_request(self):
        req = DriveSessionRequest(
            session_uuid="sess-1",
            random_seed=42,
            debug_info=DebugInfo(scene_id="scene_a"),
            rollout_spec=RolloutSpec(vehicle=VehicleDefinition()),
        )
        proto = drive_session_request_to_proto(req)
        assert proto.session_uuid == "sess-1"
        assert proto.random_seed == 42
        assert proto.debug_info.scene_id == "scene_a"

    def test_rollout_camera_image(self):
        img = RolloutCameraImage(
            session_uuid="sess-1",
            camera_image=CameraImage(
                frame_start_us=100,
                frame_end_us=200,
                image_bytes=b"\x00\x01",
                logical_id="cam_front",
            ),
        )
        proto = rollout_camera_image_to_proto(img)
        assert proto.session_uuid == "sess-1"
        assert proto.camera_image.frame_start_us == 100
        assert proto.camera_image.frame_end_us == 200
        assert proto.camera_image.image_bytes == b"\x00\x01"
        assert proto.camera_image.logical_id == "cam_front"

    def test_rollout_ego_trajectory(self, sample_trajectory, sample_dynamic_state):
        ego = RolloutEgoTrajectory(
            session_uuid="sess-1",
            trajectory=sample_trajectory,
            dynamic_state=sample_dynamic_state,
        )
        proto = rollout_ego_trajectory_to_proto(ego)
        assert proto.session_uuid == "sess-1"
        assert len(proto.trajectory.poses) == 2
        assert proto.dynamic_state.linear_velocity.x == pytest.approx(1.0)

    def test_route_request(self):
        req = RouteRequest(
            session_uuid="sess-1",
            route=Route(
                timestamp_us=500,
                waypoints=[Vec3(x=1.0, y=2.0, z=0.0), Vec3(x=3.0, y=4.0, z=0.0)],
            ),
        )
        proto = route_request_to_proto(req)
        assert proto.session_uuid == "sess-1"
        assert proto.route.timestamp_us == 500
        assert len(proto.route.waypoints) == 2
        assert proto.route.waypoints[0].x == pytest.approx(1.0)

    def test_ground_truth_request(self, sample_trajectory):
        req = GroundTruthRequest(
            session_uuid="sess-1",
            ground_truth=GroundTruth(
                timestamp_us=1000, trajectory=sample_trajectory
            ),
        )
        proto = ground_truth_request_to_proto(req)
        assert proto.session_uuid == "sess-1"
        assert proto.ground_truth.timestamp_us == 1000
        assert len(proto.ground_truth.trajectory.poses) == 2


# ---------------------------------------------------------------------------
# Layer 3: controller types
# ---------------------------------------------------------------------------


class TestControllerTypes:
    def test_run_controller_request(self, sample_pose, sample_dynamic_state, sample_trajectory):
        req = RunControllerAndVehicleModelRequest(
            session_uuid="sess-1",
            state=StateAtTime(
                timestamp_us=100, pose=sample_pose, state=sample_dynamic_state
            ),
            planned_trajectory_in_rig=sample_trajectory,
            future_time_us=200,
            coerce_dynamic_state=True,
        )
        proto = run_controller_request_to_proto(req)
        assert proto.session_uuid == "sess-1"
        assert proto.future_time_us == 200
        assert proto.coerce_dynamic_state is True
        assert proto.state.timestamp_us == 100
        assert len(proto.planned_trajectory_in_rig.poses) == 2

    def test_run_controller_response(self, sample_pose_at_time, sample_dynamic_state):
        resp = RunControllerAndVehicleModelResponse(
            pose_local_to_rig=sample_pose_at_time,
            pose_local_to_rig_estimated=sample_pose_at_time,
            dynamic_state=sample_dynamic_state,
            dynamic_state_estimated=sample_dynamic_state,
        )
        proto = run_controller_response_to_proto(resp)
        assert proto.pose_local_to_rig.timestamp_us == 123456
        assert proto.pose_local_to_rig_estimated.timestamp_us == 123456
        assert proto.dynamic_state.linear_velocity.x == pytest.approx(1.0)
        assert proto.dynamic_state_estimated.linear_velocity.x == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Layer 4: physics types
# ---------------------------------------------------------------------------


class TestPhysicsTypes:
    def test_physics_request(self, sample_pose):
        req = PhysicsGroundIntersectionRequest(
            scene_id="scene_a",
            now_us=100,
            future_us=200,
            ego_data=EgoData(
                aabb=AABB(size_x=4.0, size_y=2.0, size_z=1.5),
                pose_pair=PosePair(now_pose=sample_pose, future_pose=sample_pose),
            ),
            other_objects=[
                OtherObject(
                    aabb=AABB(size_x=3.0, size_y=1.5, size_z=1.0),
                    pose_pair=PosePair(
                        now_pose=sample_pose, future_pose=sample_pose
                    ),
                ),
            ],
        )
        proto = physics_request_to_proto(req)
        assert proto.scene_id == "scene_a"
        assert proto.now_us == 100
        assert proto.future_us == 200
        assert proto.ego_data.aabb.size_x == pytest.approx(4.0)
        assert proto.ego_data.pose_pair.now_pose.vec.x == pytest.approx(1.0)
        assert len(proto.other_objects) == 1
        assert proto.other_objects[0].aabb.size_x == pytest.approx(3.0)

    def test_physics_response(self, sample_pose):
        resp = PhysicsGroundIntersectionReturn(
            ego_pose=ReturnPose(
                pose=sample_pose,
                status=GroundIntersectionStatus.SUCCESSFUL_UPDATE,
            ),
            other_poses=[
                ReturnPose(
                    pose=sample_pose,
                    status=GroundIntersectionStatus.HIGH_TRANSLATION,
                ),
            ],
        )
        proto = physics_response_to_proto(resp)
        assert proto.ego_pose.pose.vec.x == pytest.approx(1.0)
        assert len(proto.other_poses) == 1

    def test_physics_response_status_mapping(self, sample_pose):
        from alpasim_grpc.v0 import physics_pb2

        for dds_status, expected_proto in [
            (GroundIntersectionStatus.SUCCESSFUL_UPDATE, physics_pb2.PhysicsGroundIntersectionReturn.SUCCESSFUL_UPDATE),
            (GroundIntersectionStatus.INSUFFICIENT_POINTS_FITPLANE, physics_pb2.PhysicsGroundIntersectionReturn.INSUFFICIENT_POINTS_FITPLANE),
            (GroundIntersectionStatus.HIGH_TRANSLATION, physics_pb2.PhysicsGroundIntersectionReturn.HIGH_TRANSLATION),
            (GroundIntersectionStatus.HIGH_ROTATION, physics_pb2.PhysicsGroundIntersectionReturn.HIGH_ROTATION),
        ]:
            resp = PhysicsGroundIntersectionReturn(
                ego_pose=ReturnPose(pose=sample_pose, status=dds_status),
            )
            proto = physics_response_to_proto(resp)
            assert proto.ego_pose.status == expected_proto
