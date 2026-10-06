from unittest.mock import patch

from typer.testing import CliRunner

from pyrange.cli import app
from pyrange.engine import (
    DockerOperationError,
    LabStatus,
    MachineInterfaceStatus,
    MachineStatus,
    NetworkStatus,
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


@patch("pyrange.cli.inspect_lab_status")
@patch("pyrange.cli.load_scenario")
def test_status_command(
    mock_load_scenario,
    mock_inspect_lab_status,
) -> None:
    scenario = make_test_scenario()

    mock_load_scenario.return_value = scenario
    mock_inspect_lab_status.return_value = LabStatus(
        scenario_name="cli-lab",
        state="running",
        networks=(
            NetworkStatus(
                name="cli-net",
                runtime_name="pyrange-cli-lab-cli-net",
                state="matching",
                expected_subnet="172.28.40.0/24",
                actual_subnets=("172.28.40.0/24",),
            ),
        ),
        machines=(
            MachineStatus(
                name="web",
                runtime_name="pyrange-cli-lab-web",
                state="running",
                container_state="running",
                interfaces=(
                    MachineInterfaceStatus(
                        network="cli-net",
                        runtime_network=(
                            "pyrange-cli-lab-cli-net"
                        ),
                        state="matching",
                        expected_ip="172.28.40.10",
                        actual_ip="172.28.40.10",
                    ),
                ),
                unexpected_networks=(),
            ),
        ),
    )

    result = runner.invoke(
        app,
        ["status", "scenario.yaml"],
    )

    assert result.exit_code == 0

    assert "Scenario: cli-lab" in result.stdout
    assert "Status: running" in result.stdout

    assert "Networks:" in result.stdout
    assert "cli-net: matching" in result.stdout
    assert (
        "Expected subnet: 172.28.40.0/24"
        in result.stdout
    )
    assert (
        "Actual subnets: 172.28.40.0/24"
        in result.stdout
    )

    assert "Machines:" in result.stdout
    assert "web: running" in result.stdout
    assert "Container state: running" in result.stdout
    assert "Expected IP: 172.28.40.10" in result.stdout
    assert "Actual IP: 172.28.40.10" in result.stdout

    mock_load_scenario.assert_called_once()
    mock_inspect_lab_status.assert_called_once_with(
        scenario
    )


@patch("pyrange.cli.inspect_lab_status")
@patch("pyrange.cli.load_scenario")
def test_status_command_shows_drift_details(
    mock_load_scenario,
    mock_inspect_lab_status,
) -> None:
    scenario = make_test_scenario()

    mock_load_scenario.return_value = scenario
    mock_inspect_lab_status.return_value = LabStatus(
        scenario_name="cli-lab",
        state="drifted",
        networks=(
            NetworkStatus(
                name="cli-net",
                runtime_name="pyrange-cli-lab-cli-net",
                state="drifted",
                expected_subnet="172.28.40.0/24",
                actual_subnets=("172.28.99.0/24",),
            ),
        ),
        machines=(
            MachineStatus(
                name="web",
                runtime_name="pyrange-cli-lab-web",
                state="drifted",
                container_state="running",
                interfaces=(
                    MachineInterfaceStatus(
                        network="cli-net",
                        runtime_network=(
                            "pyrange-cli-lab-cli-net"
                        ),
                        state="drifted",
                        expected_ip="172.28.40.10",
                        actual_ip="172.28.40.99",
                    ),
                ),
                unexpected_networks=(
                    "unexpected-net",
                ),
            ),
        ),
    )

    result = runner.invoke(
        app,
        ["status", "scenario.yaml"],
    )

    assert result.exit_code == 0

    assert "Status: drifted" in result.stdout
    assert "cli-net: drifted" in result.stdout
    assert (
        "Expected subnet: 172.28.40.0/24"
        in result.stdout
    )
    assert (
        "Actual subnets: 172.28.99.0/24"
        in result.stdout
    )
    assert "web: drifted" in result.stdout
    assert "Expected IP: 172.28.40.10" in result.stdout
    assert "Actual IP: 172.28.40.99" in result.stdout
    assert "Unexpected networks:" in result.stdout
    assert "unexpected-net" in result.stdout


@patch("pyrange.cli.inspect_lab_status")
@patch("pyrange.cli.load_scenario")
def test_status_docker_error_shows_clean_message(
    mock_load_scenario,
    mock_inspect_lab_status,
) -> None:
    scenario = make_test_scenario()

    mock_load_scenario.return_value = scenario
    mock_inspect_lab_status.side_effect = (
        DockerOperationError("inspection failed")
    )

    result = runner.invoke(
        app,
        ["status", "scenario.yaml"],
    )

    assert result.exit_code == 1
    assert (
        "Error: Docker error: inspection failed"
        in result.output
    )
