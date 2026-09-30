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
