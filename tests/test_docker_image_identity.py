import json
import subprocess
from unittest.mock import call, patch

import pytest

from pyrange.engine.docker import (
    DockerOperationError, DockerUnavailableError,
    create_container_snapshot, find_image_identity, inspect_image_identity,
)

IMAGE_ID = "sha256:" + "a" * 64
OTHER_ID = "sha256:" + "b" * 64
LIST = ["docker", "image", "ls", "--all", "--no-trunc", "--format", "{{json .}}"]


def completed(value):
    return subprocess.CompletedProcess([], 0, stdout=value, stderr="")


def row(repository="repo", tag="checkpoint", identity=IMAGE_ID):
    return json.dumps({"Repository": repository, "Tag": tag, "ID": identity})


def inspected(identity=IMAGE_ID, labels=None):
    return json.dumps([{"Id": identity, "Config": {"Labels": labels}}])


@patch("pyrange.engine.docker.subprocess.run")
def test_exact_tag_lookup_inspects_pinned_image_id(mock_run):
    mock_run.side_effect = [completed(row(tag="other") + "\n" + row()), completed(inspected(labels={"owner": "lab"}))]
    result = find_image_identity("repo:checkpoint")
    assert result.resource_id == IMAGE_ID
    assert result.labels == {"owner": "lab"}
    assert mock_run.call_args_list == [
        call(LIST, capture_output=True, text=True, check=True),
        call(["docker", "image", "inspect", IMAGE_ID], capture_output=True, text=True, check=True),
    ]


@pytest.mark.parametrize("output", ["", row(tag="checkpoint-backup"), row(repository="other")])
@patch("pyrange.engine.docker.subprocess.run")
def test_missing_exact_reference_returns_none(mock_run, output):
    mock_run.return_value = completed(output)
    assert find_image_identity("repo:checkpoint") is None
    assert mock_run.call_count == 1


@pytest.mark.parametrize("output", ["not-json", "[]", "{}", row(identity="short"), row()+"\nnot-json", row()+"\n"+row(identity=OTHER_ID)])
@patch("pyrange.engine.docker.subprocess.run")
def test_invalid_or_ambiguous_listing_cannot_be_absence(mock_run, output):
    mock_run.return_value = completed(output)
    with pytest.raises(DockerOperationError):
        find_image_identity("repo:checkpoint")
    assert mock_run.call_count == 1


@patch("pyrange.engine.docker.subprocess.run")
def test_different_inspected_id_is_rejected(mock_run):
    mock_run.side_effect = [completed(row()), completed(inspected(identity=OTHER_ID))]
    with pytest.raises(DockerOperationError, match="different image ID"):
        find_image_identity("repo:checkpoint")


@pytest.mark.parametrize("stage", ["list", "inspect"])
@patch("pyrange.engine.docker.subprocess.run")
def test_query_failure_is_not_absence(mock_run, stage):
    error = subprocess.CalledProcessError(1, ["docker"], stderr="query failed")
    mock_run.side_effect = error if stage == "list" else [completed(row()), error]
    with pytest.raises(DockerOperationError, match="query failed"):
        find_image_identity("repo:checkpoint")


@pytest.mark.parametrize("payload", [
    [], {}, [{"Id": IMAGE_ID}], [{"Id": "short", "Config": {}}],
    [{"Id": IMAGE_ID, "Config": {"Labels": []}}],
    [{"Id": IMAGE_ID, "Config": {"Labels": {"owner": True}}}],
])
@patch("pyrange.engine.docker.subprocess.run")
def test_malformed_inspection_is_rejected(mock_run, payload):
    mock_run.return_value = completed(json.dumps(payload))
    with pytest.raises(DockerOperationError):
        inspect_image_identity(IMAGE_ID)


@pytest.mark.parametrize("labels", [None, {}, {"owner": "lab"}])
@patch("pyrange.engine.docker.subprocess.run")
def test_image_inspection_preserves_labels(mock_run, labels):
    mock_run.return_value = completed(inspected(labels=labels))
    assert inspect_image_identity(IMAGE_ID).labels == labels


@patch("pyrange.engine.docker.subprocess.run")
def test_missing_cli_is_reported(mock_run):
    mock_run.side_effect = FileNotFoundError()
    with pytest.raises(DockerUnavailableError):
        find_image_identity("repo:checkpoint")


@patch("pyrange.engine.docker.subprocess.run")
def test_snapshot_commit_passes_literal_label_changes(mock_run):
    mock_run.return_value = completed(IMAGE_ID)
    labels = {"pyrange.resource.kind": "snapshot", "description": 'price $HOME "quoted" \\path'}
    assert create_container_snapshot("a" * 64, "repo:checkpoint", labels=labels) == IMAGE_ID
    mock_run.assert_called_once_with(
        ["docker", "commit", "--change", 'LABEL description="price \\$HOME \\"quoted\\" \\\\path"',
         "--change", 'LABEL pyrange.resource.kind="snapshot"', "a" * 64, "repo:checkpoint"],
        capture_output=True, text=True, check=True,
    )
    assert labels["description"] == 'price $HOME "quoted" \\path'


@pytest.mark.parametrize("labels", [{"bad key": "x"}, {"ok": "x\ny"}, {"ok": "x\r"}, {"ok": "\x00"}, {"ok": 123}])
@patch("pyrange.engine.docker.subprocess.run")
def test_invalid_snapshot_labels_rejected_before_docker(mock_run, labels):
    with pytest.raises(ValueError):
        create_container_snapshot("a" * 64, "repo:checkpoint", labels=labels)
    mock_run.assert_not_called()
