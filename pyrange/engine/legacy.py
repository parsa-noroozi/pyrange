"""Read-only discovery of ambiguous pre-v2 resource names.

A name match is a candidate for manual review, never proof of ownership.
"""
from dataclasses import dataclass

from pyrange.engine.docker import (
    DockerOperationError,
    DockerUnavailableError,
    find_container_identity,
    find_image_identity,
    find_network_identity,
)
from pyrange.models import MachineConfig, ScenarioConfig


class LegacyResourceError(DockerOperationError):
    """Unresolved legacy candidates prevent a new operation."""


@dataclass(frozen=True)
class LegacyCandidate:
    kind: str
    logical_name: str
    runtime_name: str
    resource_id: str


@dataclass(frozen=True)
class LegacyLookupFailure:
    kind: str
    logical_name: str
    runtime_name: str
    error: Exception


@dataclass(frozen=True)
class LegacyScan:
    candidates: tuple[LegacyCandidate, ...]
    failures: tuple[LegacyLookupFailure, ...]


def describe_candidate(candidate: LegacyCandidate) -> str:
    return (
        f"Legacy {candidate.kind} candidate '{candidate.runtime_name}' "
        f"(ID {candidate.resource_id}); ownership is not established. "
        "Manual review is required; no automatic migration or deletion."
    )


def scan_legacy_resources(
    scenario: ScenarioConfig,
    *,
    machine: MachineConfig | None = None,
    snapshot_name: str | None = None,
) -> LegacyScan:
    if snapshot_name is not None and machine is None:
        raise ValueError("snapshot lookup requires a selected machine")
    machines = scenario.machines if machine is None else [machine]
    selected_networks = (
        None if machine is None else {item.network for item in machine.interfaces}
    )
    candidates = []
    failures = []
    queries = [
        ("container", item.name, f"pyrange-{scenario.name}-{item.name}", find_container_identity)
        for item in machines
    ]
    queries.extend(
        ("network", item.name, f"pyrange-{scenario.name}-{item.name}", find_network_identity)
        for item in scenario.networks
        if selected_networks is None or item.name in selected_networks
    )
    if snapshot_name is not None:
        queries.append((
            "snapshot", machine.name,
            f"pyrange-snapshots/{scenario.name}-{machine.name}:{snapshot_name}",
            find_image_identity,
        ))
    for kind, logical_name, runtime_name, lookup in queries:
        try:
            identity = lookup(runtime_name)
        except (DockerOperationError, DockerUnavailableError) as exc:
            failures.append(LegacyLookupFailure(kind, logical_name, runtime_name, exc))
        else:
            if identity is not None:
                candidates.append(LegacyCandidate(
                    kind, logical_name, runtime_name, identity.resource_id,
                ))
    return LegacyScan(tuple(candidates), tuple(failures))


def require_no_legacy_resources(
    scenario: ScenarioConfig,
    *,
    machine: MachineConfig | None = None,
    snapshot_name: str | None = None,
) -> None:
    scan = scan_legacy_resources(scenario, machine=machine, snapshot_name=snapshot_name)
    if not scan.candidates and not scan.failures:
        return
    messages = [describe_candidate(candidate) for candidate in scan.candidates]
    messages.extend(
        f"Could not check legacy {item.kind} name '{item.runtime_name}': {item.error}"
        for item in scan.failures
    )
    error = LegacyResourceError("Legacy compatibility preflight failed: " + "; ".join(messages))
    if scan.failures:
        raise error from scan.failures[0].error
    raise error
