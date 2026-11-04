# Legacy resource compatibility and manual review

## Scope

Before versioned naming, resources used these ambiguous names:

- Container: `pyrange-{scenario}-{machine}`
- Network: `pyrange-{scenario}-{network}`
- Snapshot: `pyrange-snapshots/{scenario}-{machine}:{checkpoint}`

For example, `alpha-beta/web` and `alpha/beta-web` map to the same old
container name. A matching name or the old `pyrange.managed=true` label does
not establish which scenario owns a resource.

Discovery is read-only. Matching resources are candidates for manual review;
they are never automatically adopted, relabeled, migrated, or deleted. Even a
candidate that happens to have newer labels is not automatically migrated.

## Behavior

| Operation | Legacy scope | Result if unresolved |
| --- | --- | --- |
| start | All scenario containers and networks | Fail before creation |
| status | All scenario containers and networks | Report an error, not a misleading stopped/running result |
| snapshot / restore | Selected machine, its attached networks, selected legacy checkpoint reference | Fail before commit or target mutation |
| stop | All scenario containers and networks | Preserve legacy candidates, continue independently verified v2 cleanup, report incomplete cleanup |

A failed lookup is not absence. Queries for other candidates continue so a
lookup failure does not erase evidence of an independently discovered candidate.
The preflight fails if any candidate or query failure remains.

Stop emits `resource.legacy.detected` with `ownership_verified=false` for a
candidate and `legacy.discovery.failed` for a lookup failure. These are operational
failures. Event-writing failures are additional diagnostics, not replacements
for the operational error. `lab.stop.completed` is not emitted while these
issues remain unresolved.

Stop does not remove snapshot images, old or new. It does not scan every old
checkpoint tag. Snapshot/restore checks the explicitly requested checkpoint.
Discovery concerns the supplied scenario; it is not a host-wide orphan-resource
inventory. Telemetry retains its current v2 runtime-name scope and is not a
legacy inventory or an ownership decision.

## Resources with current names but missing labels

Current-name resources still require all ownership labels before destructive
operations. They are not repaired merely to make a check pass. Legacy discovery
adds compatibility checks; it does not replace current-name ownership checks.

## Manual review procedure

1. Record the reported resource kind, full ID, runtime name, and operation.
2. Pause concurrent operations for the affected scenario/checkpoint.
3. Inspect by full ID using the appropriate read-only Docker command:
   `docker container inspect`, `docker network inspect`, or `docker image inspect`.
   Supply the recorded ID as the argument.
4. Compare creation time, image, network attachments, labels, prior scenario
   definitions, and available run records. Name similarity alone is insufficient.
5. Preserve needed data before retiring anything. Container writable layers,
   named/bind-mounted volumes, and snapshot images require separate consideration;
   Docker commit is not a backup of mounted-volume data.
6. If ownership cannot be established, leave the candidate untouched and resolve
   the ambiguity manually. Do not rewrite its labels to bypass the check.
7. If the operator independently establishes ownership and intentionally retires
   a resource, use its reviewed full ID, not an ambiguous name or wildcard.
   Container/network/image removal is an explicit manual operation, not performed
   by this compatibility mechanism. Do not use broad prune commands as migration.
8. Rerun the read-only inspection and the intended PyRange operation. Once relevant
   candidates are resolved, PyRange can create fresh v2 resources normally.

Old snapshots are not automatically converted to ownership-verified snapshots.
Review/export their contents separately if needed and create a new checkpoint
from a verified current container. Keep unresolved snapshots intact.

## Concurrency and validation

Discovery is a point-in-time observation, not a Docker-daemon transaction or
lock. Do not mutate affected legacy/current names concurrently while resolving
compatibility issues. Full IDs prevent name reuse from retargeting cleanup;
labels are not an authentication boundary against Docker-daemon administrators.

Unit tests cover ambiguous names, scope, lookup failures, rejection before
mutation, stop reporting, independent v2 cleanup, and event-writing failures.
The integration test creates a uniquely named legacy network and checks that
start/stop reject it without adopting or deleting it. Only the test's own
recorded network ID is used for final test cleanup. Integration results must be
recorded separately from unit-test results before declaring package A complete.
