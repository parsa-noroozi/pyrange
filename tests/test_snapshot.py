from unittest.mock import patch

import pytest

from pyrange.engine import (
    MachineSnapshot,
    SnapshotError,
    create_machine_snapshot,
    get_snapshot_image_ref,
)
from pyrange.models import (
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
