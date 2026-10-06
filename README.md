# PyRange

PyRange is a Python-based platform for defining, validating, orchestrating, inspecting, recovering, and observing reproducible cybersecurity labs with Docker.

Instead of manually creating Docker networks, containers, static addressing, health checks, recovery points, runtime inspection workflows, and execution logs for every lab, PyRange allows an environment to be described as a declarative YAML scenario and managed through a command-line interface.

PyRange is evolving toward a reproducible cybersecurity experimentation platform in which lab infrastructure, execution context, telemetry, controlled actions, detections, and experiment results can be correlated and evaluated consistently.

> PyRange is intended for authorized cybersecurity labs, research environments, and educational use only.

## Current Version

**v0.5.0 - Structured Events and Execution Context**

PyRange v0.5.0 adds a structured execution-event layer on top of the orchestration, health-check, snapshot, and runtime-inspection capabilities introduced in earlier releases.

The release establishes a machine-readable execution history for important lab operations while preserving the existing orchestration architecture.

The v0.5.0 release adds:

* Per-operation execution contexts
* UUID-based `run_id` correlation
* UUID-based event identities
* Ordered per-run event sequences
* UTC timestamps
* Versioned structured event records
* JSON-compatible event attributes
* Resource-aware event metadata
* Append-only JSONL event persistence
* Event-sink abstraction through a protocol
* Structured lab startup events
* Structured lab shutdown events
* Startup rollback events
* Health-check outcome events
* Snapshot lifecycle events
* Restore lifecycle events
* Explicit event-logging failure semantics
* Protection against event failures masking primary operational failures
* `--event-log` support for `start`, `stop`, `snapshot`, and `restore`
* CLI display of execution `run_id`
* Real Docker end-to-end structured-event integration coverage

## Features

### Scenario Definition and Validation

* YAML-based lab definitions
* Pydantic-based scenario models
* Strict rejection of unknown configuration fields
* Multiple networks per scenario
* Multiple network interfaces per machine
* Static IPv4 addresses per interface
* IPv4 subnet validation
* Duplicate machine name detection
* Duplicate network name detection
* Duplicate IP detection within a network
* Duplicate network attachment detection
* Unknown network reference detection
* Network and broadcast address validation
* Overlapping subnet detection

### Lab Orchestration

* Docker Engine availability checks
* Isolated Docker bridge networks
* Deterministic Docker resource naming
* Multi-network container attachment
* Static IPv4 assignment
* Scenario-level lab startup and shutdown
* Automatic rollback on startup failure
* Reverse-order resource cleanup
* Managed-container labeling

### Structured Events and Execution Context

* One execution context per instrumented operation
* UUID `run_id` shared by all events in the operation
* UUID `event_id` for every individual event
* Monotonic sequence numbers within one recorder
* Timezone-aware UTC timestamps
* Explicit event schema version
* Structured resource references
* JSON-compatible attributes
* Optional success/failure outcomes
* JSONL persistence
* Append-only event files
* Strict JSON serialization
* Event sink failures surfaced explicitly
* Event ordering preserved by the recorder
* Failed sink writes do not consume sequence numbers
* Health-check stdout and stderr excluded from event logs by default
* CLI event logging is opt-in

### Runtime Status and Drift Detection

* Read-only inspection of Docker runtime state
* Detection of missing expected networks
* Detection of missing expected containers
* Comparison of expected and actual Docker network subnets
* Comparison of expected and actual container network membership
* Comparison of expected and actual static IPv4 addresses
* Detection of missing interfaces on existing containers
* Detection of unexpected Docker network attachments
* Preservation of raw Docker container status such as `running` or `exited`
* Machine-level runtime classification
* Lab-level runtime classification
* Runtime inspection without modifying the lab

### Health Checks

* Optional per-machine health checks
* Command-based readiness evaluation
* Configurable per-attempt timeout
* Configurable retry interval
* Configurable retry count
* Health checks run after all containers have started
* Startup rollback when a machine remains unhealthy
* Docker command failures and health-check results handled separately by the execution layer
* Structured health outcome events when an event recorder is active

### Snapshots

* Machine snapshots created through Docker image commits
* Deterministic snapshot image references
* Docker image preflight validation before destructive restore
* Snapshot restore pinned to a resolved Docker image ID
* Multi-network topology reconstruction during restore
* Original scenario static IP restoration
* Optional post-restore health validation
* Structured snapshot and restore events
* Snapshot and restore CLI commands

### CLI and Testing

* Scenario inspection
* Lab start and stop commands
* Runtime status inspection
* Snapshot and restore commands
* Optional JSONL event logging
* Execution `run_id` display
* Clean handling of scenario, Docker, orchestration, snapshot, and event-log errors
* Unit coverage for validation, orchestration, events, runtime status, health checks, snapshots, and CLI behavior
* Real Docker integration coverage for lab lifecycle, segmented topology, runtime status, snapshot restoration, and structured events

## Architecture

```text
                             scenario.yaml
                                  |
                                  v
                              YAML Loader
                                  |
                                  v
                            ScenarioConfig
                                  |
                                  v
                         Topology Validation
                                  |
              +-------------------+-------------------+
              |                   |                   |
              v                   v                   v
         Lab Manager        Snapshot Engine     Status Engine
              |                   |                   |
              |                   |                   |
              +-------------------+-------------------+
                                  |
                                  v
                            Docker Backend
                                  |
             +--------------------+--------------------+
             |                    |                    |
             v                    v                    v
         Networks            Containers             Images
             |                    |                    |
             |                    +-- docker exec      |
             |                    |                    |
             +-- network connect  +-- inspect runtime  |
             |                                         |
             +-- inspect subnet                 docker commit
                                                      |
                                                      v
                                                Snapshot Images


                         Health Evaluator
                              |
                              v
                      Container Command Check
                              |
                +-------------+-------------+
                |             |             |
                v             v             v
             timeout       retries       exit code
```

v0.5 adds a structured event path around instrumented operations:

```text
                              CLI
                               |
                               v
                      ExecutionContext
                   +---------------------+
                   | run_id              |
                   | scenario            |
                   | operation           |
                   +---------------------+
                               |
                               v
                        EventRecorder
                               |
                    +----------+----------+
                    |                     |
                    v                     v
               EventRecord            EventSink
                    |                     |
                    |                     v
                    |               JsonlEventSink
                    |                     |
                    |                     v
                    |                events.jsonl
                    |
                    v
              Engine Operation
                    |
          +---------+----------+
          |                    |
          v                    v
     Lab Manager         Snapshot Engine
          |                    |
          +---------+----------+
                    |
                    v
              Docker Backend
```

PyRange separates scenario definition, validation, lab orchestration, runtime inspection, health evaluation, snapshot management, structured event recording, and low-level Docker operations into independent components.

The scenario model represents the desired lab topology and optional machine health checks.

The Lab Manager translates a validated scenario into Docker networks and containers.

The Docker backend provides imperative lifecycle operations and read-only runtime inspection primitives.

The Runtime Status Engine compares the scenario-defined desired state with actual Docker runtime state.

The Health Evaluator executes configured commands inside running containers and determines whether a machine is ready during startup or restoration.

The Snapshot Engine coordinates snapshot creation and restoration while reusing the same Docker backend and deterministic resource naming rules used by normal lab orchestration.

The structured event layer does not live inside the Docker backend. Higher-level orchestration components emit domain events while Docker remains responsible for Docker-specific operations.

This separation provides a foundation for future telemetry collection, scenario actions, detection experiments, and scoring without coupling those capabilities directly to the Docker backend.

## Requirements

* Python 3.12 or newer
* Docker Desktop or Docker Engine
* Git

Docker must be running before starting a lab, inspecting live runtime state, or running tests that require a real Docker Engine.

## Installation

Clone the repository:

```bash
git clone https://github.com/parsa-noroozi/pyrange.git
cd pyrange
```

Create a virtual environment.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
```

Install PyRange:

```bash
python -m pip install -e .
```

For development:

```bash
python -m pip install -e ".[dev]"
```

## Scenario Format

A PyRange scenario defines networks and machines.

Each machine contains one or more network interfaces and may optionally define a command-based health check.

Example:

```yaml
name: segmented-lab
description: Multi-network segmented cybersecurity laboratory

networks:
  - name: public-net
    subnet: 172.28.20.0/24

  - name: private-net
    subnet: 172.28.30.0/24

machines:
  - name: web
    image: nginx:alpine

    interfaces:
      - network: public-net
        ip: 172.28.20.10

    health_check:
      type: command
      command:
        - sh
        - -c
        - test -f /usr/share/nginx/html/index.html
      interval_seconds: 2
      timeout_seconds: 2
      retries: 3

  - name: analyst
    image: nginx:alpine

    interfaces:
      - network: public-net
        ip: 172.28.20.20

      - network: private-net
        ip: 172.28.30.20
```

This scenario describes the following topology:

```text
segmented-lab

public-net (172.28.20.0/24)
|
+-- web
|   `-- 172.28.20.10
|
`-- analyst
    `-- 172.28.20.20


private-net (172.28.30.0/24)
|
`-- analyst
    `-- 172.28.30.20
```

The `analyst` machine is multi-homed because it is connected to both networks with a separate static IP address on each interface.

The `web` machine also defines a command-based health check that PyRange evaluates after all containers have started.

## Scenario Validation

PyRange validates the complete scenario before Docker resources are created.

Rejected configurations include:

* Duplicate machine names
* Duplicate network names
* Duplicate network attachments on the same machine
* Duplicate IP addresses on the same network
* Interfaces referencing undefined networks
* IP addresses outside the referenced subnet
* Network addresses assigned to interfaces
* Broadcast addresses assigned to interfaces
* Overlapping network subnets
* Empty machine or network names
* Invalid health check configuration
* Empty health check commands
* Empty health check command items
* Non-positive health check intervals
* Non-positive health check timeouts
* Negative retry counts
* Unsupported health check types
* Unknown configuration fields

This keeps invalid topology and health configuration out of the Docker orchestration layer.

## Structured Events

PyRange v0.5.0 introduces structured execution events for instrumented operations.

Structured events are intended to provide a stable machine-readable execution history that later releases can correlate with telemetry, actions, detections, and experiment results.

Event recording is currently supported for:

* Lab startup
* Lab shutdown
* Snapshot creation
* Snapshot restoration
* Health outcomes that occur inside those operations
* Startup rollback activity

Runtime `status` and scenario `inspect` remain read-only commands and do not currently expose `--event-log`.

### Execution Context

Every instrumented CLI operation creates one `ExecutionContext`.

The context contains:

| Field | Meaning |
| --- | --- |
| `run_id` | UUID identifying the complete operation. |
| `scenario` | Scenario name associated with the operation. |
| `operation` | Operation name such as `start`, `stop`, `snapshot`, or `restore`. |

All events emitted by one recorder reuse the same `run_id`.

This provides correlation across the complete execution.

For example:

```text
pyrange start
      |
      v
run_id = 3e4c...
      |
      +-- event 1: lab.start.requested
      |
      +-- event 2: network.created
      |
      +-- event 3: machine.created
      |
      +-- event 4: machine.started
      |
      `-- event N: lab.start.completed
```

### Event Record Schema

The current event schema version is:

```text
schema_version = 1
```

Every event contains the following fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | Version of the structured event schema. |
| `event_id` | UUID unique to the individual event. |
| `run_id` | UUID shared by all events in the execution. |
| `sequence` | Monotonic event sequence within the recorder. |
| `timestamp` | Timezone-aware UTC timestamp. |
| `scenario` | Scenario name. |
| `operation` | Operation that created the execution context. |
| `event_type` | Machine-readable event name. |
| `outcome` | Optional `success` or `failure` result. |
| `resource` | Optional structured resource reference. |
| `attributes` | JSON-compatible event metadata. |

A resource reference contains:

```json
{
  "type": "machine",
  "name": "web"
}
```

Example JSONL record:

```json
{"schema_version":1,"event_id":"22222222-2222-4222-8222-222222222222","run_id":"11111111-1111-4111-8111-111111111111","sequence":4,"timestamp":"2026-10-06T18:30:00Z","scenario":"segmented-lab","operation":"start","event_type":"machine.started","outcome":"success","resource":{"type":"machine","name":"web"},"attributes":{"runtime_name":"pyrange-segmented-lab-web"}}
```

Each line in the event file is an independent JSON object.

### Event Ordering

`EventRecorder` assigns sequence numbers beginning at `1`.

For one successful recorder:

```text
1
2
3
4
...
N
```

Sequence advancement occurs only after the event sink successfully accepts the event.

If an event write fails, that failed write does not consume a sequence number.

The recorder serializes emission within the process so events from one recorder are ordered consistently.

Sequence numbers are local to one recorder and one execution context. They are not global counters across separate PyRange processes.

### JSONL Event Sink

The initial event sink is `JsonlEventSink`.

It uses append mode:

```text
existing events
      |
      v
events.jsonl
      |
      +-- new run event 1
      +-- new run event 2
      `-- ...
```

Multiple PyRange operations may therefore append to the same file.

Separate executions are distinguished by their `run_id`.

JSON serialization is strict. Non-finite floating-point values such as `NaN` and infinity are rejected.

The sink writes UTF-8 JSONL and flushes the file after each event write.

The parent directory is not created automatically.

For example, this succeeds when the current directory is writable:

```bash
pyrange start scenarios/segmented-lab.yaml --event-log events.jsonl
```

But a path whose parent directory does not exist produces an explicit event-log error.

### Event Vocabulary

Lab startup may emit:

```text
lab.start.requested
network.created
machine.created
machine.network.attached
machine.started
health.passed
health.failed
resource.rollback.removed
resource.rollback.failed
lab.start.completed
lab.start.failed
```

Lab shutdown may emit:

```text
lab.stop.requested
machine.removed
machine.remove.failed
network.removed
network.remove.failed
lab.stop.completed
lab.stop.failed
```

Snapshot creation may emit:

```text
snapshot.requested
snapshot.created
snapshot.failed
```

Snapshot restoration may emit:

```text
restore.requested
restore.container.removed
restore.container.created
restore.network.attached
restore.container.started
health.passed
health.failed
restore.completed
restore.failed
```

Not every event appears in every run.

For example, rollback events occur only when startup fails after resources have been created.

### Event Attributes

Event attributes carry operation-specific metadata.

Examples include:

```text
runtime_name
subnet
image
network
runtime_network
ip
primary
attempts
exit_code
snapshot_name
image_ref
image_id
error_type
rollback_error_count
operational_error_count
event_error_count
stage
destructive_started
operational_completed
```

Attributes are intentionally restricted to JSON-compatible values.

### Health-Check Data Boundary

Health checks may internally produce stdout and stderr.

PyRange does not include raw health-check stdout or stderr in structured events by default.

Health events currently record metadata such as:

```json
{
  "attempts": 3,
  "exit_code": 1
}
```

This reduces the risk of copying command output, application data, tokens, diagnostics, or other sensitive content into persistent event logs.

Operational exceptions may still contain diagnostic text for the interactive caller, but raw command output is not placed into event attributes automatically.

## Structured Event Failure Semantics

Event logging is optional.

Without an event recorder, orchestration behavior remains compatible with earlier releases.

When an event recorder is supplied, event persistence becomes part of the operation contract: event failures are surfaced rather than silently ignored.

Different operations apply failure handling according to their operational semantics.

### Startup

Before resource creation, an event failure can stop startup immediately.

After resources have been created, an event failure during normal startup is treated as an operation failure and triggers startup rollback.

Rollback itself continues even if recording rollback events fails.

A rollback-event failure does not replace the original startup failure.

For example:

```text
network created
      |
      v
network.created event fails
      |
      v
startup failure
      |
      v
rollback resources
      |
      v
raise event failure
```

### Health Failure

If a machine is unhealthy and recording `health.failed` also fails, the health failure remains the primary operational error.

The event logging failure is attached as additional diagnostic context rather than replacing the health failure.

### Shutdown

Shutdown prioritizes resource cleanup.

If an event write fails while containers and networks are being removed, PyRange continues attempting to remove the remaining resources.

After cleanup finishes, the event failure is reported.

This prevents an observability failure from unnecessarily leaving additional lab resources running.

### Snapshot Creation

If snapshot creation fails before a snapshot image is produced, PyRange attempts to record `snapshot.failed` and preserves the original operational error.

If the Docker snapshot image is successfully created but recording `snapshot.created` fails, the image remains created.

The event failure is reported explicitly, including diagnostic context indicating that the snapshot image already exists.

### Snapshot Restore

Snapshot restore has a destructive boundary.

Preflight validation occurs before the existing container is removed.

Once the restore operation enters container removal, PyRange treats the operation as destructive.

After that boundary, event-write failures are collected while the restore operation continues as far as operationally possible.

If the restore infrastructure completes successfully but event logging failed during the process, the event failure is reported after the operational restore has completed.

Operational Docker or health failures remain primary when both an operational failure and event failure occur.

## CLI

### Inspect a Scenario

```bash
pyrange inspect scenarios/segmented-lab.yaml
```

Example output:

```text
Scenario: segmented-lab
Description: Multi-network segmented cybersecurity laboratory
Networks: 2
  - public-net: 172.28.20.0/24
  - private-net: 172.28.30.0/24
Machines: 2
  - web: nginx:alpine
      public-net @ 172.28.20.10
  - analyst: nginx:alpine
      public-net @ 172.28.20.20
      private-net @ 172.28.30.20
```

### Start a Lab

Without structured event logging:

```bash
pyrange start scenarios/segmented-lab.yaml
```

With structured event logging:

```bash
pyrange start scenarios/segmented-lab.yaml --event-log events.jsonl
```

Example event-enabled output:

```text
Starting lab: segmented-lab
Run ID: 11111111-1111-4111-8111-111111111111
Event log: events.jsonl
Lab started successfully.
```

The actual `run_id` is generated dynamically for each execution.

### Stop a Lab

Without event logging:

```bash
pyrange stop scenarios/segmented-lab.yaml
```

With event logging:

```bash
pyrange stop scenarios/segmented-lab.yaml --event-log events.jsonl
```

A stop invocation creates a new execution context and therefore receives a new `run_id`.

### Inspect Runtime Status

```bash
pyrange status scenarios/segmented-lab.yaml
```

The status command is read-only.

Example output when the lab is not running:

```text
Scenario: segmented-lab
Status: stopped

Networks:
  - public-net: missing
      Runtime: pyrange-segmented-lab-public-net
      Expected subnet: 172.28.20.0/24
      Actual subnets: -
  - private-net: missing
      Runtime: pyrange-segmented-lab-private-net
      Expected subnet: 172.28.30.0/24
      Actual subnets: -

Machines:
  - web: missing
      Runtime: pyrange-segmented-lab-web
      Container state: -
      Interfaces:
        - public-net: missing
            Runtime network: pyrange-segmented-lab-public-net
            Expected IP: 172.28.20.10
            Actual IP: -

  - analyst: missing
      Runtime: pyrange-segmented-lab-analyst
      Container state: -
      Interfaces:
        - public-net: missing
            Runtime network: pyrange-segmented-lab-public-net
            Expected IP: 172.28.20.20
            Actual IP: -
        - private-net: missing
            Runtime network: pyrange-segmented-lab-private-net
            Expected IP: 172.28.30.20
            Actual IP: -
```

The command exits successfully for valid runtime states such as `running`, `stopped`, `partial`, and `drifted`.

Those states describe the lab; they are not CLI failures.

Scenario loading errors, validation failures, Docker unavailability, and Docker inspection errors are reported as command errors.

### Create a Snapshot

Create a named snapshot of a machine:

```bash
pyrange snapshot scenarios/segmented-lab.yaml web checkpoint-1
```

With structured event logging:

```bash
pyrange snapshot scenarios/segmented-lab.yaml web checkpoint-1 --event-log events.jsonl
```

Example output without event logging:

```text
Creating snapshot: web (checkpoint-1)
Snapshot created successfully.
Machine: web
Image: pyrange-snapshots/segmented-lab-web:checkpoint-1
Image ID: sha256:...
```

### Restore a Snapshot

Restore a machine from a previously created snapshot:

```bash
pyrange restore scenarios/segmented-lab.yaml web checkpoint-1
```

With structured event logging:

```bash
pyrange restore scenarios/segmented-lab.yaml web checkpoint-1 --event-log events.jsonl
```

Example output without event logging:

```text
Restoring snapshot: web (checkpoint-1)
Snapshot restored successfully.
Machine: web
Image: pyrange-snapshots/segmented-lab-web:checkpoint-1
Image ID: sha256:...
```

> Restoring a snapshot replaces the current container. Unsnapshotted changes in that container's writable filesystem are discarded.

## Runtime Status

Runtime inspection loads the scenario, derives expected deterministic Docker resource names, inspects Docker runtime state, and compares actual resources against the scenario-defined desired state.

It does not create, remove, restart, reconnect, or otherwise modify Docker resources.

### Network Status

Each scenario network is classified as one of:

| State | Meaning |
| --- | --- |
| `matching` | The Docker network exists and its subnet matches the scenario. |
| `missing` | The expected Docker network does not exist. |
| `drifted` | The network exists but its runtime subnet configuration differs from the scenario. |

Example:

```text
- public-net: matching
    Runtime: pyrange-segmented-lab-public-net
    Expected subnet: 172.28.20.0/24
    Actual subnets: 172.28.20.0/24
```

A subnet mismatch is reported as drift:

```text
- public-net: drifted
    Expected subnet: 172.28.20.0/24
    Actual subnets: 172.28.99.0/24
```

### Machine Status

Each scenario machine preserves the raw Docker container state while also receiving a PyRange runtime classification.

| State | Meaning |
| --- | --- |
| `running` | The container exists, is running, and its expected network topology matches the scenario. |
| `stopped` | The container exists and topology matches, but the Docker container state is not `running`. |
| `missing` | The expected container does not exist. |
| `drifted` | The container exists but its network membership or static addressing differs from the scenario. |

A container may therefore be represented as:

```text
- web: stopped
    Container state: exited
```

### Interface Status

For every expected machine interface, PyRange compares:

* Expected network membership
* Actual network membership
* Expected static IPv4 address
* Actual Docker IPv4 address

An interface may be `matching`, `missing`, or `drifted`.

Example:

```text
- public-net: drifted
    Expected IP: 172.28.20.10
    Actual IP: 172.28.20.99
```

A missing expected network attachment is considered topology drift for an existing container.

### Unexpected Networks

If an expected container is attached to a Docker network that is not declared for that machine in the scenario, PyRange records the attachment as unexpected.

Example:

```text
Unexpected networks:
  - temporary-debug-net
```

Unexpected network attachments cause the machine to be classified as `drifted`.

### Lab Status

The complete lab is classified as:

| State | Meaning |
| --- | --- |
| `running` | All expected networks match and all expected machines are running with matching topology. |
| `stopped` | All expected networks and machines are absent. |
| `partial` | Some expected resources exist, but the lab is neither completely running nor completely absent, and no topology drift was detected. |
| `drifted` | At least one network or machine has detected topology drift. |

Drift takes precedence over other lab states.

A lab with one running machine and one missing machine is `partial`.

A lab with an IP mismatch is `drifted`.

## Health Checks

Health checks are optional and configured per machine.

The current health check type is `command`:

```yaml
health_check:
  type: command
  command:
    - sh
    - -c
    - test -f /usr/share/nginx/html/index.html
  interval_seconds: 5
  timeout_seconds: 2
  retries: 3
```

The health check fields are:

| Field | Meaning |
| --- | --- |
| `type` | Health check type. Currently only `command` is supported. |
| `command` | Command and arguments executed inside the container. |
| `interval_seconds` | Delay between failed attempts. |
| `timeout_seconds` | Maximum execution time for one attempt. |
| `retries` | Number of additional retries after the initial attempt. |

A command exit code of `0` means the machine is healthy.

A non-zero exit code means the health check failed for that attempt.

`retries` represents **additional attempts after the initial execution**.

For example:

```yaml
retries: 0
```

means exactly one health check attempt.

With:

```yaml
retries: 3
```

PyRange may perform up to four total attempts:

```text
Initial attempt
      |
      +-- failed
      |
Retry 1
      |
      +-- failed
      |
Retry 2
      |
      +-- failed
      |
Retry 3
```

The configured interval is applied between failed attempts.

Each individual attempt is bounded by `timeout_seconds`.

Health checks run only after all containers in the scenario have been started.

This ordering allows machines to depend on services provided by other machines in the same lab.

If a machine remains unhealthy after all configured attempts, lab startup fails and PyRange rolls back the Docker resources created for the lab.

## Lab Lifecycle

When a lab starts, PyRange performs:

```text
Validate scenario
      |
      v
Create isolated networks
      |
      v
Create each container on its primary network
      |
      v
Attach additional network interfaces
      |
      v
Assign static IP addresses
      |
      v
Start all containers
      |
      v
Run configured health checks
      |
      v
Lab ready
```

For a multi-homed machine, the first interface is configured when the container is created.

Additional interfaces are attached using Docker network connections and their configured static IP addresses.

Health checks run only after all containers have started.

If container creation, network attachment, startup, health validation, or strict event persistence during startup fails, PyRange attempts to roll back resources created during startup.

Rollback removes containers first and then networks in reverse creation order.

When a lab is stopped normally, PyRange removes its containers and networks in reverse order.

Shutdown continues cleanup attempts even if structured event recording fails during removal.

## Runtime Inspection Lifecycle

Runtime status evaluation is independent of startup and shutdown.

```text
Load scenario
      |
      v
Derive expected Docker resource names
      |
      v
Inspect expected Docker networks
      |
      v
Compare expected and actual subnets
      |
      v
Inspect expected containers
      |
      v
Read Docker container state
      |
      v
Read network attachments and IP addresses
      |
      v
Compare desired and actual topology
      |
      v
Classify network, machine, and lab state
```

A missing expected Docker resource is treated as runtime information rather than an exceptional Docker failure.

Operational Docker failures are reported separately through the Docker error hierarchy.

Runtime inspection is intentionally read-only.

## Snapshots

PyRange snapshots are Docker-image-based recovery points for individual machines.

### Snapshot Creation

Snapshot creation uses Docker's container commit mechanism:

```text
Running container
      |
      v
docker commit
      |
      v
Snapshot image
```

Snapshot image references are deterministic:

```text
pyrange-snapshots/<scenario-name>-<machine-name>:<snapshot-name>
```

For example:

```text
pyrange-snapshots/segmented-lab-web:checkpoint-1
```

Snapshot names:

* Must begin with a letter, digit, or underscore
* May contain letters, digits, underscores, periods, and hyphens
* May contain up to 128 characters

Valid examples:

```text
checkpoint-1
before-test
baseline_01
v1.2
```

Names containing spaces, `/`, or `:` are rejected.

### Snapshot Restore

Restore performs validation before removing the current container.

Before the destructive part begins, PyRange:

1. Resolves the target machine from the scenario.
2. Validates the snapshot name.
3. Builds the deterministic snapshot image reference.
4. Verifies that the Docker image exists.
5. Resolves that image reference to a Docker image ID.

Only after these checks succeed does PyRange enter the destructive restore phase.

```text
Resolve target machine
      |
      v
Validate snapshot name
      |
      v
Resolve snapshot image reference
      |
      v
Verify snapshot image exists
      |
      v
Resolve immutable image ID
      |
      v
Enter destructive restore phase
      |
      v
Remove current container
      |
      v
Create replacement from image ID
      |
      v
Attach primary network + static IP
      |
      v
Attach secondary networks + static IPs
      |
      v
Start replacement container
      |
      v
Run configured health check
```

The replacement container uses the network topology defined by the current scenario.

Network membership and static IP addresses are reconstructed from the scenario rather than recovered from the snapshot image.

The resolved Docker image ID is used for recreation instead of relying on the mutable snapshot tag after preflight validation.

### Restore Failure Semantics

Snapshot restore is protected by preflight checks, but it is **not fully transactional**.

Failures before the destructive phase leave the existing container untouched.

After PyRange enters container removal, a later failure during removal, container creation, network attachment, startup, or health validation may leave the machine in a partial runtime state.

PyRange does not currently reconstruct the previous runtime container automatically after such a failure.

Structured restore events expose metadata such as the failure `stage` and whether the destructive phase was entered.

This behavior is an explicit limitation rather than an implicit recovery guarantee.

### Snapshot Semantics

PyRange snapshots currently use `docker commit`.

They capture changes in the container's writable filesystem layer.

They do **not** represent full virtual-machine-style checkpoints.

Snapshots do not capture:

* Container memory
* Live process execution state
* External Docker volume contents
* Host filesystem state
* PyRange runtime state outside the container filesystem

A restored machine is a new container created from the snapshot image and reattached to the topology defined by the scenario.

## Resource Naming

Docker resources created by PyRange use deterministic names.

For the segmented example:

```text
pyrange-segmented-lab-public-net
pyrange-segmented-lab-private-net
pyrange-segmented-lab-web
pyrange-segmented-lab-analyst
```

Runtime inspection uses these same deterministic names to locate expected Docker resources.

Snapshot images use a separate deterministic namespace:

```text
pyrange-snapshots/segmented-lab-web:checkpoint-1
```

Managed containers are labeled with:

```text
pyrange.managed=true
```

Deterministic naming makes orchestration and runtime inspection predictable and provides a stable basis for event correlation, telemetry, and future experiment management.

## Testing

Run the full test suite:

```bash
pytest -v
```

PyRange v0.5.0 currently contains **157 automated tests**.

The suite covers:

* Scenario model validation
* YAML scenario loading
* IPv4 topology validation
* Duplicate resource detection
* Overlapping subnet detection
* Health check configuration validation
* Health check retry semantics
* Health check timeout behavior
* Docker command execution
* Docker container runtime inspection
* Docker network runtime inspection
* Invalid Docker inspection data handling
* Exact-name runtime resource discovery
* Health-gated startup
* Health failure rollback
* Startup rollback event semantics
* Shutdown cleanup semantics
* Lab Manager error handling
* Execution context validation
* Structured event schema validation
* UTC timestamp normalization
* Structured event naming validation
* JSON-compatible event attributes
* Event sequence ordering
* Failed-write sequence behavior
* Strict JSON serialization
* JSONL append behavior
* JSONL write failures
* Lab lifecycle events
* Resource lifecycle events
* Health outcome events
* Snapshot lifecycle events
* Restore lifecycle events
* Event failure precedence
* Event failures during cleanup
* Post-destructive restore event behavior
* CLI event-recorder wiring
* CLI `--event-log` behavior
* CLI event-log errors
* CLI execution-context output
* Real JSONL persistence through the CLI
* Docker network lifecycle
* Docker container lifecycle
* Multi-network attachment
* Runtime network subnet comparison
* Runtime static IP comparison
* Missing resource classification
* Missing interface detection
* Unexpected network detection
* Machine runtime classification
* Lab runtime classification
* Runtime status CLI behavior
* Runtime status CLI error handling
* Docker image inspection
* Snapshot image creation
* Snapshot name validation
* Snapshot orchestration
* Snapshot restore orchestration
* Snapshot preflight validation
* Restore by immutable image ID
* Multi-network topology restoration
* Post-restore health checks
* General CLI behavior
* General CLI error handling
* Real Docker lab lifecycle
* Real Docker segmented multi-network topology
* Real Docker runtime status inspection
* Real Docker snapshot and restore behavior
* Real Docker structured-event persistence

Tests requiring a running Docker Engine use the `integration` marker.

Run only the integration tests:

```bash
pytest -v -m integration -rs
```

PyRange v0.5.0 currently includes **5 real Docker integration tests**:

1. Basic single-network lab lifecycle
2. Segmented multi-network lab lifecycle and topology
3. Runtime status across real lab startup and shutdown
4. Snapshot creation and restoration
5. Structured lifecycle events through the CLI and JSONL sink

### Structured Event Integration Test

The structured-event integration test performs a real end-to-end workflow:

```text
Load real scenario
      |
      v
Invoke PyRange CLI
      |
      v
Create ExecutionContext
      |
      v
Create JSONL EventRecorder
      |
      v
Start real Docker lab
      |
      v
Verify Docker resources exist
      |
      v
Read JSONL event file
      |
      v
Verify schema version
      |
      v
Verify one shared run_id
      |
      v
Verify unique event_id values
      |
      v
Verify contiguous sequence numbers
      |
      v
Verify lifecycle event counts
      |
      v
Verify start completed successfully
      |
      v
Clean Docker resources
```

This verifies the complete path:

```text
CLI
 |
 v
ExecutionContext
 |
 v
EventRecorder
 |
 v
Lab Manager
 |
 v
Docker Engine
 |
 v
JSONL file
```

The integration test does not mock the Docker lifecycle.

### Runtime Status Integration Test

The runtime-status integration test performs:

```text
Create test scenario
      |
      v
Inspect absent resources
      |
      v
Verify lab = stopped
      |
      v
Start real lab
      |
      v
Inspect Docker networks and containers
      |
      v
Verify topology = matching
      |
      v
Verify lab = running
      |
      v
Stop real lab
      |
      v
Inspect resources again
      |
      v
Verify lab = stopped
      |
      v
Final cleanup
```

### Snapshot Integration Test

The snapshot/restore integration test performs:

```text
Start real lab
      |
      v
Write snapshot-state marker
      |
      v
Create machine snapshot
      |
      v
Overwrite marker with modified-state
      |
      v
Verify modified state
      |
      v
Restore snapshot
      |
      v
Verify snapshot-state returned
      |
      v
Clean Docker resources
```

The integration suite verifies real Docker behavior rather than relying only on mocked unit tests.

If Docker is unavailable, Docker-dependent integration tests are skipped.

## Project Structure

```text
pyrange/
|
|-- pyrange/
|   |
|   |-- cli.py
|   |
|   |-- core/
|   |   `-- scenario_loader.py
|   |
|   |-- engine/
|   |   |-- docker.py
|   |   |-- events.py
|   |   |-- health.py
|   |   |-- manager.py
|   |   |-- snapshot.py
|   |   `-- status.py
|   |
|   `-- models/
|       `-- scenario.py
|
|-- scenarios/
|   |-- basic-web-lab.yaml
|   `-- segmented-lab.yaml
|
|-- tests/
|   |-- integration/
|   |   |-- test_lab_lifecycle.py
|   |   |-- test_multi_network_lifecycle.py
|   |   |-- test_runtime_status.py
|   |   `-- test_structured_events.py
|   |
|   |-- test_cli.py
|   |-- test_cli_events.py
|   |-- test_docker_engine.py
|   |-- test_events.py
|   |-- test_health.py
|   |-- test_lab_manager.py
|   |-- test_lab_manager_events.py
|   |-- test_scenario.py
|   |-- test_scenario_loader.py
|   |-- test_snapshot.py
|   |-- test_snapshot_events.py
|   |-- test_snapshot_integration.py
|   |-- test_status.py
|   `-- test_status_cli.py
|
|-- docs/
|-- pyproject.toml
|-- README.md
`-- SECURITY.md
```

## Current Limitations

PyRange v0.5.0 focuses on reproducible Docker topology, runtime topology inspection, machine readiness, filesystem-oriented snapshots, and structured execution events.

Current limitations include:

* IPv4 networking only
* Docker is the only execution backend
* Health checks are command-based only
* No custom machine startup command model
* No persistent PyRange state database
* Runtime status is evaluated on demand rather than continuously
* No background monitoring daemon
* Runtime status does not currently execute configured health checks
* Runtime status focuses on expected scenario resources rather than a complete arbitrary Docker inventory
* Unexpected network attachments are detected only on expected scenario containers
* No persistent runtime-status history
* Structured events are currently persisted only to local JSONL files
* No event database
* No remote event shipping
* No event-streaming daemon
* No event-file rotation
* No event signing or tamper-evidence layer
* CLI `--event-log` is currently available for `start`, `stop`, `snapshot`, and `restore`, not `inspect` or `status`
* Event sequence numbers are scoped to a recorder rather than globally coordinated across processes
* Parent directories for JSONL event files are not created automatically
* No persistent snapshot catalog
* No snapshot listing command
* No snapshot deletion command
* Snapshot storage is managed as local Docker images
* Snapshot images capture container writable filesystem state rather than full machine state
* External Docker volume data is not captured by snapshots
* Container memory and live process state are not captured
* Restore replaces the current container
* Restore is not fully transactional after the destructive phase begins
* No telemetry collection
* No scenario action engine
* No detection integration
* No detection evaluation
* No scoring system
* No experiment-result model

These are explicit scope boundaries of the current release rather than hidden capabilities.

## Roadmap

### v0.1 - Core Orchestration

* [x] Scenario models
* [x] YAML loading
* [x] Validation
* [x] CLI
* [x] Docker network lifecycle
* [x] Docker container lifecycle
* [x] Lab Manager
* [x] Rollback
* [x] End-to-end testing

### v0.2 - Network Topology

* [x] Multiple networks per scenario
* [x] Multiple interfaces per machine
* [x] Static IP addresses per interface
* [x] Network reference validation
* [x] Overlapping subnet detection
* [x] Docker network attachment
* [x] Multi-network orchestration
* [x] Multi-network rollback and cleanup
* [x] End-to-end segmented topology testing

### v0.3 - Health Checks and Snapshots

* [x] Command-based health check model
* [x] Health check configuration validation
* [x] Configurable intervals, timeouts, and retries
* [x] Docker-backed health check execution
* [x] Health-gated lab startup
* [x] Rollback when startup health validation fails
* [x] Machine snapshot creation
* [x] Deterministic snapshot image naming
* [x] Snapshot image preflight validation
* [x] Snapshot restore orchestration
* [x] Immutable image ID restoration
* [x] Multi-network topology restoration
* [x] Post-restore health validation
* [x] Snapshot CLI command
* [x] Restore CLI command
* [x] Real Docker snapshot/restore integration coverage

### v0.4 - Runtime Status and Drift Detection

* [x] Docker container runtime inspection
* [x] Docker network runtime inspection
* [x] Read-only runtime status model
* [x] Missing resource detection
* [x] Network subnet drift detection
* [x] Static IP drift detection
* [x] Missing interface detection
* [x] Unexpected network attachment detection
* [x] Machine runtime classification
* [x] Lab runtime classification
* [x] Runtime status CLI command
* [x] Real Docker runtime-status integration coverage

### v0.5 - Structured Events and Execution Context

* [x] Versioned structured event schema
* [x] Execution context model
* [x] Per-operation `run_id`
* [x] Per-event `event_id`
* [x] Ordered sequence numbers
* [x] UTC timestamps
* [x] Structured resource metadata
* [x] JSON-compatible event attributes
* [x] Event sink protocol
* [x] JSONL event sink
* [x] Explicit event-sink errors
* [x] Lab startup events
* [x] Lab shutdown events
* [x] Rollback events
* [x] Health outcome events
* [x] Snapshot lifecycle events
* [x] Restore lifecycle events
* [x] Event failure precedence semantics
* [x] `--event-log` CLI support
* [x] Execution `run_id` CLI output
* [x] Real Docker structured-event integration coverage

### v0.6 - Telemetry Collection

Planned:

* Container execution telemetry
* Network-oriented telemetry sources
* Correlation with execution `run_id`
* Structured telemetry records
* Experiment artifact organization
* Controlled collection boundaries

### v0.7 - Scenario Action Engine

Planned:

* Declarative scenario actions
* Controlled action execution
* Action lifecycle events
* Deterministic action ordering
* Action failure semantics
* Integration with telemetry collection

### v0.8 - Detection Evaluation

Planned:

* Detection-engine integration
* Detection result model
* Correlation between actions, telemetry, and detections
* Expected-versus-observed detection evaluation
* Experiment-level detection summaries

### v0.9 - Scoring and Experiment Results

Planned:

* Experiment result model
* Detection scoring
* Structured evaluation summaries
* Reproducible result artifacts
* Machine-readable experiment outcomes

### v1.0 - Stable Experiment Platform

The long-term target is a stable workflow in which PyRange can:

```text
validate experiment
      |
      v
provision lab
      |
      v
verify readiness
      |
      v
capture baseline
      |
      v
execute controlled action
      |
      v
collect telemetry
      |
      v
evaluate detections
      |
      v
produce results
      |
      v
preserve artifacts
      |
      v
cleanup / restore
```

The intended direction is a reproducible cybersecurity experimentation platform rather than a collection of unrelated orchestration features.

## Security

PyRange is designed for controlled and authorized cybersecurity environments.

Use PyRange only on systems, Docker environments, and networks for which you have explicit authorization.

Do not use PyRange against third-party systems or infrastructure without permission.

Structured event logs may contain lab names, Docker resource names, network information, IP addresses, snapshot references, image identifiers, and operational error metadata.

Treat event logs as experiment artifacts and protect them accordingly.

PyRange intentionally avoids recording raw health-check stdout and stderr into structured event attributes by default, but users remain responsible for reviewing the sensitivity of generated artifacts.

See `SECURITY.md` for the project's security policy.
