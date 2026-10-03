from unittest.mock import call, patch

import pytest

from pyrange.engine import (
    ContainerCommandResult,
    DockerOperationError,
    DockerUnavailableError,
    HealthCheckResult,
    evaluate_health_check,
)
from pyrange.models import HealthCheckConfig


def make_health_check(
    retries: int = 2,
) -> HealthCheckConfig:
    return HealthCheckConfig(
        command=["health-check"],
        interval_seconds=1.5,
        timeout_seconds=2.0,
        retries=retries,
    )


@patch("pyrange.engine.health.time.sleep")
@patch(
    "pyrange.engine.health.execute_container_command"
)
def test_health_check_succeeds_on_first_attempt(
    mock_execute,
    mock_sleep,
) -> None:
    mock_execute.return_value = ContainerCommandResult(
        exit_code=0,
        stdout="ready\n",
        stderr="",
    )

    result = evaluate_health_check(
        "test-web",
        make_health_check(),
    )

    assert result == HealthCheckResult(
        healthy=True,
        attempts=1,
        exit_code=0,
        stdout="ready\n",
        stderr="",
    )

    mock_execute.assert_called_once_with(
        name="test-web",
        command=["health-check"],
        timeout_seconds=2.0,
    )
    mock_sleep.assert_not_called()


@patch("pyrange.engine.health.time.sleep")
@patch(
    "pyrange.engine.health.execute_container_command"
)
def test_health_check_retries_until_success(
    mock_execute,
    mock_sleep,
) -> None:
    mock_execute.side_effect = [
        ContainerCommandResult(
            exit_code=1,
            stdout="",
            stderr="not ready\n",
        ),
        ContainerCommandResult(
            exit_code=0,
            stdout="ready\n",
            stderr="",
        ),
    ]

    result = evaluate_health_check(
        "test-web",
        make_health_check(),
    )

    assert result.healthy is True
    assert result.attempts == 2
    assert result.exit_code == 0

    assert mock_execute.call_count == 2
    mock_sleep.assert_called_once_with(1.5)


@patch("pyrange.engine.health.time.sleep")
@patch(
    "pyrange.engine.health.execute_container_command"
)
def test_health_check_returns_unhealthy_after_retries(
    mock_execute,
    mock_sleep,
) -> None:
    mock_execute.return_value = ContainerCommandResult(
        exit_code=1,
        stdout="",
        stderr="not ready\n",
    )

    result = evaluate_health_check(
        "test-web",
        make_health_check(retries=2),
    )

    assert result == HealthCheckResult(
        healthy=False,
        attempts=3,
        exit_code=1,
        stdout="",
        stderr="not ready\n",
    )

    assert mock_execute.call_count == 3
    assert mock_sleep.call_args_list == [
        call(1.5),
        call(1.5),
    ]


@patch("pyrange.engine.health.time.sleep")
@patch(
    "pyrange.engine.health.execute_container_command"
)
def test_health_check_retries_command_timeout(
    mock_execute,
    mock_sleep,
) -> None:
    mock_execute.side_effect = DockerOperationError(
        "Command timed out"
    )

    result = evaluate_health_check(
        "test-web",
        make_health_check(retries=1),
    )

    assert result == HealthCheckResult(
        healthy=False,
        attempts=2,
        exit_code=None,
        stdout="",
        stderr="Command timed out",
    )

    assert mock_execute.call_count == 2
    mock_sleep.assert_called_once_with(1.5)


@patch("pyrange.engine.health.time.sleep")
@patch(
    "pyrange.engine.health.execute_container_command"
)
def test_health_check_does_not_retry_docker_unavailable(
    mock_execute,
    mock_sleep,
) -> None:
    mock_execute.side_effect = DockerUnavailableError(
        "Docker CLI was not found."
    )

    with pytest.raises(
        DockerUnavailableError,
        match="Docker CLI was not found",
    ):
        evaluate_health_check(
            "test-web",
            make_health_check(),
        )

    mock_execute.assert_called_once()
    mock_sleep.assert_not_called()


@patch("pyrange.engine.health.time.sleep")
@patch(
    "pyrange.engine.health.execute_container_command"
)
def test_health_check_with_zero_retries_runs_once(
    mock_execute,
    mock_sleep,
) -> None:
    mock_execute.return_value = ContainerCommandResult(
        exit_code=1,
        stdout="",
        stderr="not ready\n",
    )

    result = evaluate_health_check(
        "test-web",
        make_health_check(retries=0),
    )

    assert result == HealthCheckResult(
        healthy=False,
        attempts=1,
        exit_code=1,
        stdout="",
        stderr="not ready\n",
    )

    mock_execute.assert_called_once()
    mock_sleep.assert_not_called()
