import subprocess
from unittest.mock import patch

import pytest

from pyrange.engine.docker import create_container


@patch("pyrange.engine.docker.subprocess.run")
def test_create_container_passes_labels_as_arguments(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="container123\n",
        stderr="",
    )
    labels = {
        "pyrange.resource.kind": "container",
        "description": "lab one = local",
    }

    container_id = create_container(
        "test-web",
        "nginx:alpine",
        "test-net",
        "172.28.10.10",
        labels=labels,
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
            "description=lab one = local",
            "--label",
            "pyrange.managed=true",
            "--label",
            "pyrange.resource.kind=container",
            "nginx:alpine",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert labels == {
        "pyrange.resource.kind": "container",
        "description": "lab one = local",
    }


@pytest.mark.parametrize("labels", [None, {}])
@patch("pyrange.engine.docker.subprocess.run")
def test_create_container_preserves_default_label(
    mock_run,
    labels,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="container123\n",
        stderr="",
    )

    create_container(
        "test-web",
        "nginx:alpine",
        "test-net",
        "172.28.10.10",
        labels=labels,
    )

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
