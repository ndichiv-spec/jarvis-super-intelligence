"""Versioned event names and serializable envelopes for runtime presentation updates."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from .schemas import ContractModel, Identifier


class PresentationEvent(ContractModel):
    protocol: Literal["jarvis.presentation"]
    version: str
    presentation_id: Identifier
    session_id: Identifier
    sequence: int = Field(ge=0)
    type: Literal[
        "created", "updated", "transitioned", "interaction", "capability_changed",
        "media_ready", "error", "closed",
    ]
    occurred_at: datetime
    payload: dict[str, object] = Field(default_factory=dict)


PresentationEventBatch = Annotated[list[PresentationEvent], Field(max_length=1000)]
