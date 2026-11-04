import json
import subprocess
from unittest.mock import patch

import pytest

from pyrange.engine.docker import (
    DockerOperationError,
    DockerUnavailableError,
    inspect_network_identity,
)


NETWORK_ID = "c" * 64


def completed(payload) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout=json.dumps(payload),
        stderr="",
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_reads_network_id_and_top_level_labels(mock_run) -> None:
    labels = {
        "pyrange.managed": "true",
        "pyrange.scenario.name": "school",
    }
    mock_run.return_value = completed([
        {
            "Id": NETWORK_ID,
            "Labels": labels,
            "Config": {
                "Labels": {"wrong-location": "must-not-be-used"},
            },
        }
    ])

    identity = inspect_network_identity("test-net")

    assert identity.resource_id == NETWORK_ID
    assert identity.labels == labels
    mock_run.assert_called_once_with(
        ["docker", "network", "inspect", "test-net"],
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.mark.parametrize(
    "label_fields",
    [{}, {"Labels": None}, {"Labels": {}}],
)
@patch("pyrange.engine.docker.subprocess.run")
def test_preserves_missing_or_empty_labels(
    mock_run,
    label_fields,
) -> None:
    mock_run.return_value = completed([
        {
            "Id": NETWORK_ID,
            **label_fields,
        }
    ])

    identity = inspect_network_identity(NETWORK_ID)

    assert identity.resource_id == NETWORK_ID
    assert identity.labels == label_fields.get("Labels")


@pytest.mark.parametrize(
    "resource_id",
    [None, "", "short-id", "g" * 64, 123],
)
@patch("pyrange.engine.docker.subprocess.run")
def test_rejects_invalid_network_id(mock_run, resource_id) -> None:
    mock_run.return_value = completed([
        {"Id": resource_id, "Labels": {}}
    ])

    with pytest.raises(DockerOperationError, match="identity data"):
        inspect_network_identity("test-net")


@pytest.mark.parametrize(
    "labels",
    [[], "invalid", {"pyrange.managed": True}],
)
@patch("pyrange.engine.docker.subprocess.run")
def test_rejects_malformed_network_labels(mock_run, labels) -> None:
    mock_run.return_value = completed([
        {"Id": NETWORK_ID, "Labels": labels}
    ])

    with pytest.raises(DockerOperationError, match="ownership labels"):
        inspect_network_identity("test-net")


@pytest.mark.parametrize(
    "raw_output",
    [
        "not-json",
        "[]",
        "{}",
        "[null]",
        '[{"Id": "first"}, {"Id": "second"}]',
    ],
)
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
        inspect_network_identity("test-net")


@patch("pyrange.engine.docker.subprocess.run")
def test_query_failure_is_not_absence(mock_run) -> None:
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["docker"],
        stderr="network query failed",
    )

    with pytest.raises(DockerOperationError, match="network query failed"):
        inspect_network_identity("test-net")


@patch("pyrange.engine.docker.subprocess.run")
def test_reports_missing_docker_cli(mock_run) -> None:
    mock_run.side_effect = FileNotFoundError()

    with pytest.raises(DockerUnavailableError, match="CLI was not found"):
        inspect_network_identity("test-net")
