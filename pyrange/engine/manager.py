from pyrange.engine.docker import (
    DockerOperationError,
    DockerUnavailableError,
    create_container,
    create_network,
    remove_container,
    remove_network,
    start_container,
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
    return f"pyrange-{scenario.name}-{network.name}"


def get_lab_container_name(
    scenario: ScenarioConfig,
    machine: MachineConfig,
) -> str:
    return f"pyrange-{scenario.name}-{machine.name}"


def start_lab(scenario: ScenarioConfig) -> None:
    if len(scenario.networks) != 1:
        raise LabManagerError(
            "multi-network orchestration is not implemented yet"
        )

    network = scenario.networks[0]
    network_name = get_lab_network_name(
        scenario,
        network,
    )

    created_containers: list[str] = []
    network_created = False

    try:
        create_network(
            network_name,
            str(network.subnet),
        )
        network_created = True

        for machine in scenario.machines:
            container_name = get_lab_container_name(
                scenario,
                machine,
            )

            interface = machine.interfaces[0]

            create_container(
                name=container_name,
                image=machine.image,
                network=network_name,
                ip=str(interface.ip),
            )

            created_containers.append(container_name)
            start_container(container_name)

    except (DockerOperationError, DockerUnavailableError):
        for container_name in reversed(created_containers):
            try:
                remove_container(container_name)
            except (DockerOperationError, DockerUnavailableError):
                pass

        if network_created:
            try:
                remove_network(network_name)
            except (DockerOperationError, DockerUnavailableError):
                pass

        raise


def stop_lab(scenario: ScenarioConfig) -> None:
    if len(scenario.networks) != 1:
        raise LabManagerError(
            "multi-network orchestration is not implemented yet"
        )

    errors: list[str] = []

    for machine in reversed(scenario.machines):
        container_name = get_lab_container_name(
            scenario,
            machine,
        )

        try:
            remove_container(container_name)
        except (DockerOperationError, DockerUnavailableError) as exc:
            errors.append(str(exc))

    network_name = get_lab_network_name(
        scenario,
        scenario.networks[0],
    )

    try:
        remove_network(network_name)
    except (DockerOperationError, DockerUnavailableError) as exc:
        errors.append(str(exc))

    if errors:
        raise LabManagerError(
            "Failed to fully stop lab: " + "; ".join(errors)
        )
