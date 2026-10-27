from collections.abc import Mapping

from pyrange.engine.naming import build_resource_name


class ResourceOwnershipError(RuntimeError):
    """Raised when resource ownership cannot be verified."""


def build_ownership_labels(
    kind: str,
    scenario_name: str,
    resource_name: str,
) -> dict[str, str]:
    identity = build_resource_name(
        kind,
        scenario_name,
        resource_name,
    )

    return {
        "pyrange.managed": "true",
        "pyrange.ownership.version": "1",
        "pyrange.resource.kind": kind,
        "pyrange.scenario.name": scenario_name,
        "pyrange.resource.name": resource_name,
        "pyrange.resource.identity": identity,
    }


def verify_resource_ownership(
    actual_labels: Mapping[str, str] | None,
    *,
    kind: str,
    scenario_name: str,
    resource_name: str,
) -> None:
    expected_labels = build_ownership_labels(
        kind,
        scenario_name,
        resource_name,
    )

    if not isinstance(actual_labels, Mapping):
        raise ResourceOwnershipError(
            "Resource ownership labels are missing or invalid."
        )

    for key, expected_value in expected_labels.items():
        if actual_labels.get(key) != expected_value:
            raise ResourceOwnershipError(
                f"Resource ownership label mismatch: '{key}'."
            )
