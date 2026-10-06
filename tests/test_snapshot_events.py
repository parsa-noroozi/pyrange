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
from pyrange.engine.snapshot import (
    SnapshotError,
    create_machine_snapshot,
    restore_machine_snapshot,
)
from pyrange.models import (
    HealthCheckConfig,
    MachineConfig,
    NetworkConfig,
    NetworkInterfaceConfig,
    ScenarioConfig,
)


RUN_ID = UUID(
    "55555555-5555-4555-8555-555555555555"
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
        name="snapshot-lab",
        networks=[
            NetworkConfig(
                name="public-net",
                subnet="172.28.40.0/24",
            ),
            NetworkConfig(
                name="private-net",
                subnet="172.28.50.0/24",
            ),
        ],
        machines=[
            MachineConfig(
                name="web",
                image="nginx:alpine",
                interfaces=[
                    NetworkInterfaceConfig(
                        network="public-net",
                        ip="172.28.40.10",
                    ),
                    NetworkInterfaceConfig(
                        network="private-net",
                        ip="172.28.50.10",
                    ),
                ],
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


@patch(
    "pyrange.engine.snapshot."
    "create_container_snapshot"
)
def test_snapshot_emits_requested_and_created_events(
    mock_create_container_snapshot,
    scenario: ScenarioConfig,
) -> None:
    mock_create_container_snapshot.return_value = (
        "sha256:snapshot123"
    )

    sink = CollectingSink()
    recorder = make_recorder(
        scenario.name,
        "snapshot",
        sink,
    )

    create_machine_snapshot(
        scenario,
        machine_name="web",
        snapshot_name="checkpoint-1",
        recorder=recorder,
    )

    assert [
        event.event_type
        for event in sink.events
    ] == [
        "snapshot.requested",
        "snapshot.created",
    ]

    assert sink.events[1].outcome == "success"
    assert sink.events[1].attributes[
        "image_id"
    ] == "sha256:snapshot123"


@patch(
    "pyrange.engine.snapshot."
    "create_container_snapshot"
)
def test_snapshot_records_operational_failure(
    mock_create_container_snapshot,
    scenario: ScenarioConfig,
) -> None:
    mock_create_container_snapshot.side_effect = (
        DockerOperationError(
            "snapshot failed"
        )
    )

    sink = CollectingSink()
    recorder = make_recorder(
        scenario.name,
        "snapshot",
        sink,
    )

    with pytest.raises(
        DockerOperationError,
        match="snapshot failed",
    ):
        create_machine_snapshot(
            scenario,
            machine_name="web",
            snapshot_name="checkpoint-1",
            recorder=recorder,
        )

    assert [
        event.event_type
        for event in sink.events
    ] == [
        "snapshot.requested",
        "snapshot.failed",
    ]

    assert sink.events[-1].attributes[
        "snapshot_created"
    ] is False


@patch(
    "pyrange.engine.snapshot."
    "create_container_snapshot"
)
def test_snapshot_reports_event_failure_after_image_creation(
    mock_create_container_snapshot,
    scenario: ScenarioConfig,
) -> None:
    mock_create_container_snapshot.return_value = (
        "sha256:snapshot123"
    )

    sink = FailingEventSink(
        "snapshot.created"
    )

    recorder = make_recorder(
        scenario.name,
        "snapshot",
        sink,
    )

    with pytest.raises(
        EventWriteError,
        match="simulated failure",
    ):
        create_machine_snapshot(
            scenario,
            machine_name="web",
            snapshot_name="checkpoint-1",
            recorder=recorder,
        )

    mock_create_container_snapshot.assert_called_once()

    assert [
        event.event_type
        for event in sink.events
    ] == [
        "snapshot.requested",
        "snapshot.failed",
    ]

    assert sink.events[-1].attributes[
        "snapshot_created"
    ] is True


@patch("pyrange.engine.snapshot.start_container")
@patch(
    "pyrange.engine.snapshot."
    "connect_container_to_network"
)
@patch("pyrange.engine.snapshot.create_container")
@patch("pyrange.engine.snapshot.remove_container")
@patch("pyrange.engine.snapshot.get_image_id")
def test_restore_emits_ordered_topology_events(
    mock_get_image_id,
    mock_remove_container,
    mock_create_container,
    mock_connect_container_to_network,
    mock_start_container,
    scenario: ScenarioConfig,
) -> None:
    mock_get_image_id.return_value = (
        "sha256:snapshot123"
    )

    sink = CollectingSink()
    recorder = make_recorder(
        scenario.name,
        "restore",
        sink,
    )

    restore_machine_snapshot(
        scenario,
        machine_name="web",
        snapshot_name="checkpoint-1",
        recorder=recorder,
    )

    assert [
        event.event_type
        for event in sink.events
    ] == [
        "restore.requested",
        "restore.container.removed",
        "restore.container.created",
        "restore.network.attached",
        "restore.network.attached",
        "restore.container.started",
        "restore.completed",
    ]

    attachments = [
        event
        for event in sink.events
        if event.event_type
        == "restore.network.attached"
    ]

    assert attachments[0].attributes[
        "primary"
    ] is True
    assert attachments[1].attributes[
        "primary"
    ] is False

    assert [
        event.sequence
        for event in sink.events
    ] == list(
        range(1, len(sink.events) + 1)
    )


@patch("pyrange.engine.snapshot.remove_container")
@patch("pyrange.engine.snapshot.get_image_id")
def test_restore_records_preflight_failure_before_removal(
    mock_get_image_id,
    mock_remove_container,
    scenario: ScenarioConfig,
) -> None:
    mock_get_image_id.side_effect = (
        DockerOperationError(
            "No such image"
        )
    )

    sink = CollectingSink()
    recorder = make_recorder(
        scenario.name,
        "restore",
        sink,
    )

    with pytest.raises(
        DockerOperationError,
        match="No such image",
    ):
        restore_machine_snapshot(
            scenario,
            machine_name="web",
            snapshot_name="checkpoint-1",
            recorder=recorder,
        )

    mock_remove_container.assert_not_called()

    assert [
        event.event_type
        for event in sink.events
    ] == [
        "restore.requested",
        "restore.failed",
    ]

    assert sink.events[-1].attributes[
        "stage"
    ] == "preflight"
    assert sink.events[-1].attributes[
        "destructive_started"
    ] is False


@patch("pyrange.engine.snapshot.evaluate_health_check")
@patch("pyrange.engine.snapshot.start_container")
@patch(
    "pyrange.engine.snapshot."
    "connect_container_to_network"
)
@patch("pyrange.engine.snapshot.create_container")
@patch("pyrange.engine.snapshot.remove_container")
@patch("pyrange.engine.snapshot.get_image_id")
def test_restore_health_event_excludes_command_output(
    mock_get_image_id,
    mock_remove_container,
    mock_create_container,
    mock_connect_container_to_network,
    mock_start_container,
    mock_evaluate_health_check,
    scenario: ScenarioConfig,
) -> None:
    mock_get_image_id.return_value = (
        "sha256:snapshot123"
    )

    scenario.machines[0].health_check = (
        HealthCheckConfig(
            command=["health-check"],
            retries=0,
        )
    )

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
        scenario.name,
        "restore",
        sink,
    )

    restore_machine_snapshot(
        scenario,
        machine_name="web",
        snapshot_name="checkpoint-1",
        recorder=recorder,
    )

    health_event = next(
        event
        for event in sink.events
        if event.event_type == "health.passed"
    )

    assert health_event.attributes == {
        "attempts": 1,
        "exit_code": 0,
    }
    assert "stdout" not in health_event.attributes
    assert "stderr" not in health_event.attributes


@patch("pyrange.engine.snapshot.evaluate_health_check")
@patch("pyrange.engine.snapshot.start_container")
@patch(
    "pyrange.engine.snapshot."
    "connect_container_to_network"
)
@patch("pyrange.engine.snapshot.create_container")
@patch("pyrange.engine.snapshot.remove_container")
@patch("pyrange.engine.snapshot.get_image_id")
def test_restore_health_failure_remains_primary_when_logging_fails(
    mock_get_image_id,
    mock_remove_container,
    mock_create_container,
    mock_connect_container_to_network,
    mock_start_container,
    mock_evaluate_health_check,
    scenario: ScenarioConfig,
) -> None:
    mock_get_image_id.return_value = (
        "sha256:snapshot123"
    )

    scenario.machines[0].health_check = (
        HealthCheckConfig(
            command=["health-check"],
            retries=0,
        )
    )

    mock_evaluate_health_check.return_value = (
        HealthCheckResult(
            healthy=False,
            attempts=1,
            exit_code=1,
            stdout="",
            stderr="service unavailable",
        )
    )

    sink = FailingEventSink(
        "health.failed"
    )

    recorder = make_recorder(
        scenario.name,
        "restore",
        sink,
    )

    with pytest.raises(
        SnapshotError,
        match="failed health check",
    ) as exc_info:
        restore_machine_snapshot(
            scenario,
            machine_name="web",
            snapshot_name="checkpoint-1",
            recorder=recorder,
        )

    notes = getattr(
        exc_info.value,
        "__notes__",
        [],
    )

    assert any(
        "Failed to record snapshot event "
        "'health.failed'"
        in note
        for note in notes
    )

    assert sink.events[-1].event_type == (
        "restore.failed"
    )
    assert sink.events[-1].attributes[
        "error_type"
    ] == "SnapshotError"


@patch("pyrange.engine.snapshot.start_container")
@patch(
    "pyrange.engine.snapshot."
    "connect_container_to_network"
)
@patch("pyrange.engine.snapshot.create_container")
@patch("pyrange.engine.snapshot.remove_container")
@patch("pyrange.engine.snapshot.get_image_id")
def test_restore_continues_after_post_removal_event_failure(
    mock_get_image_id,
    mock_remove_container,
    mock_create_container,
    mock_connect_container_to_network,
    mock_start_container,
    scenario: ScenarioConfig,
) -> None:
    mock_get_image_id.return_value = (
        "sha256:snapshot123"
    )

    sink = FailingEventSink(
        "restore.container.removed"
    )

    recorder = make_recorder(
        scenario.name,
        "restore",
        sink,
    )

    with pytest.raises(
        EventWriteError,
        match="simulated failure",
    ):
        restore_machine_snapshot(
            scenario,
            machine_name="web",
            snapshot_name="checkpoint-1",
            recorder=recorder,
        )

    mock_create_container.assert_called_once()
    mock_connect_container_to_network.assert_called_once()
    mock_start_container.assert_called_once_with(
        "pyrange-snapshot-lab-web"
    )

    assert sink.events[-1].event_type == (
        "restore.failed"
    )
    assert sink.events[-1].attributes[
        "operational_completed"
    ] is True
    assert sink.events[-1].attributes[
        "event_error_count"
    ] == 1


@patch(
    "pyrange.engine.snapshot."
    "create_container_snapshot"
)
def test_snapshot_rejects_mismatched_event_context(
    mock_create_container_snapshot,
    scenario: ScenarioConfig,
) -> None:
    sink = CollectingSink()

    wrong_scenario = make_recorder(
        "other-lab",
        "snapshot",
        sink,
    )

    with pytest.raises(
        SnapshotError,
        match="Event recorder",
    ):
        create_machine_snapshot(
            scenario,
            machine_name="web",
            snapshot_name="checkpoint-1",
            recorder=wrong_scenario,
        )

    wrong_operation = make_recorder(
        scenario.name,
        "restore",
        sink,
    )

    with pytest.raises(
        SnapshotError,
        match="Event recorder",
    ):
        create_machine_snapshot(
            scenario,
            machine_name="web",
            snapshot_name="checkpoint-1",
            recorder=wrong_operation,
        )

    mock_create_container_snapshot.assert_not_called()
    assert sink.events == []
