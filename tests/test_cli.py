from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError
from typer.testing import CliRunner

from pyrange.cli import app
from pyrange.engine import (
    DockerOperationError,
    MachineRestoreResult,
    MachineSnapshot,
    SnapshotError,
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


def test_inspect_command(tmp_path: Path) -> None:
    scenario_file = tmp_path / "scenario.yaml"
    scenario_file.write_text(
        """
name: cli-lab
description: CLI test lab

networks:
  - name: cli-net
    subnet: 172.28.20.0/24

machines:
  - name: web
    image: nginx:alpine
    interfaces:
      - network: cli-net
        ip: 172.28.20.10
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["inspect", str(scenario_file)],
    )

    assert result.exit_code == 0
    assert "Scenario: cli-lab" in result.stdout
    assert "Networks: 1" in result.stdout
    assert "cli-net: 172.28.20.0/24" in result.stdout
    assert "Machines: 1" in result.stdout
    assert "web: nginx:alpine" in result.stdout
    assert "cli-net @ 172.28.20.10" in result.stdout


def test_inspect_missing_file_fails() -> None:
    result = runner.invoke(
        app,
        ["inspect", "does-not-exist.yaml"],
    )

    assert result.exit_code != 0


@patch("pyrange.cli.start_lab")
@patch("pyrange.cli.load_scenario")
def test_start_command(
    mock_load_scenario,
    mock_start_lab,
) -> None:
    scenario = make_test_scenario()
    mock_load_scenario.return_value = scenario

    result = runner.invoke(
        app,
        ["start", "scenario.yaml"],
    )

    assert result.exit_code == 0
    assert "Starting lab: cli-lab" in result.stdout
    assert "Lab started successfully." in result.stdout

    mock_load_scenario.assert_called_once()
    mock_start_lab.assert_called_once_with(scenario)


@patch("pyrange.cli.stop_lab")
@patch("pyrange.cli.load_scenario")
def test_stop_command(
    mock_load_scenario,
    mock_stop_lab,
) -> None:
    scenario = make_test_scenario()
    mock_load_scenario.return_value = scenario

    result = runner.invoke(
        app,
        ["stop", "scenario.yaml"],
    )

    assert result.exit_code == 0
    assert "Stopping lab: cli-lab" in result.stdout
    assert "Lab stopped successfully." in result.stdout

    mock_load_scenario.assert_called_once()
    mock_stop_lab.assert_called_once_with(scenario)


def test_inspect_missing_file_shows_clean_error() -> None:
    result = runner.invoke(
        app,
        ["inspect", "does-not-exist.yaml"],
    )

    assert result.exit_code == 1
    assert "Error: scenario file not found:" in result.stderr


@patch("pyrange.cli.load_scenario")
def test_inspect_invalid_scenario_shows_clean_error(
    mock_load_scenario,
) -> None:
    mock_load_scenario.side_effect = ValidationError.from_exception_data(
        "ScenarioConfig",
        [],
    )

    result = runner.invoke(
        app,
        ["inspect", "invalid.yaml"],
    )

    assert result.exit_code == 1
    assert "Error: invalid scenario:" in result.stderr


@patch("pyrange.cli.start_lab")
@patch("pyrange.cli.load_scenario")
def test_start_docker_error_shows_clean_message(
    mock_load_scenario,
    mock_start_lab,
) -> None:
    scenario = make_test_scenario()
    mock_load_scenario.return_value = scenario
    mock_start_lab.side_effect = DockerOperationError(
        "failed to create network"
    )

    result = runner.invoke(
        app,
        ["start", "scenario.yaml"],
    )

    assert result.exit_code == 1
    assert (
        "Error: Docker error: failed to create network"
        in result.stderr
    )


@patch("pyrange.cli.stop_lab")
@patch("pyrange.cli.load_scenario")
def test_stop_docker_error_shows_clean_message(
    mock_load_scenario,
    mock_stop_lab,
) -> None:
    scenario = make_test_scenario()
    mock_load_scenario.return_value = scenario
    mock_stop_lab.side_effect = DockerOperationError(
        "failed to remove network"
    )

    result = runner.invoke(
        app,
        ["stop", "scenario.yaml"],
    )

    assert result.exit_code == 1
    assert (
        "Error: Docker error: failed to remove network"
        in result.stderr
    )


@patch("pyrange.cli.create_machine_snapshot")
@patch("pyrange.cli.load_scenario")
def test_snapshot_command(
    mock_load_scenario,
    mock_create_machine_snapshot,
) -> None:
    scenario = make_test_scenario()
    mock_load_scenario.return_value = scenario
    mock_create_machine_snapshot.return_value = (
        MachineSnapshot(
            snapshot_name="checkpoint-1",
            machine_name="web",
            container_name="pyrange-cli-lab-web",
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
            "snapshot",
            "scenario.yaml",
            "web",
            "checkpoint-1",
        ],
    )

    assert result.exit_code == 0
    assert (
        "Creating snapshot: web (checkpoint-1)"
        in result.stdout
    )
    assert (
        "Snapshot created successfully."
        in result.stdout
    )
    assert "Machine: web" in result.stdout
    assert (
        "Image: "
        "pyrange-snapshots/cli-lab-web:checkpoint-1"
        in result.stdout
    )
    assert (
        "Image ID: sha256:snapshot123"
        in result.stdout
    )

    mock_load_scenario.assert_called_once()
    mock_create_machine_snapshot.assert_called_once_with(
        scenario,
        machine_name="web",
        snapshot_name="checkpoint-1",
    )


@patch("pyrange.cli.create_machine_snapshot")
@patch("pyrange.cli.load_scenario")
def test_snapshot_unknown_machine_shows_clean_error(
    mock_load_scenario,
    mock_create_machine_snapshot,
) -> None:
    scenario = make_test_scenario()
    mock_load_scenario.return_value = scenario
    mock_create_machine_snapshot.side_effect = SnapshotError(
        "Machine 'missing' is not defined "
        "in scenario 'cli-lab'."
    )

    result = runner.invoke(
        app,
        [
            "snapshot",
            "scenario.yaml",
            "missing",
            "checkpoint-1",
        ],
    )

    assert result.exit_code == 1
    assert (
        "Error: Snapshot error: "
        "Machine 'missing' is not defined"
        in result.stderr
    )


@patch("pyrange.cli.create_machine_snapshot")
@patch("pyrange.cli.load_scenario")
def test_snapshot_invalid_name_shows_clean_error(
    mock_load_scenario,
    mock_create_machine_snapshot,
) -> None:
    scenario = make_test_scenario()
    mock_load_scenario.return_value = scenario
    mock_create_machine_snapshot.side_effect = ValueError(
        "snapshot name must be a valid Docker tag"
    )

    result = runner.invoke(
        app,
        [
            "snapshot",
            "scenario.yaml",
            "web",
            "invalid/name",
        ],
    )

    assert result.exit_code == 1
    assert (
        "Error: Snapshot error: "
        "snapshot name must be a valid Docker tag"
        in result.stderr
    )


@patch("pyrange.cli.create_machine_snapshot")
@patch("pyrange.cli.load_scenario")
def test_snapshot_docker_error_shows_clean_message(
    mock_load_scenario,
    mock_create_machine_snapshot,
) -> None:
    scenario = make_test_scenario()
    mock_load_scenario.return_value = scenario
    mock_create_machine_snapshot.side_effect = (
        DockerOperationError(
            "failed to create container snapshot"
        )
    )

    result = runner.invoke(
        app,
        [
            "snapshot",
            "scenario.yaml",
            "web",
            "checkpoint-1",
        ],
    )

    assert result.exit_code == 1
    assert (
        "Error: Docker error: "
        "failed to create container snapshot"
        in result.stderr
    )


@patch("pyrange.cli.restore_machine_snapshot")
@patch("pyrange.cli.load_scenario")
def test_restore_command(
    mock_load_scenario,
    mock_restore_machine_snapshot,
) -> None:
    scenario = make_test_scenario()
    mock_load_scenario.return_value = scenario
    mock_restore_machine_snapshot.return_value = (
        MachineRestoreResult(
            snapshot_name="checkpoint-1",
            machine_name="web",
            container_name="pyrange-cli-lab-web",
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
            "restore",
            "scenario.yaml",
            "web",
            "checkpoint-1",
        ],
    )

    assert result.exit_code == 0
    assert (
        "Restoring snapshot: web (checkpoint-1)"
        in result.stdout
    )
    assert (
        "Snapshot restored successfully."
        in result.stdout
    )
    assert "Machine: web" in result.stdout
    assert (
        "Image: "
        "pyrange-snapshots/cli-lab-web:checkpoint-1"
        in result.stdout
    )
    assert (
        "Image ID: sha256:snapshot123"
        in result.stdout
    )

    mock_load_scenario.assert_called_once()
    mock_restore_machine_snapshot.assert_called_once_with(
        scenario,
        machine_name="web",
        snapshot_name="checkpoint-1",
    )


@patch("pyrange.cli.restore_machine_snapshot")
@patch("pyrange.cli.load_scenario")
def test_restore_unknown_machine_shows_clean_error(
    mock_load_scenario,
    mock_restore_machine_snapshot,
) -> None:
    scenario = make_test_scenario()
    mock_load_scenario.return_value = scenario
    mock_restore_machine_snapshot.side_effect = SnapshotError(
        "Machine 'missing' is not defined "
        "in scenario 'cli-lab'."
    )

    result = runner.invoke(
        app,
        [
            "restore",
            "scenario.yaml",
            "missing",
            "checkpoint-1",
        ],
    )

    assert result.exit_code == 1
    assert (
        "Error: Snapshot error: "
        "Machine 'missing' is not defined"
        in result.stderr
    )


@patch("pyrange.cli.restore_machine_snapshot")
@patch("pyrange.cli.load_scenario")
def test_restore_invalid_name_shows_clean_error(
    mock_load_scenario,
    mock_restore_machine_snapshot,
) -> None:
    scenario = make_test_scenario()
    mock_load_scenario.return_value = scenario
    mock_restore_machine_snapshot.side_effect = ValueError(
        "snapshot name must be a valid Docker tag"
    )

    result = runner.invoke(
        app,
        [
            "restore",
            "scenario.yaml",
            "web",
            "invalid/name",
        ],
    )

    assert result.exit_code == 1
    assert (
        "Error: Snapshot error: "
        "snapshot name must be a valid Docker tag"
        in result.stderr
    )


@patch("pyrange.cli.restore_machine_snapshot")
@patch("pyrange.cli.load_scenario")
def test_restore_docker_error_shows_clean_message(
    mock_load_scenario,
    mock_restore_machine_snapshot,
) -> None:
    scenario = make_test_scenario()
    mock_load_scenario.return_value = scenario
    mock_restore_machine_snapshot.side_effect = (
        DockerOperationError(
            "No such image"
        )
    )

    result = runner.invoke(
        app,
        [
            "restore",
            "scenario.yaml",
            "web",
            "checkpoint-1",
        ],
    )

    assert result.exit_code == 1
    assert (
        "Error: Docker error: No such image"
        in result.stderr
    )
