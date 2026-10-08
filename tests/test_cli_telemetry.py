from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from pyrange.cli import app
from pyrange.engine import (
    DockerOperationError,
    JsonlTelemetrySink,
    TelemetryCollectionError,
    TelemetryRecorder,
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


@patch("pyrange.cli.collect_lab_telemetry")
@patch("pyrange.cli.load_scenario")
def test_telemetry_command(
    mock_load_scenario,
    mock_collect,
    tmp_path: Path,
) -> None:
    scenario = make_test_scenario()
    mock_load_scenario.return_value = scenario
    mock_collect.return_value = ()

    telemetry_log = tmp_path / "telemetry.jsonl"

    result = runner.invoke(
        app,
        [
            "telemetry",
            "scenario.yaml",
            "--telemetry-log",
            str(telemetry_log),
        ],
    )

    assert result.exit_code == 0

    assert "Collecting telemetry: cli-lab" in result.stdout
    assert "Run ID:" in result.stdout
    assert (
        f"Telemetry log: {telemetry_log}"
        in result.stdout
    )
    assert "Telemetry records: 0" in result.stdout
    assert (
        "Telemetry collection completed successfully."
        in result.stdout
    )

    mock_load_scenario.assert_called_once()
    mock_collect.assert_called_once()

    scenario_arg, recorder = (
        mock_collect.call_args.args
    )

    assert scenario_arg is scenario
    assert isinstance(
        recorder,
        TelemetryRecorder,
    )
    assert recorder.context.scenario == "cli-lab"
    assert recorder.context.operation == "telemetry"

    assert isinstance(
        recorder.sink,
        JsonlTelemetrySink,
    )
    assert recorder.sink.path == telemetry_log


@patch("pyrange.cli.collect_lab_telemetry")
@patch("pyrange.cli.load_scenario")
def test_telemetry_artifact_dir_creates_run_scoped_log(
    mock_load_scenario,
    mock_collect,
    tmp_path: Path,
) -> None:
    scenario = make_test_scenario()
    mock_load_scenario.return_value = scenario
    mock_collect.return_value = ()

    artifact_root = tmp_path / "artifacts"

    result = runner.invoke(
        app,
        [
            "telemetry",
            "scenario.yaml",
            "--artifact-dir",
            str(artifact_root),
        ],
    )

    assert result.exit_code == 0

    mock_collect.assert_called_once()

    scenario_arg, recorder = (
        mock_collect.call_args.args
    )

    assert scenario_arg is scenario

    expected_directory = (
        artifact_root
        / str(recorder.context.run_id)
    )
    expected_telemetry_log = (
        expected_directory
        / "telemetry.jsonl"
    )

    assert expected_directory.is_dir()
    assert not expected_telemetry_log.exists()

    assert isinstance(
        recorder.sink,
        JsonlTelemetrySink,
    )
    assert (
        recorder.sink.path
        == expected_telemetry_log
    )

    assert (
        f"Run ID: {recorder.context.run_id}"
        in result.stdout
    )
    assert (
        f"Telemetry log: {expected_telemetry_log}"
        in result.stdout
    )


@patch("pyrange.cli.load_scenario")
def test_telemetry_requires_destination(
    mock_load_scenario,
) -> None:
    result = runner.invoke(
        app,
        [
            "telemetry",
            "scenario.yaml",
        ],
    )

    assert result.exit_code == 1

    assert (
        "Error: one of --telemetry-log or "
        "--artifact-dir is required"
        in result.stderr
    )

    mock_load_scenario.assert_not_called()


@patch("pyrange.cli.load_scenario")
def test_telemetry_rejects_multiple_destinations(
    mock_load_scenario,
    tmp_path: Path,
) -> None:
    telemetry_log = tmp_path / "telemetry.jsonl"
    artifact_root = tmp_path / "artifacts"

    result = runner.invoke(
        app,
        [
            "telemetry",
            "scenario.yaml",
            "--telemetry-log",
            str(telemetry_log),
            "--artifact-dir",
            str(artifact_root),
        ],
    )

    assert result.exit_code == 1

    assert (
        "Error: --telemetry-log and "
        "--artifact-dir are mutually exclusive"
        in result.stderr
    )

    mock_load_scenario.assert_not_called()
    assert not telemetry_log.exists()
    assert not artifact_root.exists()


def test_telemetry_missing_file_shows_clean_error(
    tmp_path: Path,
) -> None:
    telemetry_log = tmp_path / "telemetry.jsonl"

    result = runner.invoke(
        app,
        [
            "telemetry",
            "does-not-exist.yaml",
            "--telemetry-log",
            str(telemetry_log),
        ],
    )

    assert result.exit_code == 1

    assert (
        "Error: scenario file not found:"
        in result.stderr
    )


@patch("pyrange.cli.collect_lab_telemetry")
@patch("pyrange.cli.load_scenario")
def test_telemetry_docker_error_shows_clean_message(
    mock_load_scenario,
    mock_collect,
    tmp_path: Path,
) -> None:
    mock_load_scenario.return_value = (
        make_test_scenario()
    )
    mock_collect.side_effect = DockerOperationError(
        "stats collection failed"
    )

    telemetry_log = tmp_path / "telemetry.jsonl"

    result = runner.invoke(
        app,
        [
            "telemetry",
            "scenario.yaml",
            "--telemetry-log",
            str(telemetry_log),
        ],
    )

    assert result.exit_code == 1

    assert (
        "Error: Docker error: "
        "stats collection failed"
        in result.stderr
    )


@patch("pyrange.cli.collect_lab_telemetry")
@patch("pyrange.cli.load_scenario")
def test_telemetry_collection_error_shows_clean_message(
    mock_load_scenario,
    mock_collect,
    tmp_path: Path,
) -> None:
    mock_load_scenario.return_value = (
        make_test_scenario()
    )
    mock_collect.side_effect = (
        TelemetryCollectionError(
            "collector validation failed"
        )
    )

    telemetry_log = tmp_path / "telemetry.jsonl"

    result = runner.invoke(
        app,
        [
            "telemetry",
            "scenario.yaml",
            "--telemetry-log",
            str(telemetry_log),
        ],
    )

    assert result.exit_code == 1

    assert (
        "Error: Telemetry collection error: "
        "collector validation failed"
        in result.stderr
    )


@patch("pyrange.cli.collect_lab_telemetry")
@patch("pyrange.cli.load_scenario")
def test_telemetry_artifact_failure_shows_clean_error(
    mock_load_scenario,
    mock_collect,
    tmp_path: Path,
) -> None:
    mock_load_scenario.return_value = (
        make_test_scenario()
    )

    artifact_root = tmp_path / "artifacts"
    artifact_root.write_text(
        "not a directory",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "telemetry",
            "scenario.yaml",
            "--artifact-dir",
            str(artifact_root),
        ],
    )

    assert result.exit_code == 1

    assert (
        "Error: Artifact error: "
        "Failed to prepare artifact directory"
        in result.stderr
    )

    mock_collect.assert_not_called()


@patch(
    "pyrange.engine.telemetry_collector."
    "inspect_network_runtime"
)
@patch("pyrange.cli.load_scenario")
def test_telemetry_log_write_failure_shows_clean_error(
    mock_load_scenario,
    mock_inspect_network,
    tmp_path: Path,
) -> None:
    mock_load_scenario.return_value = (
        make_test_scenario()
    )
    mock_inspect_network.return_value = None

    telemetry_log = (
        tmp_path
        / "missing"
        / "telemetry.jsonl"
    )

    result = runner.invoke(
        app,
        [
            "telemetry",
            "scenario.yaml",
            "--telemetry-log",
            str(telemetry_log),
        ],
    )

    assert result.exit_code == 1

    assert (
        "Error: Telemetry log error: "
        "Failed to write telemetry log"
        in result.stderr
    )

    assert not telemetry_log.exists()
