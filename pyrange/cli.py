from pathlib import Path

import typer
from pydantic import ValidationError

from pyrange.core import load_scenario
from pyrange.engine import (
    DockerOperationError,
    DockerUnavailableError,
    EventRecorder,
    EventSinkError,
    ExecutionContext,
    JsonlEventSink,
    JsonlTelemetrySink,
    LabManagerError,
    SnapshotError,
    TelemetryCollectionError,
    TelemetryRecorder,
    TelemetrySinkError,
    collect_lab_telemetry,
    create_machine_snapshot,
    inspect_lab_status,
    restore_machine_snapshot,
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


def _create_event_recorder(
    *,
    scenario_name: str,
    operation: str,
    event_log: Path | None,
) -> EventRecorder | None:
    if event_log is None:
        return None

    context = ExecutionContext(
        scenario=scenario_name,
        operation=operation,
    )

    return EventRecorder(
        context,
        JsonlEventSink(event_log),
    )


def _show_event_context(
    recorder: EventRecorder | None,
    event_log: Path | None,
) -> None:
    if recorder is None or event_log is None:
        return

    typer.echo(
        f"Run ID: {recorder.context.run_id}"
    )
    typer.echo(f"Event log: {event_log}")


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
def status(path: Path) -> None:
    """Inspect the runtime status of a PyRange lab."""
    try:
        scenario = load_scenario(path)
        result = inspect_lab_status(scenario)

    except FileNotFoundError:
        fail(f"scenario file not found: {path}")

    except ValidationError as exc:
        fail(f"invalid scenario: {exc}")

    except (
        DockerUnavailableError,
        DockerOperationError,
    ) as exc:
        fail(f"Docker error: {exc}")

    typer.echo(f"Scenario: {result.scenario_name}")
    typer.echo(f"Status: {result.state}")
    typer.echo("")
    typer.echo("Networks:")

    for network in result.networks:
        actual_subnets = (
            ", ".join(network.actual_subnets)
            or "-"
        )

        typer.echo(
            f"  - {network.name}: {network.state}"
        )
        typer.echo(
            f"      Runtime: {network.runtime_name}"
        )
        typer.echo(
            f"      Expected subnet: "
            f"{network.expected_subnet}"
        )
        typer.echo(
            f"      Actual subnets: {actual_subnets}"
        )

    typer.echo("")
    typer.echo("Machines:")

    for machine in result.machines:
        container_state = machine.container_state or "-"

        typer.echo(
            f"  - {machine.name}: {machine.state}"
        )
        typer.echo(
            f"      Runtime: {machine.runtime_name}"
        )
        typer.echo(
            f"      Container state: {container_state}"
        )
        typer.echo("      Interfaces:")

        for interface in machine.interfaces:
            actual_ip = interface.actual_ip or "-"

            typer.echo(
                f"        - {interface.network}: "
                f"{interface.state}"
            )
            typer.echo(
                f"            Runtime network: "
                f"{interface.runtime_network}"
            )
            typer.echo(
                f"            Expected IP: "
                f"{interface.expected_ip}"
            )
            typer.echo(
                f"            Actual IP: {actual_ip}"
            )

        if machine.unexpected_networks:
            typer.echo("      Unexpected networks:")

            for network_name in machine.unexpected_networks:
                typer.echo(
                    f"        - {network_name}"
                )


@app.command()
def telemetry(
    path: Path,
    telemetry_log: Path = typer.Option(
        ...,
        "--telemetry-log",
        help=(
            "Append structured telemetry "
            "to a JSONL file."
        ),
    ),
) -> None:
    """Collect point-in-time telemetry from a PyRange lab."""
    try:
        scenario = load_scenario(path)

        context = ExecutionContext(
            scenario=scenario.name,
            operation="telemetry",
        )

        recorder = TelemetryRecorder(
            context,
            JsonlTelemetrySink(telemetry_log),
        )

        typer.echo(
            f"Collecting telemetry: {scenario.name}"
        )
        typer.echo(
            f"Run ID: {recorder.context.run_id}"
        )
        typer.echo(
            f"Telemetry log: {telemetry_log}"
        )

        records = collect_lab_telemetry(
            scenario,
            recorder,
        )

    except FileNotFoundError:
        fail(f"scenario file not found: {path}")

    except ValidationError as exc:
        fail(f"invalid scenario: {exc}")

    except TelemetrySinkError as exc:
        fail(f"Telemetry log error: {exc}")

    except TelemetryCollectionError as exc:
        fail(f"Telemetry collection error: {exc}")

    except (
        DockerUnavailableError,
        DockerOperationError,
    ) as exc:
        fail(f"Docker error: {exc}")

    typer.echo(
        f"Telemetry records: {len(records)}"
    )
    typer.echo(
        "Telemetry collection completed successfully."
    )


@app.command()
def start(
    path: Path,
    event_log: Path | None = typer.Option(
        None,
        "--event-log",
        help=(
            "Append structured execution events "
            "to a JSONL file."
        ),
    ),
) -> None:
    """Create and start a PyRange lab from a scenario file."""
    try:
        scenario = load_scenario(path)

        recorder = _create_event_recorder(
            scenario_name=scenario.name,
            operation="start",
            event_log=event_log,
        )

        typer.echo(
            f"Starting lab: {scenario.name}"
        )
        _show_event_context(
            recorder,
            event_log,
        )

        if recorder is None:
            start_lab(scenario)
        else:
            start_lab(
                scenario,
                recorder=recorder,
            )

    except FileNotFoundError:
        fail(f"scenario file not found: {path}")

    except ValidationError as exc:
        fail(f"invalid scenario: {exc}")

    except EventSinkError as exc:
        fail(f"Event log error: {exc}")

    except (
        DockerUnavailableError,
        DockerOperationError,
        LabManagerError,
    ) as exc:
        fail(f"Docker error: {exc}")

    typer.echo("Lab started successfully.")


@app.command()
def stop(
    path: Path,
    event_log: Path | None = typer.Option(
        None,
        "--event-log",
        help=(
            "Append structured execution events "
            "to a JSONL file."
        ),
    ),
) -> None:
    """Stop and remove a PyRange lab."""
    try:
        scenario = load_scenario(path)

        recorder = _create_event_recorder(
            scenario_name=scenario.name,
            operation="stop",
            event_log=event_log,
        )

        typer.echo(
            f"Stopping lab: {scenario.name}"
        )
        _show_event_context(
            recorder,
            event_log,
        )

        if recorder is None:
            stop_lab(scenario)
        else:
            stop_lab(
                scenario,
                recorder=recorder,
            )

    except FileNotFoundError:
        fail(f"scenario file not found: {path}")

    except ValidationError as exc:
        fail(f"invalid scenario: {exc}")

    except EventSinkError as exc:
        fail(f"Event log error: {exc}")

    except (
        DockerUnavailableError,
        DockerOperationError,
        LabManagerError,
    ) as exc:
        fail(f"Docker error: {exc}")

    typer.echo("Lab stopped successfully.")


@app.command()
def snapshot(
    path: Path,
    machine: str,
    snapshot_name: str,
    event_log: Path | None = typer.Option(
        None,
        "--event-log",
        help=(
            "Append structured execution events "
            "to a JSONL file."
        ),
    ),
) -> None:
    """Create a snapshot of a machine in a running lab."""
    try:
        scenario = load_scenario(path)

        recorder = _create_event_recorder(
            scenario_name=scenario.name,
            operation="snapshot",
            event_log=event_log,
        )

        typer.echo(
            f"Creating snapshot: "
            f"{machine} ({snapshot_name})"
        )
        _show_event_context(
            recorder,
            event_log,
        )

        if recorder is None:
            result = create_machine_snapshot(
                scenario,
                machine_name=machine,
                snapshot_name=snapshot_name,
            )
        else:
            result = create_machine_snapshot(
                scenario,
                machine_name=machine,
                snapshot_name=snapshot_name,
                recorder=recorder,
            )

    except FileNotFoundError:
        fail(f"scenario file not found: {path}")

    except ValidationError as exc:
        fail(f"invalid scenario: {exc}")

    except EventSinkError as exc:
        fail(f"Event log error: {exc}")

    except (
        SnapshotError,
        ValueError,
    ) as exc:
        fail(f"Snapshot error: {exc}")

    except (
        DockerUnavailableError,
        DockerOperationError,
    ) as exc:
        fail(f"Docker error: {exc}")

    typer.echo("Snapshot created successfully.")
    typer.echo(f"Machine: {result.machine_name}")
    typer.echo(f"Image: {result.image_ref}")
    typer.echo(f"Image ID: {result.image_id}")


@app.command()
def restore(
    path: Path,
    machine: str,
    snapshot_name: str,
    event_log: Path | None = typer.Option(
        None,
        "--event-log",
        help=(
            "Append structured execution events "
            "to a JSONL file."
        ),
    ),
) -> None:
    """Restore a machine from a snapshot."""
    try:
        scenario = load_scenario(path)

        recorder = _create_event_recorder(
            scenario_name=scenario.name,
            operation="restore",
            event_log=event_log,
        )

        typer.echo(
            f"Restoring snapshot: "
            f"{machine} ({snapshot_name})"
        )
        _show_event_context(
            recorder,
            event_log,
        )

        if recorder is None:
            result = restore_machine_snapshot(
                scenario,
                machine_name=machine,
                snapshot_name=snapshot_name,
            )
        else:
            result = restore_machine_snapshot(
                scenario,
                machine_name=machine,
                snapshot_name=snapshot_name,
                recorder=recorder,
            )

    except FileNotFoundError:
        fail(f"scenario file not found: {path}")

    except ValidationError as exc:
        fail(f"invalid scenario: {exc}")

    except EventSinkError as exc:
        fail(f"Event log error: {exc}")

    except (
        SnapshotError,
        ValueError,
    ) as exc:
        fail(f"Snapshot error: {exc}")

    except (
        DockerUnavailableError,
        DockerOperationError,
    ) as exc:
        fail(f"Docker error: {exc}")

    typer.echo("Snapshot restored successfully.")
    typer.echo(f"Machine: {result.machine_name}")
    typer.echo(f"Image: {result.image_ref}")
    typer.echo(f"Image ID: {result.image_id}")


if __name__ == "__main__":
    app()
