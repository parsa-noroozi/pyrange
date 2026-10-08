from pathlib import Path
from uuid import UUID

import pytest

from pyrange.engine.artifacts import (
    ArtifactError,
    prepare_run_artifacts,
)
from pyrange.engine.execution import ExecutionContext


def test_prepare_run_artifacts_creates_run_directory(
    tmp_path: Path,
) -> None:
    run_id = UUID(
        "11111111-1111-4111-8111-111111111111"
    )

    context = ExecutionContext(
        run_id=run_id,
        scenario="test-lab",
        operation="telemetry",
    )

    artifact_root = tmp_path / "artifacts"

    artifacts = prepare_run_artifacts(
        artifact_root,
        context,
    )

    assert artifacts.run_id == run_id
    assert artifacts.directory == (
        artifact_root / str(run_id)
    )
    assert artifacts.directory.is_dir()

    assert artifacts.telemetry_log == (
        artifacts.directory
        / "telemetry.jsonl"
    )

    assert not artifacts.telemetry_log.exists()


def test_prepare_run_artifacts_separates_runs(
    tmp_path: Path,
) -> None:
    first_context = ExecutionContext(
        run_id=UUID(
            "11111111-1111-4111-8111-111111111111"
        ),
        scenario="test-lab",
        operation="telemetry",
    )
    second_context = ExecutionContext(
        run_id=UUID(
            "22222222-2222-4222-8222-222222222222"
        ),
        scenario="test-lab",
        operation="telemetry",
    )

    first = prepare_run_artifacts(
        tmp_path,
        first_context,
    )
    second = prepare_run_artifacts(
        tmp_path,
        second_context,
    )

    assert first.directory != second.directory
    assert first.telemetry_log != second.telemetry_log

    assert first.directory.is_dir()
    assert second.directory.is_dir()


def test_prepare_run_artifacts_rejects_existing_run_directory(
    tmp_path: Path,
) -> None:
    run_id = UUID(
        "11111111-1111-4111-8111-111111111111"
    )

    context = ExecutionContext(
        run_id=run_id,
        scenario="test-lab",
        operation="telemetry",
    )

    existing_directory = (
        tmp_path / str(run_id)
    )
    existing_directory.mkdir()

    marker = existing_directory / "marker.txt"
    marker.write_text(
        "preserve",
        encoding="utf-8",
    )

    with pytest.raises(
        ArtifactError,
        match="already exists",
    ):
        prepare_run_artifacts(
            tmp_path,
            context,
        )

    assert marker.read_text(
        encoding="utf-8"
    ) == "preserve"


def test_prepare_run_artifacts_reports_creation_failure(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"

    artifact_root.write_text(
        "not a directory",
        encoding="utf-8",
    )

    context = ExecutionContext(
        scenario="test-lab",
        operation="telemetry",
    )

    with pytest.raises(
        ArtifactError,
        match="Failed to prepare artifact directory",
    ):
        prepare_run_artifacts(
            artifact_root,
            context,
        )
