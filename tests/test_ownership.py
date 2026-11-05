import pytest

from pyrange.engine.ownership import (
    ResourceOwnershipError,
    build_ownership_labels,
    verify_resource_ownership,
)


OWNERSHIP_KEYS = (
    "pyrange.managed",
    "pyrange.ownership.version",
    "pyrange.resource.kind",
    "pyrange.scenario.name",
    "pyrange.resource.name",
    "pyrange.resource.identity",
)


@pytest.fixture
def labels() -> dict[str, str]:
    return {
        "pyrange.managed": "true",
        "pyrange.ownership.version": "1",
        "pyrange.resource.kind": "container",
        "pyrange.scenario.name": "alpha-beta",
        "pyrange.resource.name": "web",
        "pyrange.resource.identity": (
            "pyrange-v2-container-"
            "559f31ac0beae6673a9c15ba9800d7ae"
            "623562c205d659266daec0d23a110df1"
        ),
    }


def test_builds_expected_ownership_labels(
    labels: dict[str, str],
) -> None:
    assert build_ownership_labels(
        "container",
        "alpha-beta",
        "web",
    ) == labels


def test_accepts_matching_ownership(
    labels: dict[str, str],
) -> None:
    verify_resource_ownership(
        labels,
        kind="container",
        scenario_name="alpha-beta",
        resource_name="web",
    )


@pytest.mark.parametrize("key", OWNERSHIP_KEYS)
def test_rejects_missing_ownership_label(
    labels: dict[str, str],
    key: str,
) -> None:
    del labels[key]

    with pytest.raises(ResourceOwnershipError):
        verify_resource_ownership(
            labels,
            kind="container",
            scenario_name="alpha-beta",
            resource_name="web",
        )


@pytest.mark.parametrize("key", OWNERSHIP_KEYS)
def test_rejects_mismatched_ownership_label(
    labels: dict[str, str],
    key: str,
) -> None:
    labels[key] = "wrong"

    with pytest.raises(ResourceOwnershipError):
        verify_resource_ownership(
            labels,
            kind="container",
            scenario_name="alpha-beta",
            resource_name="web",
        )


def test_accepts_unrelated_extra_labels(
    labels: dict[str, str],
) -> None:
    labels["description"] = "test resource"

    verify_resource_ownership(
        labels,
        kind="container",
        scenario_name="alpha-beta",
        resource_name="web",
    )


@pytest.mark.parametrize("actual_labels", [None, [], "invalid"])
def test_rejects_missing_or_invalid_label_mapping(actual_labels) -> None:
    with pytest.raises(ResourceOwnershipError):
        verify_resource_ownership(
            actual_labels,
            kind="container",
            scenario_name="alpha-beta",
            resource_name="web",
        )
