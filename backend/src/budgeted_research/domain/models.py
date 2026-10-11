from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_LIMITATIONS = "completed_with_limitations"
    BUDGET_EXHAUSTED = "budget_exhausted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ResearchBudget(DomainModel):
    max_tokens: Annotated[int, Field(gt=0)] = 50_000
    max_searches: Annotated[int, Field(gt=0)] = 15
    max_page_fetches: Annotated[int, Field(gt=0)] = 40
    max_elapsed_seconds: Annotated[float, Field(gt=0)] = 300.0
    max_cost_usd: Annotated[float | None, Field(gt=0)] = None


class ResearchRequest(DomainModel):
    question: Annotated[str, Field(min_length=3)]
    budget: ResearchBudget = Field(default_factory=ResearchBudget)


class SubQuestion(DomainModel):
    id: str
    question: str
    search_query: str
    rationale: str


class SearchResult(DomainModel):
    title: str
    url: HttpUrl
    snippet: str = ""
    rank: Annotated[int, Field(gt=0)]
    score: float | None = None
    published_at: str | None = None
    provider: str | None = None
    provider_request_id: str | None = None
    provider_usage: dict[str, int | float] = Field(default_factory=dict)


class SourceQualityTier(StrEnum):
    PRIMARY = "primary"
    AUTHORITATIVE = "authoritative"
    DOCUMENTATION = "documentation"
    COMMUNITY = "community"
    UNKNOWN = "unknown"


class SourceQuality(DomainModel):
    score: float = Field(default=0.5, ge=0.0, le=1.0)
    tier: SourceQualityTier = SourceQualityTier.UNKNOWN
    reasons: list[str] = Field(default_factory=list)


class SourceDocument(DomainModel):
    id: str
    url: HttpUrl
    title: str
    content: str
    retrieved_at: datetime = Field(default_factory=utc_now)
    quality: SourceQuality = Field(default_factory=SourceQuality)


class DocumentChunk(DomainModel):
    id: str
    source_id: str
    source_url: HttpUrl
    source_title: str
    content: str
    position: Annotated[int, Field(ge=0)]
    token_count: Annotated[int, Field(gt=0)]
    content_hash: str
    retrieved_at: datetime
    relevance_score: float = 0.0


class EvidenceItem(DomainModel):
    id: str
    subquestion_id: str
    claim: str
    support_span: str
    source_id: str
    source_url: HttpUrl
    source_title: str
    retrieved_at: datetime = Field(default_factory=utc_now)
    source_quality: SourceQuality = Field(default_factory=SourceQuality)

    @model_validator(mode="after")
    def support_span_is_present(self) -> EvidenceItem:
        if not self.support_span.strip():
            raise ValueError("support_span must not be blank")
        return self


class Usage(DomainModel):
    input_tokens: Annotated[int, Field(ge=0)] = 0
    output_tokens: Annotated[int, Field(ge=0)] = 0
    cost_usd: Annotated[float, Field(ge=0)] = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class BudgetStatus(DomainModel):
    tokens_used: int = 0
    searches_used: int = 0
    page_fetches_used: int = 0
    cost_usd_used: float = 0.0
    elapsed_seconds: float = 0.0
    tokens_remaining: int
    searches_remaining: int
    page_fetches_remaining: int
    cost_usd_remaining: float | None = None
    elapsed_seconds_remaining: float


class EvidenceMetrics(DomainModel):
    evidence_count: int = 0
    claim_cluster_count: int = 0
    duplicate_evidence_count: int = 0
    rejected_evidence_count: int = 0
    source_count: int = 0
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    novelty: float = Field(default=0.0, ge=0.0, le=1.0)
    source_diversity: float = Field(default=0.0, ge=0.0, le=1.0)
    source_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    conflict_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    low_novelty_streak: int = Field(default=0, ge=0)


class ClaimCluster(DomainModel):
    id: str
    canonical_claim: str
    evidence_ids: list[str] = Field(default_factory=list)


class ReportAssertion(DomainModel):
    """One factual report statement with its explicit evidence bindings."""

    text: Annotated[str, Field(min_length=1)]
    evidence_ids: Annotated[list[str], Field(min_length=1)]


class ReportSection(DomainModel):
    subquestion_id: str
    heading: Annotated[str, Field(min_length=1)]
    assertions: list[ReportAssertion] = Field(default_factory=list)


class ResearchReport(DomainModel):
    title: str = ""
    sections: list[ReportSection] = Field(default_factory=list)
    markdown: str = ""
    citation_ids: list[str] = Field(default_factory=list)
    rejected_assertion_count: Annotated[int, Field(ge=0)] = 0
    omitted_assertion_count: Annotated[int, Field(ge=0)] = 0
    rejection_reasons: list[str] = Field(default_factory=list)


class CompletionAssessment(DomainModel):
    sufficient: bool
    status: RunStatus
    reason: str
    unmet_conditions: list[str] = Field(default_factory=list)


class RunSummary(DomainModel):
    run_id: str
    policy: str
    status: RunStatus
    report: ResearchReport | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    search_count: int = 0
    page_fetch_count: int = 0
    elapsed_seconds: float = 0.0
    stop_reason: str | None = None
    completion_assessment: CompletionAssessment | None = None
