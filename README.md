# PyRange

PyRange is a Python-based platform for defining, validating, and orchestrating reproducible cybersecurity labs with Docker.

Instead of manually creating networks and containers for every lab, PyRange allows a lab environment to be described using a YAML scenario and managed through a command-line interface.

> PyRange is intended for authorized cybersecurity labs, research environments, and educational use.

## Current Version

**v0.2.0 - Network Topology**

PyRange v0.2.0 extends the initial orchestration engine with support for multi-network lab topologies and machines connected to multiple Docker networks.

Scenarios can now describe segmented environments with independent IPv4 subnets, multiple interfaces per machine, static IP assignments, topology validation, and automated cleanup.

## Features

* YAML-based lab definitions
* Scenario validation with Pydantic
* Multiple networks per scenario
* Multiple network interfaces per machine
* Static IPv4 addresses per interface
* IPv4 subnet validation
* Duplicate machine and network name detection
* Duplicate IP detection within a network
* Overlapping subnet detection
* Unknown network reference detection
* Network and broadcast address validation
* Docker Engine availability checks
* Isolated Docker bridge networks
* Multi-network Docker container attachment
* Scenario-level lab orchestration
* Automatic rollback on startup failure
* Reverse-order resource cleanup
* CLI-based lab management
* Clean CLI error handling
* Unit and real Docker integration tests

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
     v
Lab Manager
     |
     v
Docker Backend
     |
     +-- Network A
     |
     +-- Network B
     |
     +-- Containers
            |
            +-- Interface 1
            |
            +-- Interface 2
```

PyRange separates scenario definition, validation, orchestration, and Docker operations into independent components.

The scenario model describes the desired topology. The Lab Manager translates that validated topology into Docker resources while the Docker backend provides lower-level network and container operations.

This separation allows future capabilities such as health checks, telemetry, scenario actions, and scoring to evolve without coupling them directly to the scenario format.

## Requirements

* Python 3.12 or newer
* Docker Desktop or Docker Engine
* Git

Docker must be running before starting a lab or running Docker integration tests.

## Installation

Clone the repository:

```bash
git clone https://github.com/parsa-noroozi/pyrange.git
cd pyrange
```

Create a virtual environment:

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

A PyRange scenario can define multiple networks and multiple interfaces per machine.

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

  - name: analyst
    image: nginx:alpine
    interfaces:
      - network: public-net
        ip: 172.28.20.20

      - network: private-net
        ip: 172.28.30.20
```

This scenario produces the following topology:

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

The `analyst` machine is multi-homed: it is connected to both networks with a separate static IP address on each interface.

## Scenario Validation

PyRange validates the complete topology before Docker resources are created.

Examples of rejected configurations include:

* Duplicate machine names
* Duplicate network names
* Duplicate network attachments on the same machine
* Duplicate IP addresses on the same network
* Interfaces referencing undefined networks
* IP addresses outside the referenced subnet
* Network or broadcast addresses assigned to interfaces
* Overlapping network subnets
* Unknown configuration fields

This prevents invalid lab definitions from reaching the Docker orchestration layer.

## CLI

Inspect a scenario:

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

Start a lab:

```bash
pyrange start scenarios/segmented-lab.yaml
```

Stop and remove the lab:

```bash
pyrange stop scenarios/segmented-lab.yaml
```

## Lab Lifecycle

When a lab starts, PyRange performs the following operations:

```text
Validate scenario
      |
      v
Create all isolated networks
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
Start containers
```

For a multi-homed machine, the first interface is configured when the container is created.

Additional interfaces are attached using Docker network connections with their configured static IP addresses.

If startup fails partway through, PyRange attempts to roll back resources that were already created.

Rollback removes created containers first and then removes created networks in reverse order.

When a lab is stopped normally, PyRange also removes containers and networks in reverse order.

## Resource Naming

Docker resources created by PyRange use deterministic names.

For the segmented example:

```text
pyrange-segmented-lab-public-net
pyrange-segmented-lab-private-net
pyrange-segmented-lab-web
pyrange-segmented-lab-analyst
```

Managed containers are labeled with:

```text
pyrange.managed=true
```

This provides a foundation for future PyRange versions to identify and manage their own Docker resources safely.

## Testing

Run the full test suite:

```bash
pytest -v
```

PyRange v0.2.0 includes **47 automated tests**.

The suite covers:

* Scenario validation
* Multi-network topology validation
* YAML loading
* CLI behavior
* CLI error handling
* Docker availability
* Docker network lifecycle
* Docker container lifecycle
* Docker network attachment
* Multi-network Lab Manager orchestration
* Multi-network rollback behavior
* Reverse-order cleanup
* End-to-end Docker lifecycle
* End-to-end multi-network topology

Integration tests that require a running Docker Engine are marked separately:

```bash
pytest -v -m integration -rs
```

The v0.2.0 test suite currently includes two real Docker integration tests:

* Basic single-network lab lifecycle
* Segmented multi-network lab lifecycle

The multi-network integration test verifies real Docker network membership and static IP assignments.

## Project Structure

```text
pyrange/
|-- pyrange/
|   |-- cli.py
|   |-- core/
|   |   `-- scenario_loader.py
|   |-- engine/
|   |   |-- docker.py
|   |   `-- manager.py
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
|   |-- test_cli.py
|   |-- test_docker_engine.py
|   |-- test_lab_manager.py
|   |-- test_scenario.py
|   `-- test_scenario_loader.py
|
|-- docs/
|-- pyproject.toml
|-- README.md
`-- SECURITY.md
```

## Current Limitations

PyRange v0.2.0 focuses on topology definition and Docker orchestration.

Current limitations include:

* IPv4 networking only
* Docker is the only execution backend
* No custom machine commands
* No persistent state database
* No container health checks
* No snapshots
* No telemetry collection
* No scenario actions
* No detection integration
* No scoring system

These are planned areas of development rather than hidden limitations.

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

Planned focus:

* Container health monitoring
* Machine readiness checks
* Lab status reporting
* Snapshot foundations

Future versions will expand into telemetry, scenario actions, detection experiments, and scoring.

## Security

PyRange is designed for controlled and authorized cybersecurity environments.

Do not use PyRange against systems or networks without explicit authorization.

See `SECURITY.md` for the project's security policy.
