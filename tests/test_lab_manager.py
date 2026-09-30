from unittest.mock import call, patch

import pytest

from pyrange.engine import DockerOperationError
from pyrange.engine.manager import (
    get_lab_container_name,
    get_lab_network_name,
    start_lab,
    stop_lab,
)
from pyrange.models import MachineConfig, NetworkConfig, ScenarioConfig


@pytest.fixture
def scenario() -> ScenarioConfig:
    return ScenarioConfig(
        name="test-lab",
        network=NetworkConfig(
            name="lab-net",
            subnet="172.28.30.0/24",
        ),
        machines=[
            MachineConfig(
                name="web",
                image="nginx:alpine",
                ip="172.28.30.10",
            ),
            MachineConfig(
                name="analyst",
                image="alpine:latest",
                ip="172.28.30.20",
            ),
        ],
    )


def test_generates_resource_names(scenario: ScenarioConfig) -> None:
    assert get_lab_network_name(scenario) == "pyrange-test-lab-lab-net"
    assert (
        get_lab_container_name(scenario, scenario.machines[0])
        == "pyrange-test-lab-web"
    )


@patch("pyrange.engine.manager.start_container")
@patch("pyrange.engine.manager.create_container")
@patch("pyrange.engine.manager.create_network")
def test_start_lab_creates_network_and_containers(
    mock_create_network,
    mock_create_container,
    mock_start_container,
    scenario: ScenarioConfig,
) -> None:
    start_lab(scenario)

    mock_create_network.assert_called_once_with(
        "pyrange-test-lab-lab-net",
        "172.28.30.0/24",
    )

    assert mock_create_container.call_args_list == [
        call(
            name="pyrange-test-lab-web",
            image="nginx:alpine",
            network="pyrange-test-lab-lab-net",
            ip="172.28.30.10",
        ),
        call(
            name="pyrange-test-lab-analyst",
            image="alpine:latest",
            network="pyrange-test-lab-lab-net",
            ip="172.28.30.20",
        ),
    ]

    assert mock_start_container.call_args_list == [
        call("pyrange-test-lab-web"),
        call("pyrange-test-lab-analyst"),
    ]


@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
@patch("pyrange.engine.manager.start_container")
@patch("pyrange.engine.manager.create_container")
@patch("pyrange.engine.manager.create_network")
def test_start_lab_rolls_back_on_failure(
    mock_create_network,
    mock_create_container,
    mock_start_container,
    mock_remove_container,
    mock_remove_network,
    scenario: ScenarioConfig,
) -> None:
    mock_create_container.side_effect = [
        "container-1",
        DockerOperationError("failed to create container"),
    ]

    with pytest.raises(
        DockerOperationError,
        match="failed to create container",
    ):
        start_lab(scenario)

    mock_remove_container.assert_called_once_with(
        "pyrange-test-lab-web"
    )
    mock_remove_network.assert_called_once_with(
        "pyrange-test-lab-lab-net"
    )


@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
def test_stop_lab_removes_containers_in_reverse_order(
    mock_remove_container,
    mock_remove_network,
    scenario: ScenarioConfig,
) -> None:
    stop_lab(scenario)

    assert mock_remove_container.call_args_list == [
        call("pyrange-test-lab-analyst"),
        call("pyrange-test-lab-web"),
    ]

    mock_remove_network.assert_called_once_with(
        "pyrange-test-lab-lab-net"
    )
