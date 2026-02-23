# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-2026 NVIDIA Corporation

"""
Controller DDS server: vehicle model and controller simulation.
"""

import argparse
import asyncio
import importlib.metadata
import logging
from threading import Lock

from alpasim_controller.mpc_controller import MPCImplementation
from alpasim_controller.system_manager import SystemManager
from alpasim_dds.endpoints.controller_server import ControllerServerEndpoints
from alpasim_dds.participant import get_participant
from alpasim_dds.types.common import SessionRequestStatus, VersionResponse

logger = logging.getLogger(__name__)


class VDCSimService:
    """Vehicle Dynamics and Control service (DDS)."""

    def __init__(
        self,
        endpoints: ControllerServerEndpoints,
        log_dir: str,
        mpc_implementation: str | None = None,
    ):
        logger.info(f"VDCService initialized logging to: {log_dir}")
        self.endpoints = endpoints
        self._backend = SystemManager(log_dir, mpc_implementation=mpc_implementation)
        self._lock = Lock()
        self._stop = asyncio.Event()

    def get_version(self, request) -> VersionResponse:
        controller_version = importlib.metadata.version("alpasim_controller")
        return VersionResponse(
            version_id=controller_version,
            git_hash="n/a",
        )

    def start_session(self, request) -> SessionRequestStatus:
        logger.info(f"start_session for session_uuid: {request.session_uuid}")
        with self._lock:
            self._backend.start_session(request.session_uuid)
        return SessionRequestStatus()

    def close_session(self, request) -> None:
        logger.info(f"close_session for session_uuid: {request.session_uuid}")
        with self._lock:
            self._backend.close_session(request.session_uuid)

    def run_controller_and_vehicle(self, request):
        logger.debug(
            f"run_controller_and_vehicle called for session_uuid: {request.session_uuid}"
        )
        with self._lock:
            return self._backend.run_controller_and_vehicle_model(request)

    def shut_down(self, request) -> None:
        logger.info("shut_down")
        self._stop.set()

    async def run(self):
        """모든 endpoint의 serve 루프를 동시에 실행."""
        await asyncio.gather(
            self.endpoints.session_start.serve(self.start_session, self._stop),
            self.endpoints.session_close.serve(self.close_session, self._stop),
            self.endpoints.run.serve(self.run_controller_and_vehicle, self._stop),
            self.endpoints.version.serve(self.get_version, self._stop),
            self.endpoints.shutdown.serve(self.shut_down, self._stop),
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log_dir", type=str, default=".")
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    parser.add_argument(
        "--mpc-implementation",
        type=MPCImplementation,
        choices=list(MPCImplementation),
        default=MPCImplementation.LINEAR,
        help="MPC implementation: linear (OSQP, default) or nonlinear (CasADi)",
    )
    parser.add_argument(
        "--domain-id",
        type=int,
        default=0,
        help="DDS domain ID",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s.%(msecs)03d %(levelname)s:\t%(message)s",
        datefmt="%H:%M:%S",
    )

    participant = get_participant(args.domain_id)
    endpoints = ControllerServerEndpoints(participant)

    service = VDCSimService(
        endpoints,
        args.log_dir,
        mpc_implementation=args.mpc_implementation,
    )

    logger.info("Controller DDS service starting...")
    asyncio.run(service.run())


if __name__ == "__main__":
    main()
