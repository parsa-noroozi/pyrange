import hashlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pyrange.engine.docker import DockerResourceIdentity
from pyrange.engine.manager import get_lab_container_name, get_lab_network_name
from pyrange.engine.ownership import build_ownership_labels


@pytest.fixture
def rollback_resources():
    """Provide creation IDs and independent inspection mocks to start tests."""
    ids = {}
    containers = {}
    networks = {}

    def configure(create_network, create_container, scenario):
        for kind, resources, identities, name_builder in [
            ("container", scenario.machines, containers, get_lab_container_name),
            ("network", scenario.networks, networks, get_lab_network_name),
        ]:
            for resource in resources:
                name = name_builder(scenario, resource)
                resource_id = hashlib.sha256(name.encode()).hexdigest()
                ids[name] = resource_id
                identities[resource_id] = DockerResourceIdentity(
                    resource_id=resource_id,
                    labels=build_ownership_labels(kind, scenario.name, resource.name),
                )
        create_network.side_effect = lambda name, subnet, **kwargs: ids[name]
        create_container.side_effect = lambda **kwargs: ids[kwargs["name"]]

    with (
        patch("pyrange.engine.manager.inspect_container_identity", side_effect=containers.__getitem__) as inspect_container,
        patch("pyrange.engine.manager.inspect_network_identity", side_effect=networks.__getitem__) as inspect_network,
        patch("pyrange.engine.docker.subprocess.run", side_effect=AssertionError("Unexpected Docker call in unit test")),
    ):
        yield SimpleNamespace(
            ids=ids, containers=containers, networks=networks,
            configure=configure, inspect_container=inspect_container,
            inspect_network=inspect_network,
        )


@pytest.fixture
def snapshot_resources():
    container = DockerResourceIdentity(
        "a" * 64, build_ownership_labels("container", "snapshot-lab", "web")
    )
    image = DockerResourceIdentity(
        "sha256:" + "c" * 64,
        build_ownership_labels("snapshot", "snapshot-lab", "web"),
    )
    with (
        patch("pyrange.engine.snapshot.find_container_identity", return_value=container) as find_container,
        patch("pyrange.engine.snapshot.find_image_identity", return_value=None) as find_image,
        patch("pyrange.engine.docker.subprocess.run", side_effect=AssertionError("Unexpected Docker call in snapshot unit test")),
    ):
        yield SimpleNamespace(
            container=container, image=image,
            find_container=find_container, find_image=find_image,
        )


@pytest.fixture
def no_legacy_resources():
    """Model successful legacy lookups with no matches in focused unit tests."""
    with (
        patch("pyrange.engine.legacy.find_container_identity", return_value=None),
        patch("pyrange.engine.legacy.find_network_identity", return_value=None),
        patch("pyrange.engine.legacy.find_image_identity", return_value=None),
    ):
        yield
