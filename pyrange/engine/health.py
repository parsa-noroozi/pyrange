import time
from dataclasses import dataclass

from pyrange.engine.docker import (
    DockerOperationError,
    DockerUnavailableError,
    execute_container_command,
)
from pyrange.models import HealthCheckConfig


@dataclass(frozen=True)
class HealthCheckResult:
    healthy: bool
    attempts: int
    exit_code: int | None
    stdout: str
    stderr: str


def evaluate_health_check(
    container_name: str,
    config: HealthCheckConfig,
) -> HealthCheckResult:
    max_attempts = config.retries + 1

    for attempt in range(1, max_attempts + 1):
        try:
            result = execute_container_command(
                name=container_name,
                command=config.command,
                timeout_seconds=config.timeout_seconds,
            )
        except DockerUnavailableError:
            raise
        except DockerOperationError as exc:
            if attempt < max_attempts:
                time.sleep(config.interval_seconds)
                continue

            return HealthCheckResult(
                healthy=False,
                attempts=attempt,
                exit_code=None,
                stdout="",
                stderr=str(exc),
            )

        if result.exit_code == 0:
            return HealthCheckResult(
                healthy=True,
                attempts=attempt,
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
            )

        if attempt < max_attempts:
            time.sleep(config.interval_seconds)
            continue

        return HealthCheckResult(
            healthy=False,
            attempts=attempt,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    raise RuntimeError("health check evaluation reached invalid state")
