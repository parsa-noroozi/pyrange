from ipaddress import IPv4Address, IPv4Network

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NetworkConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    subnet: IPv4Network


class MachineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    image: str = Field(min_length=1)
    ip: IPv4Address


class ScenarioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = ""
    network: NetworkConfig
    machines: list[MachineConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_machines(self) -> "ScenarioConfig":
        names = [machine.name for machine in self.machines]
        if len(names) != len(set(names)):
            raise ValueError("machine names must be unique")

        addresses = [machine.ip for machine in self.machines]
        if len(addresses) != len(set(addresses)):
            raise ValueError("machine IP addresses must be unique")

        for machine in self.machines:
            if machine.ip not in self.network.subnet:
                raise ValueError(
                    f"machine '{machine.name}' IP {machine.ip} "
                    f"is outside subnet {self.network.subnet}"
                )

            if machine.ip in {
                self.network.subnet.network_address,
                self.network.subnet.broadcast_address,
            }:
                raise ValueError(
                    f"machine '{machine.name}' cannot use "
                    f"network or broadcast address {machine.ip}"
                )

        return self
    
    
