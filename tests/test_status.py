from unittest.mock import call, patch

import pytest

from pyrange.engine import (
    ContainerNetworkState,
    ContainerRuntimeState,
    NetworkRuntimeState,
)
from pyrange.engine.status import (
    LabStatus,
    MachineInterfaceStatus,
    MachineStatus,
    NetworkStatus,
    inspect_lab_status,
)
from pyrange.models import (
    MachineConfig,
    NetworkConfig,
    NetworkInterfaceConfig,
    ScenarioConfig,
)


@pytest.fixture
def scenario() -> ScenarioConfig:
    return ScenarioConfig(
        name="status-lab",
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
                image="nginx:alpine",
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


@patch(
    "pyrange.engine.status.inspect_container_runtime"
)
@patch(
    "pyrange.engine.status.inspect_network_runtime"
)
def test_inspect_lab_status_returns_running_when_matching(
    mock_inspect_network,
    mock_inspect_container,
    scenario: ScenarioConfig,
) -> None:
    mock_inspect_network.side_effect = [
        NetworkRuntimeState(
            name="pyrange-status-lab-public-net",
            subnets=("172.28.10.0/24",),
        ),
        NetworkRuntimeState(
            name="pyrange-status-lab-private-net",
            subnets=("172.28.20.0/24",),
        ),
    ]

    mock_inspect_container.side_effect = [
        ContainerRuntimeState(
            name="pyrange-status-lab-web",
            status="running",
            networks=(
                ContainerNetworkState(
                    network_name=(
                        "pyrange-status-lab-public-net"
                    ),
                    ip_address="172.28.10.10",
                ),
            ),
        ),
        ContainerRuntimeState(
            name="pyrange-status-lab-analyst",
            status="running",
            networks=(
                ContainerNetworkState(
                    network_name=(
                        "pyrange-status-lab-private-net"
                    ),
                    ip_address="172.28.20.20",
                ),
                ContainerNetworkState(
                    network_name=(
                        "pyrange-status-lab-public-net"
                    ),
                    ip_address="172.28.10.20",
                ),
            ),
        ),
    ]

    result = inspect_lab_status(scenario)

    assert result == LabStatus(
        scenario_name="status-lab",
        state="running",
        networks=(
            NetworkStatus(
                name="public-net",
                runtime_name=(
                    "pyrange-status-lab-public-net"
                ),
                state="matching",
                expected_subnet="172.28.10.0/24",
                actual_subnets=("172.28.10.0/24",),
            ),
            NetworkStatus(
                name="private-net",
                runtime_name=(
                    "pyrange-status-lab-private-net"
                ),
                state="matching",
                expected_subnet="172.28.20.0/24",
                actual_subnets=("172.28.20.0/24",),
            ),
        ),
        machines=(
            MachineStatus(
                name="web",
                runtime_name="pyrange-status-lab-web",
                state="running",
                container_state="running",
                interfaces=(
                    MachineInterfaceStatus(
                        network="public-net",
                        runtime_network=(
                            "pyrange-status-lab-public-net"
                        ),
                        state="matching",
                        expected_ip="172.28.10.10",
                        actual_ip="172.28.10.10",
                    ),
                ),
                unexpected_networks=(),
            ),
            MachineStatus(
                name="analyst",
                runtime_name=(
                    "pyrange-status-lab-analyst"
                ),
                state="running",
                container_state="running",
                interfaces=(
                    MachineInterfaceStatus(
                        network="public-net",
                        runtime_network=(
                            "pyrange-status-lab-public-net"
                        ),
                        state="matching",
                        expected_ip="172.28.10.20",
                        actual_ip="172.28.10.20",
                    ),
                    MachineInterfaceStatus(
                        network="private-net",
                        runtime_network=(
                            "pyrange-status-lab-private-net"
                        ),
                        state="matching",
                        expected_ip="172.28.20.20",
                        actual_ip="172.28.20.20",
                    ),
                ),
                unexpected_networks=(),
            ),
        ),
    )

    assert mock_inspect_network.call_args_list == [
        call("pyrange-status-lab-public-net"),
        call("pyrange-status-lab-private-net"),
    ]

    assert mock_inspect_container.call_args_list == [
        call("pyrange-status-lab-web"),
        call("pyrange-status-lab-analyst"),
    ]


@patch(
    "pyrange.engine.status.inspect_container_runtime"
)
@patch(
    "pyrange.engine.status.inspect_network_runtime"
)
def test_inspect_lab_status_returns_stopped_when_all_missing(
    mock_inspect_network,
    mock_inspect_container,
    scenario: ScenarioConfig,
) -> None:
    mock_inspect_network.return_value = None
    mock_inspect_container.return_value = None

    result = inspect_lab_status(scenario)

    assert result.state == "stopped"

    assert all(
        network.state == "missing"
        for network in result.networks
    )

    assert all(
        machine.state == "missing"
        for machine in result.machines
    )

    assert result.machines[0].interfaces[0].state == (
        "missing"
    )


@patch(
    "pyrange.engine.status.inspect_container_runtime"
)
@patch(
    "pyrange.engine.status.inspect_network_runtime"
)
def test_inspect_lab_status_returns_partial_when_machine_missing(
    mock_inspect_network,
    mock_inspect_container,
    scenario: ScenarioConfig,
) -> None:
    mock_inspect_network.side_effect = [
        NetworkRuntimeState(
            name="pyrange-status-lab-public-net",
            subnets=("172.28.10.0/24",),
        ),
        NetworkRuntimeState(
            name="pyrange-status-lab-private-net",
            subnets=("172.28.20.0/24",),
        ),
    ]

    mock_inspect_container.side_effect = [
        ContainerRuntimeState(
            name="pyrange-status-lab-web",
            status="running",
            networks=(
                ContainerNetworkState(
                    network_name=(
                        "pyrange-status-lab-public-net"
                    ),
                    ip_address="172.28.10.10",
                ),
            ),
        ),
        None,
    ]

    result = inspect_lab_status(scenario)

    assert result.state == "partial"
    assert result.machines[0].state == "running"
    assert result.machines[1].state == "missing"


@patch(
    "pyrange.engine.status.inspect_container_runtime"
)
@patch(
    "pyrange.engine.status.inspect_network_runtime"
)
def test_inspect_lab_status_preserves_stopped_container_state(
    mock_inspect_network,
    mock_inspect_container,
    scenario: ScenarioConfig,
) -> None:
    mock_inspect_network.side_effect = [
        NetworkRuntimeState(
            name="pyrange-status-lab-public-net",
            subnets=("172.28.10.0/24",),
        ),
        NetworkRuntimeState(
            name="pyrange-status-lab-private-net",
            subnets=("172.28.20.0/24",),
        ),
    ]

    mock_inspect_container.side_effect = [
        ContainerRuntimeState(
            name="pyrange-status-lab-web",
            status="exited",
            networks=(
                ContainerNetworkState(
                    network_name=(
                        "pyrange-status-lab-public-net"
                    ),
                    ip_address="172.28.10.10",
                ),
            ),
        ),
        ContainerRuntimeState(
            name="pyrange-status-lab-analyst",
            status="running",
            networks=(
                ContainerNetworkState(
                    network_name=(
                        "pyrange-status-lab-public-net"
                    ),
                    ip_address="172.28.10.20",
                ),
                ContainerNetworkState(
                    network_name=(
                        "pyrange-status-lab-private-net"
                    ),
                    ip_address="172.28.20.20",
                ),
            ),
        ),
    ]

    result = inspect_lab_status(scenario)

    assert result.state == "partial"

    web = result.machines[0]

    assert web.state == "stopped"
    assert web.container_state == "exited"


@patch(
    "pyrange.engine.status.inspect_container_runtime"
)
@patch(
    "pyrange.engine.status.inspect_network_runtime"
)
def test_inspect_lab_status_detects_network_subnet_drift(
    mock_inspect_network,
    mock_inspect_container,
    scenario: ScenarioConfig,
) -> None:
    mock_inspect_network.side_effect = [
        NetworkRuntimeState(
            name="pyrange-status-lab-public-net",
            subnets=("172.28.99.0/24",),
        ),
        NetworkRuntimeState(
            name="pyrange-status-lab-private-net",
            subnets=("172.28.20.0/24",),
        ),
    ]

    mock_inspect_container.return_value = None

    result = inspect_lab_status(scenario)

    assert result.state == "drifted"

    public = result.networks[0]

    assert public.state == "drifted"
    assert public.expected_subnet == "172.28.10.0/24"
    assert public.actual_subnets == ("172.28.99.0/24",)


@patch(
    "pyrange.engine.status.inspect_container_runtime"
)
@patch(
    "pyrange.engine.status.inspect_network_runtime"
)
def test_inspect_lab_status_detects_interface_ip_drift(
    mock_inspect_network,
    mock_inspect_container,
    scenario: ScenarioConfig,
) -> None:
    mock_inspect_network.return_value = None

    mock_inspect_container.side_effect = [
        ContainerRuntimeState(
            name="pyrange-status-lab-web",
            status="running",
            networks=(
                ContainerNetworkState(
                    network_name=(
                        "pyrange-status-lab-public-net"
                    ),
                    ip_address="172.28.10.99",
                ),
            ),
        ),
        None,
    ]

    result = inspect_lab_status(scenario)

    assert result.state == "drifted"

    web = result.machines[0]

    assert web.state == "drifted"
    assert web.interfaces[0].state == "drifted"
    assert web.interfaces[0].expected_ip == "172.28.10.10"
    assert web.interfaces[0].actual_ip == "172.28.10.99"


@patch(
    "pyrange.engine.status.inspect_container_runtime"
)
@patch(
    "pyrange.engine.status.inspect_network_runtime"
)
def test_inspect_lab_status_detects_missing_interface(
    mock_inspect_network,
    mock_inspect_container,
    scenario: ScenarioConfig,
) -> None:
    mock_inspect_network.return_value = None

    mock_inspect_container.side_effect = [
        None,
        ContainerRuntimeState(
            name="pyrange-status-lab-analyst",
            status="running",
            networks=(
                ContainerNetworkState(
                    network_name=(
                        "pyrange-status-lab-public-net"
                    ),
                    ip_address="172.28.10.20",
                ),
            ),
        ),
    ]

    result = inspect_lab_status(scenario)

    analyst = result.machines[1]

    assert result.state == "drifted"
    assert analyst.state == "drifted"
    assert analyst.interfaces[0].state == "matching"
    assert analyst.interfaces[1].state == "missing"
    assert analyst.interfaces[1].actual_ip is None


@patch(
    "pyrange.engine.status.inspect_container_runtime"
)
@patch(
    "pyrange.engine.status.inspect_network_runtime"
)
def test_inspect_lab_status_detects_unexpected_network(
    mock_inspect_network,
    mock_inspect_container,
    scenario: ScenarioConfig,
) -> None:
    mock_inspect_network.return_value = None

    mock_inspect_container.side_effect = [
        ContainerRuntimeState(
            name="pyrange-status-lab-web",
            status="running",
            networks=(
                ContainerNetworkState(
                    network_name=(
                        "pyrange-status-lab-public-net"
                    ),
                    ip_address="172.28.10.10",
                ),
                ContainerNetworkState(
                    network_name="unexpected-net",
                    ip_address="10.0.0.5",
                ),
            ),
        ),
        None,
    ]

    result = inspect_lab_status(scenario)

    web = result.machines[0]

    assert result.state == "drifted"
    assert web.state == "drifted"
    assert web.unexpected_networks == (
        "unexpected-net",
    )
