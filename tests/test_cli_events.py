import json
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest
from typer.testing import CliRunner

from pyrange.cli import app
from pyrange.engine import (
    EventRecorder,
    JsonlEventSink,
    MachineRestoreResult,
    MachineSnapshot,
)
from pyrange.models import (
    MachineConfig,
    NetworkConfig,
    NetworkInterfaceConfig,
    ScenarioConfig,
)


runner = CliRunner()


def make_test_scenario() -> ScenarioConfig:
    return ScenarioConfig(
        name="cli-lab",
        networks=[
            NetworkConfig(
                name="cli-net",
                subnet="172.28.40.0/24",
            )
        ],
        machines=[
            MachineConfig(
                name="web",
                image="nginx:alpine",
                interfaces=[
                    NetworkInterfaceConfig(
                        network="cli-net",
                        ip="172.28.40.10",
                    )
                ],
            )
        ],
    )


@pytest.mark.parametrize(
    (
        "command",
        "operation",
        "target",
    ),
    [
        (
            [
                "start",
                "scenario.yaml",
            ],
            "start",
            "start_lab",
        ),
        (
            [
                "stop",
                "scenario.yaml",
            ],
            "stop",
            "stop_lab",
        ),
        (
            [
                "snapshot",
                "scenario.yaml",
                "web",
                "checkpoint-1",
            ],
            "snapshot",
            "create_machine_snapshot",
        ),
        (
            [
                "restore",
                "scenario.yaml",
                "web",
                "checkpoint-1",
            ],
            "restore",
            "restore_machine_snapshot",
        ),
    ],
)
def test_event_log_option_passes_execution_recorder(
    tmp_path: Path,
    command: list[str],
    operation: str,
    target: str,
) -> None:
    scenario = make_test_scenario()
    event_log = (
        tmp_path / f"{operation}.jsonl"
    )

    with (
        patch(
            "pyrange.cli.load_scenario",
            return_value=scenario,
        ),
        patch(
            f"pyrange.cli.{target}"
        ) as mock_operation,
    ):
        if target == "create_machine_snapshot":
            mock_operation.return_value = (
                MachineSnapshot(
                    snapshot_name="checkpoint-1",
                    machine_name="web",
                    container_name=(
                        "pyrange-cli-lab-web"
                    ),
                    image_ref=(
                        "pyrange-snapshots/"
                        "cli-lab-web:checkpoint-1"
                    ),
                    image_id="sha256:snapshot123",
                )
            )

        if target == "restore_machine_snapshot":
            mock_operation.return_value = (
                MachineRestoreResult(
                    snapshot_name="checkpoint-1",
                    machine_name="web",
                    container_name=(
                        "pyrange-cli-lab-web"
                    ),
                    image_ref=(
                        "pyrange-snapshots/"
                        "cli-lab-web:checkpoint-1"
                    ),
                    image_id="sha256:snapshot123",
                )
            )

        result = runner.invoke(
            app,
            [
                *command,
                "--event-log",
                str(event_log),
            ],
        )

    assert result.exit_code == 0

    mock_operation.assert_called_once()

    recorder = (
        mock_operation.call_args.kwargs[
            "recorder"
        ]
    )

    assert isinstance(
        recorder,
        EventRecorder,
    )

    assert recorder.context.scenario == (
        "cli-lab"
    )
    assert recorder.context.operation == (
        operation
    )

    assert isinstance(
        recorder.sink,
        JsonlEventSink,
    )
    assert recorder.sink.path == event_log

    assert (
        f"Run ID: {recorder.context.run_id}"
        in result.stdout
    )
    assert (
        f"Event log: {event_log}"
        in result.stdout
    )


@patch("pyrange.cli.start_lab")
@patch("pyrange.cli.load_scenario")
def test_event_log_writes_jsonl_with_execution_context(
    mock_load_scenario,
    mock_start_lab,
    tmp_path: Path,
) -> None:
    scenario = make_test_scenario()
    mock_load_scenario.return_value = scenario

    event_log = tmp_path / "events.jsonl"

    def emit_test_event(
        received_scenario: ScenarioConfig,
        *,
        recorder: EventRecorder,
    ) -> None:
        assert received_scenario is scenario

        recorder.emit(
            "cli.test",
            outcome="success",
        )

    mock_start_lab.side_effect = emit_test_event

    result = runner.invoke(
        app,
        [
            "start",
            "scenario.yaml",
            "--event-log",
            str(event_log),
        ],
    )

    assert result.exit_code == 0
    assert event_log.exists()

    lines = event_log.read_text(
        encoding="utf-8"
    ).splitlines()

    assert len(lines) == 1

    payload = json.loads(lines[0])

    assert payload["schema_version"] == 1
    assert payload["scenario"] == "cli-lab"
    assert payload["operation"] == "start"
    assert payload["event_type"] == "cli.test"
    assert payload["outcome"] == "success"
    assert payload["sequence"] == 1

    run_id = UUID(payload["run_id"])

    assert (
        f"Run ID: {run_id}"
        in result.stdout
    )


@patch("pyrange.cli.load_scenario")
def test_event_log_write_failure_shows_clean_error(
    mock_load_scenario,
    tmp_path: Path,
) -> None:
    scenario = make_test_scenario()
    mock_load_scenario.return_value = scenario

    event_log = (
        tmp_path
        / "missing"
        / "events.jsonl"
    )

    result = runner.invoke(
        app,
        [
            "start",
            "scenario.yaml",
            "--event-log",
            str(event_log),
        ],
    )

    assert result.exit_code == 1

    assert (
        "Error: Event log error: "
        "Failed to write event log"
        in result.stderr
    )

    assert "Traceback" not in result.output
    assert not event_log.exists()
