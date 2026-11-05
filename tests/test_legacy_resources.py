from types import SimpleNamespace
from unittest.mock import call, patch

import pytest

from pyrange.engine.docker import DockerOperationError, DockerResourceIdentity, DockerUnavailableError
from pyrange.engine.events import EventRecorder, EventWriteError, ExecutionContext
from pyrange.engine.legacy import LegacyResourceError, require_no_legacy_resources, scan_legacy_resources
from pyrange.engine.manager import LabManagerError, start_lab, stop_lab
from pyrange.engine.ownership import build_ownership_labels
from pyrange.engine.snapshot import create_machine_snapshot, restore_machine_snapshot
from pyrange.models import MachineConfig, NetworkConfig, NetworkInterfaceConfig, ScenarioConfig


class Sink:
    def __init__(self, fail_on=None):
        self.events = []
        self.fail_on = fail_on

    def write(self, event):
        if event.event_type == self.fail_on:
            raise EventWriteError("legacy event failure")
        self.events.append(event)


@pytest.fixture
def legacy_case():
    scenario = ScenarioConfig(name="school", networks=[
        NetworkConfig(name="net", subnet="172.28.10.0/24"),
    ], machines=[MachineConfig(name="web", image="alpine:latest", interfaces=[
        NetworkInterfaceConfig(network="net", ip="172.28.10.10"),
    ])])
    with (
        patch("pyrange.engine.legacy.find_container_identity", return_value=None) as container,
        patch("pyrange.engine.legacy.find_network_identity", return_value=None) as network,
        patch("pyrange.engine.legacy.find_image_identity", return_value=None) as image,
        patch("pyrange.engine.docker.subprocess.run", side_effect=AssertionError("Unexpected Docker command")),
    ):
        yield SimpleNamespace(scenario=scenario, container=container, network=network, image=image,
                              identity=DockerResourceIdentity("f" * 64, None))


def record(c, operation, sink):
    return EventRecorder(ExecutionContext(scenario=c.scenario.name, operation=operation), sink)


def test_no_legacy_matches_require_successful_exact_lookups(legacy_case):
    c = legacy_case
    require_no_legacy_resources(c.scenario)
    c.container.assert_called_once_with("pyrange-school-web")
    c.network.assert_called_once_with("pyrange-school-net")
    c.image.assert_not_called()


@pytest.mark.parametrize("kind", ["container", "network", "snapshot"])
@pytest.mark.parametrize("labels", [None, {}, {"pyrange.managed": "true"}])
def test_name_match_is_only_candidate_regardless_of_labels(legacy_case, kind, labels):
    c = legacy_case
    lookup = c.image if kind == "snapshot" else getattr(c, kind)
    lookup.return_value = DockerResourceIdentity("f" * 64, labels)
    scan = scan_legacy_resources(c.scenario, machine=c.scenario.machines[0], snapshot_name="checkpoint")
    assert len(scan.candidates) == 1
    assert scan.candidates[0].kind == kind
    assert scan.candidates[0].resource_id == "f" * 64
    assert scan.failures == ()
    c.image.assert_called_with("pyrange-snapshots/school-web:checkpoint")
    with pytest.raises(LegacyResourceError, match="ownership is not established"):
        require_no_legacy_resources(c.scenario, machine=c.scenario.machines[0], snapshot_name="checkpoint")


@pytest.mark.parametrize("error_type", [DockerOperationError, DockerUnavailableError])
def test_lookup_failure_is_not_absence_and_does_not_hide_other_candidate(legacy_case, error_type):
    c = legacy_case
    error = error_type("unavailable")
    c.container.side_effect = error
    c.network.return_value = c.identity
    scan = scan_legacy_resources(c.scenario)
    assert len(scan.failures) == 1
    assert scan.failures[0].error is error
    assert len(scan.candidates) == 1
    assert scan.candidates[0].kind == "network"
    with pytest.raises(LegacyResourceError) as caught:
        require_no_legacy_resources(c.scenario)
    assert caught.value.__cause__ is error
    assert "unavailable" in str(caught.value)
    assert "pyrange-school-net" in str(caught.value)


def test_ambiguous_old_name_does_not_establish_scenario_ownership(legacy_case):
    c = legacy_case
    first = c.scenario.model_copy(deep=True)
    first.name = "alpha-beta"
    second = c.scenario.model_copy(deep=True)
    second.name = "alpha"
    second.machines[0].name = "beta-web"
    c.container.return_value = c.identity
    one = scan_legacy_resources(first).candidates[0]
    two = scan_legacy_resources(second).candidates[0]
    assert one.runtime_name == two.runtime_name == "pyrange-alpha-beta-web"
    for scenario in [first, second]:
        with pytest.raises(LegacyResourceError):
            require_no_legacy_resources(scenario)


def test_selected_machine_scopes_container_and_network_queries(legacy_case):
    c = legacy_case
    c.scenario.networks.append(NetworkConfig(name="other-net", subnet="172.28.20.0/24"))
    c.scenario.machines.append(MachineConfig(name="other", image="alpine:latest", interfaces=[
        NetworkInterfaceConfig(network="other-net", ip="172.28.20.10"),
    ]))
    scan_legacy_resources(c.scenario, machine=c.scenario.machines[0], snapshot_name="checkpoint")
    c.container.assert_called_once_with("pyrange-school-web")
    c.network.assert_called_once_with("pyrange-school-net")


@pytest.mark.parametrize("problem", ["container", "network", "query-failure"])
def test_start_rejects_legacy_before_any_creation(legacy_case, problem):
    c = legacy_case
    if problem == "query-failure":
        c.container.side_effect = DockerOperationError("query failed")
    else:
        getattr(c, problem).return_value = c.identity
    sink = Sink()
    with (
        patch("pyrange.engine.manager.create_network") as create_network,
        patch("pyrange.engine.manager.create_container") as create_container,
        patch("pyrange.engine.manager.remove_network") as remove_network,
        patch("pyrange.engine.manager.remove_container") as remove_container,
    ):
        with pytest.raises(LegacyResourceError):
            start_lab(c.scenario, recorder=record(c, "start", sink))
        for action in [create_network, create_container, remove_network, remove_container]:
            action.assert_not_called()
    assert [e.event_type for e in sink.events] == ["lab.start.requested", "lab.start.failed"]
    assert sink.events[-1].attributes["rollback_error_count"] == 0


@pytest.mark.parametrize("operation", ["snapshot", "restore"])
@pytest.mark.parametrize("problem", ["container", "network", "snapshot", "query-failure"])
def test_snapshot_operations_reject_legacy_before_mutation(legacy_case, operation, problem):
    c = legacy_case
    if problem == "query-failure":
        c.image.side_effect = DockerOperationError("image query failed")
    else:
        (c.image if problem == "snapshot" else getattr(c, problem)).return_value = c.identity
    sink = Sink()
    function = create_machine_snapshot if operation == "snapshot" else restore_machine_snapshot
    with (
        patch("pyrange.engine.snapshot.find_image_identity") as current_image,
        patch("pyrange.engine.snapshot.create_container_snapshot") as commit,
        patch("pyrange.engine.snapshot.remove_container") as remove,
        patch("pyrange.engine.snapshot.create_container") as create,
    ):
        with pytest.raises(LegacyResourceError):
            function(c.scenario, "web", "checkpoint", recorder=record(c, operation, sink))
        for action in [current_image, commit, remove, create]:
            action.assert_not_called()
    assert [e.event_type for e in sink.events] == [operation + ".requested", operation + ".failed"]
    if operation == "restore":
        assert sink.events[-1].attributes["destructive_started"] is False
    else:
        assert sink.events[-1].attributes["snapshot_created"] is False


@pytest.mark.parametrize("problem", ["container", "network", "query-failure"])
@pytest.mark.parametrize("event_failure", [False, True])
def test_stop_leaves_legacy_untouched_and_reports_incomplete_cleanup(legacy_case, problem, event_failure):
    c = legacy_case
    if problem == "query-failure":
        c.container.side_effect = DockerOperationError("legacy query failed")
        event_type = "legacy.discovery.failed"
    else:
        getattr(c, problem).return_value = c.identity
        event_type = "resource.legacy.detected"
    sink = Sink(event_type if event_failure else None)
    current_container = DockerResourceIdentity("a" * 64, build_ownership_labels("container", "school", "web"))
    current_network = DockerResourceIdentity("b" * 64, build_ownership_labels("network", "school", "net"))
    with (
        patch("pyrange.engine.manager.find_container_identity", return_value=current_container),
        patch("pyrange.engine.manager.find_network_identity", return_value=current_network),
        patch("pyrange.engine.manager.remove_container") as remove_container,
        patch("pyrange.engine.manager.remove_network") as remove_network,
    ):
        with pytest.raises(LabManagerError) as caught:
            stop_lab(c.scenario, recorder=record(c, "stop", sink))
        remove_container.assert_called_once_with("a" * 64)
        remove_network.assert_called_once_with("b" * 64)
    assert "lab.stop.completed" not in [e.event_type for e in sink.events]
    assert sink.events[-1].event_type == "lab.stop.failed"
    assert sink.events[-1].attributes == {
        "operational_error_count": 1, "event_error_count": int(event_failure),
    }
    if event_failure:
        assert any("Event logging also failed" in note for note in caught.value.__notes__)
    else:
        event = next(e for e in sink.events if e.event_type == event_type)
        if problem != "query-failure":
            assert event.attributes["ownership_verified"] is False
            assert event.attributes["runtime_id"] == c.identity.resource_id
        else:
            assert event.attributes["error_type"] == "DockerOperationError"
    assert [e.sequence for e in sink.events] == list(range(1, len(sink.events) + 1))


def test_stop_does_not_report_success_when_only_legacy_resource_exists(legacy_case):
    c = legacy_case
    c.container.return_value = c.identity
    sink = Sink()
    with (
        patch("pyrange.engine.manager.find_container_identity", return_value=None),
        patch("pyrange.engine.manager.find_network_identity", return_value=None),
        patch("pyrange.engine.manager.remove_container") as remove_container,
        patch("pyrange.engine.manager.remove_network") as remove_network,
    ):
        with pytest.raises(LabManagerError, match="Manual review"):
            stop_lab(c.scenario, recorder=record(c, "stop", sink))
        remove_container.assert_not_called()
        remove_network.assert_not_called()
    assert [e.event_type for e in sink.events] == [
        "lab.stop.requested", "resource.legacy.detected",
        "machine.absent", "network.absent", "lab.stop.failed",
    ]


@pytest.mark.parametrize("problem", ["candidate", "query-failure"])
def test_status_cannot_silently_report_stopped_with_unresolved_legacy(legacy_case, problem):
    from pyrange.engine.status import inspect_lab_status

    c = legacy_case
    if problem == "candidate":
        c.container.return_value = c.identity
    else:
        c.container.side_effect = DockerOperationError("legacy query failed")
    with (
        patch("pyrange.engine.status.inspect_container_runtime") as inspect_container,
        patch("pyrange.engine.status.inspect_network_runtime") as inspect_network,
    ):
        with pytest.raises(LegacyResourceError):
            inspect_lab_status(c.scenario)
        inspect_container.assert_not_called()
        inspect_network.assert_not_called()
