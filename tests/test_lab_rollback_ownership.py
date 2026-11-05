from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import call, patch

import pytest

from pyrange.engine.docker import DockerOperationError, DockerUnavailableError
from pyrange.engine.events import EventRecorder, EventWriteError, ExecutionContext
from pyrange.engine.manager import get_lab_container_name, get_lab_network_name, start_lab
from pyrange.models import MachineConfig, NetworkConfig, NetworkInterfaceConfig, ScenarioConfig


pytestmark = pytest.mark.usefixtures("no_legacy_resources")


class RecordingSink:
    def __init__(self, fail_on=None):
        self.events = []
        self.fail_on = fail_on

    def write(self, event):
        if event.event_type == self.fail_on:
            raise EventWriteError("event write failed")
        self.events.append(event)


@pytest.fixture
def rollback_case(rollback_resources):
    scenario = ScenarioConfig(
        name="school",
        networks=[NetworkConfig(name="net", subnet="172.28.10.0/24")],
        machines=[
            MachineConfig(name=name, image="alpine:latest", interfaces=[
                NetworkInterfaceConfig(network="net", ip=ip)
            ])
            for name, ip in [("first", "172.28.10.10"), ("second", "172.28.10.20")]
        ],
    )
    primary = DockerOperationError("original start failure")
    with (
        patch("pyrange.engine.manager.create_network") as create_network,
        patch("pyrange.engine.manager.create_container") as create_container,
        patch("pyrange.engine.manager.start_container", side_effect=[None, primary]),
        patch("pyrange.engine.manager.remove_container") as remove_container,
        patch("pyrange.engine.manager.remove_network") as remove_network,
        patch("pyrange.engine.manager.find_container_identity", side_effect=AssertionError("Rollback must not resolve names")),
        patch("pyrange.engine.manager.find_network_identity", side_effect=AssertionError("Rollback must not resolve names")),
    ):
        rollback_resources.configure(create_network, create_container, scenario)
        ids = rollback_resources.ids
        yield SimpleNamespace(
            scenario=scenario, primary=primary, resources=rollback_resources,
            create_network=create_network, create_container=create_container,
            remove_container=remove_container, remove_network=remove_network,
            first=ids[get_lab_container_name(scenario, scenario.machines[0])],
            second=ids[get_lab_container_name(scenario, scenario.machines[1])],
            network=ids[get_lab_network_name(scenario, scenario.networks[0])],
        )


def recorder(case, sink):
    return EventRecorder(ExecutionContext(scenario=case.scenario.name, operation="start"), sink)


def test_rollback_inspects_and_deletes_creation_ids_in_reverse_order(rollback_case):
    c = rollback_case
    sink = RecordingSink()
    with pytest.raises(DockerOperationError) as caught:
        start_lab(c.scenario, recorder=recorder(c, sink))
    assert caught.value is c.primary
    assert c.resources.inspect_container.call_args_list == [call(c.second), call(c.first)]
    c.resources.inspect_network.assert_called_once_with(c.network)
    assert c.remove_container.call_args_list == [call(c.second), call(c.first)]
    c.remove_network.assert_called_once_with(c.network)
    removed = [e for e in sink.events if e.event_type == "resource.rollback.removed"]
    assert [e.resource.name for e in removed] == ["second", "first", "net"]
    assert sink.events[-1].attributes["rollback_error_count"] == 0


@pytest.mark.parametrize("kind", ["container", "network"])
@pytest.mark.parametrize("problem", ["missing-labels", "wrong-labels", "different-id", "inspect-failure", "cli-unavailable", "delete-failure"])
def test_rollback_rejects_unverified_ids_and_preserves_primary(rollback_case, kind, problem):
    c = rollback_case
    target = c.second if kind == "container" else c.network
    mapping = c.resources.containers if kind == "container" else c.resources.networks
    inspector = c.resources.inspect_container if kind == "container" else c.resources.inspect_network
    remover = c.remove_container if kind == "container" else c.remove_network
    identity = mapping[target]
    if problem == "missing-labels":
        mapping[target] = replace(identity, labels=None)
    elif problem == "wrong-labels":
        mapping[target] = replace(identity, labels={**identity.labels, "pyrange.scenario.name": "foreign"})
    elif problem == "different-id":
        mapping[target] = replace(identity, resource_id="f" * 64)
    elif problem in ["inspect-failure", "cli-unavailable"]:
        error = DockerOperationError if problem == "inspect-failure" else DockerUnavailableError
        def inspect(resource_id):
            if resource_id == target:
                raise error("inspection failed")
            return mapping[resource_id]
        inspector.side_effect = inspect
    else:
        def remove(resource_id):
            if resource_id == target:
                raise DockerOperationError("deletion failed")
        remover.side_effect = remove
    sink = RecordingSink()
    with pytest.raises(DockerOperationError) as caught:
        start_lab(c.scenario, recorder=recorder(c, sink))
    assert caught.value is c.primary
    assert any("Rollback failed" in note for note in caught.value.__notes__)
    expected_containers = [call(c.second), call(c.first)]
    expected_networks = [call(c.network)]
    if problem != "delete-failure":
        if kind == "container":
            expected_containers = [call(c.first)]
        else:
            expected_networks = []
    assert c.remove_container.call_args_list == expected_containers
    assert c.remove_network.call_args_list == expected_networks
    assert sink.events[-1].attributes["rollback_error_count"] == 1
    failures = [e for e in sink.events if e.event_type == "resource.rollback.failed"]
    assert len(failures) == 1
    assert failures[0].resource.name == ("second" if kind == "container" else "net")


def test_failed_creation_is_not_added_to_rollback(rollback_case):
    c = rollback_case
    c.create_container.side_effect = [c.first, c.primary]
    with pytest.raises(DockerOperationError) as caught:
        start_lab(c.scenario)
    assert caught.value is c.primary
    c.resources.inspect_container.assert_called_once_with(c.first)
    c.remove_container.assert_called_once_with(c.first)
    c.remove_network.assert_called_once_with(c.network)


def test_failed_network_creation_does_not_remove_existing_resources(rollback_case):
    c = rollback_case
    c.create_network.side_effect = c.primary
    with pytest.raises(DockerOperationError) as caught:
        start_lab(c.scenario)
    assert caught.value is c.primary
    c.create_container.assert_not_called()
    c.resources.inspect_container.assert_not_called()
    c.resources.inspect_network.assert_not_called()
    c.remove_container.assert_not_called()
    c.remove_network.assert_not_called()


def test_resource_is_tracked_before_creation_event_is_written(rollback_case):
    c = rollback_case
    sink = RecordingSink("machine.created")
    with pytest.raises(EventWriteError, match="event write failed"):
        start_lab(c.scenario, recorder=recorder(c, sink))
    assert c.create_container.call_count == 1
    c.resources.inspect_container.assert_called_once_with(c.first)
    c.remove_container.assert_called_once_with(c.first)
    c.remove_network.assert_called_once_with(c.network)


def test_cleanup_and_event_failures_do_not_replace_primary(rollback_case):
    c = rollback_case
    c.remove_container.side_effect = DockerOperationError("cleanup failed")
    sink = RecordingSink("resource.rollback.failed")
    with pytest.raises(DockerOperationError) as caught:
        start_lab(c.scenario, recorder=recorder(c, sink))
    assert caught.value is c.primary
    notes = caught.value.__notes__
    assert sum("Rollback failed" in note for note in notes) == 2
    assert sum("Failed to record lifecycle event" in note for note in notes) == 2
    c.remove_network.assert_called_once_with(c.network)
    assert sink.events[-1].attributes["rollback_error_count"] == 2
    assert [e.sequence for e in sink.events] == list(range(1, len(sink.events) + 1))


@pytest.mark.parametrize("invalid_id", [None, "", "--force", "short"])
def test_invalid_creation_id_is_never_used_for_cleanup(rollback_case, invalid_id):
    c = rollback_case
    c.create_container.side_effect = [c.first, invalid_id]
    with pytest.raises(DockerOperationError) as caught:
        start_lab(c.scenario)
    assert caught.value is c.primary
    c.resources.inspect_container.assert_called_once_with(c.first)
    c.remove_container.assert_called_once_with(c.first)
    c.remove_network.assert_called_once_with(c.network)
    assert any("Invalid resource ID" in note for note in caught.value.__notes__)
