import json
import subprocess
from unittest.mock import call, patch

import pytest

from pyrange.engine.docker import (
    DockerOperationError,
    find_container_identity,
)


CONTAINER_ID = "a" * 64
OTHER_ID = "b" * 64

LIST_COMMAND = [
    "docker",
    "container",
    "ls",
    "--all",
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


def listing(name: str, resource_id: str = CONTAINER_ID) -> str:
    return json.dumps({
        "ID": resource_id,
        "Names": name,
    })


def inspection(resource_id: str = CONTAINER_ID) -> str:
    return json.dumps([
        {
            "Id": resource_id,
            "Config": {
                "Labels": {"pyrange.managed": "true"},
            },
        }
    ])


@patch("pyrange.engine.docker.subprocess.run")
def test_finds_exact_name_and_inspects_full_id(mock_run) -> None:
    mock_run.side_effect = [
        completed(
            listing("web-backup", OTHER_ID)
            + "\n"
            + listing("web")
        ),
        completed(inspection()),
    ]

    identity = find_container_identity("web")

    assert identity is not None
    assert identity.resource_id == CONTAINER_ID
    assert identity.labels == {"pyrange.managed": "true"}
    assert mock_run.call_args_list == [
        call(
            LIST_COMMAND,
            capture_output=True,
            text=True,
            check=True,
        ),
        call(
            ["docker", "container", "inspect", CONTAINER_ID],
            capture_output=True,
            text=True,
            check=True,
        ),
    ]


@pytest.mark.parametrize(
    "output",
    ["", listing("web-backup")],
)
@patch("pyrange.engine.docker.subprocess.run")
def test_returns_none_only_after_successful_lookup(
    mock_run,
    output,
) -> None:
    mock_run.return_value = completed(output)

    assert find_container_identity("web") is None
    mock_run.assert_called_once_with(
        LIST_COMMAND,
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
        json.dumps({"ID": "short", "Names": "web"}),
        json.dumps({"ID": CONTAINER_ID, "Names": None}),
        listing("web") + "\nnot-json",
    ],
)
@patch("pyrange.engine.docker.subprocess.run")
def test_rejects_malformed_listing(mock_run, output) -> None:
    mock_run.return_value = completed(output)

    with pytest.raises(DockerOperationError, match="listing data"):
        find_container_identity("web")

    assert mock_run.call_count == 1


@patch("pyrange.engine.docker.subprocess.run")
def test_rejects_ambiguous_name(mock_run) -> None:
    mock_run.return_value = completed(
        listing("web") + "\n" + listing("web", OTHER_ID)
    )

    with pytest.raises(DockerOperationError, match="ambiguous"):
        find_container_identity("web")

    assert mock_run.call_count == 1


@patch("pyrange.engine.docker.subprocess.run")
def test_list_failure_is_not_absence(mock_run) -> None:
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=LIST_COMMAND,
        stderr="list failed",
    )

    with pytest.raises(DockerOperationError, match="list failed"):
        find_container_identity("web")

    assert mock_run.call_count == 1


@patch("pyrange.engine.docker.subprocess.run")
def test_inspect_failure_is_not_absence(mock_run) -> None:
    mock_run.side_effect = [
        completed(listing("web")),
        subprocess.CalledProcessError(
            returncode=1,
            cmd=["docker", "container", "inspect", CONTAINER_ID],
            stderr="inspect failed",
        ),
    ]

    with pytest.raises(DockerOperationError, match="inspect failed"):
        find_container_identity("web")

    assert mock_run.call_count == 2


@patch("pyrange.engine.docker.subprocess.run")
def test_rejects_different_inspected_id(mock_run) -> None:
    mock_run.side_effect = [
        completed(listing("web")),
        completed(inspection(OTHER_ID)),
    ]

    with pytest.raises(DockerOperationError, match="different container ID"):
        find_container_identity("web")


@pytest.mark.parametrize(
    ("name", "error_type"),
    [
        (None, TypeError),
        ("", ValueError),
        (" web ", ValueError),
    ],
)
@patch("pyrange.engine.docker.subprocess.run")
def test_rejects_invalid_name_before_query(
    mock_run,
    name,
    error_type,
) -> None:
    with pytest.raises(error_type):
        find_container_identity(name)

    mock_run.assert_not_called()
