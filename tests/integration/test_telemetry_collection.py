import json
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from typer.testing import CliRunner

from pyrange.cli import app
from pyrange.core import load_scenario
from pyrange.engine import (
    DockerUnavailableError,
    get_docker_server_version,
    get_lab_container_name,
    get_lab_network_name,
    start_lab,
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
def test_cli_telemetry_collects_real_container_observations(
    tmp_path: Path,
) -> None:
    try:
        get_docker_server_version()
    except DockerUnavailableError:
        pytest.skip("Docker Engine is unavailable")

    scenario_name = (
        f"telemetry-integration-{uuid4().hex[:8]}"
    )

    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        f"""
name: {scenario_name}
description: Telemetry integration test lab

networks:
  - name: lab-net
    subnet: 10.254.251.0/28

machines:
  - name: web
    image: nginx:alpine
    interfaces:
      - network: lab-net
        ip: 10.254.251.2
""".strip(),
        encoding="utf-8",
    )

    scenario = load_scenario(scenario_path)

    telemetry_log = (
        tmp_path / "telemetry.jsonl"
    )

    network_names = [
        get_lab_network_name(
            scenario,
            network,
        )
        for network in scenario.networks
    ]

    container_names = [
        get_lab_container_name(
            scenario,
            machine,
        )
        for machine in scenario.machines
    ]

    try:
        start_lab(scenario)

        result = runner.invoke(
            app,
            [
                "telemetry",
                str(scenario_path),
                "--telemetry-log",
                str(telemetry_log),
            ],
        )

        assert result.exit_code == 0
        assert telemetry_log.exists()

        lines = telemetry_log.read_text(
            encoding="utf-8"
        ).splitlines()

        assert lines

        records = [
            json.loads(line)
            for line in lines
        ]

        assert len(records) == 2

        assert all(
            record["schema_version"] == 1
            for record in records
        )

        assert all(
            record["scenario"] == scenario.name
            for record in records
        )

        assert all(
            record["operation"] == "telemetry"
            for record in records
        )

        run_ids = {
            record["run_id"]
            for record in records
        }

        assert len(run_ids) == 1

        run_id = UUID(run_ids.pop())

        assert (
            f"Run ID: {run_id}"
            in result.stdout
        )

        assert (
            f"Telemetry log: {telemetry_log}"
            in result.stdout
        )

        assert (
            "Telemetry records: 2"
            in result.stdout
        )

        assert [
            record["sequence"]
            for record in records
        ] == [
            1,
            2,
        ]

        telemetry_ids = [
            UUID(record["telemetry_id"])
            for record in records
        ]

        assert len(
            set(telemetry_ids)
        ) == 2

        assert [
            record["telemetry_type"]
            for record in records
        ] == [
            "container.runtime",
            "container.stats",
        ]

        expected_resource = {
            "type": "machine",
            "name": "web",
        }

        runtime_record = records[0]
        stats_record = records[1]

        assert (
            runtime_record["resource"]
            == expected_resource
        )

        assert (
            stats_record["resource"]
            == expected_resource
        )

        runtime_data = runtime_record["data"]

        assert runtime_data[
            "runtime_name"
        ] == container_names[0]

        assert runtime_data["present"] is True
        assert runtime_data["status"] == "running"

        assert runtime_data["networks"] == [
            {
                "network_name": network_names[0],
                "ip_address": "10.254.251.2",
            }
        ]

        stats_data = stats_record["data"]

        assert stats_data[
            "runtime_name"
        ] == container_names[0]

        for field in (
            "cpu_percent",
            "memory_usage",
            "memory_percent",
            "network_io",
            "block_io",
        ):
            assert isinstance(
                stats_data[field],
                str,
            )
            assert stats_data[field]

        assert isinstance(
            stats_data["pids"],
            int,
        )
        assert stats_data["pids"] >= 0

    finally:
        try:
            stop_lab(scenario)
        except Exception:
            pass

    for container_name in container_names:
        assert not docker_resource_exists(
            [
                "docker",
                "container",
                "inspect",
                container_name,
            ]
        )

    for network_name in network_names:
        assert not docker_resource_exists(
            [
                "docker",
                "network",
                "inspect",
                network_name,
            ]
        )
