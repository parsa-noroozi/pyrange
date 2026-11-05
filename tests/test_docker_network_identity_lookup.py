import json
import subprocess
from unittest.mock import call, patch

import pytest

from pyrange.engine.docker import (
    DockerOperationError,
    find_network_identity,
)


NETWORK_ID = "c" * 64
OTHER_ID = "d" * 64

LIST_COMMAND = [
    "docker",
    "network",
    "ls",
    "--no-trunc",
    "--format",
    "{{json .}}",
]


def completed(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout=stdout,
        stderr="",
    )


def listing(name: str, resource_id: str = NETWORK_ID) -> str:
    return json.dumps({
        "ID": resource_id,
        "Name": name,
    })


def inspection(resource_id: str = NETWORK_ID) -> str:
    return json.dumps([
        {
            "Id": resource_id,
            "Labels": {"pyrange.managed": "true"},
        }
    ])


@patch("pyrange.engine.docker.subprocess.run")
def test_finds_exact_name_and_inspects_full_id(mock_run) -> None:
    mock_run.side_effect = [
        completed(
            listing("lab-net-backup", OTHER_ID)
            + "\n"
            + listing("lab-net")
        ),
        completed(inspection()),
    ]

    identity = find_network_identity("lab-net")

    assert identity is not None
    assert identity.resource_id == NETWORK_ID
    assert identity.labels == {"pyrange.managed": "true"}
    assert mock_run.call_args_list == [
        call(
            LIST_COMMAND,
            capture_output=True,
            text=True,
            check=True,
        ),
        call(
            ["docker", "network", "inspect", NETWORK_ID],
            capture_output=True,
            text=True,
            check=True,
        ),
    ]


@pytest.mark.parametrize(
    "output",
    ["", listing("lab-net-backup")],
)
@patch("pyrange.engine.docker.subprocess.run")
def test_returns_none_after_successful_lookup(mock_run, output) -> None:
    mock_run.return_value = completed(output)

    assert find_network_identity("lab-net") is None
    mock_run.assert_called_once_with(
        LIST_COMMAND,
        capture_output=True,
        text=True,
        check=True,
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_unrelated_swarm_network_does_not_block_lookup(mock_run) -> None:
    mock_run.side_effect = [
        completed(
            listing("unrelated-overlay", "xbtm0v4f1lfh7zjssmu8kd7xe")
            + "\n"
            + listing("lab-net")
        ),
        completed(inspection()),
    ]

    identity = find_network_identity("lab-net")

    assert identity is not None
    assert identity.resource_id == NETWORK_ID
    assert mock_run.call_args_list[1] == call(
        ["docker", "network", "inspect", NETWORK_ID],
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.mark.parametrize(
    "output",
    [
        "not-json",
        "[]",
        "{}",
        json.dumps({"ID": NETWORK_ID, "Name": None}),
        json.dumps({"ID": None, "Name": "lab-net"}),
        listing("lab-net") + "\nnot-json",
    ],
)
@patch("pyrange.engine.docker.subprocess.run")
def test_rejects_malformed_listing(mock_run, output) -> None:
    mock_run.return_value = completed(output)

    with pytest.raises(DockerOperationError, match="listing data"):
        find_network_identity("lab-net")

    assert mock_run.call_count == 1


@pytest.mark.parametrize("resource_id", ["short", "g" * 64])
@patch("pyrange.engine.docker.subprocess.run")
def test_rejects_invalid_selected_id(mock_run, resource_id) -> None:
    mock_run.return_value = completed(listing("lab-net", resource_id))

    with pytest.raises(DockerOperationError, match="network ID"):
        find_network_identity("lab-net")

    assert mock_run.call_count == 1


@patch("pyrange.engine.docker.subprocess.run")
def test_rejects_ambiguous_name(mock_run) -> None:
    mock_run.return_value = completed(
        listing("lab-net") + "\n" + listing("lab-net", OTHER_ID)
    )

    with pytest.raises(DockerOperationError, match="ambiguous"):
        find_network_identity("lab-net")

    assert mock_run.call_count == 1


@patch("pyrange.engine.docker.subprocess.run")
def test_list_failure_is_not_absence(mock_run) -> None:
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=LIST_COMMAND,
        stderr="list failed",
    )

    with pytest.raises(DockerOperationError, match="list failed"):
        find_network_identity("lab-net")

    assert mock_run.call_count == 1


@patch("pyrange.engine.docker.subprocess.run")
def test_inspect_failure_is_not_absence(mock_run) -> None:
    mock_run.side_effect = [
        completed(listing("lab-net")),
        subprocess.CalledProcessError(
            returncode=1,
            cmd=["docker", "network", "inspect", NETWORK_ID],
            stderr="inspect failed",
        ),
    ]

    with pytest.raises(DockerOperationError, match="inspect failed"):
        find_network_identity("lab-net")

    assert mock_run.call_count == 2


@patch("pyrange.engine.docker.subprocess.run")
def test_rejects_different_inspected_id(mock_run) -> None:
    mock_run.side_effect = [
        completed(listing("lab-net")),
        completed(inspection(OTHER_ID)),
    ]

    with pytest.raises(DockerOperationError, match="different network ID"):
        find_network_identity("lab-net")


@pytest.mark.parametrize(
    ("name", "error_type"),
    [
        (None, TypeError),
        ("", ValueError),
        (" lab-net ", ValueError),
    ],
)
@patch("pyrange.engine.docker.subprocess.run")
def test_rejects_invalid_name_before_query(
    mock_run,
    name,
    error_type,
) -> None:
    with pytest.raises(error_type):
        find_network_identity(name)

    mock_run.assert_not_called()
