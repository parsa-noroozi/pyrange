import json
import subprocess

import pytest

from pyrange.core import load_scenario
from pyrange.engine import (
    DockerUnavailableError,
    get_docker_server_version,
    start_lab,
    stop_lab,
)


def docker_resource_exists(command: list[str]) -> bool:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def inspect_container_networks(
    container_name: str,
) -> dict[str, dict]:
    result = subprocess.run(
        [
            "docker",
            "container",
            "inspect",
            container_name,
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)

    return data[0]["NetworkSettings"]["Networks"]


@pytest.mark.integration
def test_segmented_lab_multi_network_lifecycle() -> None:
    try:
        get_docker_server_version()
    except DockerUnavailableError:
        pytest.skip("Docker Engine is unavailable")

    scenario = load_scenario(
        "scenarios/segmented-lab.yaml"
    )

    public_network = (
        "pyrange-v2-network-"
        "e766ac61206c7ae3d71571ae1872401af69f7d756d5e2d1c52b6e99a8d7dda8d"
    )
    private_network = (
        "pyrange-v2-network-"
        "9b692d460dc781424b243d45281ac928e348d8f82fc6266ed6bf44477bec2027"
    )
    web_container = (
        "pyrange-v2-container-"
        "12ac3acb9b451ad60efb6ba7e0fda1ce7ddf48c60ec26104388a769622d55d8c"
    )
    analyst_container = (
        "pyrange-v2-container-"
        "9570b0024cb6a01a4921131433a5dc16830e6ea15fe4ba55b1c94c3298d37427"
    )

    try:
        start_lab(scenario)

        assert docker_resource_exists(
            [
                "docker",
                "network",
                "inspect",
                public_network,
            ]
        )

        assert docker_resource_exists(
            [
                "docker",
                "network",
                "inspect",
                private_network,
            ]
        )

        web_networks = inspect_container_networks(
            web_container
        )

        analyst_networks = inspect_container_networks(
            analyst_container
        )

        assert set(web_networks) == {
            public_network,
        }

        assert (
            web_networks[public_network]["IPAddress"]
            == "172.28.20.10"
        )

        assert set(analyst_networks) == {
            public_network,
            private_network,
        }

        assert (
            analyst_networks[public_network]["IPAddress"]
            == "172.28.20.20"
        )

        assert (
            analyst_networks[private_network]["IPAddress"]
            == "172.28.30.20"
        )

    finally:
        try:
            stop_lab(scenario)
        except Exception:
            pass

    assert not docker_resource_exists(
        [
            "docker",
            "network",
            "inspect",
            public_network,
        ]
    )

    assert not docker_resource_exists(
        [
            "docker",
            "network",
            "inspect",
            private_network,
        ]
    )

    assert not docker_resource_exists(
        [
            "docker",
            "container",
            "inspect",
            web_container,
        ]
    )

    assert not docker_resource_exists(
        [
            "docker",
            "container",
            "inspect",
            analyst_container,
        ]
    )
