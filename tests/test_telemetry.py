import json
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from pyrange.engine import ExecutionContext
from pyrange.engine.telemetry import (
    JsonlTelemetrySink,
    TelemetryRecord,
    TelemetryRecorder,
    TelemetryResource,
    TelemetrySerializationError,
    TelemetryWriteError,
)


class MemoryTelemetrySink:
    def __init__(self) -> None:
        self.records: list[TelemetryRecord] = []

    def write(
        self,
        record: TelemetryRecord,
    ) -> None:
        self.records.append(record)


class FailOnceTelemetrySink:
    def __init__(self) -> None:
        self.failed = False
        self.records: list[TelemetryRecord] = []

    def write(
        self,
        record: TelemetryRecord,
    ) -> None:
        if not self.failed:
            self.failed = True
            raise TelemetryWriteError(
                "simulated telemetry write failure"
            )

        self.records.append(record)


def test_telemetry_recorder_creates_ordered_records() -> None:
    context = ExecutionContext(
        run_id=UUID(
            "11111111-1111-4111-8111-111111111111"
        ),
        scenario="test-lab",
        operation="telemetry",
    )
    sink = MemoryTelemetrySink()

    telemetry_ids = iter(
        [
            UUID(
                "22222222-2222-4222-8222-222222222222"
            ),
            UUID(
                "33333333-3333-4333-8333-333333333333"
            ),
        ]
    )
    timestamps = iter(
        [
            datetime(
                2026,
                10,
                7,
                12,
                0,
                tzinfo=timezone.utc,
            ),
            datetime(
                2026,
                10,
                7,
                12,
                0,
                1,
                tzinfo=timezone.utc,
            ),
        ]
    )

    recorder = TelemetryRecorder(
        context,
        sink,
        clock=lambda: next(timestamps),
        telemetry_id_factory=(
            lambda: next(telemetry_ids)
        ),
    )

    first = recorder.record(
        "container.runtime",
        resource=TelemetryResource(
            type="machine",
            name="web",
        ),
        data={
            "status": "running",
        },
    )

    second = recorder.record(
        "container.stats",
        resource=TelemetryResource(
            type="machine",
            name="web",
        ),
        data={
            "pids": 4,
        },
    )

    assert first.sequence == 1
    assert second.sequence == 2

    assert first.run_id == context.run_id
    assert second.run_id == context.run_id

    assert first.telemetry_type == (
        "container.runtime"
    )
    assert second.telemetry_type == (
        "container.stats"
    )

    assert sink.records == [
        first,
        second,
    ]


def test_telemetry_recorder_does_not_advance_sequence_on_sink_failure(
) -> None:
    context = ExecutionContext(
        scenario="test-lab",
        operation="telemetry",
    )
    sink = FailOnceTelemetrySink()

    recorder = TelemetryRecorder(
        context,
        sink,
    )

    with pytest.raises(
        TelemetryWriteError,
        match="simulated telemetry write failure",
    ):
        recorder.record(
            "container.runtime",
        )

    record = recorder.record(
        "container.runtime",
    )

    assert record.sequence == 1
    assert sink.records == [record]


def test_telemetry_record_normalizes_timestamp_to_utc(
) -> None:
    local_timezone = timezone(
        timedelta(
            hours=3,
            minutes=30,
        )
    )

    record = TelemetryRecord(
        telemetry_id=UUID(
            "22222222-2222-4222-8222-222222222222"
        ),
        run_id=UUID(
            "11111111-1111-4111-8111-111111111111"
        ),
        sequence=1,
        timestamp=datetime(
            2026,
            10,
            7,
            20,
            0,
            tzinfo=local_timezone,
        ),
        scenario="test-lab",
        operation="telemetry",
        telemetry_type="container.runtime",
    )

    assert record.timestamp == datetime(
        2026,
        10,
        7,
        16,
        30,
        tzinfo=timezone.utc,
    )


def test_telemetry_record_rejects_naive_timestamp(
) -> None:
    with pytest.raises(
        ValidationError,
        match="timestamp must be timezone-aware",
    ):
        TelemetryRecord(
            telemetry_id=UUID(
                "22222222-2222-4222-8222-222222222222"
            ),
            run_id=UUID(
                "11111111-1111-4111-8111-111111111111"
            ),
            sequence=1,
            timestamp=datetime(
                2026,
                10,
                7,
                12,
                0,
            ),
            scenario="test-lab",
            operation="telemetry",
            telemetry_type="container.runtime",
        )


def test_telemetry_record_rejects_invalid_telemetry_name(
) -> None:
    with pytest.raises(ValidationError):
        TelemetryRecord(
            telemetry_id=UUID(
                "22222222-2222-4222-8222-222222222222"
            ),
            run_id=UUID(
                "11111111-1111-4111-8111-111111111111"
            ),
            sequence=1,
            timestamp=datetime.now(timezone.utc),
            scenario="test-lab",
            operation="telemetry",
            telemetry_type="Container Runtime",
        )


def test_telemetry_record_rejects_non_json_data(
) -> None:
    with pytest.raises(ValidationError):
        TelemetryRecord(
            telemetry_id=UUID(
                "22222222-2222-4222-8222-222222222222"
            ),
            run_id=UUID(
                "11111111-1111-4111-8111-111111111111"
            ),
            sequence=1,
            timestamp=datetime.now(timezone.utc),
            scenario="test-lab",
            operation="telemetry",
            telemetry_type="container.runtime",
            data={
                "invalid": object(),
            },
        )


def test_jsonl_telemetry_sink_appends_valid_json(
    tmp_path: Path,
) -> None:
    telemetry_log = tmp_path / "telemetry.jsonl"

    context = ExecutionContext(
        run_id=UUID(
            "11111111-1111-4111-8111-111111111111"
        ),
        scenario="test-lab",
        operation="telemetry",
    )

    recorder = TelemetryRecorder(
        context,
        JsonlTelemetrySink(telemetry_log),
    )

    recorder.record(
        "container.runtime",
        resource=TelemetryResource(
            type="machine",
            name="web",
        ),
        data={
            "status": "running",
        },
    )

    recorder.record(
        "container.stats",
        resource=TelemetryResource(
            type="machine",
            name="web",
        ),
        data={
            "pids": 4,
        },
    )

    lines = telemetry_log.read_text(
        encoding="utf-8"
    ).splitlines()

    assert len(lines) == 2

    first = json.loads(lines[0])
    second = json.loads(lines[1])

    assert first["schema_version"] == 1
    assert first["sequence"] == 1
    assert second["sequence"] == 2

    assert first["run_id"] == (
        "11111111-1111-4111-8111-111111111111"
    )
    assert second["run_id"] == first["run_id"]

    assert first["telemetry_type"] == (
        "container.runtime"
    )
    assert second["telemetry_type"] == (
        "container.stats"
    )


def test_jsonl_telemetry_sink_reports_write_failure(
    tmp_path: Path,
) -> None:
    telemetry_log = (
        tmp_path
        / "missing"
        / "telemetry.jsonl"
    )

    context = ExecutionContext(
        scenario="test-lab",
        operation="telemetry",
    )

    recorder = TelemetryRecorder(
        context,
        JsonlTelemetrySink(telemetry_log),
    )

    with pytest.raises(
        TelemetryWriteError,
        match="Failed to write telemetry log",
    ):
        recorder.record(
            "container.runtime",
        )

    assert not telemetry_log.exists()


def test_jsonl_telemetry_sink_rejects_non_finite_float(
    tmp_path: Path,
) -> None:
    telemetry_log = tmp_path / "telemetry.jsonl"

    context = ExecutionContext(
        scenario="test-lab",
        operation="telemetry",
    )

    recorder = TelemetryRecorder(
        context,
        JsonlTelemetrySink(telemetry_log),
    )

    with pytest.raises(
        TelemetrySerializationError,
        match="Failed to serialize telemetry",
    ):
        recorder.record(
            "container.stats",
            data={
                "cpu_percent": float("nan"),
            },
        )

    assert not telemetry_log.exists()
