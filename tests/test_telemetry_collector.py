from unittest.mock import call, patch

import pytest

from pyrange.engine import (
    ContainerNetworkState,
    ContainerRuntimeState,
    ContainerStatsSnapshot,
    DockerOperationError,
    ExecutionContext,
    TelemetryRecord,
    TelemetryRecorder,
    TelemetryWriteError,
)
from pyrange.engine.telemetry_collector import (
    TelemetryCollectionError,
    collect_container_telemetry,
)
from pyrange.models import (
    MachineConfig,
    NetworkConfig,
    NetworkInterfaceConfig,
    ScenarioConfig,
)


class MemoryTelemetrySink:
    def __init__(self) -> None:
        self.records: list[TelemetryRecord] = []

    def write(
        self,
        record: TelemetryRecord,
    ) -> None:
        self.records.append(record)


class FailingTelemetrySink:
    def write(
        self,
        record: TelemetryRecord,
    ) -> None:
        raise TelemetryWriteError(
            "simulated telemetry write failure"
        )


@pytest.fixture
def scenario() -> ScenarioConfig:
    return ScenarioConfig(
        name="telemetry-lab",
        networks=[
            NetworkConfig(
                name="public-net",
                subnet="172.28.10.0/24",
            ),
            NetworkConfig(
                name="private-net",
                subnet="172.28.20.0/24",
            ),
        ],
        machines=[
            MachineConfig(
                name="web",
                image="nginx:alpine",
                interfaces=[
                    NetworkInterfaceConfig(
                        network="public-net",
                        ip="172.28.10.10",
                    )
                ],
            ),
            MachineConfig(
                name="analyst",
                image="alpine:latest",
                interfaces=[
                    NetworkInterfaceConfig(
                        network="private-net",
                        ip="172.28.20.20",
                    )
                ],
            ),
        ],
    )


@patch(
    "pyrange.engine.telemetry_collector."
    "get_container_stats"
)
@patch(
    "pyrange.engine.telemetry_collector."
    "inspect_container_runtime"
)
def test_collect_container_telemetry_records_running_machines(
    mock_inspect,
    mock_stats,
    scenario: ScenarioConfig,
) -> None:
    mock_inspect.side_effect = [
        ContainerRuntimeState(
            name="pyrange-telemetry-lab-web",
            status="running",
            networks=(
                ContainerNetworkState(
                    network_name=(
                        "pyrange-telemetry-lab-public-net"
                    ),
                    ip_address="172.28.10.10",
                ),
            ),
        ),
        ContainerRuntimeState(
            name="pyrange-telemetry-lab-analyst",
            status="running",
            networks=(
                ContainerNetworkState(
                    network_name=(
                        "pyrange-telemetry-lab-private-net"
                    ),
                    ip_address="172.28.20.20",
                ),
            ),
        ),
    ]

    mock_stats.side_effect = [
        ContainerStatsSnapshot(
            name="pyrange-telemetry-lab-web",
            cpu_percent="0.15%",
            memory_usage="12.3MiB / 1GiB",
            memory_percent="1.20%",
            network_io="1.2kB / 900B",
            block_io="0B / 4.1kB",
            pids=7,
        ),
        ContainerStatsSnapshot(
            name="pyrange-telemetry-lab-analyst",
            cpu_percent="0.05%",
            memory_usage="4.1MiB / 1GiB",
            memory_percent="0.40%",
            network_io="800B / 500B",
            block_io="0B / 0B",
            pids=2,
        ),
    ]

    sink = MemoryTelemetrySink()
    recorder = TelemetryRecorder(
        ExecutionContext(
            scenario="telemetry-lab",
            operation="telemetry",
        ),
        sink,
    )

    records = collect_container_telemetry(
        scenario,
        recorder,
    )

    assert records == tuple(sink.records)
    assert len(records) == 4

    assert [
        record.sequence
        for record in records
    ] == [
        1,
        2,
        3,
        4,
    ]

    assert [
        record.telemetry_type
        for record in records
    ] == [
        "container.runtime",
        "container.stats",
        "container.runtime",
        "container.stats",
    ]

    assert records[0].resource is not None
    assert records[0].resource.type == "machine"
    assert records[0].resource.name == "web"
    assert records[0].data == {
        "runtime_name": "pyrange-telemetry-lab-web",
        "present": True,
        "status": "running",
        "networks": [
            {
                "network_name": (
                    "pyrange-telemetry-lab-public-net"
                ),
                "ip_address": "172.28.10.10",
            }
        ],
    }

    assert records[1].data == {
        "runtime_name": "pyrange-telemetry-lab-web",
        "cpu_percent": "0.15%",
        "memory_usage": "12.3MiB / 1GiB",
        "memory_percent": "1.20%",
        "network_io": "1.2kB / 900B",
        "block_io": "0B / 4.1kB",
        "pids": 7,
    }

    assert mock_inspect.call_args_list == [
        call("pyrange-telemetry-lab-web"),
        call("pyrange-telemetry-lab-analyst"),
    ]

    assert mock_stats.call_args_list == [
        call("pyrange-telemetry-lab-web"),
        call("pyrange-telemetry-lab-analyst"),
    ]


@patch(
    "pyrange.engine.telemetry_collector."
    "get_container_stats"
)
@patch(
    "pyrange.engine.telemetry_collector."
    "inspect_container_runtime"
)
def test_collect_container_telemetry_records_missing_machine(
    mock_inspect,
    mock_stats,
    scenario: ScenarioConfig,
) -> None:
    scenario = scenario.model_copy(
        update={
            "machines": [
                scenario.machines[0],
            ]
        }
    )

    mock_inspect.return_value = None

    sink = MemoryTelemetrySink()
    recorder = TelemetryRecorder(
        ExecutionContext(
            scenario="telemetry-lab",
            operation="telemetry",
        ),
        sink,
    )

    records = collect_container_telemetry(
        scenario,
        recorder,
    )

    assert len(records) == 1
    assert records[0].telemetry_type == (
        "container.runtime"
    )
    assert records[0].data == {
        "runtime_name": "pyrange-telemetry-lab-web",
        "present": False,
        "status": None,
        "networks": [],
    }

    mock_stats.assert_not_called()


@patch(
    "pyrange.engine.telemetry_collector."
    "get_container_stats"
)
@patch(
    "pyrange.engine.telemetry_collector."
    "inspect_container_runtime"
)
def test_collect_container_telemetry_skips_stats_when_not_running(
    mock_inspect,
    mock_stats,
    scenario: ScenarioConfig,
) -> None:
    scenario = scenario.model_copy(
        update={
            "machines": [
                scenario.machines[0],
            ]
        }
    )

    mock_inspect.return_value = ContainerRuntimeState(
        name="pyrange-telemetry-lab-web",
        status="exited",
        networks=(
            ContainerNetworkState(
                network_name=(
                    "pyrange-telemetry-lab-public-net"
                ),
                ip_address="172.28.10.10",
            ),
        ),
    )

    sink = MemoryTelemetrySink()
    recorder = TelemetryRecorder(
        ExecutionContext(
            scenario="telemetry-lab",
            operation="telemetry",
        ),
        sink,
    )

    records = collect_container_telemetry(
        scenario,
        recorder,
    )

    assert len(records) == 1
    assert records[0].data["present"] is True
    assert records[0].data["status"] == "exited"

    mock_stats.assert_not_called()


@patch(
    "pyrange.engine.telemetry_collector."
    "inspect_container_runtime"
)
def test_collect_container_telemetry_rejects_mismatched_scenario(
    mock_inspect,
    scenario: ScenarioConfig,
) -> None:
    recorder = TelemetryRecorder(
        ExecutionContext(
            scenario="other-lab",
            operation="telemetry",
        ),
        MemoryTelemetrySink(),
    )

    with pytest.raises(
        TelemetryCollectionError,
        match="scenario does not match",
    ):
        collect_container_telemetry(
            scenario,
            recorder,
        )

    mock_inspect.assert_not_called()


@patch(
    "pyrange.engine.telemetry_collector."
    "get_container_stats"
)
@patch(
    "pyrange.engine.telemetry_collector."
    "inspect_container_runtime"
)
def test_collect_container_telemetry_preserves_runtime_record_on_stats_failure(
    mock_inspect,
    mock_stats,
    scenario: ScenarioConfig,
) -> None:
    scenario = scenario.model_copy(
        update={
            "machines": [
                scenario.machines[0],
            ]
        }
    )

    mock_inspect.return_value = ContainerRuntimeState(
        name="pyrange-telemetry-lab-web",
        status="running",
        networks=(),
    )
    mock_stats.side_effect = DockerOperationError(
        "stats collection failed"
    )

    sink = MemoryTelemetrySink()
    recorder = TelemetryRecorder(
        ExecutionContext(
            scenario="telemetry-lab",
            operation="telemetry",
        ),
        sink,
    )

    with pytest.raises(
        DockerOperationError,
        match="stats collection failed",
    ):
        collect_container_telemetry(
            scenario,
            recorder,
        )

    assert len(sink.records) == 1
    assert sink.records[0].telemetry_type == (
        "container.runtime"
    )


@patch(
    "pyrange.engine.telemetry_collector."
    "get_container_stats"
)
@patch(
    "pyrange.engine.telemetry_collector."
    "inspect_container_runtime"
)
def test_collect_container_telemetry_stops_after_sink_failure(
    mock_inspect,
    mock_stats,
    scenario: ScenarioConfig,
) -> None:
    scenario = scenario.model_copy(
        update={
            "machines": [
                scenario.machines[0],
            ]
        }
    )

    mock_inspect.return_value = ContainerRuntimeState(
        name="pyrange-telemetry-lab-web",
        status="running",
        networks=(),
    )

    recorder = TelemetryRecorder(
        ExecutionContext(
            scenario="telemetry-lab",
            operation="telemetry",
        ),
        FailingTelemetrySink(),
    )

    with pytest.raises(
        TelemetryWriteError,
        match="simulated telemetry write failure",
    ):
        collect_container_telemetry(
            scenario,
            recorder,
        )

    mock_stats.assert_not_called()


@patch(
    "pyrange.engine.telemetry_collector."
    "get_container_stats"
)
@patch(
    "pyrange.engine.telemetry_collector."
    "inspect_container_runtime"
)
def test_collect_container_telemetry_allows_shared_execution_operation(
    mock_inspect,
    mock_stats,
    scenario: ScenarioConfig,
) -> None:
    scenario = scenario.model_copy(
        update={
            "machines": [
                scenario.machines[0],
            ]
        }
    )

    mock_inspect.return_value = None

    sink = MemoryTelemetrySink()
    recorder = TelemetryRecorder(
        ExecutionContext(
            scenario="telemetry-lab",
            operation="start",
        ),
        sink,
    )

    records = collect_container_telemetry(
        scenario,
        recorder,
    )

    assert len(records) == 1
    assert records[0].operation == "start"
    assert records[0].run_id == recorder.context.run_id

    mock_stats.assert_not_called()