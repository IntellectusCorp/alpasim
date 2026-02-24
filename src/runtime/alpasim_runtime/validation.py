# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-2026 NVIDIA Corporation

"""Pre-flight validation for simulation runs."""

import asyncio
import logging
import os

import alpasim_runtime
from alpasim_grpc.v0.common_pb2 import Empty
from alpasim_runtime.config import (
    NetworkSimulatorConfig,
    ScenarioConfig,
    SimulatorConfig,
)
from alpasim_runtime.endpoints import get_service_endpoints

import grpc

logger = logging.getLogger(__name__)

# Services that have been migrated to DDS (no gRPC server)
DDS_SERVICES = {"driver", "controller", "physics"}


async def _probe_version_grpc(
    svc_name: str,
    stub_class: type,
    address: str,
    timeout_s: int,
) -> None:
    """Probe a single gRPC service for version info."""
    logger.info("Connecting to %s at %s...", svc_name, address)
    channel = grpc.aio.insecure_channel(address)
    try:
        stub = stub_class(channel)
        if svc_name == "trafficsim":
            # trafficsim returns version via get_metadata instead of get_version
            metadata = await stub.get_metadata(
                Empty(), wait_for_ready=True, timeout=timeout_s
            )
            version = metadata.version_id
        else:
            version = await stub.get_version(
                Empty(), wait_for_ready=True, timeout=timeout_s
            )
        logger.info("Connected to %s: %s", svc_name, version)
    finally:
        await channel.close()


async def _probe_version_dds(
    svc_name: str,
    timeout_s: int,
) -> None:
    """Probe a single DDS service for version info."""
    from alpasim_dds.participant import get_participant
    from alpasim_dds.transport import DDSTransport
    from alpasim_dds.types.common import VersionRequest, VersionResponse

    logger.info("Connecting to %s via DDS...", svc_name)
    participant = get_participant()
    transport = DDSTransport(
        participant, f"{svc_name}/version",
        VersionRequest, VersionResponse,
    )
    version = await transport.request(VersionRequest())
    logger.info("Connected to %s: %s (git: %s)", svc_name, version.version_id, version.git_hash)


async def gather_versions_from_addresses(
    network_config: NetworkSimulatorConfig,
    timeout_s: int = 30,
) -> None:
    """Probe each endpoint for version info before spawning workers."""
    runtime_version = alpasim_runtime.VERSION_MESSAGE
    logger.info("runtime: %s", runtime_version)

    endpoint_stubs = get_service_endpoints(network_config)

    tasks = []
    for svc_name, (stub_class, addresses) in endpoint_stubs.items():
        if not addresses:
            continue
        if svc_name in DDS_SERVICES:
            tasks.append(_probe_version_dds(svc_name, timeout_s))
        else:
            tasks.append(_probe_version_grpc(svc_name, stub_class, addresses[0], timeout_s))

    await asyncio.gather(*tasks)


async def validate_scenarios(config: SimulatorConfig) -> None:
    """
    Validate all scenarios before building job list.

    Uses lightweight probes to check scene availability without creating full pools.
    This ensures we fail fast in the parent if any scenario is invalid.
    """
    # driver and controller return wildcard (work with any scene), no need to probe
    grpc_services = ["sensorsim", "trafficsim"]
    dds_services = ["physics"]

    # gRPC service probes
    service_endpoints = get_service_endpoints(
        config.network, services=grpc_services
    )

    tasks = []
    for svc_name, (stub_class, addresses) in service_endpoints.items():
        if not addresses:
            continue
        tasks.append(
            _probe_scenario_compatibility_grpc(
                svc_name,
                stub_class,
                addresses[0],
                config.user.scenarios,
                timeout_s=config.user.endpoints.startup_timeout_s,
                use_metadata=(svc_name == "trafficsim"),
            )
        )

    # DDS service probes
    for svc_name in dds_services:
        tasks.append(
            _probe_scenario_compatibility_dds(
                svc_name,
                config.user.scenarios,
                timeout_s=config.user.endpoints.startup_timeout_s,
            )
        )

    results = await asyncio.gather(*tasks)
    error_messages = [msg for errors in results for msg in errors]

    if error_messages:
        raise AssertionError("\n".join(error_messages))


async def _probe_scenario_compatibility_grpc(
    svc_name: str,
    stub_class: type,
    address: str,
    scenarios: list[ScenarioConfig],
    timeout_s: int = 30,
    use_metadata: bool = False,
) -> list[str]:
    """Probe a gRPC service to validate scenario compatibility."""
    incompatibilities = []

    logger.info("Validating scenarios on %s at %s...", svc_name, address)
    channel = grpc.aio.insecure_channel(address)
    try:
        stub = stub_class(channel)
        if use_metadata:
            # trafficsim uses get_metadata with supported_map_ids
            response = await stub.get_metadata(
                Empty(), wait_for_ready=True, timeout=timeout_s
            )
            # trafficsim returns map_ids without the clipgt- prefix, so we add it
            available_scenes = set(
                f"clipgt-{map_id}" for map_id in response.supported_map_ids
            )
        else:
            response = await stub.get_available_scenes(
                Empty(), wait_for_ready=True, timeout=timeout_s
            )
            available_scenes = set(response.scene_ids)

        for scenario in scenarios:
            if (
                scenario.scene_id not in available_scenes
                and "*" not in available_scenes
            ):
                incompatibilities.append(
                    f"Scene {scenario.scene_id} not available at {address}. "
                    f"Available: {sorted(available_scenes)}"
                )

        if incompatibilities:
            logger.error(
                "Scenario validation failed on %s: %d issue(s)",
                svc_name,
                len(incompatibilities),
            )
        else:
            logger.info("Scenario validation passed on %s", svc_name)
    finally:
        await channel.close()

    return incompatibilities


async def _probe_scenario_compatibility_dds(
    svc_name: str,
    scenarios: list[ScenarioConfig],
    timeout_s: int = 30,
) -> list[str]:
    """Probe a DDS service to validate scenario compatibility."""
    from alpasim_dds.participant import get_participant
    from alpasim_dds.transport import DDSTransport
    from alpasim_dds.types.common import AvailableScenesRequest, AvailableScenesResponse

    incompatibilities = []

    logger.info("Validating scenarios on %s via DDS...", svc_name)
    participant = get_participant()
    transport = DDSTransport(
        participant, f"{svc_name}/available_scenes",
        AvailableScenesRequest, AvailableScenesResponse,
    )
    response = await transport.request(AvailableScenesRequest())
    available_scenes = set(response.scene_ids or [])

    for scenario in scenarios:
        if (
            scenario.scene_id not in available_scenes
            and "*" not in available_scenes
        ):
            incompatibilities.append(
                f"Scene {scenario.scene_id} not available on {svc_name} (DDS). "
                f"Available: {sorted(available_scenes)}"
            )

    if incompatibilities:
        logger.error(
            "Scenario validation failed on %s: %d issue(s)",
            svc_name,
            len(incompatibilities),
        )
    else:
        logger.info("Scenario validation passed on %s", svc_name)

    return incompatibilities


def validate_array_job_config(array_job_dir: str | None) -> None:
    """Validate array_job_dir is provided when running as SLURM array job.

    Args:
        array_job_dir: The --array-job-dir argument value (or None if not provided).

    Raises:
        ValueError: If running as SLURM array job without explicit array_job_dir.
    """
    slurm_array_count = int(os.environ.get("SLURM_ARRAY_TASK_COUNT", "0"))
    if slurm_array_count > 0 and array_job_dir is None:
        raise ValueError("Running as SLURM array job but --array-job-dir not provided.")
