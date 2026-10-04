# PyRange

PyRange is a Python-based platform for defining, validating, and orchestrating reproducible cybersecurity labs with Docker.

Instead of manually creating Docker networks, containers, static addressing, health checks, and recovery points for every lab, PyRange allows an environment to be described as a declarative YAML scenario and managed through a command-line interface.

> PyRange is intended for authorized cybersecurity labs, research environments, and educational use only.

## Current Version

**v0.3.0 - Health Checks and Snapshots**

PyRange v0.3.0 extends the network orchestration introduced in v0.2.0 with machine readiness checks and Docker-backed snapshots.

The v0.3.0 release adds:

* Command-based machine health checks
* Configurable health check retries, intervals, and timeouts
* Health-gated lab startup
* Automatic rollback when startup health validation fails
* Named machine snapshots backed by Docker images
* Snapshot preflight validation
* Machine restoration from immutable Docker image IDs
* Restoration of scenario-defined network topology and static IP addresses
* Post-restore health validation
* Snapshot and restore CLI commands
* Real Docker snapshot/restore integration coverage

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
* Snapshot and restore commands
* Clean handling of scenario, Docker, orchestration, and snapshot errors
* Unit coverage for validation, orchestration, health checks, snapshots, and CLI behavior
* Real Docker integration coverage for lab lifecycle, segmented topology, and snapshot restoration

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
                 +------------+------------+
                 |                         |
                 v                         v
            Lab Manager              Snapshot Engine
                 |                         |
                 |                         |
                 +------------+------------+
                              |
                              v
                        Docker Backend
                              |
              +---------------+---------------+
              |               |               |
              v               v               v
           Networks        Containers      Docker Images
              |               |               |
              |               |               |
              |               +-- docker exec |
              |                               |
              +-------- network connect       |
                                              |
                                  docker commit / inspect
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

PyRange separates scenario definition, validation, lab orchestration, health evaluation, snapshot management, and low-level Docker operations into independent components.

The scenario model represents the desired lab topology and optional machine health checks.

The Lab Manager translates a validated scenario into Docker networks and containers.

The Health Evaluator executes configured commands inside running containers and determines whether a machine is ready.

The Snapshot Engine coordinates snapshot creation and restoration while reusing the same Docker backend and deterministic resource naming rules used by normal lab orchestration.

This separation keeps future capabilities such as telemetry, scenario actions, detection experiments, status reporting, and scoring outside the core orchestration layer.

## Requirements

* Python 3.12 or newer
* Docker Desktop or Docker Engine
* Git

Docker must be running before starting a lab or running tests that require a real Docker Engine.

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

Snapshot images use a separate deterministic namespace:

```text
pyrange-snapshots/segmented-lab-web:checkpoint-1
```

Managed containers are labeled with:

```text
pyrange.managed=true
```

Deterministic naming makes orchestration predictable and provides a foundation for future resource discovery and management capabilities.

## Testing

Run the full test suite:

```bash
pytest -v
```

PyRange v0.3.0 currently contains **100 automated tests**.

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
* Health-gated startup
* Health failure rollback
* Lab Manager error handling through the CLI
* Docker network lifecycle
* Docker container lifecycle
* Multi-network attachment
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
* Real Docker snapshot and restore behavior

Tests that require a running Docker Engine use the `integration` marker.

Run only the integration tests with:

```bash
pytest -v -m integration -rs
```

PyRange v0.3.0 currently includes **3 real Docker integration tests**:

1. Basic single-network lab lifecycle
2. Segmented multi-network lab lifecycle and topology
3. Snapshot creation and restoration

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
|   |   `-- snapshot.py
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
|   |   `-- test_multi_network_lifecycle.py
|   |
|   |-- test_cli.py
|   |-- test_docker_engine.py
|   |-- test_health.py
|   |-- test_lab_manager.py
|   |-- test_scenario.py
|   |-- test_scenario_loader.py
|   |-- test_snapshot.py
|   `-- test_snapshot_integration.py
|
|-- docs/
|-- pyproject.toml
|-- README.md
`-- SECURITY.md
```

## Current Limitations

PyRange v0.3.0 focuses on reproducible Docker topology, machine readiness checks, and filesystem-oriented machine snapshots.

Current limitations include:

* IPv4 networking only
* Docker is the only execution backend
* Health checks are command-based only
* No custom machine startup command model
* No persistent PyRange state database
* No persistent snapshot catalog
* No snapshot listing command
* No snapshot deletion command
* Snapshot storage is managed as local Docker images
* Snapshot images capture container writable filesystem state rather than full machine state
* External Docker volume data is not captured by snapshots
* Container memory and live process state are not captured
* Restore replaces the current container
* Restore is not fully transactional after the original container has been removed
* No dedicated lab status command
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

### Future Development

Planned areas of development include:

* Lab status and runtime inspection
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
