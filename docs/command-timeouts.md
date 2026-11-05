# Command timeout and cancellation contract

## Scope

This contract covers `execute_container_command` and health checks. It does
not add a global deadline to lab start, stop, rollback, snapshot, telemetry,
or Docker queries. Those operations still have no general timeout guarantee.
It does not implement the v0.7 execution state machine or workload cancellation.

## Behavior

- The command timeout must be a finite positive number (booleans are rejected)
  and is validated before launching Docker.
- Python's `subprocess.run(timeout=...)` terminates and waits for the child
  Docker CLI process when its communication deadline expires. Process creation
  may itself delay the exception; this is not a strict wall-clock deadline.
- The client process and the command inside the container are different
  processes. Client timeout is not evidence that the workload stopped.
- PyRange raises `DockerCommandTimeoutError`, a `DockerOperationError` subclass.
  Existing callers catching the base class remain compatible.
- The error retains the original exception as its cause, container reference,
  configured timeout, and available partial stdout/stderr. Missing output becomes
  an empty string; bytes are decoded with the local encoding and replacement
  for malformed bytes. This is diagnostic text, not lossless binary evidence.
- `cancellation_confirmed` is false. No exit code or workload completion is inferred.
- The exception message does not include command arguments or captured output.
  Exception attributes and the chained Python exception can contain sensitive
  data. Partial streams remain subject to existing output-size limitations.
- This function performs no automatic retry, container kill, or deletion.

## Health checks

A timeout ends the health-check evaluation immediately, even when retries remain.
The result is unhealthy with `exit_code=None`, actual attempts, partial stdout,
and a diagnostic explaining the uncertain workload state. Partial stderr is
appended to that diagnostic. `healthy=False` means readiness was not established;
it does not prove termination or a definitive application failure.

Completed nonzero commands and other `DockerOperationError` failures retain
existing retry behavior. Docker unavailability is still propagated. Existing
manager rollback behavior remains in place: the health evaluator does not itself
cancel anything, while its caller may initiate ownership-checked cleanup.

## Real Docker characterization experiment

Prerequisites: Linux Docker Engine reachable through the current Docker context,
local `alpine:latest`, and no concurrent daemon manipulation. The experiment pins
the inspected local image ID, uses a random container name, no network, and no
host mounts. Its primary process has a 120-second lifetime.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_exec_timeout.py -v -s --tb=short
```

The workload writes a start marker and waits for a release marker. After the
client timeout, the test verifies that execution started and has not finished,
then writes the release marker. A finish marker proves execution after timeout
in this environment. Absence of that marker is a failed characterization,
not proof of cancellation. Slow startup or daemon failure may also fail the test;
inspect diagnostics rather than weakening its assertions. Missing prerequisites
fail this explicit gate instead of silently skipping it.

The test prints JSON with Python/platform, engine version, image ID, observations,
and cleanup outcome, and writes `timeout-evidence.json` in pytest's temporary
folder. Preserve the printed report with review evidence. It is not a universal
Docker guarantee and not a production cancellation API.

Cleanup inspects the recorded full creation ID and unique test label before
removing that ID. It never prunes or removes by name. Cleanup errors are added to
a primary failure instead of replacing it. A create timeout before the ID is
returned can leave an untracked test container; investigate its unique probe name
and label manually. Successful cleanup must not be inferred from a failed query.
The helper CLI calls use 30-second client timeouts; these are not daemon-side
transaction deadlines. The test has bounded polling, not an exact total runtime.

## Validation boundary

Unit tests cover typed diagnostics, partial output, invalid limits, exception
chaining, and no retries after a first or later timed-out health-check attempt.
Real Docker results must be recorded after running the experiment; unit test
success does not establish workload behavior.

## References

- [Python subprocess.run and TimeoutExpired](https://docs.python.org/3.14/library/subprocess.html)
- [Docker container exec](https://docs.docker.com/reference/cli/docker/container/exec/)
