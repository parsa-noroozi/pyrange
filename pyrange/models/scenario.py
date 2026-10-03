from ipaddress import IPv4Address, IPv4Network
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


NonEmptyString = Annotated[str, Field(min_length=1)]


class NetworkConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    subnet: IPv4Network


class NetworkInterfaceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    network: str = Field(min_length=1)
    ip: IPv4Address


class HealthCheckConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["command"] = "command"
    command: list[NonEmptyString] = Field(min_length=1)
    interval_seconds: float = Field(default=5.0, gt=0)
    timeout_seconds: float = Field(default=2.0, gt=0)
    retries: int = Field(default=3, ge=1)


class MachineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    image: str = Field(min_length=1)
    interfaces: list[NetworkInterfaceConfig] = Field(min_length=1)
    health_check: HealthCheckConfig | None = None

    @model_validator(mode="after")
    def validate_interfaces(self) -> "MachineConfig":
        network_names = [
            interface.network
            for interface in self.interfaces
        ]

        if len(network_names) != len(set(network_names)):
            raise ValueError(
                "machine interfaces must use unique networks"
            )

        return self


class ScenarioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = ""
    networks: list[NetworkConfig] = Field(min_length=1)
    machines: list[MachineConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_topology(self) -> "ScenarioConfig":
        network_names = [
            network.name
            for network in self.networks
        ]

        if len(network_names) != len(set(network_names)):
            raise ValueError(
                "network names must be unique"
            )

        machine_names = [
            machine.name
            for machine in self.machines
        ]

        if len(machine_names) != len(set(machine_names)):
            raise ValueError(
                "machine names must be unique"
            )

        for index, network in enumerate(self.networks):
            for other in self.networks[index + 1:]:
                if network.subnet.overlaps(other.subnet):
                    raise ValueError(
                        f"network '{network.name}' subnet "
                        f"{network.subnet} overlaps network "
                        f"'{other.name}' subnet {other.subnet}"
                    )

        networks_by_name = {
            network.name: network
            for network in self.networks
        }

        used_addresses: dict[str, set[IPv4Address]] = {
            network.name: set()
            for network in self.networks
        }

        for machine in self.machines:
            for interface in machine.interfaces:
                network = networks_by_name.get(
                    interface.network
                )

                if network is None:
                    raise ValueError(
                        f"machine '{machine.name}' references "
                        f"unknown network '{interface.network}'"
                    )

                if interface.ip not in network.subnet:
                    raise ValueError(
                        f"machine '{machine.name}' IP "
                        f"{interface.ip} is outside subnet "
                        f"{network.subnet}"
                    )

                if interface.ip in {
                    network.subnet.network_address,
                    network.subnet.broadcast_address,
                }:
                    raise ValueError(
                        f"machine '{machine.name}' cannot use "
                        f"network or broadcast address "
                        f"{interface.ip}"
                    )

                if interface.ip in used_addresses[network.name]:
                    raise ValueError(
                        f"IP address {interface.ip} is already "
                        f"in use on network '{network.name}'"
                    )

                used_addresses[network.name].add(
                    interface.ip
                )

        return self
