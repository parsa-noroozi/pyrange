import json
import subprocess
from dataclasses import dataclass


class DockerUnavailableError(RuntimeError):
    pass


def get_docker_server_version() -> str:
    try:
        result = subprocess.run(
            [
                "docker",
                "version",
                "--format",
                "{{.Server.Version}}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise DockerUnavailableError(
            "Docker CLI was not found."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = (
            exc.stderr.strip()
            or "Docker Engine is unavailable."
        )
        raise DockerUnavailableError(message) from exc

    version = result.stdout.strip()

    if not version:
        raise DockerUnavailableError(
            "Docker Engine returned an empty server version."
        )

    return version


class DockerOperationError(RuntimeError):
    pass


@dataclass(frozen=True)
class DockerResourceIdentity:
    resource_id: str
    labels: dict[str, str] | None




@dataclass(frozen=True)
class ContainerCommandResult:
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ContainerNetworkState:
    network_name: str
    ip_address: str


@dataclass(frozen=True)
class ContainerRuntimeState:
    name: str
    status: str
    networks: tuple[ContainerNetworkState, ...]


@dataclass(frozen=True)
class ContainerStatsSnapshot:
    name: str
    cpu_percent: str
    memory_usage: str
    memory_percent: str
    network_io: str
    block_io: str
    pids: int


@dataclass(frozen=True)
class NetworkRuntimeState:
    name: str
    subnets: tuple[str, ...]


def _run_docker_query(
    command: list[str],
    fallback_error: str,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise DockerUnavailableError(
            "Docker CLI was not found."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or fallback_error
        raise DockerOperationError(message) from exc


def _load_single_inspect_object(
    raw_output: str,
    resource_description: str,
) -> dict[str, object]:
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise DockerOperationError(
            "Docker returned invalid inspection data for "
            f"{resource_description}."
        ) from exc

    if (
        not isinstance(payload, list)
        or len(payload) != 1
        or not isinstance(payload[0], dict)
    ):
        raise DockerOperationError(
            "Docker returned invalid inspection data for "
            f"{resource_description}."
        )

    return payload[0]


def inspect_container_identity(
    reference: str,
) -> DockerResourceIdentity:
    result = _run_docker_query(
        [
            "docker",
            "container",
            "inspect",
            reference,
        ],
        f"Failed to inspect Docker container '{reference}'.",
    )

    payload = _load_single_inspect_object(
        result.stdout,
        f"container '{reference}'",
    )

    resource_id = payload.get("Id")
    config = payload.get("Config")

    if (
        not isinstance(resource_id, str)
        or len(resource_id) != 64
        or any(
            character not in "0123456789abcdef"
            for character in resource_id
        )
        or not isinstance(config, dict)
    ):
        raise DockerOperationError(
            "Docker returned invalid identity data for "
            f"container '{reference}'."
        )

    labels = config.get("Labels")

    if labels is not None:
        if not isinstance(labels, dict) or any(
            not isinstance(key, str)
            or not isinstance(value, str)
            for key, value in labels.items()
        ):
            raise DockerOperationError(
                "Docker returned invalid ownership labels for "
                f"container '{reference}'."
            )

    return DockerResourceIdentity(
        resource_id=resource_id,
        labels=None if labels is None else dict(labels),
    )


def find_container_identity(
    name: str,
) -> DockerResourceIdentity | None:
    if not isinstance(name, str):
        raise TypeError("container name must be a string")
    if not name or name != name.strip():
        raise ValueError("container name must not be empty or padded")

    result = _run_docker_query(
        [
            "docker",
            "container",
            "ls",
            "--all",
            "--no-trunc",
            "--format",
            "{{json .}}",
        ],
        "Failed to list Docker containers.",
    )

    matching_ids: list[str] = []

    for line in result.stdout.splitlines():
        if not line.strip():
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DockerOperationError(
                "Docker returned invalid container listing data."
            ) from exc

        if not isinstance(entry, dict):
            raise DockerOperationError(
                "Docker returned invalid container listing data."
            )

        resource_id = entry.get("ID")
        names = entry.get("Names")

        if (
            not isinstance(resource_id, str)
            or len(resource_id) != 64
            or any(
                character not in "0123456789abcdef"
                for character in resource_id
            )
            or not isinstance(names, str)
            or not names.strip()
        ):
            raise DockerOperationError(
                "Docker returned invalid container listing data."
            )

        listed_names = {
            item.strip()
            for item in names.split(",")
        }

        if name in listed_names:
            matching_ids.append(resource_id)

    if not matching_ids:
        return None

    if len(matching_ids) != 1:
        raise DockerOperationError(
            f"Docker returned ambiguous container name '{name}'."
        )

    selected_id = matching_ids[0]
    identity = inspect_container_identity(selected_id)

    if identity.resource_id != selected_id:
        raise DockerOperationError(
            "Docker inspection returned a different container ID."
        )

    return identity


def inspect_container_runtime(
    name: str,
) -> ContainerRuntimeState | None:
    list_result = _run_docker_query(
        [
            "docker",
            "container",
            "ls",
            "--all",
            "--format",
            "{{.Names}}",
        ],
        "Failed to list Docker containers.",
    )

    container_names = {
        line.strip()
        for line in list_result.stdout.splitlines()
        if line.strip()
    }

    if name not in container_names:
        return None

    inspect_result = _run_docker_query(
        [
            "docker",
            "container",
            "inspect",
            name,
        ],
        f"Failed to inspect Docker container '{name}'.",
    )

    payload = _load_single_inspect_object(
        inspect_result.stdout,
        f"container '{name}'",
    )

    state_data = payload.get("State")
    network_settings = payload.get("NetworkSettings")

    if (
        not isinstance(state_data, dict)
        or not isinstance(network_settings, dict)
    ):
        raise DockerOperationError(
            "Docker returned invalid inspection data for "
            f"container '{name}'."
        )

    status = state_data.get("Status")
    networks_data = network_settings.get("Networks")

    if (
        not isinstance(status, str)
        or not status
        or not isinstance(networks_data, dict)
    ):
        raise DockerOperationError(
            "Docker returned invalid inspection data for "
            f"container '{name}'."
        )

    networks: list[ContainerNetworkState] = []

    for network_name, attachment in sorted(
        networks_data.items()
    ):
        if (
            not isinstance(network_name, str)
            or not isinstance(attachment, dict)
        ):
            raise DockerOperationError(
                "Docker returned invalid inspection data for "
                f"container '{name}'."
            )

        ip_address = attachment.get("IPAddress")

        if not isinstance(ip_address, str):
            raise DockerOperationError(
                "Docker returned invalid inspection data for "
                f"container '{name}'."
            )

        networks.append(
            ContainerNetworkState(
                network_name=network_name,
                ip_address=ip_address,
            )
        )

    return ContainerRuntimeState(
        name=name,
        status=status,
        networks=tuple(networks),
    )


def get_container_stats(
    name: str,
) -> ContainerStatsSnapshot:
    result = _run_docker_query(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            name,
        ],
        f"Failed to collect Docker stats for "
        f"container '{name}'.",
    )

    lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]

    if len(lines) != 1:
        raise DockerOperationError(
            "Docker returned invalid stats data for "
            f"container '{name}'."
        )

    try:
        payload = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise DockerOperationError(
            "Docker returned invalid stats data for "
            f"container '{name}'."
        ) from exc

    if not isinstance(payload, dict):
        raise DockerOperationError(
            "Docker returned invalid stats data for "
            f"container '{name}'."
        )

    returned_name = payload.get("Name")
    cpu_percent = payload.get("CPUPerc")
    memory_usage = payload.get("MemUsage")
    memory_percent = payload.get("MemPerc")
    network_io = payload.get("NetIO")
    block_io = payload.get("BlockIO")
    pids_raw = payload.get("PIDs")

    string_fields = (
        returned_name,
        cpu_percent,
        memory_usage,
        memory_percent,
        network_io,
        block_io,
    )

    if any(
        not isinstance(value, str)
        or not value.strip()
        for value in string_fields
    ):
        raise DockerOperationError(
            "Docker returned invalid stats data for "
            f"container '{name}'."
        )

    if returned_name != name:
        raise DockerOperationError(
            "Docker returned invalid stats data for "
            f"container '{name}'."
        )

    if isinstance(pids_raw, bool):
        raise DockerOperationError(
            "Docker returned invalid stats data for "
            f"container '{name}'."
        )

    if isinstance(pids_raw, int):
        pids = pids_raw
    elif (
        isinstance(pids_raw, str)
        and pids_raw.strip().isdigit()
    ):
        pids = int(pids_raw)
    else:
        raise DockerOperationError(
            "Docker returned invalid stats data for "
            f"container '{name}'."
        )

    if pids < 0:
        raise DockerOperationError(
            "Docker returned invalid stats data for "
            f"container '{name}'."
        )

    return ContainerStatsSnapshot(
        name=returned_name,
        cpu_percent=cpu_percent,
        memory_usage=memory_usage,
        memory_percent=memory_percent,
        network_io=network_io,
        block_io=block_io,
        pids=pids,
    )


def inspect_network_identity(
    reference: str,
) -> DockerResourceIdentity:
    result = _run_docker_query(
        [
            "docker",
            "network",
            "inspect",
            reference,
        ],
        f"Failed to inspect Docker network '{reference}'.",
    )

    payload = _load_single_inspect_object(
        result.stdout,
        f"network '{reference}'",
    )

    resource_id = payload.get("Id")

    if (
        not isinstance(resource_id, str)
        or len(resource_id) != 64
        or any(
            character not in "0123456789abcdef"
            for character in resource_id
        )
    ):
        raise DockerOperationError(
            "Docker returned invalid identity data for "
            f"network '{reference}'."
        )

    labels = payload.get("Labels")

    if labels is not None:
        if not isinstance(labels, dict) or any(
            not isinstance(key, str)
            or not isinstance(value, str)
            for key, value in labels.items()
        ):
            raise DockerOperationError(
                "Docker returned invalid ownership labels for "
                f"network '{reference}'."
            )

    return DockerResourceIdentity(
        resource_id=resource_id,
        labels=None if labels is None else dict(labels),
    )


def find_network_identity(
    name: str,
) -> DockerResourceIdentity | None:
    if not isinstance(name, str):
        raise TypeError("network name must be a string")
    if not name or name != name.strip():
        raise ValueError("network name must not be empty or padded")

    result = _run_docker_query(
        [
            "docker",
            "network",
            "ls",
            "--no-trunc",
            "--format",
            "{{json .}}",
        ],
        "Failed to list Docker networks.",
    )

    matching_ids: list[str] = []

    for line in result.stdout.splitlines():
        if not line.strip():
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DockerOperationError(
                "Docker returned invalid network listing data."
            ) from exc

        if not isinstance(entry, dict):
            raise DockerOperationError(
                "Docker returned invalid network listing data."
            )

        resource_id = entry.get("ID")
        listed_name = entry.get("Name")

        if (
            not isinstance(resource_id, str)
            or not resource_id.strip()
            or not isinstance(listed_name, str)
            or not listed_name.strip()
        ):
            raise DockerOperationError(
                "Docker returned invalid network listing data."
            )

        if listed_name != name:
            continue

        if (
            len(resource_id) != 64
            or any(
                character not in "0123456789abcdef"
                for character in resource_id
            )
        ):
            raise DockerOperationError(
                "Docker returned an invalid or unsupported "
                f"network ID for '{name}'."
            )

        matching_ids.append(resource_id)

    if not matching_ids:
        return None

    if len(matching_ids) != 1:
        raise DockerOperationError(
            f"Docker returned ambiguous network name '{name}'."
        )

    selected_id = matching_ids[0]
    identity = inspect_network_identity(selected_id)

    if identity.resource_id != selected_id:
        raise DockerOperationError(
            "Docker inspection returned a different network ID."
        )

    return identity


def inspect_network_runtime(
    name: str,
) -> NetworkRuntimeState | None:
    list_result = _run_docker_query(
        [
            "docker",
            "network",
            "ls",
            "--format",
            "{{.Name}}",
        ],
        "Failed to list Docker networks.",
    )

    network_names = {
        line.strip()
        for line in list_result.stdout.splitlines()
        if line.strip()
    }

    if name not in network_names:
        return None

    inspect_result = _run_docker_query(
        [
            "docker",
            "network",
            "inspect",
            name,
        ],
        f"Failed to inspect Docker network '{name}'.",
    )

    payload = _load_single_inspect_object(
        inspect_result.stdout,
        f"network '{name}'",
    )

    ipam_data = payload.get("IPAM")

    if not isinstance(ipam_data, dict):
        raise DockerOperationError(
            "Docker returned invalid inspection data for "
            f"network '{name}'."
        )

    config_data = ipam_data.get("Config")

    if not isinstance(config_data, list):
        raise DockerOperationError(
            "Docker returned invalid inspection data for "
            f"network '{name}'."
        )

    subnets: list[str] = []

    for config in config_data:
        if not isinstance(config, dict):
            raise DockerOperationError(
                "Docker returned invalid inspection data for "
                f"network '{name}'."
            )

        subnet = config.get("Subnet")

        if subnet is None:
            continue

        if not isinstance(subnet, str):
            raise DockerOperationError(
                "Docker returned invalid inspection data for "
                f"network '{name}'."
            )

        if subnet:
            subnets.append(subnet)

    return NetworkRuntimeState(
        name=name,
        subnets=tuple(sorted(subnets)),
    )


def get_image_id(image_ref: str) -> str:
    try:
        result = subprocess.run(
            [
                "docker",
                "image",
                "inspect",
                "--format",
                "{{.Id}}",
                image_ref,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise DockerUnavailableError(
            "Docker CLI was not found."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = (
            exc.stderr.strip()
            or f"Failed to inspect Docker image '{image_ref}'."
        )
        raise DockerOperationError(message) from exc

    image_id = result.stdout.strip()

    if not image_id:
        raise DockerOperationError(
            "Docker returned an empty image ID."
        )

    return image_id


def create_network(
    name: str,
    subnet: str,
    *,
    labels: dict[str, str] | None = None,
) -> str:
    command = [
        "docker",
        "network",
        "create",
        "--driver",
        "bridge",
        "--subnet",
        subnet,
        "--internal",
    ]

    if labels is not None:
        for key, value in sorted(labels.items()):
            command.extend([
                "--label",
                f"{key}={value}",
            ])

    command.append(name)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise DockerUnavailableError(
            "Docker CLI was not found."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = (
            exc.stderr.strip()
            or "Failed to create Docker network."
        )
        raise DockerOperationError(message) from exc

    network_id = result.stdout.strip()

    if not network_id:
        raise DockerOperationError(
            "Docker returned an empty network ID."
        )

    return network_id


def remove_network(name: str) -> None:
    try:
        subprocess.run(
            ["docker", "network", "rm", name],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise DockerUnavailableError(
            "Docker CLI was not found."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = (
            exc.stderr.strip()
            or "Failed to remove Docker network."
        )
        raise DockerOperationError(message) from exc


def connect_container_to_network(
    name: str,
    network: str,
    ip: str,
) -> None:
    result = subprocess.run(
        [
            "docker",
            "network",
            "connect",
            "--ip",
            ip,
            network,
            name,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        message = result.stderr.strip()
        raise DockerOperationError(
            message
            or (
                f"failed to connect container '{name}' "
                f"to network '{network}'"
            )
        )


def create_container(
    name: str,
    image: str,
    network: str,
    ip: str,
    *,
    labels: dict[str, str] | None = None,
) -> str:
    container_labels = {
        "pyrange.managed": "true",
    }
    if labels is not None:
        container_labels.update(labels)

    command = [
        "docker",
        "create",
        "--name",
        name,
        "--network",
        network,
        "--ip",
        ip,
    ]

    for key, value in sorted(container_labels.items()):
        command.extend([
            "--label",
            f"{key}={value}",
        ])

    command.append(image)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise DockerUnavailableError(
            "Docker CLI was not found."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = (
            exc.stderr.strip()
            or "Failed to create Docker container."
        )
        raise DockerOperationError(message) from exc

    container_id = result.stdout.strip()

    if not container_id:
        raise DockerOperationError(
            "Docker returned an empty container ID."
        )

    return container_id


def start_container(name: str) -> None:
    try:
        subprocess.run(
            ["docker", "start", name],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise DockerUnavailableError(
            "Docker CLI was not found."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = (
            exc.stderr.strip()
            or "Failed to start Docker container."
        )
        raise DockerOperationError(message) from exc


def execute_container_command(
    name: str,
    command: list[str],
    timeout_seconds: float,
) -> ContainerCommandResult:
    if not command:
        raise ValueError("command must not be empty")

    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                name,
                *command,
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise DockerUnavailableError(
            "Docker CLI was not found."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise DockerOperationError(
            f"Command timed out in container '{name}' "
            f"after {timeout_seconds} seconds."
        ) from exc

    return ContainerCommandResult(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def create_container_snapshot(
    name: str,
    image_ref: str,
    *,
    labels: dict[str, str] | None = None,
) -> str:
    command = ["docker", "commit"]
    if labels is not None:
        for key, value in sorted(labels.items()):
            if (
                not isinstance(key, str) or not key
                or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for c in key)
                or not isinstance(value, str)
                or any(c in value for c in "\r\n\x00")
            ):
                raise ValueError("Invalid snapshot label key or value.")
            escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")
            command.extend(["--change", f'LABEL {key}="{escaped}"'])
    command.extend([name, image_ref])

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise DockerUnavailableError(
            "Docker CLI was not found."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = (
            exc.stderr.strip()
            or "Failed to create container snapshot."
        )
        raise DockerOperationError(message) from exc

    image_id = result.stdout.strip()

    if not image_id:
        raise DockerOperationError(
            "Docker returned an empty snapshot image ID."
        )

    return image_id


def remove_container(name: str) -> None:
    try:
        subprocess.run(
            ["docker", "rm", "--force", name],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise DockerUnavailableError(
            "Docker CLI was not found."
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = (
            exc.stderr.strip()
            or "Failed to remove Docker container."
        )
        raise DockerOperationError(message) from exc


def _valid_image_identity(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(c in "0123456789abcdef" for c in value[7:])
    )


def inspect_image_identity(reference: str) -> DockerResourceIdentity:
    result = _run_docker_query(
        ["docker", "image", "inspect", reference],
        f"Failed to inspect Docker image '{reference}'.",
    )
    payload = _load_single_inspect_object(result.stdout, f"image '{reference}'")
    resource_id = payload.get("Id")
    config = payload.get("Config")
    if not _valid_image_identity(resource_id) or not isinstance(config, dict):
        raise DockerOperationError("Docker returned invalid image identity data.")
    labels = config.get("Labels")
    if labels is not None and (
        not isinstance(labels, dict)
        or any(not isinstance(k, str) or not isinstance(v, str) for k, v in labels.items())
    ):
        raise DockerOperationError("Docker returned invalid image ownership labels.")
    return DockerResourceIdentity(resource_id, None if labels is None else dict(labels))


def find_image_identity(image_ref: str) -> DockerResourceIdentity | None:
    """Resolve an explicit repository:tag, then inspect its immutable image ID."""
    if not isinstance(image_ref, str):
        raise TypeError("image reference must be a string")
    repository, separator, tag = image_ref.rpartition(":")
    if not separator or not repository or not tag or "/" in tag or "@" in image_ref or any(c.isspace() for c in image_ref):
        raise ValueError("image reference must contain an explicit repository and tag")
    result = _run_docker_query(
        ["docker", "image", "ls", "--all", "--no-trunc", "--format", "{{json .}}"],
        "Failed to list Docker images.",
    )
    matches = set()
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DockerOperationError("Docker returned invalid image listing data.") from exc
        if not isinstance(entry, dict) or any(
            not isinstance(entry.get(key), str) or not entry[key]
            for key in ("Repository", "Tag", "ID")
        ):
            raise DockerOperationError("Docker returned invalid image listing data.")
        if entry["Repository"] == repository and entry["Tag"] == tag:
            if not _valid_image_identity(entry["ID"]):
                raise DockerOperationError("Docker returned invalid image ID.")
            matches.add(entry["ID"])
    if not matches:
        return None
    if len(matches) != 1:
        raise DockerOperationError("Docker returned ambiguous image reference.")
    selected_id = matches.pop()
    identity = inspect_image_identity(selected_id)
    if identity.resource_id != selected_id:
        raise DockerOperationError("Docker inspection returned a different image ID.")
    return identity
