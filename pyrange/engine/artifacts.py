from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from pyrange.engine.execution import ExecutionContext


class ArtifactError(RuntimeError):
    """Raised when run artifact organization fails."""


@dataclass(frozen=True)
class RunArtifacts:
    """Filesystem locations reserved for one execution run."""

    run_id: UUID
    directory: Path
    telemetry_log: Path


def prepare_run_artifacts(
    root: str | Path,
    context: ExecutionContext,
) -> RunArtifacts:
    """Create an isolated artifact directory for one run."""

    root_path = Path(root)
    run_directory = (
        root_path / str(context.run_id)
    )

    try:
        run_directory.mkdir(
            parents=True,
            exist_ok=False,
        )
    except FileExistsError as exc:
        if run_directory.is_dir():
            raise ArtifactError(
                "Artifact directory already exists for "
                f"run '{context.run_id}': "
                f"'{run_directory}'."
            ) from exc

        raise ArtifactError(
            "Failed to prepare artifact directory "
            f"'{run_directory}': {exc}"
        ) from exc
    except OSError as exc:
        raise ArtifactError(
            "Failed to prepare artifact directory "
            f"'{run_directory}': {exc}"
        ) from exc

    return RunArtifacts(
        run_id=context.run_id,
        directory=run_directory,
        telemetry_log=(
            run_directory / "telemetry.jsonl"
        ),
    )
