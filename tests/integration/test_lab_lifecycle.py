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


@pytest.mark.integration
def test_basic_web_lab_lifecycle() -> None:
    try:
        get_docker_server_version()
    except DockerUnavailableError:
        pytest.skip("Docker Engine is unavailable")

    scenario = load_scenario(
        "scenarios/basic-web-lab.yaml"
    )

    network_name = (
        "pyrange-v2-network-"
        "5b70c90f2ef42c0bbb53ef371a3eb36f92f8e085d658aca24c9b24abb885b289"
    )
    web_container = (
        "pyrange-v2-container-"
        "3969cf8bdfdea9ed8848e1d514f1e25788f90a81a7a2f918fe961a4588b318f5"
    )
    analyst_container = (
        "pyrange-v2-container-"
        "fe292e84433c0f01d4f2189d4fd9a6bb1d88425965cbf530798c472fe4707c54"
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
