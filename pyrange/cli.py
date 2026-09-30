from pathlib import Path

import typer

from pyrange.core import load_scenario
from pyrange.engine import start_lab, stop_lab

app = typer.Typer(
    name="pyrange",
    help="Create and manage reproducible cybersecurity labs.",
)


@app.callback()
def main() -> None:
    """Create and manage reproducible cybersecurity labs."""


@app.command()
def inspect(path: Path) -> None:
    """Inspect and validate a PyRange scenario file."""
    scenario = load_scenario(path)

    typer.echo(f"Scenario: {scenario.name}")
    typer.echo(f"Description: {scenario.description or '-'}")
    typer.echo(f"Network: {scenario.network.name}")
    typer.echo(f"Subnet: {scenario.network.subnet}")
    typer.echo(f"Machines: {len(scenario.machines)}")

    for machine in scenario.machines:
        typer.echo(
            f"  - {machine.name}: "
            f"{machine.image} @ {machine.ip}"
        )


@app.command()
def start(path: Path) -> None:
    """Create and start a PyRange lab from a scenario file."""
    scenario = load_scenario(path)

    typer.echo(f"Starting lab: {scenario.name}")
    start_lab(scenario)
    typer.echo("Lab started successfully.")


@app.command()
def stop(path: Path) -> None:
    """Stop and remove a PyRange lab."""
    scenario = load_scenario(path)

    typer.echo(f"Stopping lab: {scenario.name}")
    stop_lab(scenario)
    typer.echo("Lab stopped successfully.")


if __name__ == "__main__":
    app()
