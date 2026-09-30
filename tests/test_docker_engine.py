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


@patch("pyrange.engine.docker.subprocess.run")
def test_create_container_returns_container_id(mock_run) -> None:
    from pyrange.engine import create_container

    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="container123\n",
        stderr="",
    )

    container_id = create_container(
        "test-web",
        "nginx:alpine",
        "test-net",
        "172.28.10.10",
    )

    assert container_id == "container123"

    mock_run.assert_called_once_with(
        [
            "docker",
            "create",
            "--name",
            "test-web",
            "--network",
            "test-net",
            "--ip",
            "172.28.10.10",
            "--label",
            "pyrange.managed=true",
            "nginx:alpine",
        ],
        capture_output=True,
        text=True,
        check=True,
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_create_container_raises_on_docker_error(mock_run) -> None:
    from pyrange.engine import DockerOperationError, create_container

    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["docker"],
        stderr="container already exists",
    )

    with pytest.raises(
        DockerOperationError,
        match="container already exists",
    ):
        create_container(
            "test-web",
            "nginx:alpine",
            "test-net",
            "172.28.10.10",
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_create_container_rejects_empty_container_id(mock_run) -> None:
    from pyrange.engine import DockerOperationError, create_container

    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="",
        stderr="",
    )

    with pytest.raises(
        DockerOperationError,
        match="empty container ID",
    ):
        create_container(
            "test-web",
            "nginx:alpine",
            "test-net",
            "172.28.10.10",
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_start_container_runs_docker_command(mock_run) -> None:
    from pyrange.engine import start_container

    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="test-web\n",
        stderr="",
    )

    start_container("test-web")

    mock_run.assert_called_once_with(
        ["docker", "start", "test-web"],
        capture_output=True,
        text=True,
        check=True,
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_start_container_raises_on_docker_error(mock_run) -> None:
    from pyrange.engine import DockerOperationError, start_container

    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["docker"],
        stderr="failed to start container",
    )

    with pytest.raises(
        DockerOperationError,
        match="failed to start container",
    ):
        start_container("test-web")


@patch("pyrange.engine.docker.subprocess.run")
def test_remove_container_runs_docker_command(mock_run) -> None:
    from pyrange.engine import remove_container

    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="test-web\n",
        stderr="",
    )

    remove_container("test-web")

    mock_run.assert_called_once_with(
        ["docker", "rm", "--force", "test-web"],
        capture_output=True,
        text=True,
        check=True,
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_remove_container_raises_on_docker_error(mock_run) -> None:
    from pyrange.engine import DockerOperationError, remove_container

    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["docker"],
        stderr="container not found",
    )

    with pytest.raises(
        DockerOperationError,
        match="container not found",
    ):
        remove_container("test-web")
