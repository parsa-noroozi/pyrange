from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
)

from pyrange.engine.execution import (
    ExecutionContext,
    NonEmptyString,
    StructuredName,
)


TelemetryName = StructuredName


class TelemetryResource(BaseModel):
    """Identify the resource associated with telemetry."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    type: TelemetryName
    name: NonEmptyString


class TelemetryRecord(BaseModel):
    """A versioned telemetry observation for one execution."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    schema_version: Literal[1] = 1
    telemetry_id: UUID
    run_id: UUID
    sequence: int = Field(ge=1)
    timestamp: datetime
    scenario: NonEmptyString
    operation: StructuredName
    telemetry_type: TelemetryName
    resource: TelemetryResource | None = None
    data: dict[str, JsonValue] = Field(
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


class TelemetrySink(Protocol):
    """Destination for structured telemetry."""

    def write(
        self,
        record: TelemetryRecord,
    ) -> None:
        ...


class TelemetrySinkError(RuntimeError):
    """Base error for telemetry sink failures."""


class TelemetrySerializationError(
    TelemetrySinkError
):
    """Raised when telemetry cannot be serialized."""


class TelemetryWriteError(TelemetrySinkError):
    """Raised when telemetry cannot be persisted."""


class JsonlTelemetrySink:
    """Append telemetry records to a JSON Lines file."""

    def __init__(
        self,
        path: str | Path,
    ) -> None:
        self.path = Path(path)

    def write(
        self,
        record: TelemetryRecord,
    ) -> None:
        payload = record.model_dump(mode="json")

        try:
            line = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise TelemetrySerializationError(
                f"Failed to serialize telemetry "
                f"'{record.telemetry_id}': {exc}"
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
            raise TelemetryWriteError(
                f"Failed to write telemetry log "
                f"'{self.path}': {exc}"
            ) from exc


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TelemetryRecorder:
    """Create ordered telemetry for one execution."""

    def __init__(
        self,
        context: ExecutionContext,
        sink: TelemetrySink,
        *,
        clock: Callable[[], datetime] = _utc_now,
        telemetry_id_factory: Callable[
            [], UUID
        ] = uuid4,
    ) -> None:
        self.context = context
        self.sink = sink
        self._clock = clock
        self._telemetry_id_factory = (
            telemetry_id_factory
        )
        self._sequence = 0
        self._lock = Lock()

    def record(
        self,
        telemetry_type: str,
        *,
        resource: TelemetryResource | None = None,
        data: dict[str, JsonValue] | None = None,
    ) -> TelemetryRecord:
        with self._lock:
            sequence = self._sequence + 1

            record = TelemetryRecord(
                telemetry_id=(
                    self._telemetry_id_factory()
                ),
                run_id=self.context.run_id,
                sequence=sequence,
                timestamp=self._clock(),
                scenario=self.context.scenario,
                operation=self.context.operation,
                telemetry_type=telemetry_type,
                resource=resource,
                data=(
                    {}
                    if data is None
                    else data
                ),
            )

            self.sink.write(record)
            self._sequence = sequence

            return record
