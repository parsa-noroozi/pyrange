import subprocess
from unittest.mock import patch

import pytest

from pyrange.engine import (
    ContainerCommandResult,
    DockerOperationError,
    DockerUnavailableError,
    connect_container_to_network,
    execute_container_command,
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


def test_connect_container_to_network_success() -> None:
    with patch(
        "pyrange.engine.docker.subprocess.run"
    ) as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""

        connect_container_to_network(
            name="pyrange-test-web",
            network="pyrange-test-private",
            ip="172.28.20.10",
        )

        mock_run.assert_called_once_with(
            [
                "docker",
                "network",
                "connect",
                "--ip",
                "172.28.20.10",
                "pyrange-test-private",
                "pyrange-test-web",
            ],
            capture_output=True,
            text=True,
        )


def test_connect_container_to_network_error() -> None:
    with patch(
        "pyrange.engine.docker.subprocess.run"
    ) as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = (
            "failed to connect container"
        )

        with pytest.raises(
            DockerOperationError,
            match="failed to connect container",
        ):
            connect_container_to_network(
                name="pyrange-test-web",
                network="pyrange-test-private",
                ip="172.28.20.10",
            )
            
            
@patch("pyrange.engine.docker.subprocess.run")
def test_execute_container_command_returns_result(
    mock_run,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="healthy\n",
        stderr="",
    )

    result = execute_container_command(
        name="test-web",
        command=["wget", "--spider", "http://127.0.0.1"],
        timeout_seconds=2.0,
    )

    assert result == ContainerCommandResult(
        exit_code=0,
        stdout="healthy\n",
        stderr="",
    )

    mock_run.assert_called_once_with(
        [
            "docker",
            "exec",
            "test-web",
            "wget",
            "--spider",
            "http://127.0.0.1",
        ],
        capture_output=True,
        text=True,
        timeout=2.0,
        check=False,
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_execute_container_command_preserves_failure(
    mock_run,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=1,
        stdout="",
        stderr="service unavailable\n",
    )

    result = execute_container_command(
        name="test-web",
        command=["health-check"],
        timeout_seconds=2.0,
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == "service unavailable\n"


@patch("pyrange.engine.docker.subprocess.run")
def test_execute_container_command_raises_on_timeout(
    mock_run,
) -> None:
    mock_run.side_effect = subprocess.TimeoutExpired(
        cmd=["docker", "exec"],
        timeout=2.0,
    )

    with pytest.raises(
        DockerOperationError,
        match="Command timed out",
    ):
        execute_container_command(
            name="test-web",
            command=["health-check"],
            timeout_seconds=2.0,
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_execute_container_command_raises_when_cli_missing(
    mock_run,
) -> None:
    mock_run.side_effect = FileNotFoundError

    with pytest.raises(
        DockerUnavailableError,
        match="Docker CLI was not found",
    ):
        execute_container_command(
            name="test-web",
            command=["health-check"],
            timeout_seconds=2.0,
        )


def test_execute_container_command_rejects_empty_command() -> None:
    with pytest.raises(
        ValueError,
        match="command must not be empty",
    ):
        execute_container_command(
            name="test-web",
            command=[],
            timeout_seconds=2.0,
        )
