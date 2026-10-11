from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import Field

from budgeted_research.domain.actions import ActionStatus, ActionType
from budgeted_research.domain.models import DomainModel, utc_now


class ActionRecord(DomainModel):
    sequence: int
    action_id: str
    action_type: ActionType
    policy: str
    target: str | None = None
    reason: str
    status: ActionStatus
    occurred_at: datetime = Field(default_factory=utc_now)
    estimated_resources: dict[str, int | float] = Field(default_factory=dict)
    actual_resources: dict[str, int | float] = Field(default_factory=dict)
    decision_context: dict[str, int | float | str | bool] = Field(
        default_factory=dict
    )
    error: str | None = None


class EventSink(Protocol):
    async def record(self, event: ActionRecord) -> None: ...


class InMemoryEventSink:
    def __init__(self) -> None:
        self.events: list[ActionRecord] = []

    async def record(self, event: ActionRecord) -> None:
        self.events.append(event)

    def as_dicts(self) -> list[dict[str, Any]]:
        return [event.model_dump(mode="json") for event in self.events]


class CompositeEventSink:
    """Records an event in each sink in the declared order."""

    def __init__(self, *sinks: EventSink) -> None:
        self.sinks = sinks

    async def record(self, event: ActionRecord) -> None:
        for sink in self.sinks:
            await sink.record(event)
