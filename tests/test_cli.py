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
