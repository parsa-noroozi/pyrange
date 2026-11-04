from pydantic import JsonValue

from pyrange.engine.docker import (
    DockerOperationError,
    DockerUnavailableError,
    connect_container_to_network,
    create_container,
    create_network,
    find_container_identity,
    find_network_identity,
    inspect_container_identity,
    inspect_network_identity,
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
from pyrange.engine.legacy import (
    describe_candidate,
    require_no_legacy_resources,
    scan_legacy_resources,
)
from pyrange.engine.naming import build_resource_name
from pyrange.engine.ownership import (
    ResourceOwnershipError,
    build_ownership_labels,
    verify_resource_ownership,
)
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
    return build_resource_name(
        kind="network",
        scenario_name=scenario.name,
        resource_name=network.name,
    )


def get_lab_container_name(
    scenario: ScenarioConfig,
    machine: MachineConfig,
) -> str:
    return build_resource_name(
        kind="container",
        scenario_name=scenario.name,
        resource_name=machine.name,
    )


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


def _verify_rollback_identity(
    resource_id: str,
    *,
    kind: str,
    scenario_name: str,
    resource_name: str,
) -> None:
    # Never resolve a creation ID through a possibly reused runtime name.
    if (
        not isinstance(resource_id, str)
        or len(resource_id) != 64
        or any(character not in "0123456789abcdef" for character in resource_id)
    ):
        raise ResourceOwnershipError("Invalid resource ID recorded during creation.")

    if kind == "container":
        identity = inspect_container_identity(resource_id)
    elif kind == "network":
        identity = inspect_network_identity(resource_id)
    else:
        raise ValueError("unsupported rollback resource kind")

    if identity.resource_id != resource_id:
        raise ResourceOwnershipError("Rollback inspection returned a different resource ID.")

    verify_resource_ownership(
        identity.labels,
        kind=kind,
        scenario_name=scenario_name,
        resource_name=resource_name,
    )


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
        tuple[NetworkConfig, str, str]
    ] = []
    created_containers: list[
        tuple[MachineConfig, str, str]
    ] = []

    network_names = {
        network.name: get_lab_network_name(
            scenario,
            network,
        )
        for network in scenario.networks
    }

    try:
        require_no_legacy_resources(scenario)
        for network in scenario.networks:
            network_name = network_names[network.name]

            network_id = create_network(
                network_name,
                str(network.subnet),
                labels=build_ownership_labels(
                    kind="network",
                    scenario_name=scenario.name,
                    resource_name=network.name,
                ),
            )

            created_networks.append(
                (network, network_name, network_id)
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

            container_id = create_container(
                name=container_name,
                image=machine.image,
                network=primary_network_name,
                ip=str(primary_interface.ip),
                labels=build_ownership_labels(
                    kind="container",
                    scenario_name=scenario.name,
                    resource_name=machine.name,
                ),
            )

            created_containers.append(
                (machine, container_name, container_id)
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

        for machine, container_name, container_id in reversed(
            created_containers
        ):
            try:
                _verify_rollback_identity(
                    container_id,
                    kind="container",
                    scenario_name=scenario.name,
                    resource_name=machine.name,
                )
                remove_container(container_id)
            except Exception as cleanup_error:
                rollback_errors += 1
                exc.add_note(
                    f"Rollback failed for container '{container_name}' "
                    f"(ID {container_id}): {cleanup_error}"
                )

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

        for network, network_name, network_id in reversed(
            created_networks
        ):
            try:
                _verify_rollback_identity(
                    network_id,
                    kind="network",
                    scenario_name=scenario.name,
                    resource_name=network.name,
                )
                remove_network(network_id)
            except Exception as cleanup_error:
                rollback_errors += 1
                exc.add_note(
                    f"Rollback failed for network '{network_name}' "
                    f"(ID {network_id}): {cleanup_error}"
                )

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

    legacy_scan = scan_legacy_resources(scenario)
    for candidate in legacy_scan.candidates:
        errors.append(describe_candidate(candidate))
        _record_stop_event(
            recorder, event_errors, "resource.legacy.detected",
            outcome="failure",
            resource=EventResource(
                type="machine" if candidate.kind == "container" else candidate.kind,
                name=candidate.logical_name,
            ),
            attributes={
                "runtime_name": candidate.runtime_name,
                "runtime_id": candidate.resource_id,
                "ownership_verified": False,
            },
        )
    for failure in legacy_scan.failures:
        errors.append(
            f"Could not check legacy {failure.kind} name "
            f"'{failure.runtime_name}': {failure.error}"
        )
        _record_stop_event(
            recorder, event_errors, "legacy.discovery.failed",
            outcome="failure",
            resource=EventResource(
                type="machine" if failure.kind == "container" else failure.kind,
                name=failure.logical_name,
            ),
            attributes={
                "runtime_name": failure.runtime_name,
                "error_type": type(failure.error).__name__,
            },
        )

    for machine in reversed(scenario.machines):
        container_name = get_lab_container_name(
            scenario,
            machine,
        )

        try:
            identity = find_container_identity(container_name)

            if identity is None:
                _record_stop_event(
                    recorder,
                    event_errors,
                    "machine.absent",
                    resource=EventResource(
                        type="machine",
                        name=machine.name,
                    ),
                    attributes={
                        "runtime_name": container_name,
                    },
                )
                continue

            verify_resource_ownership(
                identity.labels,
                kind="container",
                scenario_name=scenario.name,
                resource_name=machine.name,
            )

            remove_container(identity.resource_id)
        except (
            DockerOperationError,
            DockerUnavailableError,
            ResourceOwnershipError,
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
            identity = find_network_identity(network_name)

            if identity is None:
                _record_stop_event(
                    recorder,
                    event_errors,
                    "network.absent",
                    resource=EventResource(
                        type="network",
                        name=network.name,
                    ),
                    attributes={
                        "runtime_name": network_name,
                    },
                )
                continue

            verify_resource_ownership(
                identity.labels,
                kind="network",
                scenario_name=scenario.name,
                resource_name=network.name,
            )

            remove_network(identity.resource_id)
        except (
            DockerOperationError,
            DockerUnavailableError,
            ResourceOwnershipError,
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
