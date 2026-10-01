import pytest
from pydantic import ValidationError

from pyrange.models import (
    MachineConfig,
    NetworkConfig,
    NetworkInterfaceConfig,
    ScenarioConfig,
)


def make_interface(
    network: str,
    ip: str,
) -> NetworkInterfaceConfig:
    return NetworkInterfaceConfig(
        network=network,
        ip=ip,
    )


def test_valid_scenario() -> None:
    scenario = ScenarioConfig(
        name="web-lab",
        networks=[
            NetworkConfig(
                name="lab-net",
                subnet="172.28.10.0/24",
            )
        ],
        machines=[
            MachineConfig(
                name="web",
                image="nginx:alpine",
                interfaces=[
                    make_interface(
                        "lab-net",
                        "172.28.10.10",
                    )
                ],
            )
        ],
    )

    assert scenario.name == "web-lab"
    assert len(scenario.networks) == 1
    assert len(scenario.machines) == 1


def test_rejects_duplicate_machine_names() -> None:
    with pytest.raises(
        ValidationError,
        match="machine names must be unique",
    ):
        ScenarioConfig(
            name="lab",
            networks=[
                NetworkConfig(
                    name="lab-net",
                    subnet="172.28.10.0/24",
                )
            ],
            machines=[
                MachineConfig(
                    name="web",
                    image="nginx:alpine",
                    interfaces=[
                        make_interface(
                            "lab-net",
                            "172.28.10.10",
                        )
                    ],
                ),
                MachineConfig(
                    name="web",
                    image="alpine:latest",
                    interfaces=[
                        make_interface(
                            "lab-net",
                            "172.28.10.20",
                        )
                    ],
                ),
            ],
        )


def test_rejects_duplicate_network_names() -> None:
    with pytest.raises(
        ValidationError,
        match="network names must be unique",
    ):
        ScenarioConfig(
            name="lab",
            networks=[
                NetworkConfig(
                    name="lab-net",
                    subnet="172.28.10.0/24",
                ),
                NetworkConfig(
                    name="lab-net",
                    subnet="172.28.20.0/24",
                ),
            ],
            machines=[
                MachineConfig(
                    name="web",
                    image="nginx:alpine",
                    interfaces=[
                        make_interface(
                            "lab-net",
                            "172.28.10.10",
                        )
                    ],
                )
            ],
        )


def test_rejects_overlapping_subnets() -> None:
    with pytest.raises(
        ValidationError,
        match="overlaps network",
    ):
        ScenarioConfig(
            name="lab",
            networks=[
                NetworkConfig(
                    name="public-net",
                    subnet="172.28.10.0/24",
                ),
                NetworkConfig(
                    name="private-net",
                    subnet="172.28.10.128/25",
                ),
            ],
            machines=[
                MachineConfig(
                    name="web",
                    image="nginx:alpine",
                    interfaces=[
                        make_interface(
                            "public-net",
                            "172.28.10.10",
                        )
                    ],
                )
            ],
        )


def test_rejects_unknown_network_reference() -> None:
    with pytest.raises(
        ValidationError,
        match="references unknown network",
    ):
        ScenarioConfig(
            name="lab",
            networks=[
                NetworkConfig(
                    name="lab-net",
                    subnet="172.28.10.0/24",
                )
            ],
            machines=[
                MachineConfig(
                    name="web",
                    image="nginx:alpine",
                    interfaces=[
                        make_interface(
                            "missing-net",
                            "172.28.10.10",
                        )
                    ],
                )
            ],
        )


def test_rejects_duplicate_ip_addresses_on_network() -> None:
    with pytest.raises(
        ValidationError,
        match="is already in use",
    ):
        ScenarioConfig(
            name="lab",
            networks=[
                NetworkConfig(
                    name="lab-net",
                    subnet="172.28.10.0/24",
                )
            ],
            machines=[
                MachineConfig(
                    name="web",
                    image="nginx:alpine",
                    interfaces=[
                        make_interface(
                            "lab-net",
                            "172.28.10.10",
                        )
                    ],
                ),
                MachineConfig(
                    name="analyst",
                    image="alpine:latest",
                    interfaces=[
                        make_interface(
                            "lab-net",
                            "172.28.10.10",
                        )
                    ],
                ),
            ],
        )


def test_rejects_duplicate_interfaces_on_same_network() -> None:
    with pytest.raises(
        ValidationError,
        match="interfaces must use unique networks",
    ):
        MachineConfig(
            name="router",
            image="alpine:latest",
            interfaces=[
                make_interface(
                    "lab-net",
                    "172.28.10.10",
                ),
                make_interface(
                    "lab-net",
                    "172.28.10.11",
                ),
            ],
        )


def test_rejects_ip_outside_subnet() -> None:
    with pytest.raises(
        ValidationError,
        match="is outside subnet",
    ):
        ScenarioConfig(
            name="lab",
            networks=[
                NetworkConfig(
                    name="lab-net",
                    subnet="172.28.10.0/24",
                )
            ],
            machines=[
                MachineConfig(
                    name="web",
                    image="nginx:alpine",
                    interfaces=[
                        make_interface(
                            "lab-net",
                            "10.0.0.5",
                        )
                    ],
                )
            ],
        )


@pytest.mark.parametrize(
    "address",
    [
        "172.28.10.0",
        "172.28.10.255",
    ],
)
def test_rejects_network_and_broadcast_addresses(
    address: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match="cannot use network or broadcast address",
    ):
        ScenarioConfig(
            name="lab",
            networks=[
                NetworkConfig(
                    name="lab-net",
                    subnet="172.28.10.0/24",
                )
            ],
            machines=[
                MachineConfig(
                    name="web",
                    image="nginx:alpine",
                    interfaces=[
                        make_interface(
                            "lab-net",
                            address,
                        )
                    ],
                )
            ],
        )


def test_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        NetworkInterfaceConfig(
            network="lab-net",
            ip="172.28.10.10",
            unexpected="value",
        )
