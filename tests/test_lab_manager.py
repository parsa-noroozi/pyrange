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
        == PUBLIC_NETWORK_NAME
    )

    assert (
        get_lab_network_name(
            scenario,
            scenario.networks[1],
        )
        == PRIVATE_NETWORK_NAME
    )

    assert (
        get_lab_container_name(
            scenario,
            scenario.machines[0],
        )
        == WEB_CONTAINER_NAME
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
            PUBLIC_NETWORK_NAME,
            "172.28.10.0/24",
            labels={
                "pyrange.managed": "true",
                "pyrange.ownership.version": "1",
                "pyrange.resource.kind": "network",
                "pyrange.scenario.name": "segmented-lab",
                "pyrange.resource.name": "public-net",
                "pyrange.resource.identity": PUBLIC_NETWORK_NAME,
            },
        ),
        call(
            PRIVATE_NETWORK_NAME,
            "172.28.20.0/24",
            labels={
                "pyrange.managed": "true",
                "pyrange.ownership.version": "1",
                "pyrange.resource.kind": "network",
                "pyrange.scenario.name": "segmented-lab",
                "pyrange.resource.name": "private-net",
                "pyrange.resource.identity": PRIVATE_NETWORK_NAME,
            },
        ),
    ]

    assert mock_create_container.call_args_list == [
        call(
            name=WEB_CONTAINER_NAME,
            image="nginx:alpine",
            network=PUBLIC_NETWORK_NAME,
            ip="172.28.10.10",
            labels={
                "pyrange.managed": "true",
                "pyrange.ownership.version": "1",
                "pyrange.resource.kind": "container",
                "pyrange.scenario.name": "segmented-lab",
                "pyrange.resource.name": "web",
                "pyrange.resource.identity": WEB_CONTAINER_NAME,
            },
        ),
        call(
            name=ANALYST_CONTAINER_NAME,
            image="alpine:latest",
            network=PUBLIC_NETWORK_NAME,
            ip="172.28.10.20",
            labels={
                "pyrange.managed": "true",
                "pyrange.ownership.version": "1",
                "pyrange.resource.kind": "container",
                "pyrange.scenario.name": "segmented-lab",
                "pyrange.resource.name": "analyst",
                "pyrange.resource.identity": ANALYST_CONTAINER_NAME,
            },
        ),
    ]

    mock_connect_container_to_network.assert_called_once_with(
        name=ANALYST_CONTAINER_NAME,
        network=PRIVATE_NETWORK_NAME,
        ip="172.28.20.20",
    )

    assert mock_start_container.call_args_list == [
        call(WEB_CONTAINER_NAME),
        call(ANALYST_CONTAINER_NAME),
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
        call(ANALYST_CONTAINER_NAME),
        call(WEB_CONTAINER_NAME),
    ]

    assert mock_remove_network.call_args_list == [
        call(PRIVATE_NETWORK_NAME),
        call(PUBLIC_NETWORK_NAME),
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
        call(ANALYST_CONTAINER_NAME),
        call(WEB_CONTAINER_NAME),
    ]

    assert mock_remove_network.call_args_list == [
        call(PRIVATE_NETWORK_NAME),
        call(PUBLIC_NETWORK_NAME),
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
        HEALTH_CONTAINER_NAME
    )

    mock_evaluate_health_check.assert_called_once_with(
        HEALTH_CONTAINER_NAME,
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
        HEALTH_CONTAINER_NAME
    )

    mock_remove_network.assert_called_once_with(
        HEALTH_NETWORK_NAME
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
    f"start:{WEB_CONTAINER_NAME}",
    f"start:{ANALYST_CONTAINER_NAME}",
    f"health:{WEB_CONTAINER_NAME}",
    ]
