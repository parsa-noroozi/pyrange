import subprocess
from unittest.mock import patch

import pytest

from pyrange.engine import DockerCommandTimeoutError, DockerOperationError
from pyrange.engine.docker import ContainerCommandResult, execute_container_command
from pyrange.engine.health import evaluate_health_check
from pyrange.models import HealthCheckConfig


@pytest.mark.parametrize('stdout,stderr,expected_out,expected_err', [
    (None, None, '', ''),
    (b'partial output', b'partial error', 'partial output', 'partial error'),
    ('text output', 'text error', 'text output', 'text error'),
])
def test_timeout_preserves_diagnostics_and_cause(stdout, stderr, expected_out, expected_err):
    cause = subprocess.TimeoutExpired(['docker', 'exec'], 2, output=stdout, stderr=stderr)
    with patch('pyrange.engine.docker.subprocess.run', side_effect=cause) as run:
        with pytest.raises(DockerCommandTimeoutError) as caught:
            execute_container_command('container-id', ['secret-argument'], 2)
    error = caught.value
    assert isinstance(error, DockerOperationError)
    assert error.__cause__ is cause
    assert error.container_reference == 'container-id'
    assert error.timeout_seconds == 2
    assert error.stdout == expected_out
    assert error.stderr == expected_err
    assert error.cancellation_confirmed is False
    assert 'cancellation is not confirmed' in str(error)
    assert 'secret-argument' not in str(error)
    run.assert_called_once()  # No hidden retry, kill, or removal.


def test_timeout_diagnostic_decode_failure_does_not_mask_timeout():
    cause = subprocess.TimeoutExpired(['docker', 'exec'], 1, output=b'\xff')
    with patch('pyrange.engine.docker.locale.getencoding', return_value='utf-8'):
        with patch('pyrange.engine.docker.subprocess.run', side_effect=cause):
            with pytest.raises(DockerCommandTimeoutError) as caught:
                execute_container_command('container-id', ['check'], 1)
    assert caught.value.stdout == '\ufffd'
    assert caught.value.__cause__ is cause


@pytest.mark.parametrize('value,error', [
    (0, ValueError), (-1, ValueError), (float('nan'), ValueError),
    (float('inf'), ValueError), (float('-inf'), ValueError),
    (None, TypeError), ('2', TypeError), (True, TypeError),
])
def test_invalid_timeout_is_rejected_before_execution(value, error):
    with patch('pyrange.engine.docker.subprocess.run') as run:
        with pytest.raises(error):
            execute_container_command('container-id', ['check'], value)
    run.assert_not_called()


@pytest.mark.parametrize('prior_failure', [False, True])
def test_health_timeout_stops_retries_and_preserves_output(prior_failure):
    error = DockerCommandTimeoutError('container-id', 2, stdout='partial', stderr='detail')
    outcomes = ([ContainerCommandResult(1, '', 'not ready')] if prior_failure else []) + [error]
    config = HealthCheckConfig(command=['check'], timeout_seconds=2, interval_seconds=1, retries=5)
    with patch('pyrange.engine.health.execute_container_command', side_effect=outcomes) as run:
        with patch('pyrange.engine.health.time.sleep') as sleep:
            result = evaluate_health_check('container-id', config)
    assert result.healthy is False
    assert result.exit_code is None
    assert result.stdout == 'partial'
    assert 'cancellation is not confirmed' in result.stderr
    assert result.stderr.endswith('\ndetail')
    assert result.attempts == (2 if prior_failure else 1)
    assert run.call_count == result.attempts
    assert sleep.call_count == (1 if prior_failure else 0)
