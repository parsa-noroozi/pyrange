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

    network_name = "pyrange-basic-web-lab-lab-net"
    web_container = "pyrange-basic-web-lab-web"
    analyst_container = "pyrange-basic-web-lab-analyst"

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
