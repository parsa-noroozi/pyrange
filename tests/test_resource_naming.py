from pyrange.engine.manager import (
    get_lab_container_name,
    get_lab_network_name,
)
from pyrange.engine.snapshot import get_snapshot_image_ref
from pyrange.models import (
    MachineConfig,
    NetworkConfig,
    NetworkInterfaceConfig,
    ScenarioConfig,
)


def make_scenario(
    scenario_name: str,
    machine_name: str = "web",
    network_name: str = "lab-net",
) -> ScenarioConfig:
    return ScenarioConfig(
        name=scenario_name,
        networks=[
            NetworkConfig(
                name=network_name,
                subnet="172.28.10.0/24",
            )
        ],
        machines=[
            MachineConfig(
                name=machine_name,
                image="nginx:alpine",
                interfaces=[
                    NetworkInterfaceConfig(
                        network=network_name,
                        ip="172.28.10.10",
                    )
                ],
            )
        ],
    )


def test_container_names_distinguish_scenario_machine_pairs() -> None:
    first = make_scenario(
        scenario_name="alpha-beta",
        machine_name="web",
    )
    second = make_scenario(
        scenario_name="alpha",
        machine_name="beta-web",
    )

    first_name = get_lab_container_name(first, first.machines[0])
    second_name = get_lab_container_name(second, second.machines[0])

    assert first_name != second_name


def test_network_names_distinguish_scenario_network_pairs() -> None:
    first = make_scenario(
        scenario_name="alpha-beta",
        network_name="net",
    )
    second = make_scenario(
        scenario_name="alpha",
        network_name="beta-net",
    )

    first_name = get_lab_network_name(first, first.networks[0])
    second_name = get_lab_network_name(second, second.networks[0])

    assert first_name != second_name


def test_snapshot_refs_distinguish_scenario_machine_pairs() -> None:
    first = make_scenario(
        scenario_name="alpha-beta",
        machine_name="web",
    )
    second = make_scenario(
        scenario_name="alpha",
        machine_name="beta-web",
    )

    first_ref = get_snapshot_image_ref(
        first,
        first.machines[0],
        "checkpoint",
    )
    second_ref = get_snapshot_image_ref(
        second,
        second.machines[0],
        "checkpoint",
    )

    assert first_ref != second_ref