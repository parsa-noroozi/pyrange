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
from pyrange.engine.ownership import build_ownership_labels
from pyrange.models import (
    HealthCheckConfig,
    MachineConfig,
    NetworkConfig,
    NetworkInterfaceConfig,
    ScenarioConfig,
)


WEB_CONTAINER_NAME = (
    "pyrange-v2-container-"
    "a72b1735188af3b6fc188ccb131308e2549b3cdb40bb59c2ff48eb58e5ff4b2b"
)

LAB_NETWORK_NAME = (
    "pyrange-v2-network-"
    "acd1d32065691d60b08f07b36886b6edffdc48c3271c6cdc5f34f6d9d8658c0c"
)

PUBLIC_NETWORK_NAME = (
    "pyrange-v2-network-"
    "2fd34f153f539616bede1d0acecdfe54fcbeb06fc41e712d20eeee8c892c1afd"
)

PRIVATE_NETWORK_NAME = (
    "pyrange-v2-network-"
    "5b79cc70f0d5cf933d15f35197bf4d859311bdfb986f4836e938da1510f159b8"
)

SNAPSHOT_REPOSITORY_NAME = (
    "pyrange-v2-snapshot-"
    "70608625e6a6d15470792918e79ff8237bf46fae8048a3af6339b3ef3e9fe7ae"
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
        f"{SNAPSHOT_REPOSITORY_NAME}:checkpoint-1"
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
    snapshot_resources,
) -> None:
    mock_create_container_snapshot.return_value = (
        ("sha256:" + "c" * 64)
    )

    snapshot = create_machine_snapshot(
        scenario,
        machine_name="web",
        snapshot_name="checkpoint-1",
    )

    assert snapshot == MachineSnapshot(
        snapshot_name="checkpoint-1",
        machine_name="web",
        container_name=WEB_CONTAINER_NAME,
        image_ref=(
            "pyrange-snapshots/"
            f"{SNAPSHOT_REPOSITORY_NAME}:checkpoint-1"
        ),
        image_id=("sha256:" + "c" * 64),
    )

    mock_create_container_snapshot.assert_called_once_with(
        name=snapshot_resources.container.resource_id,
        image_ref=(
            "pyrange-snapshots/"
            f"{SNAPSHOT_REPOSITORY_NAME}:checkpoint-1"
        ),
        labels=build_ownership_labels("snapshot", "snapshot-lab", "web"),
    )


@patch(
    "pyrange.engine.snapshot."
    "create_container_snapshot"
)
def test_rejects_unknown_machine(
    mock_create_container_snapshot,
    scenario: ScenarioConfig,
    snapshot_resources,
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
@patch("pyrange.engine.snapshot.find_image_identity")
def test_restores_machine_snapshot(
    mock_find_image_identity,
    mock_remove_container,
    mock_create_container,
    mock_start_container,
    scenario: ScenarioConfig,
    snapshot_resources,
) -> None:
    mock_find_image_identity.return_value = snapshot_resources.image

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
        container_name=WEB_CONTAINER_NAME,
        image_ref=(
            "pyrange-snapshots/"
            f"{SNAPSHOT_REPOSITORY_NAME}:checkpoint-1"
        ),
        image_id=("sha256:" + "c" * 64),
    )

    mock_find_image_identity.assert_called_once_with(
        "pyrange-snapshots/"
        f"{SNAPSHOT_REPOSITORY_NAME}:checkpoint-1"
    )

    mock_create_container.assert_called_once_with(
        name=WEB_CONTAINER_NAME,
        image=("sha256:" + "c" * 64),
        network=LAB_NETWORK_NAME,
        ip="172.28.40.10",
        labels=build_ownership_labels("container", "snapshot-lab", "web"),
    )

    assert events == [
       f"remove:{snapshot_resources.container.resource_id}",
      f"create:{WEB_CONTAINER_NAME}",
       f"start:{WEB_CONTAINER_NAME}",
    ]


@patch("pyrange.engine.snapshot.start_container")
@patch(
    "pyrange.engine.snapshot."
    "connect_container_to_network"
)
@patch("pyrange.engine.snapshot.create_container")
@patch("pyrange.engine.snapshot.remove_container")
@patch("pyrange.engine.snapshot.find_image_identity")
def test_restore_reconnects_secondary_networks(
    mock_find_image_identity,
    mock_remove_container,
    mock_create_container,
    mock_connect_container_to_network,
    mock_start_container,
    multi_network_scenario: ScenarioConfig,
    snapshot_resources,
) -> None:
    mock_find_image_identity.return_value = snapshot_resources.image

    restore_machine_snapshot(
        multi_network_scenario,
        machine_name="web",
        snapshot_name="checkpoint-1",
    )

    mock_create_container.assert_called_once_with(
        name=WEB_CONTAINER_NAME,
        image=("sha256:" + "c" * 64),
        network=(
            PUBLIC_NETWORK_NAME
        ),
        ip="172.28.40.10",
        labels=build_ownership_labels("container", "snapshot-lab", "web"),
    )

    mock_connect_container_to_network.assert_called_once_with(
        name=WEB_CONTAINER_NAME,
        network=(
            PRIVATE_NETWORK_NAME
        ),
        ip="172.28.50.10",
    )

    mock_start_container.assert_called_once_with(
        WEB_CONTAINER_NAME
    )


@patch("pyrange.engine.snapshot.evaluate_health_check")
@patch("pyrange.engine.snapshot.start_container")
@patch("pyrange.engine.snapshot.create_container")
@patch("pyrange.engine.snapshot.remove_container")
@patch("pyrange.engine.snapshot.find_image_identity")
def test_restore_evaluates_health_check(
    mock_find_image_identity,
    mock_remove_container,
    mock_create_container,
    mock_start_container,
    mock_evaluate_health_check,
    scenario: ScenarioConfig,
    snapshot_resources,
) -> None:
    mock_find_image_identity.return_value = snapshot_resources.image

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
        WEB_CONTAINER_NAME,
        scenario.machines[0].health_check,
    )


@patch("pyrange.engine.snapshot.evaluate_health_check")
@patch("pyrange.engine.snapshot.start_container")
@patch("pyrange.engine.snapshot.create_container")
@patch("pyrange.engine.snapshot.remove_container")
@patch("pyrange.engine.snapshot.find_image_identity")
def test_restore_rejects_unhealthy_machine(
    mock_find_image_identity,
    mock_remove_container,
    mock_create_container,
    mock_start_container,
    mock_evaluate_health_check,
    scenario: ScenarioConfig,
    snapshot_resources,
) -> None:
    mock_find_image_identity.return_value = snapshot_resources.image

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
@patch("pyrange.engine.snapshot.find_image_identity")
def test_restore_checks_snapshot_before_removing_container(
    mock_find_image_identity,
    mock_remove_container,
    scenario: ScenarioConfig,
    snapshot_resources,
) -> None:
    mock_find_image_identity.side_effect = DockerOperationError(
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

    mock_find_image_identity.assert_called_once_with(
        "pyrange-snapshots/"
        f"{SNAPSHOT_REPOSITORY_NAME}:checkpoint-1"
    )
    mock_remove_container.assert_not_called()


@patch("pyrange.engine.snapshot.remove_container")
def test_restore_rejects_unknown_machine(
    mock_remove_container,
    scenario: ScenarioConfig,
    snapshot_resources,
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
    snapshot_resources,
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
