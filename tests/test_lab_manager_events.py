from unittest.mock import call, patch
from uuid import UUID

import pytest

from pyrange.engine import (
    DockerOperationError,
    HealthCheckResult,
)
from pyrange.engine.events import (
    EventRecord,
    EventRecorder,
    EventWriteError,
    ExecutionContext,
)
from pyrange.engine.manager import (
    LabManagerError,
    start_lab,
    stop_lab,
)
from pyrange.models import (
    HealthCheckConfig,
    MachineConfig,
    NetworkConfig,
    NetworkInterfaceConfig,
    ScenarioConfig,
)


RUN_ID = UUID(
    "44444444-4444-4444-8444-444444444444"
)


class CollectingSink:
    def __init__(self) -> None:
        self.events: list[EventRecord] = []

    def write(
        self,
        event: EventRecord,
    ) -> None:
        self.events.append(event)


class FailingEventSink:
    def __init__(
        self,
        event_type: str,
    ) -> None:
        self.event_type = event_type
        self.events: list[EventRecord] = []
        self.failed = False

    def write(
        self,
        event: EventRecord,
    ) -> None:
        if (
            event.event_type == self.event_type
            and not self.failed
        ):
            self.failed = True
            raise EventWriteError(
                f"simulated failure for "
                f"{self.event_type}"
            )

        self.events.append(event)


@pytest.fixture
def scenario() -> ScenarioConfig:
    return ScenarioConfig(
        name="segmented-lab",
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
                        network="public-net",
                        ip="172.28.10.20",
                    ),
                    NetworkInterfaceConfig(
                        network="private-net",
                        ip="172.28.20.20",
                    ),
                ],
            ),
        ],
    )


@pytest.fixture
def health_scenario() -> ScenarioConfig:
    return ScenarioConfig(
        name="health-lab",
        networks=[
            NetworkConfig(
                name="lab-net",
                subnet="172.28.30.0/24",
            )
        ],
        machines=[
            MachineConfig(
                name="web",
                image="nginx:alpine",
                interfaces=[
                    NetworkInterfaceConfig(
                        network="lab-net",
                        ip="172.28.30.10",
                    )
                ],
                health_check=HealthCheckConfig(
                    command=[
                        "wget",
                        "--spider",
                        "http://127.0.0.1",
                    ],
                    interval_seconds=1,
                    timeout_seconds=2,
                    retries=2,
                ),
            )
        ],
    )


def make_recorder(
    scenario_name: str,
    operation: str,
    sink: CollectingSink | FailingEventSink,
) -> EventRecorder:
    return EventRecorder(
        ExecutionContext(
            run_id=RUN_ID,
            scenario=scenario_name,
            operation=operation,
        ),
        sink,
    )


@patch("pyrange.engine.manager.start_container")
@patch(
    "pyrange.engine.manager."
    "connect_container_to_network"
)
@patch("pyrange.engine.manager.create_container")
@patch("pyrange.engine.manager.create_network")
def test_start_lab_emits_ordered_lifecycle_events(
    mock_create_network,
    mock_create_container,
    mock_connect_container_to_network,
    mock_start_container,
    scenario: ScenarioConfig,
) -> None:
    sink = CollectingSink()
    recorder = make_recorder(
        scenario.name,
        "start",
        sink,
    )

    start_lab(
        scenario,
        recorder=recorder,
    )

    assert [
        event.event_type
        for event in sink.events
    ] == [
        "lab.start.requested",
        "network.created",
        "network.created",
        "machine.created",
        "machine.network.attached",
        "machine.started",
        "machine.created",
        "machine.network.attached",
        "machine.network.attached",
        "machine.started",
        "lab.start.completed",
    ]

    assert [
        event.sequence
        for event in sink.events
    ] == list(
        range(1, len(sink.events) + 1)
    )

    analyst_attachments = [
        event
        for event in sink.events
        if (
            event.event_type
            == "machine.network.attached"
            and event.resource is not None
            and event.resource.name == "analyst"
        )
    ]

    assert len(analyst_attachments) == 2

    assert analyst_attachments[0].attributes == {
        "network": "public-net",
        "runtime_network": (
            "pyrange-segmented-lab-public-net"
        ),
        "ip": "172.28.10.20",
        "primary": True,
    }

    assert analyst_attachments[1].attributes == {
        "network": "private-net",
        "runtime_network": (
            "pyrange-segmented-lab-private-net"
        ),
        "ip": "172.28.20.20",
        "primary": False,
    }

    assert sink.events[-1].outcome == "success"


@patch("pyrange.engine.manager.evaluate_health_check")
@patch("pyrange.engine.manager.start_container")
@patch("pyrange.engine.manager.create_container")
@patch("pyrange.engine.manager.create_network")
def test_start_lab_emits_health_passed_without_output(
    mock_create_network,
    mock_create_container,
    mock_start_container,
    mock_evaluate_health_check,
    health_scenario: ScenarioConfig,
) -> None:
    mock_evaluate_health_check.return_value = (
        HealthCheckResult(
            healthy=True,
            attempts=1,
            exit_code=0,
            stdout="sensitive stdout",
            stderr="sensitive stderr",
        )
    )

    sink = CollectingSink()
    recorder = make_recorder(
        health_scenario.name,
        "start",
        sink,
    )

    start_lab(
        health_scenario,
        recorder=recorder,
    )

    health_event = next(
        event
        for event in sink.events
        if event.event_type == "health.passed"
    )

    assert health_event.outcome == "success"
    assert health_event.attributes == {
        "attempts": 1,
        "exit_code": 0,
    }

    assert "stdout" not in health_event.attributes
    assert "stderr" not in health_event.attributes

    assert sink.events[-1].event_type == (
        "lab.start.completed"
    )


@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
@patch("pyrange.engine.manager.evaluate_health_check")
@patch("pyrange.engine.manager.start_container")
@patch("pyrange.engine.manager.create_container")
@patch("pyrange.engine.manager.create_network")
def test_start_lab_emits_health_failure_and_rollback(
    mock_create_network,
    mock_create_container,
    mock_start_container,
    mock_evaluate_health_check,
    mock_remove_container,
    mock_remove_network,
    health_scenario: ScenarioConfig,
) -> None:
    mock_evaluate_health_check.return_value = (
        HealthCheckResult(
            healthy=False,
            attempts=3,
            exit_code=1,
            stdout="sensitive stdout",
            stderr="service unavailable",
        )
    )

    sink = CollectingSink()
    recorder = make_recorder(
        health_scenario.name,
        "start",
        sink,
    )

    with pytest.raises(
        LabManagerError,
        match="Health check failed",
    ):
        start_lab(
            health_scenario,
            recorder=recorder,
        )

    assert [
        event.event_type
        for event in sink.events
    ] == [
        "lab.start.requested",
        "network.created",
        "machine.created",
        "machine.network.attached",
        "machine.started",
        "health.failed",
        "resource.rollback.removed",
        "resource.rollback.removed",
        "lab.start.failed",
    ]

    health_event = sink.events[5]

    assert health_event.attributes == {
        "attempts": 3,
        "exit_code": 1,
    }

    assert "stdout" not in health_event.attributes
    assert "stderr" not in health_event.attributes

    assert sink.events[-1].attributes[
        "rollback_error_count"
    ] == 0


@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
@patch("pyrange.engine.manager.evaluate_health_check")
@patch("pyrange.engine.manager.start_container")
@patch("pyrange.engine.manager.create_container")
@patch("pyrange.engine.manager.create_network")
def test_health_failure_remains_primary_when_event_logging_fails(
    mock_create_network,
    mock_create_container,
    mock_start_container,
    mock_evaluate_health_check,
    mock_remove_container,
    mock_remove_network,
    health_scenario: ScenarioConfig,
) -> None:
    mock_evaluate_health_check.return_value = (
        HealthCheckResult(
            healthy=False,
            attempts=3,
            exit_code=1,
            stdout="",
            stderr="service unavailable",
        )
    )

    sink = FailingEventSink(
        "health.failed"
    )

    recorder = make_recorder(
        health_scenario.name,
        "start",
        sink,
    )

    with pytest.raises(
        LabManagerError,
        match="Health check failed",
    ) as exc_info:
        start_lab(
            health_scenario,
            recorder=recorder,
        )

    mock_remove_container.assert_called_once_with(
        "pyrange-health-lab-web"
    )

    mock_remove_network.assert_called_once_with(
        "pyrange-health-lab-lab-net"
    )

    notes = getattr(
        exc_info.value,
        "__notes__",
        [],
    )

    assert any(
        "Failed to record lifecycle event "
        "'health.failed'"
        in note
        for note in notes
    )

    assert [
        event.event_type
        for event in sink.events
    ] == [
        "lab.start.requested",
        "network.created",
        "machine.created",
        "machine.network.attached",
        "machine.started",
        "resource.rollback.removed",
        "resource.rollback.removed",
        "lab.start.failed",
    ]

    assert sink.events[-1].attributes[
        "error_type"
    ] == "LabManagerError"


@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
@patch("pyrange.engine.manager.evaluate_health_check")
@patch("pyrange.engine.manager.start_container")
@patch("pyrange.engine.manager.create_container")
@patch("pyrange.engine.manager.create_network")
def test_start_lab_records_rollback_cleanup_failure(
    mock_create_network,
    mock_create_container,
    mock_start_container,
    mock_evaluate_health_check,
    mock_remove_container,
    mock_remove_network,
    health_scenario: ScenarioConfig,
) -> None:
    mock_evaluate_health_check.return_value = (
        HealthCheckResult(
            healthy=False,
            attempts=3,
            exit_code=1,
            stdout="",
            stderr="service unavailable",
        )
    )

    mock_remove_network.side_effect = (
        DockerOperationError(
            "failed to remove network"
        )
    )

    sink = CollectingSink()
    recorder = make_recorder(
        health_scenario.name,
        "start",
        sink,
    )

    with pytest.raises(
        LabManagerError,
        match="Health check failed",
    ):
        start_lab(
            health_scenario,
            recorder=recorder,
        )

    rollback_failure = next(
        event
        for event in sink.events
        if (
            event.event_type
            == "resource.rollback.failed"
        )
    )

    assert rollback_failure.resource is not None
    assert rollback_failure.resource.type == "network"
    assert rollback_failure.resource.name == "lab-net"

    assert rollback_failure.attributes[
        "error_type"
    ] == "DockerOperationError"

    assert sink.events[-1].event_type == (
        "lab.start.failed"
    )
    assert sink.events[-1].attributes[
        "rollback_error_count"
    ] == 1


@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
@patch("pyrange.engine.manager.create_container")
@patch("pyrange.engine.manager.create_network")
def test_start_lab_rolls_back_when_event_sink_fails(
    mock_create_network,
    mock_create_container,
    mock_remove_container,
    mock_remove_network,
    scenario: ScenarioConfig,
) -> None:
    sink = FailingEventSink(
        "machine.created"
    )

    recorder = make_recorder(
        scenario.name,
        "start",
        sink,
    )

    with pytest.raises(
        EventWriteError,
        match="simulated failure",
    ):
        start_lab(
            scenario,
            recorder=recorder,
        )

    mock_remove_container.assert_called_once_with(
        "pyrange-segmented-lab-web"
    )

    assert mock_remove_network.call_args_list == [
        call("pyrange-segmented-lab-private-net"),
        call("pyrange-segmented-lab-public-net"),
    ]

    assert [
        event.event_type
        for event in sink.events
    ] == [
        "lab.start.requested",
        "network.created",
        "network.created",
        "resource.rollback.removed",
        "resource.rollback.removed",
        "resource.rollback.removed",
        "lab.start.failed",
    ]

    assert [
        event.sequence
        for event in sink.events
    ] == list(
        range(1, len(sink.events) + 1)
    )

    assert sink.events[-1].attributes[
        "error_type"
    ] == "EventWriteError"


@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
def test_stop_lab_emits_ordered_lifecycle_events(
    mock_remove_container,
    mock_remove_network,
    scenario: ScenarioConfig,
) -> None:
    sink = CollectingSink()
    recorder = make_recorder(
        scenario.name,
        "stop",
        sink,
    )

    stop_lab(
        scenario,
        recorder=recorder,
    )

    assert [
        event.event_type
        for event in sink.events
    ] == [
        "lab.stop.requested",
        "machine.removed",
        "machine.removed",
        "network.removed",
        "network.removed",
        "lab.stop.completed",
    ]

    assert sink.events[1].resource is not None
    assert sink.events[1].resource.name == "analyst"

    assert sink.events[2].resource is not None
    assert sink.events[2].resource.name == "web"

    assert sink.events[3].resource is not None
    assert sink.events[3].resource.name == (
        "private-net"
    )

    assert sink.events[4].resource is not None
    assert sink.events[4].resource.name == (
        "public-net"
    )


@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
def test_stop_lab_records_resource_failures(
    mock_remove_container,
    mock_remove_network,
    scenario: ScenarioConfig,
) -> None:
    mock_remove_container.side_effect = [
        DockerOperationError(
            "analyst removal failed"
        ),
        None,
    ]

    mock_remove_network.side_effect = [
        None,
        DockerOperationError(
            "public network removal failed"
        ),
    ]

    sink = CollectingSink()
    recorder = make_recorder(
        scenario.name,
        "stop",
        sink,
    )

    with pytest.raises(
        LabManagerError,
        match="Failed to fully stop lab",
    ):
        stop_lab(
            scenario,
            recorder=recorder,
        )

    assert mock_remove_container.call_args_list == [
        call("pyrange-segmented-lab-analyst"),
        call("pyrange-segmented-lab-web"),
    ]

    assert mock_remove_network.call_args_list == [
        call("pyrange-segmented-lab-private-net"),
        call("pyrange-segmented-lab-public-net"),
    ]

    assert [
        event.event_type
        for event in sink.events
    ] == [
        "lab.stop.requested",
        "machine.remove.failed",
        "machine.removed",
        "network.removed",
        "network.remove.failed",
        "lab.stop.failed",
    ]

    assert sink.events[-1].attributes == {
        "operational_error_count": 2,
        "event_error_count": 0,
    }


@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
def test_stop_lab_continues_cleanup_after_event_failure(
    mock_remove_container,
    mock_remove_network,
    scenario: ScenarioConfig,
) -> None:
    sink = FailingEventSink(
        "machine.removed"
    )

    recorder = make_recorder(
        scenario.name,
        "stop",
        sink,
    )

    with pytest.raises(
        EventWriteError,
        match="simulated failure",
    ):
        stop_lab(
            scenario,
            recorder=recorder,
        )

    assert mock_remove_container.call_args_list == [
        call("pyrange-segmented-lab-analyst"),
        call("pyrange-segmented-lab-web"),
    ]

    assert mock_remove_network.call_args_list == [
        call("pyrange-segmented-lab-private-net"),
        call("pyrange-segmented-lab-public-net"),
    ]

    assert [
        event.event_type
        for event in sink.events
    ] == [
        "lab.stop.requested",
        "machine.removed",
        "network.removed",
        "network.removed",
        "lab.stop.failed",
    ]

    assert sink.events[-1].attributes == {
        "operational_error_count": 0,
        "event_error_count": 1,
    }

    assert [
        event.sequence
        for event in sink.events
    ] == list(
        range(1, len(sink.events) + 1)
    )


@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
def test_stop_lab_continues_cleanup_when_requested_event_fails(
    mock_remove_container,
    mock_remove_network,
    scenario: ScenarioConfig,
) -> None:
    sink = FailingEventSink(
        "lab.stop.requested"
    )

    recorder = make_recorder(
        scenario.name,
        "stop",
        sink,
    )

    with pytest.raises(
        EventWriteError,
        match="simulated failure",
    ):
        stop_lab(
            scenario,
            recorder=recorder,
        )

    assert mock_remove_container.call_args_list == [
        call("pyrange-segmented-lab-analyst"),
        call("pyrange-segmented-lab-web"),
    ]

    assert mock_remove_network.call_args_list == [
        call("pyrange-segmented-lab-private-net"),
        call("pyrange-segmented-lab-public-net"),
    ]

    assert [
        event.event_type
        for event in sink.events
    ] == [
        "machine.removed",
        "machine.removed",
        "network.removed",
        "network.removed",
        "lab.stop.failed",
    ]

    assert sink.events[-1].attributes == {
        "operational_error_count": 0,
        "event_error_count": 1,
    }


@pytest.mark.parametrize(
    ("context_scenario", "operation"),
    [
        ("other-lab", "start"),
        ("segmented-lab", "stop"),
    ],
)
@patch("pyrange.engine.manager.create_network")
def test_start_lab_rejects_mismatched_event_context(
    mock_create_network,
    context_scenario: str,
    operation: str,
    scenario: ScenarioConfig,
) -> None:
    sink = CollectingSink()

    recorder = make_recorder(
        context_scenario,
        operation,
        sink,
    )

    with pytest.raises(
        LabManagerError,
        match="Event recorder",
    ):
        start_lab(
            scenario,
            recorder=recorder,
        )

    mock_create_network.assert_not_called()
    assert sink.events == []
