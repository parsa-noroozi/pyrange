import pytest
from pydantic import ValidationError

from pyrange.models import MachineConfig, NetworkConfig, ScenarioConfig


def test_valid_scenario() -> None:
    scenario = ScenarioConfig(
        name="web-lab",
        network=NetworkConfig(
            name="lab-net",
            subnet="172.28.10.0/24",
        ),
        machines=[
            MachineConfig(
                name="web",
                image="nginx:alpine",
                ip="172.28.10.10",
            )
        ],
    )

    assert scenario.name == "web-lab"
    assert len(scenario.machines) == 1


def test_rejects_duplicate_machine_names() -> None:
    with pytest.raises(ValidationError, match="machine names must be unique"):
        ScenarioConfig(
            name="lab",
            network=NetworkConfig(
                name="lab-net",
                subnet="172.28.10.0/24",
            ),
            machines=[
                MachineConfig(
                    name="web",
                    image="nginx:alpine",
                    ip="172.28.10.10",
                ),
                MachineConfig(
                    name="web",
                    image="alpine:latest",
                    ip="172.28.10.20",
                ),
            ],
        )


def test_rejects_duplicate_ip_addresses() -> None:
    with pytest.raises(ValidationError, match="machine IP addresses must be unique"):
        ScenarioConfig(
            name="lab",
            network=NetworkConfig(
                name="lab-net",
                subnet="172.28.10.0/24",
            ),
            machines=[
                MachineConfig(
                    name="web",
                    image="nginx:alpine",
                    ip="172.28.10.10",
                ),
                MachineConfig(
                    name="analyst",
                    image="alpine:latest",
                    ip="172.28.10.10",
                ),
            ],
        )


def test_rejects_ip_outside_subnet() -> None:
    with pytest.raises(ValidationError, match="is outside subnet"):
        ScenarioConfig(
            name="lab",
            network=NetworkConfig(
                name="lab-net",
                subnet="172.28.10.0/24",
            ),
            machines=[
                MachineConfig(
                    name="web",
                    image="nginx:alpine",
                    ip="10.0.0.5",
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
def test_rejects_network_and_broadcast_addresses(address: str) -> None:
    with pytest.raises(
        ValidationError,
        match="cannot use network or broadcast address",
    ):
        ScenarioConfig(
            name="lab",
            network=NetworkConfig(
                name="lab-net",
                subnet="172.28.10.0/24",
            ),
            machines=[
                MachineConfig(
                    name="web",
                    image="nginx:alpine",
                    ip=address,
                )
            ],
        )


def test_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        MachineConfig(
            name="web",
            image="nginx:alpine",
            ip="172.28.10.10",
            unexpected="value",
        )
        
