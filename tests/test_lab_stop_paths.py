from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pyrange.engine.docker import (
    DockerOperationError,
    DockerResourceIdentity,
)
from pyrange.engine.manager import (
    LabManagerError,
    get_lab_container_name,
    get_lab_network_name,
    stop_lab,
)
from pyrange.engine.ownership import build_ownership_labels
from pyrange.models import (
    MachineConfig,
    NetworkConfig,
    NetworkInterfaceConfig,
    ScenarioConfig,
)


CONTAINER_ID = "a" * 64
NETWORK_ID = "b" * 64


@pytest.fixture
def stop_case():
    scenario = ScenarioConfig(
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

    container = DockerResourceIdentity(
        resource_id=CONTAINER_ID,
        labels=build_ownership_labels(
            kind="container",
            scenario_name="school",
            resource_name="web",
        ),
    )
    network = DockerResourceIdentity(
        resource_id=NETWORK_ID,
        labels=build_ownership_labels(
            kind="network",
            scenario_name="school",
            resource_name="lab-net",
        ),
    )

    with (
        patch(
            "pyrange.engine.manager.find_container_identity",
            return_value=container,
        ) as find_container,
        patch(
            "pyrange.engine.manager.find_network_identity",
            return_value=network,
        ) as find_network,
        patch(
            "pyrange.engine.manager.remove_container",
        ) as remove_container,
        patch(
            "pyrange.engine.manager.remove_network",
        ) as remove_network,
        patch(
            "pyrange.engine.docker.subprocess.run",
            side_effect=AssertionError(
                "This unit test must not execute Docker."
            ),
        ),
    ):
        yield SimpleNamespace(
            scenario=scenario,
            find_container=find_container,
            find_network=find_network,
            remove_container=remove_container,
            remove_network=remove_network,
        )


def test_stop_removes_verified_resources_by_id(stop_case) -> None:
    stop_lab(stop_case.scenario)

    stop_case.find_container.assert_called_once_with(
        get_lab_container_name(
            stop_case.scenario,
            stop_case.scenario.machines[0],
        )
    )
    stop_case.find_network.assert_called_once_with(
        get_lab_network_name(
            stop_case.scenario,
            stop_case.scenario.networks[0],
        )
    )

    stop_case.remove_container.assert_called_once_with(CONTAINER_ID)
    stop_case.remove_network.assert_called_once_with(NETWORK_ID)


def test_stop_does_not_delete_absent_resources(stop_case) -> None:
    stop_case.find_container.return_value = None
    stop_case.find_network.return_value = None

    stop_lab(stop_case.scenario)

    stop_case.find_container.assert_called_once()
    stop_case.find_network.assert_called_once()
    stop_case.remove_container.assert_not_called()
    stop_case.remove_network.assert_not_called()


@pytest.mark.parametrize("kind", ["container", "network"])
def test_lookup_failure_blocks_its_delete_but_not_other_cleanup(
    stop_case,
    kind,
) -> None:
    failed_lookup = getattr(stop_case, f"find_{kind}")
    failed_lookup.side_effect = DockerOperationError("lookup failed")

    with pytest.raises(LabManagerError, match="lookup failed"):
        stop_lab(stop_case.scenario)

    if kind == "container":
        stop_case.remove_container.assert_not_called()
        stop_case.remove_network.assert_called_once_with(NETWORK_ID)
    else:
        stop_case.remove_network.assert_not_called()
        stop_case.remove_container.assert_called_once_with(CONTAINER_ID)

    stop_case.find_container.assert_called_once()
    stop_case.find_network.assert_called_once()


@pytest.mark.parametrize("kind", ["container", "network"])
def test_delete_failure_is_reported_and_other_cleanup_is_attempted(
    stop_case,
    kind,
) -> None:
    failed_delete = getattr(stop_case, f"remove_{kind}")
    failed_delete.side_effect = DockerOperationError("delete failed")

    with pytest.raises(LabManagerError, match="delete failed"):
        stop_lab(stop_case.scenario)

    stop_case.remove_container.assert_called_once_with(CONTAINER_ID)
    stop_case.remove_network.assert_called_once_with(NETWORK_ID)
