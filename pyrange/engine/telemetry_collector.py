from __future__ import annotations

from pydantic import JsonValue

from pyrange.engine.docker import (
    ContainerRuntimeState,
    ContainerStatsSnapshot,
    NetworkRuntimeState,
    get_container_stats,
    inspect_container_runtime,
    inspect_network_runtime,
)
from pyrange.engine.manager import (
    get_lab_container_name,
    get_lab_network_name,
)
from pyrange.engine.telemetry import (
    TelemetryRecord,
    TelemetryRecorder,
    TelemetryResource,
)
from pyrange.models import ScenarioConfig


class TelemetryCollectionError(RuntimeError):
    """Raised when telemetry collection cannot be started."""


def _validate_recorder(
    scenario: ScenarioConfig,
    recorder: TelemetryRecorder,
) -> None:
    if recorder.context.scenario != scenario.name:
        raise TelemetryCollectionError(
            "Telemetry recorder scenario does not match "
            f"lab scenario '{scenario.name}'."
        )


def _network_runtime_data(
    runtime_name: str,
    runtime: NetworkRuntimeState | None,
) -> dict[str, JsonValue]:
    if runtime is None:
        return {
            "runtime_name": runtime_name,
            "present": False,
            "subnets": [],
        }

    return {
        "runtime_name": runtime_name,
        "present": True,
        "subnets": list(runtime.subnets),
    }


def _container_runtime_data(
    runtime_name: str,
    runtime: ContainerRuntimeState | None,
) -> dict[str, JsonValue]:
    if runtime is None:
        return {
            "runtime_name": runtime_name,
            "present": False,
            "status": None,
            "networks": [],
        }

    networks = [
        {
            "network_name": attachment.network_name,
            "ip_address": attachment.ip_address,
        }
        for attachment in runtime.networks
    ]

    return {
        "runtime_name": runtime_name,
        "present": True,
        "status": runtime.status,
        "networks": networks,
    }


def _stats_data(
    snapshot: ContainerStatsSnapshot,
) -> dict[str, JsonValue]:
    return {
        "runtime_name": snapshot.name,
        "cpu_percent": snapshot.cpu_percent,
        "memory_usage": snapshot.memory_usage,
        "memory_percent": snapshot.memory_percent,
        "network_io": snapshot.network_io,
        "block_io": snapshot.block_io,
        "pids": snapshot.pids,
    }


def _collect_network_telemetry(
    scenario: ScenarioConfig,
    recorder: TelemetryRecorder,
) -> list[TelemetryRecord]:
    records: list[TelemetryRecord] = []

    for network in scenario.networks:
        runtime_name = get_lab_network_name(
            scenario,
            network,
        )

        runtime = inspect_network_runtime(
            runtime_name
        )

        record = recorder.record(
            "network.runtime",
            resource=TelemetryResource(
                type="network",
                name=network.name,
            ),
            data=_network_runtime_data(
                runtime_name,
                runtime,
            ),
        )
        records.append(record)

    return records


def _collect_container_telemetry(
    scenario: ScenarioConfig,
    recorder: TelemetryRecorder,
) -> list[TelemetryRecord]:
    records: list[TelemetryRecord] = []

    for machine in scenario.machines:
        runtime_name = get_lab_container_name(
            scenario,
            machine,
        )

        runtime = inspect_container_runtime(
            runtime_name
        )

        runtime_record = recorder.record(
            "container.runtime",
            resource=TelemetryResource(
                type="machine",
                name=machine.name,
            ),
            data=_container_runtime_data(
                runtime_name,
                runtime,
            ),
        )
        records.append(runtime_record)

        if (
            runtime is None
            or runtime.status != "running"
        ):
            continue

        stats = get_container_stats(
            runtime_name
        )

        stats_record = recorder.record(
            "container.stats",
            resource=TelemetryResource(
                type="machine",
                name=machine.name,
            ),
            data=_stats_data(stats),
        )
        records.append(stats_record)

    return records


def collect_network_telemetry(
    scenario: ScenarioConfig,
    recorder: TelemetryRecorder,
) -> tuple[TelemetryRecord, ...]:
    """Collect point-in-time network telemetry for a lab."""

    _validate_recorder(
        scenario,
        recorder,
    )

    return tuple(
        _collect_network_telemetry(
            scenario,
            recorder,
        )
    )


def collect_container_telemetry(
    scenario: ScenarioConfig,
    recorder: TelemetryRecorder,
) -> tuple[TelemetryRecord, ...]:
    """Collect point-in-time container telemetry for a lab."""

    _validate_recorder(
        scenario,
        recorder,
    )

    return tuple(
        _collect_container_telemetry(
            scenario,
            recorder,
        )
    )


def collect_lab_telemetry(
    scenario: ScenarioConfig,
    recorder: TelemetryRecorder,
) -> tuple[TelemetryRecord, ...]:
    """Collect point-in-time runtime telemetry for a lab."""

    _validate_recorder(
        scenario,
        recorder,
    )

    records = _collect_network_telemetry(
        scenario,
        recorder,
    )

    records.extend(
        _collect_container_telemetry(
            scenario,
            recorder,
        )
    )

    return tuple(records)
