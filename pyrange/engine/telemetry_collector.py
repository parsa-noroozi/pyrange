from __future__ import annotations

from pydantic import JsonValue

from pyrange.engine.docker import (
    ContainerRuntimeState,
    ContainerStatsSnapshot,
    get_container_stats,
    inspect_container_runtime,
)
from pyrange.engine.manager import get_lab_container_name
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


def _runtime_data(
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


def collect_container_telemetry(
    scenario: ScenarioConfig,
    recorder: TelemetryRecorder,
) -> tuple[TelemetryRecord, ...]:
    """Collect point-in-time container telemetry for a lab."""

    _validate_recorder(
        scenario,
        recorder,
    )

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
            data=_runtime_data(
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

    return tuple(records)
