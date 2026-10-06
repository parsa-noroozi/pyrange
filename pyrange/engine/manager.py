from pydantic import JsonValue

from pyrange.engine.docker import (
    DockerOperationError,
    DockerUnavailableError,
    connect_container_to_network,
    create_container,
    create_network,
    remove_container,
    remove_network,
    start_container,
)
from pyrange.engine.events import (
    EventOutcome,
    EventRecorder,
    EventResource,
)
from pyrange.engine.health import evaluate_health_check
from pyrange.models import (
    MachineConfig,
    NetworkConfig,
    ScenarioConfig,
)


class LabManagerError(RuntimeError):
    pass


def get_lab_network_name(
    scenario: ScenarioConfig,
    network: NetworkConfig,
) -> str:
    return f"pyrange-{scenario.name}-{network.name}"


def get_lab_container_name(
    scenario: ScenarioConfig,
    machine: MachineConfig,
) -> str:
    return f"pyrange-{scenario.name}-{machine.name}"


def _validate_recorder(
    scenario: ScenarioConfig,
    recorder: EventRecorder | None,
    operation: str,
) -> None:
    if recorder is None:
        return

    if recorder.context.scenario != scenario.name:
        raise LabManagerError(
            "Event recorder scenario does not match "
            f"lab scenario '{scenario.name}'."
        )

    if recorder.context.operation != operation:
        raise LabManagerError(
            "Event recorder operation does not match "
            f"lab operation '{operation}'."
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
        primary_error.add_note(
            "Failed to record lifecycle event "
            f"'{event_type}': {event_error}"
        )


def _record_stop_event(
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


def start_lab(
    scenario: ScenarioConfig,
    *,
    recorder: EventRecorder | None = None,
) -> None:
    _validate_recorder(
        scenario,
        recorder,
        "start",
    )

    _emit_event(
        recorder,
        "lab.start.requested",
    )

    created_networks: list[
        tuple[NetworkConfig, str]
    ] = []
    created_containers: list[
        tuple[MachineConfig, str]
    ] = []

    network_names = {
        network.name: get_lab_network_name(
            scenario,
            network,
        )
        for network in scenario.networks
    }

    try:
        for network in scenario.networks:
            network_name = network_names[network.name]

            create_network(
                network_name,
                str(network.subnet),
            )

            created_networks.append(
                (network, network_name)
            )

            _emit_event(
                recorder,
                "network.created",
                outcome="success",
                resource=EventResource(
                    type="network",
                    name=network.name,
                ),
                attributes={
                    "runtime_name": network_name,
                    "subnet": str(network.subnet),
                },
            )

        for machine in scenario.machines:
            container_name = get_lab_container_name(
                scenario,
                machine,
            )

            primary_interface = machine.interfaces[0]
            primary_network_name = network_names[
                primary_interface.network
            ]

            create_container(
                name=container_name,
                image=machine.image,
                network=primary_network_name,
                ip=str(primary_interface.ip),
            )

            created_containers.append(
                (machine, container_name)
            )

            _emit_event(
                recorder,
                "machine.created",
                outcome="success",
                resource=EventResource(
                    type="machine",
                    name=machine.name,
                ),
                attributes={
                    "runtime_name": container_name,
                    "image": machine.image,
                },
            )

            _emit_event(
                recorder,
                "machine.network.attached",
                outcome="success",
                resource=EventResource(
                    type="machine",
                    name=machine.name,
                ),
                attributes={
                    "network": primary_interface.network,
                    "runtime_network": (
                        primary_network_name
                    ),
                    "ip": str(primary_interface.ip),
                    "primary": True,
                },
            )

            for interface in machine.interfaces[1:]:
                runtime_network = network_names[
                    interface.network
                ]

                connect_container_to_network(
                    name=container_name,
                    network=runtime_network,
                    ip=str(interface.ip),
                )

                _emit_event(
                    recorder,
                    "machine.network.attached",
                    outcome="success",
                    resource=EventResource(
                        type="machine",
                        name=machine.name,
                    ),
                    attributes={
                        "network": interface.network,
                        "runtime_network": (
                            runtime_network
                        ),
                        "ip": str(interface.ip),
                        "primary": False,
                    },
                )

            start_container(container_name)

            _emit_event(
                recorder,
                "machine.started",
                outcome="success",
                resource=EventResource(
                    type="machine",
                    name=machine.name,
                ),
                attributes={
                    "runtime_name": container_name,
                },
            )

        for machine in scenario.machines:
            if machine.health_check is None:
                continue

            container_name = get_lab_container_name(
                scenario,
                machine,
            )

            result = evaluate_health_check(
                container_name,
                machine.health_check,
            )

            health_attributes: dict[str, JsonValue] = {
                "attempts": result.attempts,
                "exit_code": result.exit_code,
            }

            if result.healthy:
                _emit_event(
                    recorder,
                    "health.passed",
                    outcome="success",
                    resource=EventResource(
                        type="machine",
                        name=machine.name,
                    ),
                    attributes=health_attributes,
                )
                continue

            details = (
                result.stderr.strip()
                or result.stdout.strip()
            )

            if not details:
                if result.exit_code is None:
                    details = "no diagnostic output"
                else:
                    details = (
                        f"exit code {result.exit_code}"
                    )

            health_error = LabManagerError(
                f"Health check failed for machine "
                f"'{machine.name}' after "
                f"{result.attempts} attempt(s): "
                f"{details}"
            )

            _emit_failure_path_event(
                recorder,
                health_error,
                "health.failed",
                outcome="failure",
                resource=EventResource(
                    type="machine",
                    name=machine.name,
                ),
                attributes=health_attributes,
            )

            raise health_error

        _emit_event(
            recorder,
            "lab.start.completed",
            outcome="success",
        )

    except Exception as exc:
        rollback_errors = 0

        for machine, container_name in reversed(
            created_containers
        ):
            try:
                remove_container(container_name)
            except Exception as cleanup_error:
                rollback_errors += 1

                _emit_failure_path_event(
                    recorder,
                    exc,
                    "resource.rollback.failed",
                    outcome="failure",
                    resource=EventResource(
                        type="machine",
                        name=machine.name,
                    ),
                    attributes={
                        "runtime_name": container_name,
                        "error_type": type(
                            cleanup_error
                        ).__name__,
                    },
                )
            else:
                _emit_failure_path_event(
                    recorder,
                    exc,
                    "resource.rollback.removed",
                    outcome="success",
                    resource=EventResource(
                        type="machine",
                        name=machine.name,
                    ),
                    attributes={
                        "runtime_name": container_name,
                    },
                )

        for network, network_name in reversed(
            created_networks
        ):
            try:
                remove_network(network_name)
            except Exception as cleanup_error:
                rollback_errors += 1

                _emit_failure_path_event(
                    recorder,
                    exc,
                    "resource.rollback.failed",
                    outcome="failure",
                    resource=EventResource(
                        type="network",
                        name=network.name,
                    ),
                    attributes={
                        "runtime_name": network_name,
                        "error_type": type(
                            cleanup_error
                        ).__name__,
                    },
                )
            else:
                _emit_failure_path_event(
                    recorder,
                    exc,
                    "resource.rollback.removed",
                    outcome="success",
                    resource=EventResource(
                        type="network",
                        name=network.name,
                    ),
                    attributes={
                        "runtime_name": network_name,
                    },
                )

        _emit_failure_path_event(
            recorder,
            exc,
            "lab.start.failed",
            outcome="failure",
            attributes={
                "error_type": type(exc).__name__,
                "rollback_error_count": (
                    rollback_errors
                ),
            },
        )

        raise


def stop_lab(
    scenario: ScenarioConfig,
    *,
    recorder: EventRecorder | None = None,
) -> None:
    _validate_recorder(
        scenario,
        recorder,
        "stop",
    )

    errors: list[str] = []
    event_errors: list[Exception] = []

    _record_stop_event(
        recorder,
        event_errors,
        "lab.stop.requested",
    )

    for machine in reversed(scenario.machines):
        container_name = get_lab_container_name(
            scenario,
            machine,
        )

        try:
            remove_container(container_name)
        except (
            DockerOperationError,
            DockerUnavailableError,
        ) as exc:
            errors.append(str(exc))

            _record_stop_event(
                recorder,
                event_errors,
                "machine.remove.failed",
                outcome="failure",
                resource=EventResource(
                    type="machine",
                    name=machine.name,
                ),
                attributes={
                    "runtime_name": container_name,
                    "error_type": type(exc).__name__,
                },
            )
        else:
            _record_stop_event(
                recorder,
                event_errors,
                "machine.removed",
                outcome="success",
                resource=EventResource(
                    type="machine",
                    name=machine.name,
                ),
                attributes={
                    "runtime_name": container_name,
                },
            )

    for network in reversed(scenario.networks):
        network_name = get_lab_network_name(
            scenario,
            network,
        )

        try:
            remove_network(network_name)
        except (
            DockerOperationError,
            DockerUnavailableError,
        ) as exc:
            errors.append(str(exc))

            _record_stop_event(
                recorder,
                event_errors,
                "network.remove.failed",
                outcome="failure",
                resource=EventResource(
                    type="network",
                    name=network.name,
                ),
                attributes={
                    "runtime_name": network_name,
                    "error_type": type(exc).__name__,
                },
            )
        else:
            _record_stop_event(
                recorder,
                event_errors,
                "network.removed",
                outcome="success",
                resource=EventResource(
                    type="network",
                    name=network.name,
                ),
                attributes={
                    "runtime_name": network_name,
                },
            )

    if errors:
        error = LabManagerError(
            "Failed to fully stop lab: "
            + "; ".join(errors)
        )

        for event_error in event_errors:
            error.add_note(
                "Event logging also failed during "
                f"stop: {event_error}"
            )

        _emit_failure_path_event(
            recorder,
            error,
            "lab.stop.failed",
            outcome="failure",
            attributes={
                "operational_error_count": len(errors),
                "event_error_count": len(event_errors),
            },
        )

        raise error

    if event_errors:
        error = event_errors[0]

        for event_error in event_errors[1:]:
            error.add_note(
                "Additional event logging failure "
                f"during stop: {event_error}"
            )

        _emit_failure_path_event(
            recorder,
            error,
            "lab.stop.failed",
            outcome="failure",
            attributes={
                "operational_error_count": 0,
                "event_error_count": len(event_errors),
            },
        )

        raise error

    _emit_event(
        recorder,
        "lab.stop.completed",
        outcome="success",
    )
