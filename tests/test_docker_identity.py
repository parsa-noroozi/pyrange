import json
import subprocess
from unittest.mock import patch

import pytest

from pyrange.engine.docker import (
    DockerOperationError,
    DockerUnavailableError,
    inspect_container_identity,
)


CONTAINER_ID = "a" * 64


def inspect_result(payload):
    return subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout=json.dumps(payload),
        stderr="",
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_reads_container_id_and_labels(mock_run) -> None:
    labels = {
        "pyrange.managed": "true",
        "pyrange.scenario.name": "school",
    }
    mock_run.return_value = inspect_result([
        {
            "Id": CONTAINER_ID,
            "Config": {"Labels": labels},
        }
    ])

    identity = inspect_container_identity("test-web")

    assert identity.resource_id == CONTAINER_ID
    assert identity.labels == labels
    mock_run.assert_called_once_with(
        ["docker", "container", "inspect", "test-web"],
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.mark.parametrize("config", [{}, {"Labels": None}])
@patch("pyrange.engine.docker.subprocess.run")
def test_preserves_missing_labels(mock_run, config) -> None:
    mock_run.return_value = inspect_result([
        {
            "Id": CONTAINER_ID,
            "Config": config,
        }
    ])

    identity = inspect_container_identity(CONTAINER_ID)

    assert identity.resource_id == CONTAINER_ID
    assert identity.labels is None


@pytest.mark.parametrize(
    "resource_id",
    [None, "", "short-id", "g" * 64, 123],
)
@patch("pyrange.engine.docker.subprocess.run")
def test_rejects_invalid_container_id(
    mock_run,
    resource_id,
) -> None:
    mock_run.return_value = inspect_result([
        {
            "Id": resource_id,
            "Config": {"Labels": {}},
        }
    ])

    with pytest.raises(DockerOperationError, match="identity data"):
        inspect_container_identity("test-web")


@pytest.mark.parametrize("config", [None, [], "invalid"])
@patch("pyrange.engine.docker.subprocess.run")
def test_rejects_invalid_config(mock_run, config) -> None:
    mock_run.return_value = inspect_result([
        {
            "Id": CONTAINER_ID,
            "Config": config,
        }
    ])

    with pytest.raises(DockerOperationError, match="identity data"):
        inspect_container_identity("test-web")


@pytest.mark.parametrize(
    "labels",
    [[], "invalid", {"pyrange.managed": True}],
)
@patch("pyrange.engine.docker.subprocess.run")
def test_rejects_malformed_labels(mock_run, labels) -> None:
    mock_run.return_value = inspect_result([
        {
            "Id": CONTAINER_ID,
            "Config": {"Labels": labels},
        }
    ])

    with pytest.raises(DockerOperationError, match="ownership labels"):
        inspect_container_identity("test-web")


@patch("pyrange.engine.docker.subprocess.run")
def test_accepts_empty_labels_without_claiming_ownership(mock_run) -> None:
    mock_run.return_value = inspect_result([
        {
            "Id": CONTAINER_ID,
            "Config": {"Labels": {}},
        }
    ])

    identity = inspect_container_identity("test-web")

    assert identity.labels == {}


@pytest.mark.parametrize("raw_output", ["not-json", "[]", "{}"])
@patch("pyrange.engine.docker.subprocess.run")
def test_rejects_invalid_inspection_output(
    mock_run,
    raw_output,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout=raw_output,
        stderr="",
    )

    with pytest.raises(DockerOperationError, match="inspection data"):
        inspect_container_identity("test-web")


@patch("pyrange.engine.docker.subprocess.run")
def test_query_failure_is_not_reported_as_absence(mock_run) -> None:
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["docker"],
        stderr="daemon query failed",
    )

    with pytest.raises(DockerOperationError, match="daemon query failed"):
        inspect_container_identity("test-web")


@patch("pyrange.engine.docker.subprocess.run")
def test_reports_missing_docker_cli(mock_run) -> None:
    mock_run.side_effect = FileNotFoundError()

    with pytest.raises(DockerUnavailableError, match="CLI was not found"):
        inspect_container_identity("test-web")
