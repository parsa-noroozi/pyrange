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


@pytest.mark.integration
def test_basic_web_lab_lifecycle() -> None:
    try:
        get_docker_server_version()
    except DockerUnavailableError:
        pytest.skip("Docker Engine is unavailable")

    scenario = load_scenario(
        "scenarios/basic-web-lab.yaml"
    )
    scenario.name = f"integration-{uuid4().hex}"

    network_name = get_lab_network_name(
        scenario, next(item for item in scenario.networks if item.name == "lab-net")
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
            ["docker", "network", "inspect", network_name]
        )

        assert docker_resource_exists(
            ["docker", "container", "inspect", web_container]
        )

        assert docker_resource_exists(
            ["docker", "container", "inspect", analyst_container]
        )

    finally:
        try:
            stop_lab(scenario)
        except Exception:
            pass

    assert not docker_resource_exists(
        ["docker", "network", "inspect", network_name]
    )

    assert not docker_resource_exists(
        ["docker", "container", "inspect", web_container]
    )

    assert not docker_resource_exists(
        ["docker", "container", "inspect", analyst_container]
    )
