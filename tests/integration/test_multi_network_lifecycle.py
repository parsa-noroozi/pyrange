import json
import subprocess
from uuid import uuid4

import pytest

from pyrange.core import load_scenario
from pyrange.engine.docker import find_container_identity, find_network_identity
from pyrange.engine import (
    DockerUnavailableError,
    get_docker_server_version,
    get_lab_container_name,
    get_lab_network_name,
    start_lab,
    stop_lab,
)


def docker_resource_exists(command: list[str]) -> bool:
    # A failed query must not be accepted as proof of successful cleanup.
    if len(command) != 4:
        raise ValueError("Expected an inspect command with one resource name")
    if command[:3] == ["docker", "container", "inspect"]:
        return find_container_identity(command[3]) is not None
    if command[:3] == ["docker", "network", "inspect"]:
        return find_network_identity(command[3]) is not None
    raise ValueError("Unsupported resource inspection command")


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
    scenario.name = f"integration-{uuid4().hex}"

    public_network = get_lab_network_name(
        scenario, next(item for item in scenario.networks if item.name == "public-net")
    )
    private_network = get_lab_network_name(
        scenario, next(item for item in scenario.networks if item.name == "private-net")
    )
    web_container = get_lab_container_name(
        scenario, next(item for item in scenario.machines if item.name == "web")
    )
    analyst_container = get_lab_container_name(
        scenario, next(item for item in scenario.machines if item.name == "analyst")
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
