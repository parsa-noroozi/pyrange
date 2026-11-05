"""Characterize exec survival on the tested Docker environment, not all engines."""
import json
import platform
import re
import subprocess
import time
from uuid import uuid4

import pytest

from pyrange.engine.docker import DockerCommandTimeoutError, execute_container_command


def docker(*args):
    return subprocess.run(
        ['docker', *args], capture_output=True, text=True, check=True, timeout=30,
    ).stdout.strip()


@pytest.mark.integration
def test_exec_workload_can_continue_after_client_timeout(tmp_path):
    # Missing prerequisites fail this experiment rather than silently satisfying its gate.
    engine = json.loads(docker('version', '--format', '{{json .Server}}'))
    assert docker('info', '--format', '{{.OSType}}') == 'linux'
    image_id = docker('image', 'inspect', 'alpine:latest', '--format', '{{.Id}}')
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', image_id)
    token = uuid4().hex
    name = f'pyrange-timeout-probe-{token}'
    container_id = None
    primary = None
    evidence = {'python': platform.python_version(), 'platform': platform.system(),
                'engine': engine.get('Version'), 'image_id': image_id,
                'client_timeout_observed': False, 'continued_after_timeout': False}
    try:
        container_id = docker(
            'create', '--name', name, '--network', 'none',
            '--label', f'pyrange.timeout-probe={token}', image_id, 'sleep', '120',
        )
        assert re.fullmatch(r'[0-9a-f]{64}', container_id)
        docker('start', container_id)
        with pytest.raises(DockerCommandTimeoutError) as caught:
            execute_container_command(container_id, ['sh', '-c',
                'touch /tmp/started; '
                'while [ ! -f /tmp/release ]; do sleep 0.1; done; '
                'touch /tmp/finished'], 3)
        evidence['client_timeout_observed'] = True
        assert caught.value.cancellation_confirmed is False
        # A start marker rules out a client timeout before the exec was launched.
        docker('exec', container_id, 'test', '-f', '/tmp/started')
        docker('exec', container_id, 'test', '!', '-f', '/tmp/finished')
        # Only now release the original workload: completion proves post-timeout execution.
        docker('exec', container_id, 'touch', '/tmp/release')
        deadline = time.monotonic() + 10
        while True:
            result = execute_container_command(container_id, ['test', '-f', '/tmp/finished'], 2)
            if result.exit_code == 0:
                break
            assert result.exit_code == 1, result.stderr
            assert time.monotonic() < deadline, 'No continuation observed; investigate, do not infer cancellation.'
            time.sleep(0.2)
        evidence['continued_after_timeout'] = True
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            if container_id is not None:
                assert re.fullmatch(r'[0-9a-f]{64}', container_id), 'Refusing cleanup without a full ID'
                obj = json.loads(docker('container', 'inspect', container_id))[0]
                assert obj['Id'] == container_id
                assert obj['Config']['Labels'].get('pyrange.timeout-probe') == token
                docker('rm', '-f', container_id)
                evidence['cleanup'] = 'removed_created_id'
        except BaseException as cleanup:
            evidence['cleanup'] = 'failed'
            if primary is None:
                primary = cleanup
                raise
            primary.add_note(f'Timeout probe cleanup failed for {container_id}: {cleanup}')
        finally:
            report = json.dumps(evidence, indent=2)
            print('\nTimeout experiment:\n' + report)
            try:
                (tmp_path / 'timeout-evidence.json').write_text(report, encoding='utf-8')
            except OSError as write_error:
                if primary is None:
                    raise
                primary.add_note(f'Could not save timeout evidence: {write_error}')
