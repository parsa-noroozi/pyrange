"""Install one built wheel in a fresh venv and smoke-test it outside the checkout."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import venv


def run(command, *, cwd, env):
    result = subprocess.run(command, cwd=cwd, env=env, text=True,
                            capture_output=True, timeout=300)
    if result.stdout:
        print(result.stdout, end='')
    if result.stderr:
        print(result.stderr, end='', file=sys.stderr)
    result.check_returncode()
    return result.stdout


def verify(wheel: Path) -> None:
    wheel = wheel.resolve(strict=True)
    if not wheel.is_file() or wheel.suffix != '.whl':
        raise ValueError('Provide exactly one .whl file')
    root = Path(__file__).resolve().parents[1]
    expected = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    env = os.environ.copy()
    for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV'):
        env.pop(key, None)
    env['PYTHONNOUSERSITE'] = '1'
    with tempfile.TemporaryDirectory(prefix='pyrange-wheel-') as directory:
        work = Path(directory).resolve()
        if work.is_relative_to(root):
            raise ValueError('Temporary directory must be outside the source checkout; adjust TMPDIR/TEMP')
        environment = work / 'venv'
        venv.EnvBuilder(with_pip=True).create(environment)
        bindir = environment / ('Scripts' if os.name == 'nt' else 'bin')
        python = bindir / ('python.exe' if os.name == 'nt' else 'python')
        cli = bindir / ('pyrange.exe' if os.name == 'nt' else 'pyrange')
        env['PATH'] = str(bindir) + os.pathsep + env.get('PATH', '')
        run([str(python), '-I', '-m', 'pip', 'install', '--disable-pip-version-check',
             str(wheel)], cwd=work, env=env)
        run([str(python), '-I', '-m', 'pip', 'check'], cwd=work, env=env)
        probe = '''
import importlib, importlib.metadata, json, pathlib, pkgutil, sys
import pyrange
prefix = pathlib.Path(sys.prefix).resolve()
source = pathlib.Path(sys.argv[1]).resolve()
modules = [pyrange] + [importlib.import_module(item.name)
    for item in pkgutil.walk_packages(pyrange.__path__, pyrange.__name__ + '.')]
for module in modules:
    location = pathlib.Path(module.__file__).resolve()
    assert location.is_relative_to(prefix), (module.__name__, location)
    assert not location.is_relative_to(source), (module.__name__, location)
assert importlib.metadata.version('pyrange') == sys.argv[2]
print(json.dumps({'version': sys.argv[2], 'imported_modules': len(modules),
                  'package_path': str(pathlib.Path(pyrange.__file__).resolve())}))
'''
        run([str(python), '-I', '-c', probe, str(root), expected], cwd=work, env=env)
        run([str(cli), '--help'], cwd=work, env=env)
        # A self-contained scenario proves the installed parser and models work,
        # without relying on repository-relative sample files or Docker.
        scenario = work / 'smoke.yaml'
        scenario.write_text(json.dumps({
            'name': 'wheel-smoke',
            'networks': [{'name': 'net', 'subnet': '172.28.10.0/24'}],
            'machines': [{'name': 'web', 'image': 'alpine:latest',
                          'interfaces': [{'network': 'net', 'ip': '172.28.10.2'}]}],
        }), encoding='utf-8')
        output = run([str(cli), 'inspect', str(scenario)], cwd=work, env=env)
        if 'Scenario: wheel-smoke' not in output or 'Machines: 1' not in output:
            raise RuntimeError('Installed CLI did not inspect the expected scenario')
        run([str(python), '-I', '-m', 'pip', 'freeze'], cwd=work, env=env)
        print('Wheel verification passed: isolated imports, CLI and scenario parsing')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheel', type=Path)
    args = parser.parse_args()
    verify(args.wheel)
