from unittest.mock import patch

import pytest

from pyrange.engine import (
    DockerOperationError,
    HealthCheckResult,
    MachineRestoreResult,
    MachineSnapshot,
    SnapshotError,
    create_machine_snapshot,
    get_snapshot_image_ref,
    restore_machine_snapshot,
)
from pyrange.models import (
    HealthCheckConfig,
    MachineConfig,
    NetworkConfig,
    NetworkInterfaceConfig,
    ScenarioConfig,
)


@pytest.fixture
def scenario() -> ScenarioConfig:
    return ScenarioConfig(
        name="snapshot-lab",
        networks=[
            NetworkConfig(
                name="lab-net",
                subnet="172.28.40.0/24",
            )
        ],
        machines=[
            MachineConfig(
                name="web",
                image="nginx:alpine",
                interfaces=[
                    NetworkInterfaceConfig(
                        network="lab-net",
                        ip="172.28.40.10",
                    )
                ],
            )
        ],
    )


@pytest.fixture
def multi_network_scenario() -> ScenarioConfig:
    return ScenarioConfig(
        name="snapshot-lab",
        networks=[
            NetworkConfig(
                name="public-net",
                subnet="172.28.40.0/24",
            ),
            NetworkConfig(
                name="private-net",
                subnet="172.28.50.0/24",
            ),
        ],
        machines=[
            MachineConfig(
                name="web",
                image="nginx:alpine",
                interfaces=[
                    NetworkInterfaceConfig(
                        network="public-net",
                        ip="172.28.40.10",
                    ),
                    NetworkInterfaceConfig(
                        network="private-net",
                        ip="172.28.50.10",
                    ),
                ],
            )
        ],
    )


def test_generates_snapshot_image_ref(
    scenario: ScenarioConfig,
) -> None:
    image_ref = get_snapshot_image_ref(
        scenario,
        scenario.machines[0],
        "checkpoint-1",
    )

    assert image_ref == (
        "pyrange-snapshots/"
        "snapshot-lab-web:checkpoint-1"
    )


def test_rejects_invalid_snapshot_names(
    scenario: ScenarioConfig,
) -> None:
    invalid_names = [
        "",
        "   ",
        "-checkpoint",
        ".checkpoint",
        "checkpoint 1",
        "checkpoint/1",
        "checkpoint:1",
        "a" * 129,
    ]

    for snapshot_name in invalid_names:
        with pytest.raises(
            ValueError,
            match="snapshot name must be a valid Docker tag",
        ):
            get_snapshot_image_ref(
                scenario,
                scenario.machines[0],
                snapshot_name,
            )


@patch(
    "pyrange.engine.snapshot."
    "create_container_snapshot"
)
def test_creates_machine_snapshot(
    mock_create_container_snapshot,
    scenario: ScenarioConfig,
) -> None:
    mock_create_container_snapshot.return_value = (
        "sha256:snapshot123"
    )

    snapshot = create_machine_snapshot(
        scenario,
        machine_name="web",
        snapshot_name="checkpoint-1",
    )

    assert snapshot == MachineSnapshot(
        snapshot_name="checkpoint-1",
        machine_name="web",
        container_name="pyrange-snapshot-lab-web",
        image_ref=(
            "pyrange-snapshots/"
            "snapshot-lab-web:checkpoint-1"
        ),
        image_id="sha256:snapshot123",
    )

    mock_create_container_snapshot.assert_called_once_with(
        name="pyrange-snapshot-lab-web",
        image_ref=(
            "pyrange-snapshots/"
            "snapshot-lab-web:checkpoint-1"
        ),
    )


@patch(
    "pyrange.engine.snapshot."
    "create_container_snapshot"
)
def test_rejects_unknown_machine(
    mock_create_container_snapshot,
    scenario: ScenarioConfig,
) -> None:
    with pytest.raises(
        SnapshotError,
        match="Machine 'missing' is not defined",
    ):
        create_machine_snapshot(
            scenario,
            machine_name="missing",
            snapshot_name="checkpoint-1",
        )

    mock_create_container_snapshot.assert_not_called()


@patch("pyrange.engine.snapshot.start_container")
@patch("pyrange.engine.snapshot.create_container")
@patch("pyrange.engine.snapshot.remove_container")
@patch("pyrange.engine.snapshot.get_image_id")
def test_restores_machine_snapshot(
    mock_get_image_id,
    mock_remove_container,
    mock_create_container,
    mock_start_container,
    scenario: ScenarioConfig,
) -> None:
    mock_get_image_id.return_value = "sha256:snapshot123"

    events: list[str] = []

    mock_remove_container.side_effect = (
        lambda name: events.append(
            f"remove:{name}"
        )
    )

    mock_create_container.side_effect = (
        lambda **kwargs: events.append(
            f"create:{kwargs['name']}"
        )
    )

    mock_start_container.side_effect = (
        lambda name: events.append(
            f"start:{name}"
        )
    )

    result = restore_machine_snapshot(
        scenario,
        machine_name="web",
        snapshot_name="checkpoint-1",
    )

    assert result == MachineRestoreResult(
        snapshot_name="checkpoint-1",
        machine_name="web",
        container_name="pyrange-snapshot-lab-web",
        image_ref=(
            "pyrange-snapshots/"
            "snapshot-lab-web:checkpoint-1"
        ),
        image_id="sha256:snapshot123",
    )

    mock_get_image_id.assert_called_once_with(
        "pyrange-snapshots/"
        "snapshot-lab-web:checkpoint-1"
    )

    mock_create_container.assert_called_once_with(
        name="pyrange-snapshot-lab-web",
        image="sha256:snapshot123",
        network="pyrange-snapshot-lab-lab-net",
        ip="172.28.40.10",
    )

    assert events == [
        "remove:pyrange-snapshot-lab-web",
        "create:pyrange-snapshot-lab-web",
        "start:pyrange-snapshot-lab-web",
    ]


@patch("pyrange.engine.snapshot.start_container")
@patch(
    "pyrange.engine.snapshot."
    "connect_container_to_network"
)
@patch("pyrange.engine.snapshot.create_container")
@patch("pyrange.engine.snapshot.remove_container")
@patch("pyrange.engine.snapshot.get_image_id")
def test_restore_reconnects_secondary_networks(
    mock_get_image_id,
    mock_remove_container,
    mock_create_container,
    mock_connect_container_to_network,
    mock_start_container,
    multi_network_scenario: ScenarioConfig,
) -> None:
    mock_get_image_id.return_value = "sha256:snapshot123"

    restore_machine_snapshot(
        multi_network_scenario,
        machine_name="web",
        snapshot_name="checkpoint-1",
    )

    mock_create_container.assert_called_once_with(
        name="pyrange-snapshot-lab-web",
        image="sha256:snapshot123",
        network=(
            "pyrange-snapshot-lab-public-net"
        ),
        ip="172.28.40.10",
    )

    mock_connect_container_to_network.assert_called_once_with(
        name="pyrange-snapshot-lab-web",
        network=(
            "pyrange-snapshot-lab-private-net"
        ),
        ip="172.28.50.10",
    )

    mock_start_container.assert_called_once_with(
        "pyrange-snapshot-lab-web"
    )


@patch("pyrange.engine.snapshot.evaluate_health_check")
@patch("pyrange.engine.snapshot.start_container")
@patch("pyrange.engine.snapshot.create_container")
@patch("pyrange.engine.snapshot.remove_container")
@patch("pyrange.engine.snapshot.get_image_id")
def test_restore_evaluates_health_check(
    mock_get_image_id,
    mock_remove_container,
    mock_create_container,
    mock_start_container,
    mock_evaluate_health_check,
    scenario: ScenarioConfig,
) -> None:
    mock_get_image_id.return_value = "sha256:snapshot123"

    scenario.machines[0].health_check = HealthCheckConfig(
        command=["health-check"],
        retries=0,
    )

    mock_evaluate_health_check.return_value = (
        HealthCheckResult(
            healthy=True,
            attempts=1,
            exit_code=0,
            stdout="ready\n",
            stderr="",
        )
    )

    restore_machine_snapshot(
        scenario,
        machine_name="web",
        snapshot_name="checkpoint-1",
    )

    mock_evaluate_health_check.assert_called_once_with(
        "pyrange-snapshot-lab-web",
        scenario.machines[0].health_check,
    )


@patch("pyrange.engine.snapshot.evaluate_health_check")
@patch("pyrange.engine.snapshot.start_container")
@patch("pyrange.engine.snapshot.create_container")
@patch("pyrange.engine.snapshot.remove_container")
@patch("pyrange.engine.snapshot.get_image_id")
def test_restore_rejects_unhealthy_machine(
    mock_get_image_id,
    mock_remove_container,
    mock_create_container,
    mock_start_container,
    mock_evaluate_health_check,
    scenario: ScenarioConfig,
) -> None:
    mock_get_image_id.return_value = "sha256:snapshot123"

    scenario.machines[0].health_check = HealthCheckConfig(
        command=["health-check"],
        retries=0,
    )

    mock_evaluate_health_check.return_value = (
        HealthCheckResult(
            healthy=False,
            attempts=1,
            exit_code=1,
            stdout="",
            stderr="service unavailable\n",
        )
    )

    with pytest.raises(
        SnapshotError,
        match=(
            "Restored machine 'web' "
            "failed health check"
        ),
    ):
        restore_machine_snapshot(
            scenario,
            machine_name="web",
            snapshot_name="checkpoint-1",
        )


@patch("pyrange.engine.snapshot.remove_container")
@patch("pyrange.engine.snapshot.get_image_id")
def test_restore_checks_snapshot_before_removing_container(
    mock_get_image_id,
    mock_remove_container,
    scenario: ScenarioConfig,
) -> None:
    mock_get_image_id.side_effect = DockerOperationError(
        "No such image"
    )

    with pytest.raises(
        DockerOperationError,
        match="No such image",
    ):
        restore_machine_snapshot(
            scenario,
            machine_name="web",
            snapshot_name="checkpoint-1",
        )

    mock_get_image_id.assert_called_once_with(
        "pyrange-snapshots/"
        "snapshot-lab-web:checkpoint-1"
    )
    mock_remove_container.assert_not_called()


@patch("pyrange.engine.snapshot.remove_container")
def test_restore_rejects_unknown_machine(
    mock_remove_container,
    scenario: ScenarioConfig,
) -> None:
    with pytest.raises(
        SnapshotError,
        match="Machine 'missing' is not defined",
    ):
        restore_machine_snapshot(
            scenario,
            machine_name="missing",
            snapshot_name="checkpoint-1",
        )

    mock_remove_container.assert_not_called()


@patch("pyrange.engine.snapshot.remove_container")
def test_restore_rejects_invalid_snapshot_name_before_removal(
    mock_remove_container,
    scenario: ScenarioConfig,
) -> None:
    with pytest.raises(
        ValueError,
        match="snapshot name must be a valid Docker tag",
    ):
        restore_machine_snapshot(
            scenario,
            machine_name="web",
            snapshot_name="invalid/name",
        )

    mock_remove_container.assert_not_called()
