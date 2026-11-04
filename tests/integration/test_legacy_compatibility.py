from uuid import uuid4

import pytest

from pyrange.engine.docker import (
    DockerUnavailableError, create_network, find_network_identity,
    get_docker_server_version, remove_network,
)
from pyrange.engine.legacy import LegacyResourceError
from pyrange.engine.manager import LabManagerError, get_lab_network_name, start_lab, stop_lab
from pyrange.models import MachineConfig, NetworkConfig, NetworkInterfaceConfig, ScenarioConfig


@pytest.mark.integration
def test_legacy_network_is_reported_and_never_adopted_or_deleted():
    try:
        get_docker_server_version()
    except DockerUnavailableError as exc:
        pytest.skip(f"Docker is unavailable: {exc}")
    scenario = ScenarioConfig(
        name=f"legacy-int-{uuid4().hex}",
        networks=[NetworkConfig(name="net", subnet="10.254.250.0/28")],
        machines=[MachineConfig(name="web", image="alpine:latest", interfaces=[
            NetworkInterfaceConfig(network="net", ip="10.254.250.2"),
        ])],
    )
    legacy_name = f"pyrange-{scenario.name}-net"
    # The test alone creates this resource and tracks the returned ID for cleanup.
    legacy_id = create_network(legacy_name, "10.254.250.0/28")
    try:
        with pytest.raises(LegacyResourceError):
            start_lab(scenario)
        assert find_network_identity(get_lab_network_name(scenario, scenario.networks[0])) is None
        with pytest.raises(LabManagerError, match="Legacy network candidate"):
            stop_lab(scenario)
        remaining = find_network_identity(legacy_name)
        assert remaining is not None
        assert remaining.resource_id == legacy_id
    finally:
        remove_network(legacy_id)
