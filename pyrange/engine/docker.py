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
