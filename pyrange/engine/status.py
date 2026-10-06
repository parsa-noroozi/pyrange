from dataclasses import dataclass
from typing import Literal

from pyrange.engine.docker import (
    ContainerRuntimeState,
    inspect_container_runtime,
    inspect_network_runtime,
)
from pyrange.engine.manager import (
    get_lab_container_name,
    get_lab_network_name,
)
from pyrange.models import (
    MachineConfig,
    NetworkConfig,
    NetworkInterfaceConfig,
    ScenarioConfig,
)


ResourceMatchState = Literal[
    "matching",
    "missing",
    "drifted",
]

MachineState = Literal[
    "running",
    "stopped",
    "missing",
    "drifted",
]

LabState = Literal[
    "running",
    "stopped",
    "partial",
    "drifted",
]


@dataclass(frozen=True)
class NetworkStatus:
    name: str
    runtime_name: str
    state: ResourceMatchState
    expected_subnet: str
    actual_subnets: tuple[str, ...]


@dataclass(frozen=True)
class MachineInterfaceStatus:
    network: str
    runtime_network: str
    state: ResourceMatchState
    expected_ip: str
    actual_ip: str | None


@dataclass(frozen=True)
class MachineStatus:
    name: str
    runtime_name: str
    state: MachineState
    container_state: str | None
    interfaces: tuple[MachineInterfaceStatus, ...]
    unexpected_networks: tuple[str, ...]


@dataclass(frozen=True)
class LabStatus:
    scenario_name: str
    state: LabState
    networks: tuple[NetworkStatus, ...]
    machines: tuple[MachineStatus, ...]


def _inspect_network_status(
    scenario: ScenarioConfig,
    network: NetworkConfig,
) -> NetworkStatus:
    runtime_name = get_lab_network_name(
        scenario,
        network,
    )

    runtime = inspect_network_runtime(runtime_name)

    expected_subnet = str(network.subnet)

    if runtime is None:
        return NetworkStatus(
            name=network.name,
            runtime_name=runtime_name,
            state="missing",
            expected_subnet=expected_subnet,
            actual_subnets=(),
        )

    expected_subnets = (expected_subnet,)

    state: ResourceMatchState

    if runtime.subnets == expected_subnets:
        state = "matching"
    else:
        state = "drifted"

    return NetworkStatus(
        name=network.name,
        runtime_name=runtime_name,
        state=state,
        expected_subnet=expected_subnet,
        actual_subnets=runtime.subnets,
    )


def _inspect_interface_status(
    scenario: ScenarioConfig,
    interface: NetworkInterfaceConfig,
    networks_by_name: dict[str, NetworkConfig],
    runtime: ContainerRuntimeState,
) -> MachineInterfaceStatus:
    network = networks_by_name[interface.network]

    runtime_network = get_lab_network_name(
        scenario,
        network,
    )

    attachments = {
        attachment.network_name: attachment
        for attachment in runtime.networks
    }

    attachment = attachments.get(runtime_network)

    expected_ip = str(interface.ip)

    if attachment is None:
        return MachineInterfaceStatus(
            network=interface.network,
            runtime_network=runtime_network,
            state="missing",
            expected_ip=expected_ip,
            actual_ip=None,
        )

    state: ResourceMatchState

    if attachment.ip_address == expected_ip:
        state = "matching"
    else:
        state = "drifted"

    return MachineInterfaceStatus(
        network=interface.network,
        runtime_network=runtime_network,
        state=state,
        expected_ip=expected_ip,
        actual_ip=attachment.ip_address,
    )


def _missing_interface_statuses(
    scenario: ScenarioConfig,
    machine: MachineConfig,
    networks_by_name: dict[str, NetworkConfig],
) -> tuple[MachineInterfaceStatus, ...]:
    statuses: list[MachineInterfaceStatus] = []

    for interface in machine.interfaces:
        network = networks_by_name[interface.network]

        statuses.append(
            MachineInterfaceStatus(
                network=interface.network,
                runtime_network=get_lab_network_name(
                    scenario,
                    network,
                ),
                state="missing",
                expected_ip=str(interface.ip),
                actual_ip=None,
            )
        )

    return tuple(statuses)


def _inspect_machine_status(
    scenario: ScenarioConfig,
    machine: MachineConfig,
    networks_by_name: dict[str, NetworkConfig],
) -> MachineStatus:
    runtime_name = get_lab_container_name(
        scenario,
        machine,
    )

    runtime = inspect_container_runtime(runtime_name)

    if runtime is None:
        return MachineStatus(
            name=machine.name,
            runtime_name=runtime_name,
            state="missing",
            container_state=None,
            interfaces=_missing_interface_statuses(
                scenario,
                machine,
                networks_by_name,
            ),
            unexpected_networks=(),
        )

    interfaces = tuple(
        _inspect_interface_status(
            scenario,
            interface,
            networks_by_name,
            runtime,
        )
        for interface in machine.interfaces
    )

    expected_runtime_networks = {
        get_lab_network_name(
            scenario,
            networks_by_name[interface.network],
        )
        for interface in machine.interfaces
    }

    actual_runtime_networks = {
        attachment.network_name
        for attachment in runtime.networks
    }

    unexpected_networks = tuple(
        sorted(
            actual_runtime_networks
            - expected_runtime_networks
        )
    )

    has_interface_drift = any(
        interface.state != "matching"
        for interface in interfaces
    )

    if has_interface_drift or unexpected_networks:
        state: MachineState = "drifted"
    elif runtime.status == "running":
        state = "running"
    else:
        state = "stopped"

    return MachineStatus(
        name=machine.name,
        runtime_name=runtime_name,
        state=state,
        container_state=runtime.status,
        interfaces=interfaces,
        unexpected_networks=unexpected_networks,
    )


def inspect_lab_status(
    scenario: ScenarioConfig,
) -> LabStatus:
    networks_by_name = {
        network.name: network
        for network in scenario.networks
    }

    networks = tuple(
        _inspect_network_status(
            scenario,
            network,
        )
        for network in scenario.networks
    )

    machines = tuple(
        _inspect_machine_status(
            scenario,
            machine,
            networks_by_name,
        )
        for machine in scenario.machines
    )

    has_drift = any(
        network.state == "drifted"
        for network in networks
    ) or any(
        machine.state == "drifted"
        for machine in machines
    )

    all_missing = all(
        network.state == "missing"
        for network in networks
    ) and all(
        machine.state == "missing"
        for machine in machines
    )

    fully_running = all(
        network.state == "matching"
        for network in networks
    ) and all(
        machine.state == "running"
        for machine in machines
    )

    state: LabState

    if has_drift:
        state = "drifted"
    elif all_missing:
        state = "stopped"
    elif fully_running:
        state = "running"
    else:
        state = "partial"

    return LabStatus(
        scenario_name=scenario.name,
        state=state,
        networks=networks,
        machines=machines,
    )
