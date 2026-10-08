import subprocess
from unittest.mock import call, patch

import pytest

from pyrange.engine import (
    ContainerCommandResult,
    ContainerNetworkState,
    ContainerRuntimeState,
    ContainerStatsSnapshot,
    DockerOperationError,
    DockerUnavailableError,
    NetworkRuntimeState,
    connect_container_to_network,
    create_container_snapshot,
    execute_container_command,
    get_container_stats,
    get_docker_server_version,
    get_image_id,
    inspect_container_runtime,
    inspect_network_runtime,
)


@patch("pyrange.engine.docker.subprocess.run")
def test_returns_docker_server_version(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="29.0.0\n",
        stderr="",
    )

    version = get_docker_server_version()

    assert version == "29.0.0"


@patch("pyrange.engine.docker.subprocess.run")
def test_raises_when_docker_cli_is_missing(mock_run) -> None:
    mock_run.side_effect = FileNotFoundError

    with pytest.raises(
        DockerUnavailableError,
        match="Docker CLI was not found",
    ):
        get_docker_server_version()


@patch("pyrange.engine.docker.subprocess.run")
def test_raises_when_docker_engine_is_unavailable(mock_run) -> None:
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["docker"],
        stderr="Cannot connect to the Docker daemon",
    )

    with pytest.raises(
        DockerUnavailableError,
        match="Cannot connect to the Docker daemon",
    ):
        get_docker_server_version()


@patch("pyrange.engine.docker.subprocess.run")
def test_rejects_empty_server_version(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="",
        stderr="",
    )

    with pytest.raises(
        DockerUnavailableError,
        match="empty server version",
    ):
        get_docker_server_version()


@patch("pyrange.engine.docker.subprocess.run")
def test_create_network_returns_network_id(mock_run) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="abc123\n",
        stderr="",
    )

    from pyrange.engine import create_network

    network_id = create_network(
        "test-net",
        "172.28.10.0/24",
    )

    assert network_id == "abc123"

    mock_run.assert_called_once_with(
        [
            "docker",
            "network",
            "create",
            "--driver",
            "bridge",
            "--subnet",
            "172.28.10.0/24",
            "--internal",
            "test-net",
        ],
        capture_output=True,
        text=True,
        check=True,
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_create_network_raises_on_docker_error(mock_run) -> None:
    from pyrange.engine import DockerOperationError, create_network

    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["docker"],
        stderr="network already exists",
    )

    with pytest.raises(
        DockerOperationError,
        match="network already exists",
    ):
        create_network(
            "test-net",
            "172.28.10.0/24",
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_create_network_rejects_empty_network_id(mock_run) -> None:
    from pyrange.engine import DockerOperationError, create_network

    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="",
        stderr="",
    )

    with pytest.raises(
        DockerOperationError,
        match="empty network ID",
    ):
        create_network(
            "test-net",
            "172.28.10.0/24",
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_remove_network_runs_docker_command(mock_run) -> None:
    from pyrange.engine import remove_network

    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="test-net\n",
        stderr="",
    )

    remove_network("test-net")

    mock_run.assert_called_once_with(
        ["docker", "network", "rm", "test-net"],
        capture_output=True,
        text=True,
        check=True,
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_remove_network_raises_on_docker_error(mock_run) -> None:
    from pyrange.engine import DockerOperationError, remove_network

    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["docker"],
        stderr="network not found",
    )

    with pytest.raises(
        DockerOperationError,
        match="network not found",
    ):
        remove_network("test-net")


@patch("pyrange.engine.docker.subprocess.run")
def test_create_container_returns_container_id(mock_run) -> None:
    from pyrange.engine import create_container

    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="container123\n",
        stderr="",
    )

    container_id = create_container(
        "test-web",
        "nginx:alpine",
        "test-net",
        "172.28.10.10",
    )

    assert container_id == "container123"

    mock_run.assert_called_once_with(
        [
            "docker",
            "create",
            "--name",
            "test-web",
            "--network",
            "test-net",
            "--ip",
            "172.28.10.10",
            "--label",
            "pyrange.managed=true",
            "nginx:alpine",
        ],
        capture_output=True,
        text=True,
        check=True,
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_create_container_raises_on_docker_error(mock_run) -> None:
    from pyrange.engine import DockerOperationError, create_container

    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["docker"],
        stderr="container already exists",
    )

    with pytest.raises(
        DockerOperationError,
        match="container already exists",
    ):
        create_container(
            "test-web",
            "nginx:alpine",
            "test-net",
            "172.28.10.10",
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_create_container_rejects_empty_container_id(mock_run) -> None:
    from pyrange.engine import DockerOperationError, create_container

    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="",
        stderr="",
    )

    with pytest.raises(
        DockerOperationError,
        match="empty container ID",
    ):
        create_container(
            "test-web",
            "nginx:alpine",
            "test-net",
            "172.28.10.10",
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_start_container_runs_docker_command(mock_run) -> None:
    from pyrange.engine import start_container

    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="test-web\n",
        stderr="",
    )

    start_container("test-web")

    mock_run.assert_called_once_with(
        ["docker", "start", "test-web"],
        capture_output=True,
        text=True,
        check=True,
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_start_container_raises_on_docker_error(mock_run) -> None:
    from pyrange.engine import DockerOperationError, start_container

    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["docker"],
        stderr="failed to start container",
    )

    with pytest.raises(
        DockerOperationError,
        match="failed to start container",
    ):
        start_container("test-web")


@patch("pyrange.engine.docker.subprocess.run")
def test_remove_container_runs_docker_command(mock_run) -> None:
    from pyrange.engine import remove_container

    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="test-web\n",
        stderr="",
    )

    remove_container("test-web")

    mock_run.assert_called_once_with(
        ["docker", "rm", "--force", "test-web"],
        capture_output=True,
        text=True,
        check=True,
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_remove_container_raises_on_docker_error(mock_run) -> None:
    from pyrange.engine import DockerOperationError, remove_container

    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["docker"],
        stderr="container not found",
    )

    with pytest.raises(
        DockerOperationError,
        match="container not found",
    ):
        remove_container("test-web")


def test_connect_container_to_network_success() -> None:
    with patch(
        "pyrange.engine.docker.subprocess.run"
    ) as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stderr = ""

        connect_container_to_network(
            name="pyrange-test-web",
            network="pyrange-test-private",
            ip="172.28.20.10",
        )

        mock_run.assert_called_once_with(
            [
                "docker",
                "network",
                "connect",
                "--ip",
                "172.28.20.10",
                "pyrange-test-private",
                "pyrange-test-web",
            ],
            capture_output=True,
            text=True,
        )


def test_connect_container_to_network_error() -> None:
    with patch(
        "pyrange.engine.docker.subprocess.run"
    ) as mock_run:
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = (
            "failed to connect container"
        )

        with pytest.raises(
            DockerOperationError,
            match="failed to connect container",
        ):
            connect_container_to_network(
                name="pyrange-test-web",
                network="pyrange-test-private",
                ip="172.28.20.10",
            )
            
            
@patch("pyrange.engine.docker.subprocess.run")
def test_execute_container_command_returns_result(
    mock_run,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="healthy\n",
        stderr="",
    )

    result = execute_container_command(
        name="test-web",
        command=["wget", "--spider", "http://127.0.0.1"],
        timeout_seconds=2.0,
    )

    assert result == ContainerCommandResult(
        exit_code=0,
        stdout="healthy\n",
        stderr="",
    )

    mock_run.assert_called_once_with(
        [
            "docker",
            "exec",
            "test-web",
            "wget",
            "--spider",
            "http://127.0.0.1",
        ],
        capture_output=True,
        text=True,
        timeout=2.0,
        check=False,
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_execute_container_command_preserves_failure(
    mock_run,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=1,
        stdout="",
        stderr="service unavailable\n",
    )

    result = execute_container_command(
        name="test-web",
        command=["health-check"],
        timeout_seconds=2.0,
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == "service unavailable\n"


@patch("pyrange.engine.docker.subprocess.run")
def test_execute_container_command_raises_on_timeout(
    mock_run,
) -> None:
    mock_run.side_effect = subprocess.TimeoutExpired(
        cmd=["docker", "exec"],
        timeout=2.0,
    )

    with pytest.raises(
        DockerOperationError,
        match="Command timed out",
    ):
        execute_container_command(
            name="test-web",
            command=["health-check"],
            timeout_seconds=2.0,
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_execute_container_command_raises_when_cli_missing(
    mock_run,
) -> None:
    mock_run.side_effect = FileNotFoundError

    with pytest.raises(
        DockerUnavailableError,
        match="Docker CLI was not found",
    ):
        execute_container_command(
            name="test-web",
            command=["health-check"],
            timeout_seconds=2.0,
        )


def test_execute_container_command_rejects_empty_command() -> None:
    with pytest.raises(
        ValueError,
        match="command must not be empty",
    ):
        execute_container_command(
            name="test-web",
            command=[],
            timeout_seconds=2.0,
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_create_container_snapshot_returns_image_id(
    mock_run,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="sha256:snapshot123\n",
        stderr="",
    )

    image_id = create_container_snapshot(
        name="test-web",
        image_ref="pyrange-snapshots/web:checkpoint-1",
    )

    assert image_id == "sha256:snapshot123"

    mock_run.assert_called_once_with(
        [
            "docker",
            "commit",
            "test-web",
            "pyrange-snapshots/web:checkpoint-1",
        ],
        capture_output=True,
        text=True,
        check=True,
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_create_container_snapshot_raises_on_docker_error(
    mock_run,
) -> None:
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["docker", "commit"],
        stderr="container not found",
    )

    with pytest.raises(
        DockerOperationError,
        match="container not found",
    ):
        create_container_snapshot(
            name="test-web",
            image_ref="pyrange-snapshots/web:checkpoint-1",
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_create_container_snapshot_rejects_empty_image_id(
    mock_run,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="",
        stderr="",
    )

    with pytest.raises(
        DockerOperationError,
        match="empty snapshot image ID",
    ):
        create_container_snapshot(
            name="test-web",
            image_ref="pyrange-snapshots/web:checkpoint-1",
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_create_container_snapshot_raises_when_cli_missing(
    mock_run,
) -> None:
    mock_run.side_effect = FileNotFoundError

    with pytest.raises(
        DockerUnavailableError,
        match="Docker CLI was not found",
    ):
        create_container_snapshot(
            name="test-web",
            image_ref="pyrange-snapshots/web:checkpoint-1",
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_get_image_id_returns_image_id(
    mock_run,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="sha256:snapshot123\n",
        stderr="",
    )

    image_id = get_image_id(
        "pyrange-snapshots/web:checkpoint-1"
    )

    assert image_id == "sha256:snapshot123"

    mock_run.assert_called_once_with(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            "{{.Id}}",
            "pyrange-snapshots/web:checkpoint-1",
        ],
        capture_output=True,
        text=True,
        check=True,
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_get_image_id_raises_on_docker_error(
    mock_run,
) -> None:
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["docker", "image", "inspect"],
        stderr="No such image",
    )

    with pytest.raises(
        DockerOperationError,
        match="No such image",
    ):
        get_image_id(
            "pyrange-snapshots/web:missing"
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_get_image_id_rejects_empty_image_id(
    mock_run,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="",
        stderr="",
    )

    with pytest.raises(
        DockerOperationError,
        match="empty image ID",
    ):
        get_image_id(
            "pyrange-snapshots/web:checkpoint-1"
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_get_image_id_raises_when_cli_missing(
    mock_run,
) -> None:
    mock_run.side_effect = FileNotFoundError

    with pytest.raises(
        DockerUnavailableError,
        match="Docker CLI was not found",
    ):
        get_image_id(
            "pyrange-snapshots/web:checkpoint-1"
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_inspect_container_runtime_returns_state(
    mock_run,
) -> None:
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout=(
                "other-container\n"
                "pyrange-test-lab-web\n"
            ),
            stderr="",
        ),
        subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout=(
                "[{"
                '"State":{"Status":"running"},'
                '"NetworkSettings":{"Networks":{'
                '"pyrange-test-lab-private":{'
                '"IPAddress":"172.28.20.10"'
                "},"
                '"pyrange-test-lab-public":{'
                '"IPAddress":"172.28.10.10"'
                "}"
                "}}"
                "}]"
            ),
            stderr="",
        ),
    ]

    result = inspect_container_runtime(
        "pyrange-test-lab-web"
    )

    assert result == ContainerRuntimeState(
        name="pyrange-test-lab-web",
        status="running",
        networks=(
            ContainerNetworkState(
                network_name=(
                    "pyrange-test-lab-private"
                ),
                ip_address="172.28.20.10",
            ),
            ContainerNetworkState(
                network_name=(
                    "pyrange-test-lab-public"
                ),
                ip_address="172.28.10.10",
            ),
        ),
    )

    assert mock_run.call_args_list == [
        call(
            [
                "docker",
                "container",
                "ls",
                "--all",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            check=True,
        ),
        call(
            [
                "docker",
                "container",
                "inspect",
                "pyrange-test-lab-web",
            ],
            capture_output=True,
            text=True,
            check=True,
        ),
    ]


@patch("pyrange.engine.docker.subprocess.run")
def test_inspect_container_runtime_returns_none_when_missing(
    mock_run,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout=(
            "pyrange-test-lab-web-old\n"
            "unrelated-container\n"
        ),
        stderr="",
    )

    result = inspect_container_runtime(
        "pyrange-test-lab-web"
    )

    assert result is None

    mock_run.assert_called_once_with(
        [
            "docker",
            "container",
            "ls",
            "--all",
            "--format",
            "{{.Names}}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_inspect_container_runtime_raises_when_cli_missing(
    mock_run,
) -> None:
    mock_run.side_effect = FileNotFoundError

    with pytest.raises(
        DockerUnavailableError,
        match="Docker CLI was not found",
    ):
        inspect_container_runtime(
            "pyrange-test-lab-web"
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_inspect_container_runtime_raises_on_inspect_error(
    mock_run,
) -> None:
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout="pyrange-test-lab-web\n",
            stderr="",
        ),
        subprocess.CalledProcessError(
            returncode=1,
            cmd=["docker", "container", "inspect"],
            stderr="container inspection failed",
        ),
    ]

    with pytest.raises(
        DockerOperationError,
        match="container inspection failed",
    ):
        inspect_container_runtime(
            "pyrange-test-lab-web"
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_inspect_container_runtime_rejects_invalid_data(
    mock_run,
) -> None:
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout="pyrange-test-lab-web\n",
            stderr="",
        ),
        subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout="not-json",
            stderr="",
        ),
    ]

    with pytest.raises(
        DockerOperationError,
        match="invalid inspection data",
    ):
        inspect_container_runtime(
            "pyrange-test-lab-web"
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_inspect_network_runtime_returns_state(
    mock_run,
) -> None:
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout=(
                "bridge\n"
                "pyrange-test-lab-public\n"
            ),
            stderr="",
        ),
        subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout=(
                "[{"
                '"IPAM":{"Config":['
                '{"Subnet":"172.28.20.0/24"},'
                '{"Subnet":"172.28.10.0/24"}'
                "]}"
                "}]"
            ),
            stderr="",
        ),
    ]

    result = inspect_network_runtime(
        "pyrange-test-lab-public"
    )

    assert result == NetworkRuntimeState(
        name="pyrange-test-lab-public",
        subnets=(
            "172.28.10.0/24",
            "172.28.20.0/24",
        ),
    )

    assert mock_run.call_args_list == [
        call(
            [
                "docker",
                "network",
                "ls",
                "--format",
                "{{.Name}}",
            ],
            capture_output=True,
            text=True,
            check=True,
        ),
        call(
            [
                "docker",
                "network",
                "inspect",
                "pyrange-test-lab-public",
            ],
            capture_output=True,
            text=True,
            check=True,
        ),
    ]


@patch("pyrange.engine.docker.subprocess.run")
def test_inspect_network_runtime_returns_none_when_missing(
    mock_run,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout=(
            "bridge\n"
            "pyrange-test-lab-public-old\n"
        ),
        stderr="",
    )

    result = inspect_network_runtime(
        "pyrange-test-lab-public"
    )

    assert result is None

    mock_run.assert_called_once_with(
        [
            "docker",
            "network",
            "ls",
            "--format",
            "{{.Name}}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_inspect_network_runtime_raises_on_inspect_error(
    mock_run,
) -> None:
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout="pyrange-test-lab-public\n",
            stderr="",
        ),
        subprocess.CalledProcessError(
            returncode=1,
            cmd=["docker", "network", "inspect"],
            stderr="network inspection failed",
        ),
    ]

    with pytest.raises(
        DockerOperationError,
        match="network inspection failed",
    ):
        inspect_network_runtime(
            "pyrange-test-lab-public"
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_get_container_stats_returns_snapshot(
    mock_run,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout=(
            '{"Name":"pyrange-test-lab-web",'
            '"CPUPerc":"0.15%",'
            '"MemUsage":"12.3MiB / 1GiB",'
            '"MemPerc":"1.20%",'
            '"NetIO":"1.2kB / 900B",'
            '"BlockIO":"0B / 4.1kB",'
            '"PIDs":"7"}\n'
        ),
        stderr="",
    )

    result = get_container_stats(
        "pyrange-test-lab-web"
    )

    assert result == ContainerStatsSnapshot(
        name="pyrange-test-lab-web",
        cpu_percent="0.15%",
        memory_usage="12.3MiB / 1GiB",
        memory_percent="1.20%",
        network_io="1.2kB / 900B",
        block_io="0B / 4.1kB",
        pids=7,
    )

    mock_run.assert_called_once_with(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            "pyrange-test-lab-web",
        ],
        capture_output=True,
        text=True,
        check=True,
    )


@patch("pyrange.engine.docker.subprocess.run")
def test_get_container_stats_raises_when_cli_missing(
    mock_run,
) -> None:
    mock_run.side_effect = FileNotFoundError

    with pytest.raises(
        DockerUnavailableError,
        match="Docker CLI was not found",
    ):
        get_container_stats(
            "pyrange-test-lab-web"
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_get_container_stats_raises_on_docker_error(
    mock_run,
) -> None:
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["docker", "stats"],
        stderr="container does not exist",
    )

    with pytest.raises(
        DockerOperationError,
        match="container does not exist",
    ):
        get_container_stats(
            "pyrange-test-lab-web"
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_get_container_stats_rejects_invalid_json(
    mock_run,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="not-json\n",
        stderr="",
    )

    with pytest.raises(
        DockerOperationError,
        match="invalid stats data",
    ):
        get_container_stats(
            "pyrange-test-lab-web"
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_get_container_stats_rejects_missing_fields(
    mock_run,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout=(
            '{"Name":"pyrange-test-lab-web",'
            '"CPUPerc":"0.15%"}\n'
        ),
        stderr="",
    )

    with pytest.raises(
        DockerOperationError,
        match="invalid stats data",
    ):
        get_container_stats(
            "pyrange-test-lab-web"
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_get_container_stats_rejects_invalid_pids(
    mock_run,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout=(
            '{"Name":"pyrange-test-lab-web",'
            '"CPUPerc":"0.15%",'
            '"MemUsage":"12.3MiB / 1GiB",'
            '"MemPerc":"1.20%",'
            '"NetIO":"1.2kB / 900B",'
            '"BlockIO":"0B / 4.1kB",'
            '"PIDs":"not-a-number"}\n'
        ),
        stderr="",
    )

    with pytest.raises(
        DockerOperationError,
        match="invalid stats data",
    ):
        get_container_stats(
            "pyrange-test-lab-web"
        )


@patch("pyrange.engine.docker.subprocess.run")
def test_get_container_stats_rejects_fractional_pids(
    mock_run,
) -> None:
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout=(
            '{"Name":"pyrange-test-lab-web",'
            '"CPUPerc":"0.15%",'
            '"MemUsage":"12.3MiB / 1GiB",'
            '"MemPerc":"1.20%",'
            '"NetIO":"1.2kB / 900B",'
            '"BlockIO":"0B / 4.1kB",'
            '"PIDs":7.5}\n'
        ),
        stderr="",
    )

    with pytest.raises(
        DockerOperationError,
        match="invalid stats data",
    ):
        get_container_stats(
            "pyrange-test-lab-web"
        )
