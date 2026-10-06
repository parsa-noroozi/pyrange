# PyRange

PyRange is a Python-based platform for defining, validating, orchestrating, inspecting, and recovering reproducible cybersecurity labs with Docker.

Instead of manually creating Docker networks, containers, static addressing, health checks, recovery points, and runtime inspection workflows for every lab, PyRange allows an environment to be described as a declarative YAML scenario and managed through a command-line interface.

> PyRange is intended for authorized cybersecurity labs, research environments, and educational use only.

## Current Version

**v0.4.0 - Runtime Status and Drift Detection**

PyRange v0.4.0 extends the orchestration, health-check, and snapshot capabilities introduced in earlier releases with live runtime inspection and desired-versus-actual topology comparison.

The v0.4.0 release adds:

* Read-only Docker runtime inspection
* Container runtime state inspection
* Docker network subnet inspection
* Lab-level runtime status evaluation
* Desired-versus-actual topology comparison
* Detection of missing Docker resources
* Detection of network subnet drift
* Detection of missing machine interfaces
* Detection of static IP drift
* Detection of unexpected network attachments
* Preservation of raw Docker container state
* Lab classification as `running`, `stopped`, `partial`, or `drifted`
* `pyrange status` CLI command
* Real Docker runtime-status integration coverage

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
* Docker command failures and health-check results are handled separately by the execution layer

### Snapshots

* Machine snapshots created through Docker image commits
* Deterministic snapshot image references
* Docker image preflight validation before destructive restore
* Snapshot restore pinned to a resolved Docker image ID
* Multi-network topology reconstruction during restore
* Original scenario static IP restoration
* Optional post-restore health validation
* Snapshot and restore CLI commands

### CLI and Testing

* Scenario inspection
* Lab start and stop commands
* Runtime status inspection
* Snapshot and restore commands
* Clean handling of scenario, Docker, orchestration, and snapshot errors
* Unit coverage for validation, orchestration, runtime status, health checks, snapshots, and CLI behavior
* Real Docker integration coverage for lab lifecycle, segmented topology, runtime status, and snapshot restoration

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
            +---------------------+---------------------+
            |                     |                     |
            v                     v                     v
         Networks             Containers            Images
            |                     |                     |
            |                     +-- docker exec       |
            |                     |                     |
            +-- network connect   +-- inspect runtime   |
            |                                           |
            +-- inspect subnet                  docker commit
                                                        |
                                                        v
                                                 Snapshot Images


                         Health Evaluator
                               |
                               v
                      Container Command Check
                               |
                +--------------+--------------+
                |              |              |
                v              v              v
             timeout        retries        exit code
```

PyRange separates scenario definition, validation, lab orchestration, runtime inspection, health evaluation, snapshot management, and low-level Docker operations into independent components.

The scenario model represents the desired lab topology and optional machine health checks.

The Lab Manager translates a validated scenario into Docker networks and containers.

The Docker backend provides both imperative lifecycle operations and read-only runtime inspection primitives.

The Runtime Status Engine compares the scenario-defined desired state with actual Docker runtime state.

The Health Evaluator executes configured commands inside running containers and determines whether a machine is ready during startup or restoration.

The Snapshot Engine coordinates snapshot creation and restoration while reusing the same Docker backend and deterministic resource naming rules used by normal lab orchestration.

This separation keeps future capabilities such as structured event logging, telemetry collection, scenario actions, detection experiments, and scoring outside the core orchestration layer.

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

## Runtime Status

PyRange v0.4.0 introduces runtime inspection through:

```bash
pyrange status scenarios/segmented-lab.yaml
```

The status command is read-only.

It loads the scenario, derives the expected deterministic Docker resource names, inspects Docker runtime state, and compares the actual resources against the scenario-defined desired state.

It does not create, remove, restart, reconnect, or modify Docker resources.

### Network Status

Each scenario network is classified as one of:

| State | Meaning |
| --- | --- |
| `matching` | The Docker network exists and its subnet matches the scenario. |
| `missing` | The expected Docker network does not exist. |
| `drifted` | The network exists but its runtime subnet configuration differs from the scenario. |

For example:

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

Machine states are:

| State | Meaning |
| --- | --- |
| `running` | The container exists, is running, and its expected network topology matches the scenario. |
| `stopped` | The container exists and topology matches, but the Docker container state is not `running`. |
| `missing` | The expected container does not exist. |
| `drifted` | The container exists but its network membership or static addressing differs from the scenario. |

For example, a container may be represented as:

```text
- web: stopped
    Container state: exited
```

PyRange therefore preserves Docker's actual runtime state while exposing a higher-level machine classification.

### Interface Status

For every expected machine interface, PyRange compares:

* Expected network membership
* Actual network membership
* Expected static IPv4 address
* Actual Docker IPv4 address

An expected interface may be:

* `matching`
* `missing`
* `drifted`

Example:

```text
- public-net: drifted
    Expected IP: 172.28.20.10
    Actual IP: 172.28.20.99
```

A missing expected network attachment is also considered topology drift for an existing container.

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

For example, a lab with one running machine and one missing machine is `partial`.

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

```bash
pyrange start scenarios/segmented-lab.yaml
```

### Inspect Runtime Status

```bash
pyrange status scenarios/segmented-lab.yaml
```

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

### Stop a Lab

```bash
pyrange stop scenarios/segmented-lab.yaml
```

### Create a Snapshot

Create a named snapshot of a machine in a running lab:

```bash
pyrange snapshot scenarios/segmented-lab.yaml web checkpoint-1
```

Example output:

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

Example output:

```text
Restoring snapshot: web (checkpoint-1)
Snapshot restored successfully.
Machine: web
Image: pyrange-snapshots/segmented-lab-web:checkpoint-1
Image ID: sha256:...
```

> Restoring a snapshot replaces the current container. Unsnapshotted changes in that container's writable filesystem are discarded.

## Lab Lifecycle

When a lab starts, PyRange performs the following operations:

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

If container creation, network attachment, startup, or health validation fails, PyRange attempts to roll back resources created during startup.

Rollback removes containers first and then networks in reverse creation order.

When a lab is stopped normally, PyRange also removes its containers and networks.

## Runtime Inspection Lifecycle

Runtime status evaluation is independent of lab startup and shutdown.

The inspection flow is:

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

Snapshot names accepted by PyRange:

* Must begin with a letter, digit, or underscore
* May contain letters, digits, underscores, periods, and hyphens
* May contain up to 128 characters

Valid examples include:

```text
checkpoint-1
before-test
baseline_01
v1.2
```

Examples rejected by PyRange include names containing spaces, `/`, or `:`.

### Snapshot Restore

Restore performs validation before removing the current container.

Before the destructive part of restoration begins, PyRange:

1. Resolves the target machine from the scenario.
2. Validates the snapshot name.
3. Builds the deterministic snapshot image reference.
4. Verifies that the Docker image exists.
5. Resolves that image reference to a Docker image ID.

Only after those checks succeed does PyRange remove the current machine container.

The restore lifecycle is:

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

Network membership and static IP addresses are reconstructed from the scenario rather than being recovered from the snapshot image.

The resolved Docker image ID is used for container recreation instead of relying on the mutable snapshot tag after preflight validation.

### Restore Failure Semantics

Snapshot restore is protected by preflight checks, but it is **not fully transactional**.

Failures that occur before the current container is removed leave that container untouched.

However, after the current container has been removed, a later failure during container creation, network attachment, startup, or health validation does not automatically reconstruct the previous runtime state.

This behavior is an explicit limitation of the current snapshot implementation.

### Snapshot Semantics

PyRange snapshots currently use `docker commit`.

They capture changes in the container's writable filesystem layer.

They do **not** represent a full virtual-machine-style checkpoint.

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

Deterministic naming makes orchestration and runtime inspection predictable and provides a foundation for future resource discovery, telemetry, and management capabilities.

## Testing

Run the full test suite:

```bash
pytest -v
```

PyRange v0.4.0 currently contains **120 automated tests**.

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
* Lab Manager error handling through the CLI
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
* CLI behavior
* CLI error handling
* Real Docker lab lifecycle
* Real Docker segmented multi-network topology
* Real Docker runtime status inspection
* Real Docker snapshot and restore behavior

Tests that require a running Docker Engine use the `integration` marker.

Run only the integration tests with:

```bash
pytest -v -m integration -rs
```

PyRange v0.4.0 currently includes **4 real Docker integration tests**:

1. Basic single-network lab lifecycle
2. Segmented multi-network lab lifecycle and topology
3. Runtime status across real lab startup and shutdown
4. Snapshot creation and restoration

### Runtime Status Integration Test

The runtime-status integration test performs a real Docker workflow:

```text
Create unique test scenario
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

The test also verifies a real multi-network machine and its static IP assignments through the runtime status engine.

### Snapshot Integration Test

The snapshot/restore integration test performs the following real Docker workflow:

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

If Docker is unavailable, Docker-dependent integration tests can be skipped.

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
|   |   `-- test_runtime_status.py
|   |
|   |-- test_cli.py
|   |-- test_docker_engine.py
|   |-- test_health.py
|   |-- test_lab_manager.py
|   |-- test_scenario.py
|   |-- test_scenario_loader.py
|   |-- test_snapshot.py
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

PyRange v0.4.0 focuses on reproducible Docker topology, runtime topology inspection, machine readiness checks, and filesystem-oriented machine snapshots.

Current limitations include:

* IPv4 networking only
* Docker is the only execution backend
* Health checks are command-based only
* No custom machine startup command model
* No persistent PyRange state database
* Runtime status is evaluated on demand rather than continuously
* No background monitoring daemon
* Runtime status does not currently execute configured health checks
* Runtime status focuses on expected scenario resources rather than performing a complete inventory of arbitrary extra Docker resources
* Unexpected network attachments are detected only on expected scenario containers
* No persistent runtime-status history
* No structured event log
* No persistent snapshot catalog
* No snapshot listing command
* No snapshot deletion command
* Snapshot storage is managed as local Docker images
* Snapshot images capture container writable filesystem state rather than full machine state
* External Docker volume data is not captured by snapshots
* Container memory and live process state are not captured
* Restore replaces the current container
* Restore is not fully transactional after the original container has been removed
* No telemetry collection
* No scenario action engine
* No detection integration
* No scoring system

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

### Future Development

Planned areas of development include:

* Structured event logging
* Telemetry collection
* Scenario actions
* Detection experiments
* Detection-engine integration
* Lab scoring
* Additional orchestration backends

## Security

PyRange is designed for controlled and authorized cybersecurity environments.

Use PyRange only on systems, Docker environments, and networks for which you have explicit authorization.

Do not use PyRange against third-party systems or infrastructure without permission.

See `SECURITY.md` for the project's security policy.
