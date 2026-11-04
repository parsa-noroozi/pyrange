from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pyrange.engine.docker import DockerOperationError
from pyrange.engine.events import EventRecorder, ExecutionContext
from pyrange.engine.ownership import ResourceOwnershipError
from pyrange.engine.snapshot import SnapshotError, create_machine_snapshot, restore_machine_snapshot
from pyrange.models import MachineConfig, NetworkConfig, NetworkInterfaceConfig, ScenarioConfig


class Sink:
    def __init__(self):
        self.events = []

    def write(self, event):
        self.events.append(event)


@pytest.fixture
def snapshot_case(snapshot_resources):
    scenario = ScenarioConfig(name="snapshot-lab", networks=[
        NetworkConfig(name="net", subnet="172.28.10.0/24"),
    ], machines=[MachineConfig(name="web", image="alpine:latest", interfaces=[
        NetworkInterfaceConfig(network="net", ip="172.28.10.10"),
    ])])
    with (
        patch("pyrange.engine.snapshot.create_container_snapshot", return_value=snapshot_resources.image.resource_id) as commit,
        patch("pyrange.engine.snapshot.remove_container") as remove,
        patch("pyrange.engine.snapshot.create_container") as create,
        patch("pyrange.engine.snapshot.start_container") as start,
    ):
        yield SimpleNamespace(scenario=scenario, resources=snapshot_resources,
                              commit=commit, remove=remove, create=create, start=start)


def run(case, operation, sink):
    function = create_machine_snapshot if operation == "snapshot" else restore_machine_snapshot
    return function(case.scenario, "web", "checkpoint", recorder=EventRecorder(
        ExecutionContext(scenario=case.scenario.name, operation=operation), sink,
    ))


@pytest.mark.parametrize("operation", ["snapshot", "restore"])
@pytest.mark.parametrize("problem", ["missing-labels", "wrong-scenario", "query-failure"])
def test_unverified_container_blocks_mutation(snapshot_case, operation, problem):
    c = snapshot_case
    if operation == "restore":
        c.resources.find_image.return_value = c.resources.image
    if problem == "query-failure":
        c.resources.find_container.side_effect = DockerOperationError("query failed")
        expected = DockerOperationError
    else:
        labels = None if problem == "missing-labels" else {
            **c.resources.container.labels, "pyrange.scenario.name": "foreign",
        }
        c.resources.find_container.return_value = replace(c.resources.container, labels=labels)
        expected = ResourceOwnershipError
    sink = Sink()
    with pytest.raises(expected):
        run(c, operation, sink)
    c.commit.assert_not_called()
    c.remove.assert_not_called()
    c.create.assert_not_called()
    c.start.assert_not_called()
    assert sink.events[-1].event_type == operation + ".failed"
    if operation == "restore":
        assert sink.events[-1].attributes["destructive_started"] is False
        assert sink.events[-1].attributes["stage"] == "preflight"
    else:
        assert sink.events[-1].attributes["snapshot_created"] is False


@pytest.mark.parametrize("problem", ["absent", "missing-labels", "container-labels", "query-failure"])
def test_unverified_image_blocks_restore_before_target_lookup(snapshot_case, problem):
    c = snapshot_case
    if problem == "query-failure":
        c.resources.find_image.side_effect = DockerOperationError("query failed")
        expected = DockerOperationError
    elif problem == "absent":
        expected = SnapshotError
    else:
        c.resources.find_image.return_value = replace(c.resources.image, labels=(
            None if problem == "missing-labels" else c.resources.container.labels
        ))
        expected = ResourceOwnershipError
    sink = Sink()
    with pytest.raises(expected):
        run(c, "restore", sink)
    c.resources.find_container.assert_not_called()
    c.remove.assert_not_called()
    c.create.assert_not_called()
    assert sink.events[-1].attributes["destructive_started"] is False


def test_existing_checkpoint_is_not_overwritten(snapshot_case):
    c = snapshot_case
    c.resources.find_image.return_value = c.resources.image
    with pytest.raises(SnapshotError, match="already exists"):
        run(c, "snapshot", Sink())
    c.resources.find_container.assert_not_called()
    c.commit.assert_not_called()


def test_snapshot_list_failure_does_not_authorize_overwrite(snapshot_case):
    c = snapshot_case
    c.resources.find_image.side_effect = DockerOperationError("list failed")
    with pytest.raises(DockerOperationError, match="list failed"):
        run(c, "snapshot", Sink())
    c.commit.assert_not_called()


def test_absent_source_cannot_be_snapshotted(snapshot_case):
    c = snapshot_case
    c.resources.find_container.return_value = None
    with pytest.raises(SnapshotError, match="absent"):
        run(c, "snapshot", Sink())
    c.commit.assert_not_called()


def test_snapshot_uses_verified_container_id_and_snapshot_labels(snapshot_case):
    c = snapshot_case
    run(c, "snapshot", Sink())
    args = c.commit.call_args.kwargs
    assert args["name"] == c.resources.container.resource_id
    assert args["labels"] == c.resources.image.labels
    assert args["labels"]["pyrange.resource.kind"] == "snapshot"
    assert c.resources.container.labels["pyrange.resource.kind"] == "container"


@pytest.mark.parametrize("target_exists", [True, False])
def test_restore_pins_image_and_sets_container_labels(snapshot_case, target_exists):
    c = snapshot_case
    c.resources.find_image.return_value = c.resources.image
    if not target_exists:
        c.resources.find_container.return_value = None
    sink = Sink()
    result = run(c, "restore", sink)
    assert result.image_id == c.resources.image.resource_id
    if target_exists:
        c.remove.assert_called_once_with(c.resources.container.resource_id)
    else:
        c.remove.assert_not_called()
        assert "restore.container.absent" in [e.event_type for e in sink.events]
        assert "restore.container.removed" not in [e.event_type for e in sink.events]
    args = c.create.call_args.kwargs
    assert args["image"] == c.resources.image.resource_id
    assert args["labels"] == c.resources.container.labels
    assert args["labels"]["pyrange.resource.kind"] == "container"
    assert c.resources.image.labels["pyrange.resource.kind"] == "snapshot"
    c.start.assert_called_once()
