import subprocess
from unittest.mock import patch

import pytest

from pyrange.engine import (
    DockerUnavailableError,
    get_docker_server_version,
)


@patch("pyrange.engine.docker.subprocess.run")
def test_returns_docker_server_version(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="29.0.0\n",
        stderr="",
    )

    version = get_docker_server_version()

    assert version == "29.0.0"


@patch("pyrange.engine.docker.subprocess.run")
def test_raises_when_docker_cli_is_missing(mock_run) -> None:
    mock_run.side_effect = FileNotFoundError

    with pytest.raises(
        DockerUnavailableError,
        match="Docker CLI was not found",
    ):
        get_docker_server_version()


@patch("pyrange.engine.docker.subprocess.run")
def test_raises_when_docker_engine_is_unavailable(mock_run) -> None:
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["docker"],
        stderr="Cannot connect to the Docker daemon",
    )

    with pytest.raises(
        DockerUnavailableError,
        match="Cannot connect to the Docker daemon",
    ):
        get_docker_server_version()


@patch("pyrange.engine.docker.subprocess.run")
def test_rejects_empty_server_version(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="",
        stderr="",
    )

    with pytest.raises(
        DockerUnavailableError,
        match="empty server version",
    ):
        get_docker_server_version()


@patch("pyrange.engine.docker.subprocess.run")
def test_create_network_returns_network_id(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="abc123\n",
        stderr="",
    )

    from pyrange.engine import create_network

    network_id = create_network(
        "test-net",
        "172.28.10.0/24",
    )

    assert network_id == "abc123"

    mock_run.assert_called_once_with(
        [
            "docker",
            "network",
            "create",
            "--driver",
            "bridge",
            "--subnet",
            "172.28.10.0/24",
            "--internal",
            "test-net",
        ],
        capture_output=True,
        text=True,
        check=True,
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_create_network_raises_on_docker_error(mock_run) -> None:
    from pyrange.engine import DockerOperationError, create_network

    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["docker"],
        stderr="network already exists",
    )

    with pytest.raises(
        DockerOperationError,
        match="network already exists",
    ):
        create_network(
            "test-net",
            "172.28.10.0/24",
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_create_network_rejects_empty_network_id(mock_run) -> None:
    from pyrange.engine import DockerOperationError, create_network

    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="",
        stderr="",
    )

    with pytest.raises(
        DockerOperationError,
        match="empty network ID",
    ):
        create_network(
            "test-net",
            "172.28.10.0/24",
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_remove_network_runs_docker_command(mock_run) -> None:
    from pyrange.engine import remove_network

    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="test-net\n",
        stderr="",
    )

    remove_network("test-net")

    mock_run.assert_called_once_with(
        ["docker", "network", "rm", "test-net"],
        capture_output=True,
        text=True,
        check=True,
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_remove_network_raises_on_docker_error(mock_run) -> None:
    from pyrange.engine import DockerOperationError, remove_network

    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["docker"],
        stderr="network not found",
    )

    with pytest.raises(
        DockerOperationError,
        match="network not found",
    ):
        remove_network("test-net")
