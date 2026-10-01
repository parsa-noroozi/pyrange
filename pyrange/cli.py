from pathlib import Path

import typer
from pydantic import ValidationError

from pyrange.core import load_scenario
from pyrange.engine import (
    DockerOperationError,
    DockerUnavailableError,
    LabManagerError,
    start_lab,
    stop_lab,
)

app = typer.Typer(
    name="pyrange",
    help="Create and manage reproducible cybersecurity labs.",
)


def fail(message: str) -> None:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1)


@app.callback()
def main() -> None:
    """Create and manage reproducible cybersecurity labs."""


@app.command()
def inspect(path: Path) -> None:
    """Inspect and validate a PyRange scenario file."""
    try:
        scenario = load_scenario(path)
    except FileNotFoundError:
        fail(f"scenario file not found: {path}")
    except ValidationError as exc:
        fail(f"invalid scenario: {exc}")

    typer.echo(f"Scenario: {scenario.name}")
    typer.echo(f"Description: {scenario.description or '-'}")
    typer.echo(f"Networks: {len(scenario.networks)}")

    for network in scenario.networks:
        typer.echo(
            f"  - {network.name}: {network.subnet}"
        )

    typer.echo(f"Machines: {len(scenario.machines)}")

    for machine in scenario.machines:
        typer.echo(
            f"  - {machine.name}: {machine.image}"
        )

        for interface in machine.interfaces:
            typer.echo(
                f"      {interface.network} @ {interface.ip}"
            )


@app.command()
def start(path: Path) -> None:
    """Create and start a PyRange lab from a scenario file."""
    try:
        scenario = load_scenario(path)

        typer.echo(f"Starting lab: {scenario.name}")
        start_lab(scenario)

    except FileNotFoundError:
        fail(f"scenario file not found: {path}")

    except ValidationError as exc:
        fail(f"invalid scenario: {exc}")

    except (DockerUnavailableError, DockerOperationError) as exc:
        fail(f"Docker error: {exc}")

    typer.echo("Lab started successfully.")


@app.command()
def stop(path: Path) -> None:
    """Stop and remove a PyRange lab."""
    try:
        scenario = load_scenario(path)

        typer.echo(f"Stopping lab: {scenario.name}")
        stop_lab(scenario)

    except FileNotFoundError:
        fail(f"scenario file not found: {path}")

    except ValidationError as exc:
        fail(f"invalid scenario: {exc}")

    except (
        DockerUnavailableError,
        DockerOperationError,
        LabManagerError,
    ) as exc:
        fail(f"Docker error: {exc}")

    typer.echo("Lab stopped successfully.")


if __name__ == "__main__":
    app()
