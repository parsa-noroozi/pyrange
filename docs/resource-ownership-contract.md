# Resource ownership contract

Status: Draft
Scope: Foundation hardening on fix/resource-naming.
This document describes intended behavior, not completed implementation.

## 1. Resource identity

A resource is identified by:
- Resource kind: container, network, or snapshot.
- Scenario name.
- Logical resource name.

Runtime names use the existing versioned naming algorithm.
A runtime name alone is not proof of ownership.

Snapshot tags select checkpoints within a snapshot resource identity.

## 2. Ownership labels

The following labels must match the expected identity:

- pyrange.managed
- pyrange.ownership.version
- pyrange.resource.kind
- pyrange.scenario.name
- pyrange.resource.name
- pyrange.resource.identity

Unrelated additional labels are allowed.

Missing, malformed, unsupported, or mismatched ownership metadata
must not authorize a destructive operation.

Labels protect against accidental cross-resource operations.
They are not an authorization boundary against an actor who can
modify Docker resources or access the Docker daemon.

## 3. Inspect before destructive operations

Before deleting or replacing an existing resource:

1. Inspect the resource and obtain its immutable Docker ID and labels.
2. Verify the labels against the expected identity.
3. Address the destructive operation using that verified ID.

Never fall back from a verified ID to a resource name.

If inspection fails, do not treat the resource as absent.
If ownership verification fails, do not mutate that resource.

Verification and mutation are not atomic.
Using the verified ID avoids targeting a replacement with the same name.

## 4. Missing resources and partial failures

During stop or rollback, a resource confirmed to be absent needs
no deletion. Report it as absent, not as successfully deleted.

A Docker query failure is an operational error, not proof of absence.

Cleanup may continue for other independently verified resources.
The overall operation must report any unresolved failures.

## 5. Creation and rollback

New containers and networks receive ownership labels at creation.

Record each successfully created resource's returned Docker ID
before later operations that may fail.

Rollback targets only resources created by the current attempt.
Verify their ownership before removal and address them by ID.

Preserve the original failure.
Attach cleanup and event-recording failures as additional diagnostics.

## 6. Snapshots and restore

Snapshots receive explicit ownership metadata for kind "snapshot".
Inherited container labels alone do not establish snapshot ownership.

Before restore removes or replaces a container:
- Verify ownership of the selected snapshot image.
- Pin the verified image ID.
- Verify ownership of the existing target container, if present.

Create the restored container with explicit container ownership labels.
Do not rely on snapshot labels inherited from the image.

An existing snapshot reference must not be silently overwritten.
Checkpoint replacement is outside this change's scope.

## 7. Legacy resources

Resources using the old naming format, or lacking the required labels,
must not be automatically adopted, relabeled, or deleted.

When a relevant legacy candidate is found:
- Report the resource and the compatibility issue.
- Do not infer ownership from its ambiguous legacy name.
- Fail a conflicting start or restore before mutation.
- Do not report a fully cleaned lab while that candidate is unresolved.

Automatic migration is outside this change's scope.
Manual inspection and cleanup guidance must be documented before release.

## 8. Acceptance evidence

Required checks include:

- Distinct identity pairs produce distinct names in regression cases.
- Creation passes the expected ownership labels.
- Missing or mismatched labels prevent destructive calls.
- Inspection errors prevent destructive calls.
- Destructive calls use verified IDs rather than names.
- Rollback does not remove resources from another attempt.
- Cleanup failures do not replace the original failure.
- Restore validates its snapshot before removing the target container.
- Restored containers receive container ownership metadata.
- Legacy candidates are reported without automatic mutation.
- Docker integration tests verify actual label and lifecycle behavior.
