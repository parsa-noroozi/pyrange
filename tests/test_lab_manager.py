from unittest.mock import call, patch

import pytest

from pyrange.engine import (
    DockerOperationError,
    HealthCheckResult,
)
from pyrange.engine.manager import (
    LabManagerError,
    get_lab_container_name,
    get_lab_network_name,
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


def test_generates_resource_names(
    scenario: ScenarioConfig,
) -> None:
    assert (
        get_lab_network_name(
            scenario,
            scenario.networks[0],
        )
        == "pyrange-segmented-lab-public-net"
    )

    assert (
        get_lab_network_name(
            scenario,
            scenario.networks[1],
        )
        == "pyrange-segmented-lab-private-net"
    )

    assert (
        get_lab_container_name(
            scenario,
            scenario.machines[0],
        )
        == "pyrange-segmented-lab-web"
    )


@patch("pyrange.engine.manager.start_container")
@patch(
    "pyrange.engine.manager."
    "connect_container_to_network"
)
@patch("pyrange.engine.manager.create_container")
@patch("pyrange.engine.manager.create_network")
def test_start_lab_creates_multi_network_topology(
    mock_create_network,
    mock_create_container,
    mock_connect_container_to_network,
    mock_start_container,
    scenario: ScenarioConfig,
) -> None:
    start_lab(scenario)

    assert mock_create_network.call_args_list == [
        call(
            "pyrange-segmented-lab-public-net",
            "172.28.10.0/24",
        ),
        call(
            "pyrange-segmented-lab-private-net",
            "172.28.20.0/24",
        ),
    ]

    assert mock_create_container.call_args_list == [
        call(
            name="pyrange-segmented-lab-web",
            image="nginx:alpine",
            network=(
                "pyrange-segmented-lab-public-net"
            ),
            ip="172.28.10.10",
        ),
        call(
            name="pyrange-segmented-lab-analyst",
            image="alpine:latest",
            network=(
                "pyrange-segmented-lab-public-net"
            ),
            ip="172.28.10.20",
        ),
    ]

    mock_connect_container_to_network.assert_called_once_with(
        name="pyrange-segmented-lab-analyst",
        network="pyrange-segmented-lab-private-net",
        ip="172.28.20.20",
    )

    assert mock_start_container.call_args_list == [
        call("pyrange-segmented-lab-web"),
        call("pyrange-segmented-lab-analyst"),
    ]


@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
@patch("pyrange.engine.manager.start_container")
@patch(
    "pyrange.engine.manager."
    "connect_container_to_network"
)
@patch("pyrange.engine.manager.create_container")
@patch("pyrange.engine.manager.create_network")
def test_start_lab_rolls_back_multi_network_failure(
    mock_create_network,
    mock_create_container,
    mock_connect_container_to_network,
    mock_start_container,
    mock_remove_container,
    mock_remove_network,
    scenario: ScenarioConfig,
) -> None:
    mock_connect_container_to_network.side_effect = (
        DockerOperationError(
            "failed to connect network"
        )
    )

    with pytest.raises(
        DockerOperationError,
        match="failed to connect network",
    ):
        start_lab(scenario)

    assert mock_remove_container.call_args_list == [
        call("pyrange-segmented-lab-analyst"),
        call("pyrange-segmented-lab-web"),
    ]

    assert mock_remove_network.call_args_list == [
        call("pyrange-segmented-lab-private-net"),
        call("pyrange-segmented-lab-public-net"),
    ]


@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
def test_stop_lab_removes_resources_in_reverse_order(
    mock_remove_container,
    mock_remove_network,
    scenario: ScenarioConfig,
) -> None:
    stop_lab(scenario)

    assert mock_remove_container.call_args_list == [
        call("pyrange-segmented-lab-analyst"),
        call("pyrange-segmented-lab-web"),
    ]

    assert mock_remove_network.call_args_list == [
        call("pyrange-segmented-lab-private-net"),
        call("pyrange-segmented-lab-public-net"),
    ]
    
    
@patch("pyrange.engine.manager.evaluate_health_check")
@patch("pyrange.engine.manager.start_container")
@patch("pyrange.engine.manager.create_container")
@patch("pyrange.engine.manager.create_network")
def test_start_lab_evaluates_machine_health_check(
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
            stdout="",
            stderr="",
        )
    )

    start_lab(health_scenario)

    mock_start_container.assert_called_once_with(
        "pyrange-health-lab-web"
    )

    mock_evaluate_health_check.assert_called_once_with(
        "pyrange-health-lab-web",
        health_scenario.machines[0].health_check,
    )


@patch("pyrange.engine.manager.remove_network")
@patch("pyrange.engine.manager.remove_container")
@patch("pyrange.engine.manager.evaluate_health_check")
@patch("pyrange.engine.manager.start_container")
@patch("pyrange.engine.manager.create_container")
@patch("pyrange.engine.manager.create_network")
def test_start_lab_rolls_back_unhealthy_machine(
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
            stderr="service unavailable\n",
        )
    )

    with pytest.raises(
        LabManagerError,
        match="Health check failed for machine 'web'",
    ):
        start_lab(health_scenario)

    mock_remove_container.assert_called_once_with(
        "pyrange-health-lab-web"
    )

    mock_remove_network.assert_called_once_with(
        "pyrange-health-lab-lab-net"
    )


@patch("pyrange.engine.manager.evaluate_health_check")
@patch("pyrange.engine.manager.start_container")
@patch(
    "pyrange.engine.manager."
    "connect_container_to_network"
)
@patch("pyrange.engine.manager.create_container")
@patch("pyrange.engine.manager.create_network")
def test_start_lab_runs_health_checks_after_all_containers_start(
    mock_create_network,
    mock_create_container,
    mock_connect_container_to_network,
    mock_start_container,
    mock_evaluate_health_check,
    scenario: ScenarioConfig,
) -> None:
    scenario.machines[0].health_check = HealthCheckConfig(
        command=["health-check"],
        retries=0,
    )

    events: list[str] = []

    mock_start_container.side_effect = (
        lambda name: events.append(f"start:{name}")
    )

    mock_evaluate_health_check.side_effect = (
        lambda name, config: (
            events.append(f"health:{name}")
            or HealthCheckResult(
                healthy=True,
                attempts=1,
                exit_code=0,
                stdout="",
                stderr="",
            )
        )
    )

    start_lab(scenario)

    assert events == [
        "start:pyrange-segmented-lab-web",
        "start:pyrange-segmented-lab-analyst",
        "health:pyrange-segmented-lab-web",
    ]
