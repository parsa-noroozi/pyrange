from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import call, patch
from uuid import UUID

import pytest

from pyrange.engine import (
    DockerOperationError,
    HealthCheckResult,
)
from pyrange.engine.docker import (
    DockerResourceIdentity,
    DockerUnavailableError,
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
from pyrange.engine.ownership import build_ownership_labels
from pyrange.models import (
    HealthCheckConfig,
    MachineConfig,
    NetworkConfig,
    NetworkInterfaceConfig,
    ScenarioConfig,
)


pytestmark = pytest.mark.usefixtures("no_legacy_resources")


PUBLIC_NETWORK_NAME = (
    "pyrange-v2-network-"
    "e766ac61206c7ae3d71571ae1872401af69f7d756d5e2d1c52b6e99a8d7dda8d"
)

PRIVATE_NETWORK_NAME = (
    "pyrange-v2-network-"
    "9b692d460dc781424b243d45281ac928e348d8f82fc6266ed6bf44477bec2027"
)

WEB_CONTAINER_NAME = (
    "pyrange-v2-container-"
    "12ac3acb9b451ad60efb6ba7e0fda1ce7ddf48c60ec26104388a769622d55d8c"
)

ANALYST_CONTAINER_NAME = (
    "pyrange-v2-container-"
    "9570b0024cb6a01a4921131433a5dc16830e6ea15fe4ba55b1c94c3298d37427"
)

HEALTH_CONTAINER_NAME = (
    "pyrange-v2-container-"
    "9b77efaddb94ee8f01b27814bdc79bf6af6aaeec5d88162ba7729f4edb1700d8"
)

HEALTH_NETWORK_NAME = (
    "pyrange-v2-network-"
    "6e20c278f595f82abc7c7a38897d446ba443a096f542855b7861f9c1bda89fb4"
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




WEB_CONTAINER_ID = "a" * 64
ANALYST_CONTAINER_ID = "b" * 64
PUBLIC_NETWORK_ID = "c" * 64
PRIVATE_NETWORK_ID = "d" * 64


@pytest.fixture
def owned_stop_resources():
    containers = {
        runtime_name: DockerResourceIdentity(
            resource_id=resource_id,
            labels=build_ownership_labels(
                kind="container",
                scenario_name="segmented-lab",
                resource_name=logical_name,
            ),
        )
        for runtime_name, resource_id, logical_name in [
            (WEB_CONTAINER_NAME, WEB_CONTAINER_ID, "web"),
            (ANALYST_CONTAINER_NAME, ANALYST_CONTAINER_ID, "analyst"),
        ]
    }
    networks = {
        runtime_name: DockerResourceIdentity(
            resource_id=resource_id,
            labels=build_ownership_labels(
                kind="network",
                scenario_name="segmented-lab",
                resource_name=logical_name,
            ),
        )
        for runtime_name, resource_id, logical_name in [
            (PUBLIC_NETWORK_NAME, PUBLIC_NETWORK_ID, "public-net"),
            (PRIVATE_NETWORK_NAME, PRIVATE_NETWORK_ID, "private-net"),
        ]
    }
    with (
        patch(
            "pyrange.engine.manager.find_container_identity",
            side_effect=containers.__getitem__,
        ) as find_container,
        patch(
            "pyrange.engine.manager.find_network_identity",
            side_effect=networks.__getitem__,
        ) as find_network,
        patch(
            "pyrange.engine.docker.subprocess.run",
            side_effect=AssertionError(
                "This unit test must not execute Docker."
            ),
        ),
    ):
        yield SimpleNamespace(
            containers=containers,
            networks=networks,
            find_container=find_container,
            find_network=find_network,
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
    rollback_resources,
) -> None:
    rollback_resources.configure(mock_create_network, mock_create_container, scenario)
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
            PUBLIC_NETWORK_NAME
        ),
        "ip": "172.28.10.20",
        "primary": True,
    }

    assert analyst_attachments[1].attributes == {
        "network": "private-net",
        "runtime_network": (
            PRIVATE_NETWORK_NAME
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
    rollback_resources,
) -> None:
    rollback_resources.configure(mock_create_network, mock_create_container, health_scenario)
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
    rollback_resources,
) -> None:
    rollback_resources.configure(mock_create_network, mock_create_container, health_scenario)
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
    rollback_resources,
) -> None:
    rollback_resources.configure(mock_create_network, mock_create_container, health_scenario)
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
        rollback_resources.ids[HEALTH_CONTAINER_NAME]
    )

    mock_remove_network.assert_called_once_with(
        rollback_resources.ids[HEALTH_NETWORK_NAME]
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
    rollback_resources,
) -> None:
    rollback_resources.configure(mock_create_network, mock_create_container, health_scenario)
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
    rollback_resources,
) -> None:
    rollback_resources.configure(mock_create_network, mock_create_container, scenario)
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
        rollback_resources.ids[WEB_CONTAINER_NAME]
    )

    assert mock_remove_network.call_args_list == [
        call(rollback_resources.ids[PRIVATE_NETWORK_NAME]),
        call(rollback_resources.ids[PUBLIC_NETWORK_NAME]),
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


@pytest.mark.usefixtures("owned_stop_resources")
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


@pytest.mark.usefixtures("owned_stop_resources")
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
        call(ANALYST_CONTAINER_ID),
        call(WEB_CONTAINER_ID),
    ]

    assert mock_remove_network.call_args_list == [
        call(PRIVATE_NETWORK_ID),
        call(PUBLIC_NETWORK_ID),
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


@pytest.mark.usefixtures("owned_stop_resources")
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
        call(ANALYST_CONTAINER_ID),
        call(WEB_CONTAINER_ID),
    ]

    assert mock_remove_network.call_args_list == [
        call(PRIVATE_NETWORK_ID),
        call(PUBLIC_NETWORK_ID),
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


@pytest.mark.usefixtures("owned_stop_resources")
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
        call(ANALYST_CONTAINER_ID),
        call(WEB_CONTAINER_ID),
    ]

    assert mock_remove_network.call_args_list == [
        call(PRIVATE_NETWORK_ID),
        call(PUBLIC_NETWORK_ID),
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


@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
def test_stop_reports_absence_without_removed_events(
    mock_remove_container,
    mock_remove_network,
    scenario,
    owned_stop_resources,
) -> None:
    owned_stop_resources.find_container.side_effect = None
    owned_stop_resources.find_container.return_value = None
    owned_stop_resources.find_network.side_effect = None
    owned_stop_resources.find_network.return_value = None
    sink = CollectingSink()

    stop_lab(scenario, recorder=make_recorder(scenario.name, "stop", sink))

    mock_remove_container.assert_not_called()
    mock_remove_network.assert_not_called()
    assert [event.event_type for event in sink.events] == [
        "lab.stop.requested",
        "machine.absent",
        "machine.absent",
        "network.absent",
        "network.absent",
        "lab.stop.completed",
    ]
    expected_resources = [
        ("machine", "analyst", ANALYST_CONTAINER_NAME),
        ("machine", "web", WEB_CONTAINER_NAME),
        ("network", "private-net", PRIVATE_NETWORK_NAME),
        ("network", "public-net", PUBLIC_NETWORK_NAME),
    ]
    for event, (kind, name, runtime_name) in zip(
        sink.events[1:5], expected_resources, strict=True
    ):
        assert event.resource is not None
        assert (event.resource.type, event.resource.name) == (kind, name)
        assert event.attributes == {"runtime_name": runtime_name}
        assert event.outcome is None
    assert [event.sequence for event in sink.events] == list(range(1, 7))


def assert_partial_stop_result(
    sink, mock_remove_container, mock_remove_network, kind, error_type
) -> None:
    """The rejected resource stays intact; other resources are still visited."""
    if kind == "container":
        container_calls = [call(WEB_CONTAINER_ID)]
        network_calls = [call(PRIVATE_NETWORK_ID), call(PUBLIC_NETWORK_ID)]
        failed_index = 1
        resource_type, resource_name = "machine", "analyst"
        runtime_name = ANALYST_CONTAINER_NAME
        resource_events = [
            "machine.remove.failed", "machine.removed",
            "network.removed", "network.removed",
        ]
    else:
        container_calls = [call(ANALYST_CONTAINER_ID), call(WEB_CONTAINER_ID)]
        network_calls = [call(PUBLIC_NETWORK_ID)]
        failed_index = 3
        resource_type, resource_name = "network", "private-net"
        runtime_name = PRIVATE_NETWORK_NAME
        resource_events = [
            "machine.removed", "machine.removed",
            "network.remove.failed", "network.removed",
        ]

    assert mock_remove_container.call_args_list == container_calls
    assert mock_remove_network.call_args_list == network_calls
    assert [event.event_type for event in sink.events] == [
        "lab.stop.requested", *resource_events, "lab.stop.failed",
    ]
    failed = sink.events[failed_index]
    assert failed.outcome == "failure"
    assert failed.resource is not None
    assert (failed.resource.type, failed.resource.name) == (
        resource_type, resource_name,
    )
    assert failed.attributes == {
        "runtime_name": runtime_name,
        "error_type": error_type,
    }
    assert sink.events[-1].attributes == {
        "operational_error_count": 1,
        "event_error_count": 0,
    }
    assert [event.sequence for event in sink.events] == list(range(1, 7))


@pytest.mark.parametrize("kind", ["container", "network"])
@pytest.mark.parametrize(
    "problem",
    [
        "missing", "empty",
        "pyrange.managed",
        "pyrange.ownership.version",
        "pyrange.resource.kind",
        "pyrange.scenario.name",
        "pyrange.resource.name",
        "pyrange.resource.identity",
    ],
)
@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
def test_stop_records_ownership_rejection_and_continues(
    mock_remove_container,
    mock_remove_network,
    scenario,
    owned_stop_resources,
    kind,
    problem,
) -> None:
    resources = (
        owned_stop_resources.containers if kind == "container"
        else owned_stop_resources.networks
    )
    name = ANALYST_CONTAINER_NAME if kind == "container" else PRIVATE_NETWORK_NAME
    identity = resources[name]
    if problem == "missing":
        labels = None
    elif problem == "empty":
        labels = {}
    else:
        labels = dict(identity.labels)
        labels[problem] = "incorrect"
    resources[name] = replace(identity, labels=labels)
    sink = CollectingSink()

    with pytest.raises(LabManagerError, match="Failed to fully stop lab"):
        stop_lab(scenario, recorder=make_recorder(scenario.name, "stop", sink))

    assert_partial_stop_result(
        sink, mock_remove_container, mock_remove_network,
        kind, "ResourceOwnershipError",
    )


@pytest.mark.parametrize("kind", ["container", "network"])
@pytest.mark.parametrize("error_type", [DockerOperationError, DockerUnavailableError])
@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
def test_stop_records_lookup_failure_and_continues(
    mock_remove_container,
    mock_remove_network,
    scenario,
    owned_stop_resources,
    kind,
    error_type,
) -> None:
    if kind == "container":
        owned_stop_resources.find_container.side_effect = [
            error_type("lookup unavailable"),
            owned_stop_resources.containers[WEB_CONTAINER_NAME],
        ]
    else:
        owned_stop_resources.find_network.side_effect = [
            error_type("lookup unavailable"),
            owned_stop_resources.networks[PUBLIC_NETWORK_NAME],
        ]
    sink = CollectingSink()

    with pytest.raises(LabManagerError, match="lookup unavailable"):
        stop_lab(scenario, recorder=make_recorder(scenario.name, "stop", sink))

    assert_partial_stop_result(
        sink, mock_remove_container, mock_remove_network, kind, error_type.__name__,
    )


@pytest.mark.parametrize("kind", ["container", "network"])
@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
def test_stop_preserves_ownership_error_when_failure_event_cannot_be_written(
    mock_remove_container,
    mock_remove_network,
    scenario,
    owned_stop_resources,
    kind,
) -> None:
    if kind == "container":
        resources = owned_stop_resources.containers
        name = ANALYST_CONTAINER_NAME
        failed_event = "machine.remove.failed"
        expected_container_calls = [call(WEB_CONTAINER_ID)]
        expected_network_calls = [call(PRIVATE_NETWORK_ID), call(PUBLIC_NETWORK_ID)]
    else:
        resources = owned_stop_resources.networks
        name = PRIVATE_NETWORK_NAME
        failed_event = "network.remove.failed"
        expected_container_calls = [call(ANALYST_CONTAINER_ID), call(WEB_CONTAINER_ID)]
        expected_network_calls = [call(PUBLIC_NETWORK_ID)]
    resources[name] = replace(resources[name], labels=None)
    sink = FailingEventSink(failed_event)

    with pytest.raises(LabManagerError, match="ownership") as caught:
        stop_lab(scenario, recorder=make_recorder(scenario.name, "stop", sink))

    assert mock_remove_container.call_args_list == expected_container_calls
    assert mock_remove_network.call_args_list == expected_network_calls
    assert any("Event logging also failed" in note for note in caught.value.__notes__)
    assert sink.events[-1].event_type == "lab.stop.failed"
    assert sink.events[-1].attributes == {
        "operational_error_count": 1,
        "event_error_count": 1,
    }
    assert [event.sequence for event in sink.events] == list(range(1, 6))


@pytest.mark.parametrize("event_type", ["machine.absent", "network.absent"])
@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
def test_stop_reports_logging_failure_for_absent_resource(
    mock_remove_container,
    mock_remove_network,
    scenario,
    owned_stop_resources,
    event_type,
) -> None:
    owned_stop_resources.find_container.side_effect = None
    owned_stop_resources.find_container.return_value = None
    owned_stop_resources.find_network.side_effect = None
    owned_stop_resources.find_network.return_value = None
    sink = FailingEventSink(event_type)

    with pytest.raises(EventWriteError, match="simulated failure"):
        stop_lab(scenario, recorder=make_recorder(scenario.name, "stop", sink))

    mock_remove_container.assert_not_called()
    mock_remove_network.assert_not_called()
    assert owned_stop_resources.find_container.call_count == 2
    assert owned_stop_resources.find_network.call_count == 2
    assert sink.events[-1].event_type == "lab.stop.failed"
    assert sink.events[-1].attributes == {
        "operational_error_count": 0,
        "event_error_count": 1,
    }
    assert [event.sequence for event in sink.events] == list(range(1, 6))


@pytest.mark.parametrize("kind", ["container", "network"])
@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
def test_stop_handles_mixed_absent_and_existing_resources(
    mock_remove_container,
    mock_remove_network,
    scenario,
    owned_stop_resources,
    kind,
) -> None:
    if kind == "container":
        owned_stop_resources.containers[ANALYST_CONTAINER_NAME] = None
        expected_container_calls = [call(WEB_CONTAINER_ID)]
        expected_network_calls = [call(PRIVATE_NETWORK_ID), call(PUBLIC_NETWORK_ID)]
        expected_events = [
            "machine.absent", "machine.removed",
            "network.removed", "network.removed",
        ]
    else:
        owned_stop_resources.networks[PRIVATE_NETWORK_NAME] = None
        expected_container_calls = [call(ANALYST_CONTAINER_ID), call(WEB_CONTAINER_ID)]
        expected_network_calls = [call(PUBLIC_NETWORK_ID)]
        expected_events = [
            "machine.removed", "machine.removed",
            "network.absent", "network.removed",
        ]
    sink = CollectingSink()

    stop_lab(scenario, recorder=make_recorder(scenario.name, "stop", sink))

    assert mock_remove_container.call_args_list == expected_container_calls
    assert mock_remove_network.call_args_list == expected_network_calls
    assert [event.event_type for event in sink.events] == [
        "lab.stop.requested", *expected_events, "lab.stop.completed",
    ]
    assert [event.sequence for event in sink.events] == list(range(1, 7))
