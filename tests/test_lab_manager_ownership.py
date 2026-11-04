from unittest.mock import patch

import pytest

from pyrange.engine.docker import DockerResourceIdentity
from pyrange.engine.manager import LabManagerError, stop_lab
from pyrange.engine.ownership import build_ownership_labels
from pyrange.models import (
    MachineConfig,
    NetworkConfig,
    NetworkInterfaceConfig,
    ScenarioConfig,
)


@pytest.fixture
def scenario() -> ScenarioConfig:
    return ScenarioConfig(
        name="school",
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
                    NetworkInterfaceConfig(
                        network="lab-net",
                        ip="172.28.10.10",
                    )
                ],
            )
        ],
    )


@pytest.mark.parametrize("kind", ["container", "network"])
@pytest.mark.parametrize(
    "label_problem",
    ["missing", "wrong-scenario"],
)
def test_stop_rejects_unverified_resource_without_deleting(
    scenario: ScenarioConfig,
    kind: str,
    label_problem: str,
) -> None:
    resource_name = "web" if kind == "container" else "lab-net"

    if label_problem == "missing":
        labels = None
    else:
        labels = build_ownership_labels(
            kind=kind,
            scenario_name=scenario.name,
            resource_name=resource_name,
        )
        labels["pyrange.scenario.name"] = "hospital"

    identity = DockerResourceIdentity(
        resource_id="a" * 64,
        labels=labels,
    )

    with (
        patch(
            "pyrange.engine.manager.find_container_identity",
            return_value=identity if kind == "container" else None,
        ) as mock_find_container,
        patch(
            "pyrange.engine.manager.find_network_identity",
            return_value=identity if kind == "network" else None,
        ) as mock_find_network,
        patch(
            "pyrange.engine.manager.remove_container",
        ) as mock_remove_container,
        patch(
            "pyrange.engine.manager.remove_network",
        ) as mock_remove_network,
        patch(
            "pyrange.engine.docker.subprocess.run",
            side_effect=AssertionError(
                "This unit test must not execute Docker."
            ),
        ),
    ):
        with pytest.raises(
            LabManagerError,
            match="Failed to fully stop lab",
        ):
            stop_lab(scenario)

        mock_remove_container.assert_not_called()
        mock_remove_network.assert_not_called()

        mock_find_container.assert_called_once()
        mock_find_network.assert_called_once()
