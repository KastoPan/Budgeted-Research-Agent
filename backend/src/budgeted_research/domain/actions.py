from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from budgeted_research.domain.models import DocumentChunk, DomainModel, EvidenceItem, Usage


class ActionType(StrEnum):
    PLAN = "plan"
    SEARCH = "search"
    FETCH = "fetch"
    EXTRACT_EVIDENCE = "extract_evidence"
    WRITE_REPORT = "write_report"


class ActionStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class ResourceEstimate(DomainModel):
    tokens: int = Field(default=0, ge=0)
    searches: int = Field(default=0, ge=0)
    page_fetches: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0)


class Action(DomainModel):
    id: str
    type: ActionType
    target: str | None = None
    reason: str
    payload: dict[str, Any] = Field(default_factory=dict)
    estimated_resources: ResourceEstimate = Field(default_factory=ResourceEstimate)
    decision_context: dict[str, int | float | str | bool] = Field(
        default_factory=dict
    )


class ActionResult(DomainModel):
    action_id: str
    status: ActionStatus
    output: Any = None
    usage: Usage = Field(default_factory=Usage)
    actual_resources: ResourceEstimate = Field(default_factory=ResourceEstimate)
    error: str | None = None


class EvidenceExtractionOutput(DomainModel):
    selected_chunks: list[DocumentChunk]
    evidence: list[EvidenceItem]
    processed_source_ids: list[str] = Field(default_factory=list)
    rejected_evidence_count: int = Field(default=0, ge=0)
    rejection_reasons: list[str] = Field(default_factory=list)
