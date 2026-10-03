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


def start_lab(scenario: ScenarioConfig) -> None:
    created_networks: list[str] = []
    created_containers: list[str] = []

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

            created_networks.append(network_name)

        for machine in scenario.machines:
            container_name = get_lab_container_name(
                scenario,
                machine,
            )

            primary_interface = machine.interfaces[0]

            create_container(
                name=container_name,
                image=machine.image,
                network=network_names[
                    primary_interface.network
                ],
                ip=str(primary_interface.ip),
            )

            created_containers.append(container_name)

            for interface in machine.interfaces[1:]:
                connect_container_to_network(
                    name=container_name,
                    network=network_names[
                        interface.network
                    ],
                    ip=str(interface.ip),
                )

            start_container(container_name)

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

            if result.healthy:
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

            raise LabManagerError(
                f"Health check failed for machine "
                f"'{machine.name}' after "
                f"{result.attempts} attempt(s): "
                f"{details}"
            )

    except (
        DockerOperationError,
        DockerUnavailableError,
        LabManagerError,
    ):
        for container_name in reversed(
            created_containers
        ):
            try:
                remove_container(container_name)
            except (
                DockerOperationError,
                DockerUnavailableError,
            ):
                pass

        for network_name in reversed(created_networks):
            try:
                remove_network(network_name)
            except (
                DockerOperationError,
                DockerUnavailableError,
            ):
                pass

        raise


def stop_lab(scenario: ScenarioConfig) -> None:
    errors: list[str] = []

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

    if errors:
        raise LabManagerError(
            "Failed to fully stop lab: "
            + "; ".join(errors)
        )
