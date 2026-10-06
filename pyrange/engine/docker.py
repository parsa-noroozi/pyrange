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


def create_network(name: str, subnet: str) -> str:
    try:
        result = subprocess.run(
            [
                "docker",
                "network",
                "create",
                "--driver",
                "bridge",
                "--subnet",
                subnet,
                "--internal",
                name,
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
) -> str:
    try:
        result = subprocess.run(
            [
                "docker",
                "create",
                "--name",
                name,
                "--network",
                network,
                "--ip",
                ip,
                "--label",
                "pyrange.managed=true",
                image,
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
) -> str:
    try:
        result = subprocess.run(
            [
                "docker",
                "commit",
                name,
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
