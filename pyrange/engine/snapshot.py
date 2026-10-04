import re
from dataclasses import dataclass

from pyrange.engine.docker import create_container_snapshot
from pyrange.engine.manager import get_lab_container_name
from pyrange.models import MachineConfig, ScenarioConfig


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
