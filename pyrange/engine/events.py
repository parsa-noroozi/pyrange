from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Annotated, Literal, Protocol
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
)


NonEmptyString = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
    ),
]

EventName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        pattern=r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$",
    ),
]

EventOutcome = Literal[
    "success",
    "failure",
]


class ExecutionContext(BaseModel):
    """Identify one PyRange operation execution."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    run_id: UUID = Field(default_factory=uuid4)
    scenario: NonEmptyString
    operation: EventName


class EventResource(BaseModel):
    """Identify the resource associated with an event."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    type: EventName
    name: NonEmptyString


class EventRecord(BaseModel):
    """A versioned structured event emitted during an execution."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    schema_version: Literal[1] = 1
    event_id: UUID
    run_id: UUID
    sequence: int = Field(ge=1)
    timestamp: datetime
    scenario: NonEmptyString
    operation: EventName
    event_type: EventName
    outcome: EventOutcome | None = None
    resource: EventResource | None = None
    attributes: dict[str, JsonValue] = Field(
        default_factory=dict
    )

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(
        cls,
        value: datetime,
    ) -> datetime:
        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "timestamp must be timezone-aware"
            )

        return value.astimezone(timezone.utc)


class EventSink(Protocol):
    """Destination for structured events."""

    def write(
        self,
        event: EventRecord,
    ) -> None:
        ...


class EventSinkError(RuntimeError):
    """Base error for event sink failures."""


class EventSerializationError(EventSinkError):
    """Raised when an event cannot be serialized."""


class EventWriteError(EventSinkError):
    """Raised when an event cannot be persisted."""


class JsonlEventSink:
    """Append structured events to a JSON Lines file."""

    def __init__(
        self,
        path: str | Path,
    ) -> None:
        self.path = Path(path)

    def write(
        self,
        event: EventRecord,
    ) -> None:
        payload = event.model_dump(mode="json")

        try:
            line = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise EventSerializationError(
                f"Failed to serialize event "
                f"'{event.event_id}': {exc}"
            ) from exc

        try:
            with self.path.open(
                "a",
                encoding="utf-8",
                newline="\n",
            ) as handle:
                handle.write(line)
                handle.write("\n")
                handle.flush()
        except OSError as exc:
            raise EventWriteError(
                f"Failed to write event log "
                f"'{self.path}': {exc}"
            ) from exc


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EventRecorder:
    """Create ordered events for one execution."""

    def __init__(
        self,
        context: ExecutionContext,
        sink: EventSink,
        *,
        clock: Callable[[], datetime] = _utc_now,
        event_id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self.context = context
        self.sink = sink
        self._clock = clock
        self._event_id_factory = event_id_factory
        self._sequence = 0
        self._lock = Lock()

    def emit(
        self,
        event_type: str,
        *,
        outcome: EventOutcome | None = None,
        resource: EventResource | None = None,
        attributes: dict[str, JsonValue] | None = None,
    ) -> EventRecord:
        with self._lock:
            sequence = self._sequence + 1

            event = EventRecord(
                event_id=self._event_id_factory(),
                run_id=self.context.run_id,
                sequence=sequence,
                timestamp=self._clock(),
                scenario=self.context.scenario,
                operation=self.context.operation,
                event_type=event_type,
                outcome=outcome,
                resource=resource,
                attributes=(
                    {}
                    if attributes is None
                    else attributes
                ),
            )

            self.sink.write(event)
            self._sequence = sequence

            return event
