# Foundation hardening review

## Scope and decision

Reviewed foundation behavior through `470da6a` on `fix/resource-naming`, using the
supplied source and successive patches, with user-provided local test output and
GitHub Checks screenshots. This is a scoped maintainer review, not an independent
security audit or a claim to have inspected every line of every test.

No additional merge-blocking code defect was identified in the reviewed scope.
Documentation corrections are required before closing the PR: the README still
showed legacy runtime names, old test counts and a stronger timeout claim than
implemented; the ownership contract still described itself as unimplemented.
This documentation patch reconciles those statements. Merge remains conditional
on the final revision's CI checks and repository review requirements.

## Reviewed invariants

| Path | Checked behavior | Evidence in repository |
| --- | --- | --- |
| Naming | Structured versioned tuple, kind separation, full digest | `test_naming.py`, `test_resource_naming.py` |
| Identity discovery | Successful absence differs from query/parse/inspect failure; selected ID must match inspected ID | Docker identity and identity-lookup tests |
| Stop | Verify six labels then remove by full ID; independent cleanup continues; unresolved errors fail operation | `test_lab_manager_ownership.py`, `test_lab_stop_paths.py`, manager event tests |
| Start rollback | Record returned ID before events; inspect original creation ID; reject invalid/mismatched identity; preserve original exception | `test_lab_rollback_ownership.py` |
| Snapshot | Verify source; commit by ID with snapshot labels; reject already observed checkpoint | `test_snapshot_ownership.py`, image identity tests |
| Restore | Verify image and target before removal; remove target by ID; recreate from pinned image ID with container labels | Snapshot ownership/event/integration tests |
| Legacy | Read-only candidate discovery; no inferred ownership/adoption/deletion; unresolved candidates prevent success | `test_legacy_resources.py`, real legacy compatibility test |
| Timeout | Typed error, partial diagnostics, no implied cancellation; no health retry after timeout | `test_command_timeout.py`, real exec timeout experiment |
| CI/wheel | Nonempty/no-skip report gate; fresh venv; imports and CLI outside checkout | `test_ci_report.py`, `scripts/verify_wheel.py`, workflow |

Operational exceptions remain primary when cleanup or failure-event writing also
fails. Additional diagnostics are exception notes; ordinary CLI error rendering
is not claimed to display every chained exception or note.

## Recorded validation

- Local review environment (Linux, Python 3.12): 462 non-integration tests passed,
  8 integration tests deselected. JUnit gate accepted 462 cases without skips.
- Wheel built and installed in a fresh external venv; dependency check, imports
  of 20 modules, installed CLI help and scenario inspection passed locally.
- User's Windows environment: wheel verifier passed.
- User's Windows/Python 3.14.7/Docker 29.8.2 environment: all 8 integration tests
  passed in 33.01 seconds; the JUnit gate confirmed zero skips or failures.
- The timeout probe recorded client timeout, continued workload execution, and
  removal of its recorded container ID. This is an observed environment result,
  not proof for all Docker versions/platforms.
- User-provided Checks screenshot for `470da6a`: all ten checks succeeded (five
  jobs each for push and pull_request). The matrix covered Ubuntu 24.04 and
  Windows on Python 3.12/3.14, plus Linux Docker integration. These are two
  workflow triggers, not ten distinct environments. No claim of independently
  downloading every CI log is made.

## Explicit limits and follow-up boundaries

- Labels prevent accidental misuse, not hostile access to the Docker daemon.
- No global lock or transaction protects same-scenario operations. Start/restore
  attachment, start and health operations still use names. Restore does not verify
  or pin all destination networks before deleting a target. Operate exclusively
  on a known topology; full mutation authorization is future work.
- Read-only status/telemetry are name-based observations, not ownership proofs.
- Checkpoint absence and commit are separate calls; concurrent writers are unsupported.
- Restore can leave partial state. Mounted-volume data is not captured by commit.
- Failed creation without a returned ID can leave a resource that cannot safely be
  selected for automatic rollback. Manual inspection may be necessary.
- A rollback inspect failure is a cleanup error, not classified as confirmed absence.
- Command timeout does not cancel the container workload; other Docker operations
  still lack a general deadline. Output collection is not a bounded evidence store.
- CI logs resolved dependencies but does not lock all packages, images or actions;
  the build is not claimed to be hermetic or bit-for-bit reproducible.

These boundaries do not introduce v0.7 functionality. The next planned phase is
reviewing and freezing the v0.7 documents/contracts before implementation.
