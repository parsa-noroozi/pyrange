from pathlib import Path

from typer.testing import CliRunner

from pyrange.cli import app

runner = CliRunner()


def test_inspect_command(tmp_path: Path) -> None:
    scenario_file = tmp_path / "scenario.yaml"
    scenario_file.write_text(
        """
name: cli-lab
description: CLI test lab

network:
  name: cli-net
  subnet: 172.28.20.0/24

machines:
  - name: web
    image: nginx:alpine
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
    assert "Network: cli-net" in result.stdout
    assert "Subnet: 172.28.20.0/24" in result.stdout
    assert "Machines: 1" in result.stdout
    assert "web: nginx:alpine @ 172.28.20.10" in result.stdout


def test_inspect_missing_file_fails() -> None:
    result = runner.invoke(
        app,
        ["inspect", "does-not-exist.yaml"],
    )

    assert result.exit_code != 0


from unittest.mock import patch

from pyrange.models import MachineConfig, NetworkConfig, ScenarioConfig


def make_test_scenario() -> ScenarioConfig:
    return ScenarioConfig(
        name="cli-lab",
        network=NetworkConfig(
            name="cli-net",
            subnet="172.28.40.0/24",
        ),
        machines=[
            MachineConfig(
                name="web",
                image="nginx:alpine",
                ip="172.28.40.10",
            )
        ],
    )


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


from pydantic import ValidationError

from pyrange.engine import DockerOperationError


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
    assert "Error: Docker error: failed to create network" in result.stderr


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
    assert "Error: Docker error: failed to remove network" in result.stderr
