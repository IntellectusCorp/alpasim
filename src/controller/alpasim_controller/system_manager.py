# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-2026 NVIDIA Corporation

"""
SystemManager - manages multiple systems, each with vehicle dynamics and controller
"""

import logging

from alpasim_controller.mpc_controller import MPCImplementation
from alpasim_controller.system import System, create_system
from alpasim_dds.types.common import StateAtTime
from alpasim_dds.types.controller import (
    RunControllerAndVehicleModelRequest,
    RunControllerAndVehicleModelResponse,
)


class SystemManager:
    """Manages multiple vehicle dynamics and control systems."""

    def __init__(
        self, log_dir: str, mpc_implementation: MPCImplementation | None = None
    ):
        self._log_dir = log_dir
        self._sessions: dict[str, System | None] = {}
        self._mpc_implementation = mpc_implementation or MPCImplementation.LINEAR

        logging.info(f"SystemManager using {self._mpc_implementation} MPC")

    def start_session(self, session_uuid: str) -> None:
        if session_uuid in self._sessions:
            raise KeyError(f"Session {session_uuid} already exists")
        logging.info(f"Registering session: {session_uuid}")
        self._sessions[session_uuid] = None

    def close_session(self, session_uuid: str) -> None:
        if session_uuid not in self._sessions:
            raise KeyError(f"Session {session_uuid} does not exist")

        system = self._sessions[session_uuid]
        if system is not None:
            logging.info(f"Closing session: {session_uuid}")
        else:
            logging.warning(
                f"Closing session: {session_uuid} (was registered but never used)"
            )
        del self._sessions[session_uuid]

    def _create_system(
        self, session_uuid: str, state: StateAtTime
    ) -> System:
        logging.info(
            f"Creating system for session_uuid: {session_uuid} "
            f"(mpc: {self._mpc_implementation})"
        )
        system = create_system(
            log_file=f"{self._log_dir}/alpasim_controller_{session_uuid}.csv",
            initial_state=state,
            mpc_implementation=self._mpc_implementation,
        )
        self._sessions[session_uuid] = system
        return system

    def run_controller_and_vehicle_model(
        self, request: RunControllerAndVehicleModelRequest
    ) -> RunControllerAndVehicleModelResponse:
        session_uuid = request.session_uuid
        logging.debug(
            f"run_controller_and_vehicle called for session_uuid: {session_uuid}"
        )

        if session_uuid not in self._sessions:
            raise KeyError(
                f"Session {session_uuid} does not exist. "
                "Call start_session before run_controller_and_vehicle."
            )

        system = self._sessions[session_uuid]
        if system is None:
            system = self._create_system(session_uuid, request.state)

        return system.run_controller_and_vehicle_model(request)
