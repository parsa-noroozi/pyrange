import subprocess
from unittest.mock import patch

import pytest

from pyrange.engine.docker import create_network


@patch("pyrange.engine.docker.subprocess.run")
def test_create_network_passes_labels_as_arguments(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="network123\n",
        stderr="",
    )

    labels = {
        "pyrange.managed": "true",
        "description": "lab one = local",
    }

    network_id = create_network(
        "test-net",
        "172.28.10.0/24",
        labels=labels,
    )

    assert network_id == "network123"

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
            "--label",
            "description=lab one = local",
            "--label",
            "pyrange.managed=true",
            "test-net",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert labels == {
        "pyrange.managed": "true",
        "description": "lab one = local",
    }


@pytest.mark.parametrize("labels", [None, {}])
@patch("pyrange.engine.docker.subprocess.run")
def test_create_network_preserves_command_without_labels(
    mock_run,
    labels,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="network123\n",
        stderr="",
    )

    create_network(
        "test-net",
        "172.28.10.0/24",
        labels=labels,
    )

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
