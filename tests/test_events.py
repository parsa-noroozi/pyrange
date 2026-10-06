import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from pyrange.engine.events import (
    EventRecord,
    EventRecorder,
    EventResource,
    EventSerializationError,
    EventWriteError,
    ExecutionContext,
    JsonlEventSink,
)


RUN_ID = UUID(
    "11111111-1111-4111-8111-111111111111"
)
EVENT_ID_1 = UUID(
    "22222222-2222-4222-8222-222222222222"
)
EVENT_ID_2 = UUID(
    "33333333-3333-4333-8333-333333333333"
)
FIXED_TIME = datetime(
    2026,
    10,
    6,
    18,
    30,
    tzinfo=timezone.utc,
)


class CollectingSink:
    def __init__(self) -> None:
        self.events: list[EventRecord] = []

    def write(
        self,
        event: EventRecord,
    ) -> None:
        self.events.append(event)


class FailingOnceSink:
    def __init__(self) -> None:
        self.events: list[EventRecord] = []
        self._failed = False

    def write(
        self,
        event: EventRecord,
    ) -> None:
        if not self._failed:
            self._failed = True
            raise EventWriteError(
                "simulated event write failure"
            )

        self.events.append(event)


def test_event_recorder_creates_ordered_events() -> None:
    context = ExecutionContext(
        run_id=RUN_ID,
        scenario="segmented-lab",
        operation="start",
    )

    sink = CollectingSink()

    event_ids = iter(
        [
            EVENT_ID_1,
            EVENT_ID_2,
        ]
    )

    recorder = EventRecorder(
        context,
        sink,
        clock=lambda: FIXED_TIME,
        event_id_factory=lambda: next(event_ids),
    )

    first = recorder.emit(
        "lab.start.requested",
    )

    second = recorder.emit(
        "machine.started",
        outcome="success",
        resource=EventResource(
            type="machine",
            name="web",
        ),
        attributes={
            "runtime_name": (
                "pyrange-segmented-lab-web"
            ),
        },
    )

    assert first.sequence == 1
    assert second.sequence == 2

    assert first.event_id == EVENT_ID_1
    assert second.event_id == EVENT_ID_2

    assert first.run_id == RUN_ID
    assert second.run_id == RUN_ID

    assert first.timestamp == FIXED_TIME
    assert second.timestamp == FIXED_TIME

    assert second.resource is not None
    assert second.resource.type == "machine"
    assert second.resource.name == "web"

    assert sink.events == [
        first,
        second,
    ]


def test_event_recorder_does_not_advance_sequence_on_sink_failure(
) -> None:
    context = ExecutionContext(
        run_id=RUN_ID,
        scenario="segmented-lab",
        operation="start",
    )

    sink = FailingOnceSink()

    event_ids = iter(
        [
            EVENT_ID_1,
            EVENT_ID_2,
        ]
    )

    recorder = EventRecorder(
        context,
        sink,
        clock=lambda: FIXED_TIME,
        event_id_factory=lambda: next(event_ids),
    )

    with pytest.raises(
        EventWriteError,
        match="simulated event write failure",
    ):
        recorder.emit(
            "lab.start.requested",
        )

    event = recorder.emit(
        "lab.start.requested",
    )

    assert event.sequence == 1
    assert event.event_id == EVENT_ID_2
    assert sink.events == [event]


def test_event_record_normalizes_timestamp_to_utc() -> None:
    local_timezone = timezone(
        timedelta(hours=3, minutes=30)
    )

    record = EventRecord(
        event_id=EVENT_ID_1,
        run_id=RUN_ID,
        sequence=1,
        timestamp=datetime(
            2026,
            10,
            6,
            22,
            0,
            tzinfo=local_timezone,
        ),
        scenario="segmented-lab",
        operation="status",
        event_type="lab.status.inspected",
    )

    assert record.timestamp == datetime(
        2026,
        10,
        6,
        18,
        30,
        tzinfo=timezone.utc,
    )


def test_event_record_rejects_naive_timestamp() -> None:
    with pytest.raises(
        ValidationError,
        match="timestamp must be timezone-aware",
    ):
        EventRecord(
            event_id=EVENT_ID_1,
            run_id=RUN_ID,
            sequence=1,
            timestamp=datetime(
                2026,
                10,
                6,
                18,
                30,
            ),
            scenario="segmented-lab",
            operation="status",
            event_type="lab.status.inspected",
        )


def test_event_record_rejects_invalid_event_name() -> None:
    with pytest.raises(ValidationError):
        EventRecord(
            event_id=EVENT_ID_1,
            run_id=RUN_ID,
            sequence=1,
            timestamp=FIXED_TIME,
            scenario="segmented-lab",
            operation="status",
            event_type="Lab Status",
        )


def test_event_record_rejects_non_json_attributes() -> None:
    with pytest.raises(ValidationError):
        EventRecord(
            event_id=EVENT_ID_1,
            run_id=RUN_ID,
            sequence=1,
            timestamp=FIXED_TIME,
            scenario="segmented-lab",
            operation="status",
            event_type="lab.status.inspected",
            attributes={
                "path": Path("not-json"),
            },
        )


def test_jsonl_event_sink_appends_valid_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"

    context = ExecutionContext(
        run_id=RUN_ID,
        scenario="segmented-lab",
        operation="start",
    )

    event_ids = iter(
        [
            EVENT_ID_1,
            EVENT_ID_2,
        ]
    )

    recorder = EventRecorder(
        context,
        JsonlEventSink(path),
        clock=lambda: FIXED_TIME,
        event_id_factory=lambda: next(event_ids),
    )

    recorder.emit(
        "lab.start.requested",
    )

    recorder.emit(
        "machine.started",
        outcome="success",
        resource=EventResource(
            type="machine",
            name="web",
        ),
        attributes={
            "runtime_name": (
                "pyrange-segmented-lab-web"
            ),
        },
    )

    lines = path.read_text(
        encoding="utf-8"
    ).splitlines()

    assert len(lines) == 2

    first = json.loads(lines[0])
    second = json.loads(lines[1])

    assert first["schema_version"] == 1
    assert first["event_id"] == str(EVENT_ID_1)
    assert first["run_id"] == str(RUN_ID)
    assert first["sequence"] == 1
    assert first["timestamp"] == (
        "2026-10-06T18:30:00Z"
    )
    assert first["event_type"] == (
        "lab.start.requested"
    )

    assert second["sequence"] == 2
    assert second["event_id"] == str(EVENT_ID_2)
    assert second["resource"] == {
        "type": "machine",
        "name": "web",
    }
    assert second["attributes"] == {
        "runtime_name": (
            "pyrange-segmented-lab-web"
        ),
    }


def test_jsonl_event_sink_reports_write_failure(
    tmp_path: Path,
) -> None:
    path = (
        tmp_path
        / "missing-directory"
        / "events.jsonl"
    )

    sink = JsonlEventSink(path)

    event = EventRecord(
        event_id=EVENT_ID_1,
        run_id=RUN_ID,
        sequence=1,
        timestamp=FIXED_TIME,
        scenario="segmented-lab",
        operation="status",
        event_type="lab.status.inspected",
    )

    with pytest.raises(
        EventWriteError,
        match="Failed to write event log",
    ):
        sink.write(event)


def test_jsonl_event_sink_rejects_non_finite_float(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"

    sink = JsonlEventSink(path)

    event = EventRecord(
        event_id=EVENT_ID_1,
        run_id=RUN_ID,
        sequence=1,
        timestamp=FIXED_TIME,
        scenario="segmented-lab",
        operation="status",
        event_type="lab.status.inspected",
        attributes={
            "value": float("nan"),
        },
    )

    with pytest.raises(EventSerializationError):
        sink.write(event)

    assert not path.exists()
