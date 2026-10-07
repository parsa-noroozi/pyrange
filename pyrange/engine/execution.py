from __future__ import annotations

from typing import Annotated

from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)


NonEmptyString = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
    ),
]

StructuredName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        pattern=r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$",
    ),
]


class ExecutionContext(BaseModel):
    """Identify one PyRange operation execution."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    run_id: UUID = Field(default_factory=uuid4)
    scenario: NonEmptyString
    operation: StructuredName
