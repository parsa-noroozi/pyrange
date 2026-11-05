# Foundation CI and wheel validation

## Scope and merge gate

Keep all foundation changes on `fix/resource-naming` and the PR in draft until
its latest revision passes validation and final review. Adding this workflow does
not prove GitHub has executed it. This package does not bump the version or publish
a release or package to PyPI.

`Foundation checks` runs on pushes to `main` and `fix/resource-naming`, PRs to
`main` (including drafts), and manual dispatch. Push and PR events can produce
separate runs. Repository token permissions are read-only; checkout credentials
are not persisted. No deployment secrets or `pull_request_target` are used.

| Job | Environment | Gate |
| --- | --- | --- |
| Unit and wheel | Ubuntu 24.04 and Windows; Python 3.12 and 3.14 | Non-integration tests, no skips, wheel build and clean installation smoke check |
| Docker integration | Ubuntu 24.04; Python 3.14 | Sequential real Docker tests, no skips |

Python 3.12 is the declared minimum and 3.14 is the development target. The matrix
does not prove support for every version metadata allows. Each job has a 20-minute
limit; that is a CI limit, not a production workload-cancellation guarantee.

The checkout, Python setup and artifact upload actions use their Node.js 24
runtime releases (`@v6`). Node is an implementation detail of these actions;
PyRange remains a Python project. Linux jobs use `ubuntu-24.04` explicitly so
migration of `ubuntu-latest` does not silently change their OS release. This
pins the Ubuntu release, not every installed tool or runner image revision.
Windows continues to use `windows-latest`.

## Wheel check

`scripts/verify_wheel.py PATH_TO_WHEEL` creates a temporary venv without system
site packages and installs exactly the given wheel, non-editably, plus its runtime
dependencies. It runs `pip check`, imports all PyRange modules, verifies that each
comes from the new venv rather than the source checkout, and compares the installed
version with this checkout's `pyproject.toml`.

The installed `pyrange --help` and `pyrange inspect` commands then run outside the
checkout against a self-contained scenario. Python probes use isolated mode;
`PYTHONPATH`, `PYTHONHOME` and the old `VIRTUAL_ENV` are removed. The new venv's
executable directory comes first on PATH. Temporary files are cleaned up on exit.

This smoke check needs no Docker. It needs package-index access; pip's download
cache may be reused but installed packages are not reused. Imports must remain
free of lab mutations. This is not the full test suite run against the wheel.
Repository scenarios and docs are not claimed to be installed package data.

## Docker evidence

The Docker job pulls `nginx:alpine` and `alpine:latest`, records their IDs/digests
and Docker version, and runs tests sequentially because some subnets overlap.
The timeout experiment's JSON appears in the job log. JUnit XML and built wheels
are uploaded as artifacts; reports are uploaded on ordinary test failure too,
when a report was produced.

`scripts/check_test_report.py` rejects missing/malformed/empty reports, skips,
failures, and errors. Deselected tests are not skips. Docker-unavailable skips do
not satisfy the integration gate. This guard does not freeze the test count or
prove coverage; collection and assertion quality still require review.

## Reproduce locally (PowerShell)

Run commands individually and stop on any error:

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not integration" -q --tb=short
.\.venv\Scripts\python.exe -m pip install build
$wheelOutput = Join-Path $env:TEMP ("pyrange-wheel-" + [guid]::NewGuid().ToString("N"))
.\.venv\Scripts\python.exe -m build --wheel --outdir $wheelOutput
$wheels = @(Get-ChildItem -LiteralPath $wheelOutput -Filter *.whl)
if ($wheels.Count -ne 1) { throw "Expected exactly one wheel" }
.\.venv\Scripts\python.exe scripts/verify_wheel.py $wheels[0].FullName
```

Use equivalent venv paths on Linux/macOS. The verifier's temporary directory must
be outside the checkout. Build tools may create `build/` and `*.egg-info` in the
checkout; never stage generated packaging files.

With Linux Docker running and the two images already pulled:

```powershell
$integrationReport = Join-Path $env:TEMP ("pyrange-integration-" + [guid]::NewGuid().ToString("N") + ".xml")
.\.venv\Scripts\python.exe -m pytest -m integration -v -s --tb=short -rs --junitxml $integrationReport
.\.venv\Scripts\python.exe scripts/check_test_report.py $integrationReport
```

The unique report path prevents accepting an old result. After pushing, inspect
the existing PR's Checks tab and verify all five jobs for the latest revision.
First-time or fork workflows may need repository-owner approval. If Actions is
disabled, enable it rather than accepting absent checks. Required-check branch
protection is a separate repository setting and is not configured by this patch.

## Reproducibility limits

Dependencies retain existing ranges; CI logs resolved versions with `pip freeze`.
Action major tags, hosted runner images and Docker tags can change. These are
repeatable validation steps, not hermetic or bit-for-bit reproducible builds.
Record the environment when comparing results. A local Linux pass is not evidence
of a Windows or GitHub Actions pass; those jobs must actually run.

## References

- https://docs.github.com/en/actions/tutorials/build-and-test-code/python
- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- https://build.pypa.io/en/stable/tutorial/getting-started.html
