from uuid import uuid4

import pytest

from pyrange.engine import (
    DockerUnavailableError,
    get_docker_server_version,
    inspect_lab_status,
    start_lab,
    stop_lab,
)
from pyrange.models import (
    MachineConfig,
    NetworkConfig,
    NetworkInterfaceConfig,
    ScenarioConfig,
)


@pytest.mark.integration
def test_runtime_status_tracks_real_lab_lifecycle() -> None:
    try:
        get_docker_server_version()
    except DockerUnavailableError:
        pytest.skip("Docker Engine is unavailable")

    scenario = ScenarioConfig(
        name=f"status-integration-{uuid4().hex[:8]}",
        networks=[
            NetworkConfig(
                name="public-net",
                subnet="10.254.252.0/28",
            ),
            NetworkConfig(
                name="private-net",
                subnet="10.254.252.16/28",
            ),
        ],
        machines=[
            MachineConfig(
                name="web",
                image="nginx:alpine",
                interfaces=[
                    NetworkInterfaceConfig(
                        network="public-net",
                        ip="10.254.252.2",
                    )
                ],
            ),
            MachineConfig(
                name="analyst",
                image="nginx:alpine",
                interfaces=[
                    NetworkInterfaceConfig(
                        network="public-net",
                        ip="10.254.252.3",
                    ),
                    NetworkInterfaceConfig(
                        network="private-net",
                        ip="10.254.252.18",
                    ),
                ],
            ),
        ],
    )

    try:
        initial_status = inspect_lab_status(scenario)

        assert initial_status.state == "stopped"
        assert all(
            network.state == "missing"
            for network in initial_status.networks
        )
        assert all(
            machine.state == "missing"
            for machine in initial_status.machines
        )

        start_lab(scenario)

        running_status = inspect_lab_status(scenario)

        assert running_status.state == "running"

        assert [
            network.state
            for network in running_status.networks
        ] == [
            "matching",
            "matching",
        ]

        assert [
            network.actual_subnets
            for network in running_status.networks
        ] == [
            ("10.254.252.0/28",),
            ("10.254.252.16/28",),
        ]

        web = running_status.machines[0]
        analyst = running_status.machines[1]

        assert web.state == "running"
        assert web.container_state == "running"
        assert web.interfaces[0].state == "matching"
        assert web.interfaces[0].actual_ip == (
            "10.254.252.2"
        )
        assert web.unexpected_networks == ()

        assert analyst.state == "running"
        assert analyst.container_state == "running"

        assert [
            interface.state
            for interface in analyst.interfaces
        ] == [
            "matching",
            "matching",
        ]

        assert [
            interface.actual_ip
            for interface in analyst.interfaces
        ] == [
            "10.254.252.3",
            "10.254.252.18",
        ]

        assert analyst.unexpected_networks == ()

        stop_lab(scenario)

        stopped_status = inspect_lab_status(scenario)

        assert stopped_status.state == "stopped"

        assert all(
            network.state == "missing"
            for network in stopped_status.networks
        )

        assert all(
            machine.state == "missing"
            for machine in stopped_status.machines
        )

        assert all(
            interface.state == "missing"
            for machine in stopped_status.machines
            for interface in machine.interfaces
        )

    finally:
        try:
            stop_lab(scenario)
        except Exception:
            pass
