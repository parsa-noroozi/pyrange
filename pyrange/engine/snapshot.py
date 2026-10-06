import re
from dataclasses import dataclass

from pydantic import JsonValue

from pyrange.engine.docker import (
    connect_container_to_network,
    create_container,
    create_container_snapshot,
    get_image_id,
    remove_container,
    start_container,
)
from pyrange.engine.events import (
    EventOutcome,
    EventRecorder,
    EventResource,
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


def _validate_recorder(
    scenario: ScenarioConfig,
    recorder: EventRecorder | None,
    operation: str,
) -> None:
    if recorder is None:
        return

    if recorder.context.scenario != scenario.name:
        raise SnapshotError(
            "Event recorder scenario does not match "
            f"snapshot scenario '{scenario.name}'."
        )

    if recorder.context.operation != operation:
        raise SnapshotError(
            "Event recorder operation does not match "
            f"snapshot operation '{operation}'."
        )


def _emit_event(
    recorder: EventRecorder | None,
    event_type: str,
    *,
    outcome: EventOutcome | None = None,
    resource: EventResource | None = None,
    attributes: dict[str, JsonValue] | None = None,
) -> None:
    if recorder is None:
        return

    recorder.emit(
        event_type,
        outcome=outcome,
        resource=resource,
        attributes=attributes,
    )


def _emit_failure_path_event(
    recorder: EventRecorder | None,
    primary_error: Exception,
    event_type: str,
    *,
    outcome: EventOutcome | None = None,
    resource: EventResource | None = None,
    attributes: dict[str, JsonValue] | None = None,
) -> Exception | None:
    try:
        _emit_event(
            recorder,
            event_type,
            outcome=outcome,
            resource=resource,
            attributes=attributes,
        )
    except Exception as event_error:
        primary_error.add_note(
            "Failed to record snapshot event "
            f"'{event_type}': {event_error}"
        )
        return event_error

    return None


def _record_restore_event(
    recorder: EventRecorder | None,
    event_errors: list[Exception],
    event_type: str,
    *,
    outcome: EventOutcome | None = None,
    resource: EventResource | None = None,
    attributes: dict[str, JsonValue] | None = None,
) -> None:
    try:
        _emit_event(
            recorder,
            event_type,
            outcome=outcome,
            resource=resource,
            attributes=attributes,
        )
    except Exception as event_error:
        event_errors.append(event_error)


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
    *,
    recorder: EventRecorder | None = None,
) -> MachineSnapshot:
    _validate_recorder(
        scenario,
        recorder,
        "snapshot",
    )

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

    resource = EventResource(
        type="machine",
        name=machine.name,
    )

    _emit_event(
        recorder,
        "snapshot.requested",
        resource=resource,
        attributes={
            "snapshot_name": snapshot_name,
            "runtime_name": container_name,
            "image_ref": image_ref,
        },
    )

    try:
        image_id = create_container_snapshot(
            name=container_name,
            image_ref=image_ref,
        )
    except Exception as exc:
        _emit_failure_path_event(
            recorder,
            exc,
            "snapshot.failed",
            outcome="failure",
            resource=resource,
            attributes={
                "snapshot_name": snapshot_name,
                "runtime_name": container_name,
                "image_ref": image_ref,
                "error_type": type(exc).__name__,
                "snapshot_created": False,
            },
        )
        raise

    result = MachineSnapshot(
        snapshot_name=snapshot_name,
        machine_name=machine.name,
        container_name=container_name,
        image_ref=image_ref,
        image_id=image_id,
    )

    try:
        _emit_event(
            recorder,
            "snapshot.created",
            outcome="success",
            resource=resource,
            attributes={
                "snapshot_name": snapshot_name,
                "runtime_name": container_name,
                "image_ref": image_ref,
                "image_id": image_id,
            },
        )
    except Exception as exc:
        exc.add_note(
            "The snapshot image was created before "
            "event logging failed."
        )

        _emit_failure_path_event(
            recorder,
            exc,
            "snapshot.failed",
            outcome="failure",
            resource=resource,
            attributes={
                "snapshot_name": snapshot_name,
                "runtime_name": container_name,
                "image_ref": image_ref,
                "image_id": image_id,
                "error_type": type(exc).__name__,
                "snapshot_created": True,
            },
        )

        raise

    return result


def restore_machine_snapshot(
    scenario: ScenarioConfig,
    machine_name: str,
    snapshot_name: str,
    *,
    recorder: EventRecorder | None = None,
) -> MachineRestoreResult:
    _validate_recorder(
        scenario,
        recorder,
        "restore",
    )

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

    resource = EventResource(
        type="machine",
        name=machine.name,
    )

    _emit_event(
        recorder,
        "restore.requested",
        resource=resource,
        attributes={
            "snapshot_name": snapshot_name,
            "runtime_name": container_name,
            "image_ref": image_ref,
        },
    )

    network_names = {
        network.name: get_lab_network_name(
            scenario,
            network,
        )
        for network in scenario.networks
    }

    primary_interface = machine.interfaces[0]
    event_errors: list[Exception] = []
    destructive_started = False
    stage = "preflight"

    try:
        image_id = get_image_id(image_ref)

        stage = "remove_container"
        destructive_started = True
        remove_container(container_name)

        _record_restore_event(
            recorder,
            event_errors,
            "restore.container.removed",
            outcome="success",
            resource=resource,
            attributes={
                "runtime_name": container_name,
            },
        )

        stage = "create_container"
        primary_network_name = network_names[
            primary_interface.network
        ]

        create_container(
            name=container_name,
            image=image_id,
            network=primary_network_name,
            ip=str(primary_interface.ip),
        )

        _record_restore_event(
            recorder,
            event_errors,
            "restore.container.created",
            outcome="success",
            resource=resource,
            attributes={
                "runtime_name": container_name,
                "image_id": image_id,
            },
        )

        _record_restore_event(
            recorder,
            event_errors,
            "restore.network.attached",
            outcome="success",
            resource=resource,
            attributes={
                "network": primary_interface.network,
                "runtime_network": primary_network_name,
                "ip": str(primary_interface.ip),
                "primary": True,
            },
        )

        stage = "attach_networks"

        for interface in machine.interfaces[1:]:
            runtime_network = network_names[
                interface.network
            ]

            connect_container_to_network(
                name=container_name,
                network=runtime_network,
                ip=str(interface.ip),
            )

            _record_restore_event(
                recorder,
                event_errors,
                "restore.network.attached",
                outcome="success",
                resource=resource,
                attributes={
                    "network": interface.network,
                    "runtime_network": runtime_network,
                    "ip": str(interface.ip),
                    "primary": False,
                },
            )

        stage = "start_container"
        start_container(container_name)

        _record_restore_event(
            recorder,
            event_errors,
            "restore.container.started",
            outcome="success",
            resource=resource,
            attributes={
                "runtime_name": container_name,
            },
        )

        if machine.health_check is not None:
            stage = "health_check"

            health_result = evaluate_health_check(
                container_name,
                machine.health_check,
            )

            health_attributes: dict[str, JsonValue] = {
                "attempts": health_result.attempts,
                "exit_code": health_result.exit_code,
            }

            if health_result.healthy:
                _record_restore_event(
                    recorder,
                    event_errors,
                    "health.passed",
                    outcome="success",
                    resource=resource,
                    attributes=health_attributes,
                )
            else:
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

                health_error = SnapshotError(
                    f"Restored machine '{machine.name}' "
                    f"failed health check after "
                    f"{health_result.attempts} attempt(s): "
                    f"{details}"
                )

                event_error = _emit_failure_path_event(
                    recorder,
                    health_error,
                    "health.failed",
                    outcome="failure",
                    resource=resource,
                    attributes=health_attributes,
                )

                if event_error is not None:
                    event_errors.append(event_error)

                raise health_error

        result = MachineRestoreResult(
            snapshot_name=snapshot_name,
            machine_name=machine.name,
            container_name=container_name,
            image_ref=image_ref,
            image_id=image_id,
        )

    except Exception as exc:
        for event_error in event_errors:
            exc.add_note(
                "Event logging also failed during "
                f"restore: {event_error}"
            )

        _emit_failure_path_event(
            recorder,
            exc,
            "restore.failed",
            outcome="failure",
            resource=resource,
            attributes={
                "snapshot_name": snapshot_name,
                "runtime_name": container_name,
                "image_ref": image_ref,
                "error_type": type(exc).__name__,
                "stage": stage,
                "destructive_started": destructive_started,
                "event_error_count": len(event_errors),
                "operational_completed": False,
            },
        )

        raise

    if event_errors:
        error = event_errors[0]

        for event_error in event_errors[1:]:
            error.add_note(
                "Additional event logging failure "
                f"during restore: {event_error}"
            )

        error.add_note(
            "Restore infrastructure completed before "
            "the event logging failure was reported."
        )

        _emit_failure_path_event(
            recorder,
            error,
            "restore.failed",
            outcome="failure",
            resource=resource,
            attributes={
                "snapshot_name": snapshot_name,
                "runtime_name": container_name,
                "image_ref": image_ref,
                "image_id": image_id,
                "error_type": type(error).__name__,
                "stage": "event_logging",
                "destructive_started": True,
                "event_error_count": len(event_errors),
                "operational_completed": True,
            },
        )

        raise error

    try:
        _emit_event(
            recorder,
            "restore.completed",
            outcome="success",
            resource=resource,
            attributes={
                "snapshot_name": snapshot_name,
                "runtime_name": container_name,
                "image_ref": image_ref,
                "image_id": image_id,
            },
        )
    except Exception as exc:
        exc.add_note(
            "Restore infrastructure completed before "
            "the completion event failed."
        )

        _emit_failure_path_event(
            recorder,
            exc,
            "restore.failed",
            outcome="failure",
            resource=resource,
            attributes={
                "snapshot_name": snapshot_name,
                "runtime_name": container_name,
                "image_ref": image_ref,
                "image_id": image_id,
                "error_type": type(exc).__name__,
                "stage": "event_logging",
                "destructive_started": True,
                "event_error_count": 1,
                "operational_completed": True,
            },
        )

        raise

    return result
