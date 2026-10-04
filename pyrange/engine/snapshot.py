import re
from dataclasses import dataclass

from pyrange.engine.docker import (
    connect_container_to_network,
    create_container,
    create_container_snapshot,
    get_image_id,
    remove_container,
    start_container,
)
from pyrange.engine.health import evaluate_health_check
from pyrange.engine.manager import (
    get_lab_container_name,
    get_lab_network_name,
)
from pyrange.models import (
    MachineConfig,
    ScenarioConfig,
)


_SNAPSHOT_NAME_PATTERN = re.compile(
    r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$"
)


class SnapshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class MachineSnapshot:
    snapshot_name: str
    machine_name: str
    container_name: str
    image_ref: str
    image_id: str


@dataclass(frozen=True)
class MachineRestoreResult:
    snapshot_name: str
    machine_name: str
    container_name: str
    image_ref: str
    image_id: str


def _get_machine(
    scenario: ScenarioConfig,
    machine_name: str,
) -> MachineConfig:
    machine = next(
        (
            machine
            for machine in scenario.machines
            if machine.name == machine_name
        ),
        None,
    )

    if machine is None:
        raise SnapshotError(
            f"Machine '{machine_name}' is not defined "
            f"in scenario '{scenario.name}'."
        )

    return machine


def get_snapshot_image_ref(
    scenario: ScenarioConfig,
    machine: MachineConfig,
    snapshot_name: str,
) -> str:
    if not _SNAPSHOT_NAME_PATTERN.fullmatch(
        snapshot_name
    ):
        raise ValueError(
            "snapshot name must be a valid Docker tag"
        )

    return (
        f"pyrange-snapshots/"
        f"{scenario.name}-{machine.name}:"
        f"{snapshot_name}"
    )


def create_machine_snapshot(
    scenario: ScenarioConfig,
    machine_name: str,
    snapshot_name: str,
) -> MachineSnapshot:
    machine = _get_machine(
        scenario,
        machine_name,
    )

    container_name = get_lab_container_name(
        scenario,
        machine,
    )

    image_ref = get_snapshot_image_ref(
        scenario,
        machine,
        snapshot_name,
    )

    image_id = create_container_snapshot(
        name=container_name,
        image_ref=image_ref,
    )

    return MachineSnapshot(
        snapshot_name=snapshot_name,
        machine_name=machine.name,
        container_name=container_name,
        image_ref=image_ref,
        image_id=image_id,
    )


def restore_machine_snapshot(
    scenario: ScenarioConfig,
    machine_name: str,
    snapshot_name: str,
) -> MachineRestoreResult:
    machine = _get_machine(
        scenario,
        machine_name,
    )

    container_name = get_lab_container_name(
        scenario,
        machine,
    )

    image_ref = get_snapshot_image_ref(
        scenario,
        machine,
        snapshot_name,
    )

    image_id = get_image_id(image_ref)

    network_names = {
        network.name: get_lab_network_name(
            scenario,
            network,
        )
        for network in scenario.networks
    }

    primary_interface = machine.interfaces[0]

    remove_container(container_name)

    create_container(
        name=container_name,
        image=image_id,
        network=network_names[
            primary_interface.network
        ],
        ip=str(primary_interface.ip),
    )

    for interface in machine.interfaces[1:]:
        connect_container_to_network(
            name=container_name,
            network=network_names[
                interface.network
            ],
            ip=str(interface.ip),
        )

    start_container(container_name)

    if machine.health_check is not None:
        health_result = evaluate_health_check(
            container_name,
            machine.health_check,
        )

        if not health_result.healthy:
            details = (
                health_result.stderr.strip()
                or health_result.stdout.strip()
            )

            if not details:
                if health_result.exit_code is None:
                    details = "no diagnostic output"
                else:
                    details = (
                        f"exit code "
                        f"{health_result.exit_code}"
                    )

            raise SnapshotError(
                f"Restored machine '{machine.name}' "
                f"failed health check after "
                f"{health_result.attempts} attempt(s): "
                f"{details}"
            )

    return MachineRestoreResult(
        snapshot_name=snapshot_name,
        machine_name=machine.name,
        container_name=container_name,
        image_ref=image_ref,
        image_id=image_id,
    )
