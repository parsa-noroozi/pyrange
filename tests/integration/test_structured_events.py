import json
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from typer.testing import CliRunner

from pyrange.cli import app
from pyrange.core import load_scenario
from pyrange.engine.docker import find_container_identity, find_network_identity
from pyrange.engine import (
    DockerUnavailableError,
    get_docker_server_version,
    get_lab_container_name,
    get_lab_network_name,
    stop_lab,
)


runner = CliRunner()


def docker_resource_exists(command: list[str]) -> bool:
    # A failed query must not be accepted as proof of successful cleanup.
    if len(command) != 4:
        raise ValueError("Expected an inspect command with one resource name")
    if command[:3] == ["docker", "container", "inspect"]:
        return find_container_identity(command[3]) is not None
    if command[:3] == ["docker", "network", "inspect"]:
        return find_network_identity(command[3]) is not None
    raise ValueError("Unsupported resource inspection command")


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
    scenario.name = f"integration-{uuid4().hex}"
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        json.dumps(scenario.model_dump(mode="json")), encoding="utf-8"
    )

    event_log = tmp_path / "start-events.jsonl"

    network_name = get_lab_network_name(
        scenario, next(item for item in scenario.networks if item.name == "lab-net")
    )
    web_container = get_lab_container_name(
        scenario, next(item for item in scenario.machines if item.name == "web")
    )
    analyst_container = get_lab_container_name(
        scenario, next(item for item in scenario.machines if item.name == "analyst")
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
