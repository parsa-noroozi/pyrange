import subprocess


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
        message = exc.stderr.strip() or "Docker Engine is unavailable."
        raise DockerUnavailableError(message) from exc

    version = result.stdout.strip()

    if not version:
        raise DockerUnavailableError(
            "Docker Engine returned an empty server version."
        )

    return version


class DockerOperationError(RuntimeError):
    pass


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
        message = exc.stderr.strip() or "Failed to create Docker network."
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
        message = exc.stderr.strip() or "Failed to remove Docker network."
        raise DockerOperationError(message) from exc


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
        message = exc.stderr.strip() or "Failed to create Docker container."
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
        message = exc.stderr.strip() or "Failed to start Docker container."
        raise DockerOperationError(message) from exc


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
        message = exc.stderr.strip() or "Failed to remove Docker container."
        raise DockerOperationError(message) from exc
