import hashlib
import json


RESOURCE_KINDS = frozenset({
    "container",
    "network",
    "snapshot",
})


def build_resource_name(
    kind: str,
    scenario_name: str,
    resource_name: str,
) -> str:
    """Build a versioned, deterministic Docker resource name."""
    if kind not in RESOURCE_KINDS:
        raise ValueError("unsupported resource kind")

    for value in (scenario_name, resource_name):
        if not isinstance(value, str):
            raise TypeError("resource identity fields must be strings")
        if not value:
            raise ValueError("resource identity fields must not be empty")

    payload = [
        "pyrange-resource",
        2,
        kind,
        scenario_name,
        resource_name,
    ]

    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")

    digest = hashlib.sha256(encoded).hexdigest()

    return f"pyrange-v2-{kind}-{digest}"
