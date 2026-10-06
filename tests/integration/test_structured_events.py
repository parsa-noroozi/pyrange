import json
import subprocess
from pathlib import Path
from uuid import UUID

import pytest
from typer.testing import CliRunner

from pyrange.cli import app
from pyrange.core import load_scenario
from pyrange.engine import (
    DockerUnavailableError,
    get_docker_server_version,
    stop_lab,
)


runner = CliRunner()


def docker_resource_exists(
    command: list[str],
) -> bool:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    return result.returncode == 0


@pytest.mark.integration
def test_cli_start_writes_structured_lifecycle_events(
    tmp_path: Path,
) -> None:
    try:
        get_docker_server_version()
    except DockerUnavailableError:
        pytest.skip("Docker Engine is unavailable")

    scenario_path = Path(
        "scenarios/basic-web-lab.yaml"
    )
    scenario = load_scenario(scenario_path)

    event_log = tmp_path / "start-events.jsonl"

    network_name = (
        "pyrange-basic-web-lab-lab-net"
    )
    web_container = (
        "pyrange-basic-web-lab-web"
    )
    analyst_container = (
        "pyrange-basic-web-lab-analyst"
    )

    try:
        result = runner.invoke(
            app,
            [
                "start",
                str(scenario_path),
                "--event-log",
                str(event_log),
            ],
        )

        assert result.exit_code == 0

        assert docker_resource_exists(
            [
                "docker",
                "network",
                "inspect",
                network_name,
            ]
        )

        assert docker_resource_exists(
            [
                "docker",
                "container",
                "inspect",
                web_container,
            ]
        )

        assert docker_resource_exists(
            [
                "docker",
                "container",
                "inspect",
                analyst_container,
            ]
        )

        assert event_log.exists()

        lines = event_log.read_text(
            encoding="utf-8"
        ).splitlines()

        assert lines

        events = [
            json.loads(line)
            for line in lines
        ]

        assert all(
            event["schema_version"] == 1
            for event in events
        )

        assert all(
            event["scenario"] == scenario.name
            for event in events
        )

        assert all(
            event["operation"] == "start"
            for event in events
        )

        run_ids = {
            event["run_id"]
            for event in events
        }

        assert len(run_ids) == 1

        run_id = UUID(run_ids.pop())

        assert (
            f"Run ID: {run_id}"
            in result.stdout
        )

        assert [
            event["sequence"]
            for event in events
        ] == list(
            range(1, len(events) + 1)
        )

        assert events[0]["event_type"] == (
            "lab.start.requested"
        )

        assert events[-1]["event_type"] == (
            "lab.start.completed"
        )

        assert events[-1]["outcome"] == (
            "success"
        )

        event_types = [
            event["event_type"]
            for event in events
        ]

        assert event_types.count(
            "network.created"
        ) == len(scenario.networks)

        assert event_types.count(
            "machine.created"
        ) == len(scenario.machines)

        assert event_types.count(
            "machine.started"
        ) == len(scenario.machines)

        assert event_types.count(
            "machine.network.attached"
        ) == sum(
            len(machine.interfaces)
            for machine in scenario.machines
        )

        event_ids = [
            UUID(event["event_id"])
            for event in events
        ]

        assert len(set(event_ids)) == len(
            event_ids
        )

    finally:
        try:
            stop_lab(scenario)
        except Exception:
            pass

    assert not docker_resource_exists(
        [
            "docker",
            "network",
            "inspect",
            network_name,
        ]
    )

    assert not docker_resource_exists(
        [
            "docker",
            "container",
            "inspect",
            web_container,
        ]
    )

    assert not docker_resource_exists(
        [
            "docker",
            "container",
            "inspect",
            analyst_container,
        ]
    )
