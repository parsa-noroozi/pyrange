# PyRange

PyRange is a Python-based platform for defining, validating, and orchestrating reproducible cybersecurity labs with Docker.

Instead of manually creating networks and containers for every lab, PyRange allows a lab environment to be described using a YAML scenario and managed through a command-line interface.

> PyRange is intended for authorized cybersecurity labs, research environments, and educational use.

## Current Version

**v0.1.0 — Initial Lab Orchestration**

The current release provides the core infrastructure required to load a scenario, validate it, create isolated Docker resources, and clean them up safely.

## Features

* YAML-based lab definitions
* Scenario validation with Pydantic
* IPv4 subnet validation
* Duplicate machine name and IP detection
* Docker Engine availability checks
* Isolated Docker bridge networks
* Static container IP addresses
* Docker container lifecycle management
* Scenario-level lab orchestration
* Automatic rollback on startup failure
* CLI-based lab management
* Clean CLI error handling
* Unit and end-to-end integration tests

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
Validation
     |
     v
Lab Manager
     |
     v
Docker Backend
     |
     +-- Network
     |
     +-- Containers
```

PyRange separates scenario definition, validation, orchestration, and Docker operations into independent components.

This allows the execution backend and lab capabilities to evolve without coupling them directly to the scenario format.

## Requirements

* Python 3.12 or newer
* Docker Desktop or Docker Engine
* Git

Docker must be running before starting a lab.

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

## Scenario Example

A basic lab can be defined as:

```yaml
name: basic-web-lab
description: Basic isolated web security laboratory

network:
  name: lab-net
  subnet: 172.28.10.0/24

machines:
  - name: web
    image: nginx:alpine
    ip: 172.28.10.10

  - name: analyst
    image: alpine:latest
    ip: 172.28.10.20
```

Before Docker resources are created, PyRange validates the scenario.

Examples of rejected configurations include:

* Duplicate machine names
* Duplicate IP addresses
* IP addresses outside the configured subnet
* Network or broadcast addresses assigned to machines
* Unknown configuration fields

## CLI

Inspect a scenario:

```bash
pyrange inspect scenarios/basic-web-lab.yaml
```

Example output:

```text
Scenario: basic-web-lab
Description: Basic isolated web security laboratory
Network: lab-net
Subnet: 172.28.10.0/24
Machines: 2
  - web: nginx:alpine @ 172.28.10.10
  - analyst: alpine:latest @ 172.28.10.20
```

Start a lab:

```bash
pyrange start scenarios/basic-web-lab.yaml
```

Stop and remove the lab:

```bash
pyrange stop scenarios/basic-web-lab.yaml
```

## Lab Lifecycle

When a lab starts, PyRange currently performs the following operations:

```text
Validate scenario
      |
      v
Create isolated network
      |
      v
Create containers
      |
      v
Assign static IP addresses
      |
      v
Start containers
```

If startup fails partway through, PyRange attempts to roll back resources that were already created.

When the lab is stopped, containers are removed before the Docker network is removed.

## Resource Naming

Docker resources created by PyRange use deterministic names.

For example:

```text
pyrange-basic-web-lab-lab-net
pyrange-basic-web-lab-web
pyrange-basic-web-lab-analyst
```

Managed containers are also labeled with:

```text
pyrange.managed=true
```

This will allow future PyRange versions to identify and manage their own Docker resources safely.

## Testing

Run the full test suite:

```bash
pytest -v
```

The v0.1.0 release includes **40 automated tests**.

The suite covers:

* Scenario validation
* YAML loading
* CLI behavior
* CLI error handling
* Docker availability
* Docker network lifecycle
* Docker container lifecycle
* Lab Manager orchestration
* Rollback behavior
* End-to-end Docker lifecycle

Integration tests that require Docker are marked separately:

```bash
pytest -v -m integration
```

## Project Structure

```text
pyrange/
├── pyrange/
│   ├── cli.py
│   ├── core/
│   │   └── scenario_loader.py
│   ├── engine/
│   │   ├── docker.py
│   │   └── manager.py
│   └── models/
│       └── scenario.py
│
├── scenarios/
│   └── basic-web-lab.yaml
│
├── tests/
│   ├── integration/
│   ├── test_cli.py
│   ├── test_docker_engine.py
│   ├── test_lab_manager.py
│   ├── test_scenario.py
│   └── test_scenario_loader.py
│
├── docs/
├── pyproject.toml
├── README.md
└── SECURITY.md
```

## Current Limitations

PyRange v0.1.0 intentionally keeps the lab model simple.

Current limitations include:

* One network per scenario
* One network interface per machine
* No custom machine commands
* No persistent state database
* No health checks
* No telemetry collection
* No detection or scoring system

These are planned areas of development rather than hidden limitations.

## Roadmap

### v0.1 — Core Orchestration

* [x] Scenario models
* [x] YAML loading
* [x] Validation
* [x] CLI
* [x] Docker network lifecycle
* [x] Docker container lifecycle
* [x] Lab Manager
* [x] Rollback
* [x] End-to-end testing

### v0.2 — Network Topology

Planned focus:

* Multiple networks per scenario
* Machines connected to multiple networks
* More realistic segmented lab architectures
* Improved network validation

Future versions will expand into health monitoring, telemetry, scenario actions, detection experiments, and scoring.

## Security

PyRange is designed for controlled and authorized cybersecurity environments.

Do not use PyRange against systems or networks without explicit authorization.

See `SECURITY.md` for the project's security policy.
