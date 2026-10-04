import subprocess
from uuid import uuid4

import pytest

from pyrange.engine import (
    DockerUnavailableError,
    create_machine_snapshot,
    execute_container_command,
    get_docker_server_version,
    get_lab_container_name,
    get_lab_network_name,
    get_snapshot_image_ref,
    restore_machine_snapshot,
    start_lab,
)
from pyrange.models import (
    MachineConfig,
    NetworkConfig,
    NetworkInterfaceConfig,
    ScenarioConfig,
)


def _cleanup_docker_resources(
    container_name: str,
    network_name: str,
    image_ref: str,
) -> None:
    subprocess.run(
        [
            "docker",
            "rm",
            "--force",
            container_name,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    subprocess.run(
        [
            "docker",
            "network",
            "rm",
            network_name,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    subprocess.run(
        [
            "docker",
            "image",
            "rm",
            "--force",
            image_ref,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.integration
def test_snapshot_restore_preserves_filesystem_state() -> None:
    try:
        get_docker_server_version()
    except DockerUnavailableError as exc:
        pytest.skip(f"Docker is unavailable: {exc}")

    scenario = ScenarioConfig(
        name=f"snapshot-int-{uuid4().hex[:8]}",
        networks=[
            NetworkConfig(
                name="snapshot-net",
                subnet="10.254.251.0/28",
            )
        ],
        machines=[
            MachineConfig(
                name="web",
                image="nginx:alpine",
                interfaces=[
                    NetworkInterfaceConfig(
                        network="snapshot-net",
                        ip="10.254.251.2",
                    )
                ],
            )
        ],
    )

    machine = scenario.machines[0]
    network = scenario.networks[0]
    snapshot_name = "checkpoint-1"

    container_name = get_lab_container_name(
        scenario,
        machine,
    )
    network_name = get_lab_network_name(
        scenario,
        network,
    )
    image_ref = get_snapshot_image_ref(
        scenario,
        machine,
        snapshot_name,
    )

    marker_path = (
        "/usr/share/nginx/html/"
        "pyrange-snapshot-marker.txt"
    )

    try:
        start_lab(scenario)

        initial_write = execute_container_command(
            name=container_name,
            command=[
                "sh",
                "-c",
                (
                    "printf 'snapshot-state' > "
                    f"{marker_path}"
                ),
            ],
            timeout_seconds=5.0,
        )

        assert initial_write.exit_code == 0, (
            initial_write.stderr
        )

        snapshot = create_machine_snapshot(
            scenario,
            machine_name="web",
            snapshot_name=snapshot_name,
        )

        modified_write = execute_container_command(
            name=container_name,
            command=[
                "sh",
                "-c",
                (
                    "printf 'modified-state' > "
                    f"{marker_path}"
                ),
            ],
            timeout_seconds=5.0,
        )

        assert modified_write.exit_code == 0, (
            modified_write.stderr
        )

        modified_read = execute_container_command(
            name=container_name,
            command=[
                "cat",
                marker_path,
            ],
            timeout_seconds=5.0,
        )

        assert modified_read.exit_code == 0, (
            modified_read.stderr
        )
        assert modified_read.stdout == "modified-state"

        restored = restore_machine_snapshot(
            scenario,
            machine_name="web",
            snapshot_name=snapshot_name,
        )

        restored_read = execute_container_command(
            name=container_name,
            command=[
                "cat",
                marker_path,
            ],
            timeout_seconds=5.0,
        )

        assert restored_read.exit_code == 0, (
            restored_read.stderr
        )
        assert restored_read.stdout == "snapshot-state"

        assert restored.image_ref == snapshot.image_ref
        assert restored.image_id == snapshot.image_id

    finally:
        _cleanup_docker_resources(
            container_name=container_name,
            network_name=network_name,
            image_ref=image_ref,
        )
