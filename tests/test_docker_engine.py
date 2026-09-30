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
