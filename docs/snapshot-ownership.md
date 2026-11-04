# Snapshot ownership and compatibility

This change hardens the existing snapshot/restore implementation. It does not
implement the v0.7 execution state machine.

## Snapshot creation

The requested repository:tag must be absent after a successful Docker listing.
An existing reference is rejected even if its ownership labels match. Listing
or inspection failures are errors, not evidence of absence.

The source container must exist and pass the six-label ownership check.
Docker commit targets the verified container ID and explicitly writes ownership
labels for kind `snapshot`. Container ownership labels inherited from the source
are not sufficient to identify a snapshot.

## Restore

Before deleting a target container, the selected image must pass snapshot
ownership verification. Its inspected image ID is pinned for container creation.
An existing target must also pass container ownership verification; deletion
uses its verified ID. An absent target produces `restore.container.absent`,
not a removal-success event.

The restored container explicitly receives container ownership labels, overriding
the snapshot's inherited identity labels. Operational and event-writing failures
retain the existing separation and reporting behavior.

## Compatibility and limits

Old snapshot images without the required snapshot labels are rejected. They are
not automatically relabeled or migrated. Broader legacy-resource discovery and
manual migration/cleanup guidance remain part of the foundation-hardening work.

Creation requires exclusive use of the selected checkpoint reference: do not
create, tag, delete, or replace that reference concurrently. The absence check
and Docker commit are separate calls, not an atomic create-if-absent transaction.
This change does not add a distributed lock or protect against another actor
with Docker-daemon access. The check prevents overwriting an already observed
reference; it cannot guarantee that the tag stays absent until commit.

Docker commit does not capture mounted-volume data. Filesystem restore is not a
transaction: failure after removal may leave the target absent or only partially
restored. This change does not promise rollback to the pre-restore container.

## Validation

Unit tests cover ID pinning, ownership rejection, missing resources, listing and
inspection failures, explicit snapshot/container labels, and existing event-error
behavior. The Docker integration test additionally checks actual image and
restored-container labels, checkpoint reuse rejection, and filesystem content.
A successful unit run does not substitute for executing that integration test.
