from __future__ import annotations

from pydantic import Field

from budgeted_research.domain.models import (
    BudgetStatus,
    ClaimCluster,
    CompletionAssessment,
    DocumentChunk,
    DomainModel,
    EvidenceItem,
    EvidenceMetrics,
    ResearchReport,
    ResearchRequest,
    RunStatus,
    SearchResult,
    SourceDocument,
    SubQuestion,
)


class ResearchState(DomainModel):
    run_id: str
    request: ResearchRequest
    status: RunStatus = RunStatus.PENDING
    subquestions: list[SubQuestion] = Field(default_factory=list)
    search_results: dict[str, list[SearchResult]] = Field(default_factory=dict)
    attempted_urls: dict[str, list[str]] = Field(default_factory=dict)
    source_ids_by_subquestion: dict[str, list[str]] = Field(default_factory=dict)
    sources: dict[str, SourceDocument] = Field(default_factory=dict)
    selected_chunks: dict[str, list[DocumentChunk]] = Field(default_factory=dict)
    extracted_subquestions: set[str] = Field(default_factory=set)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    report: ResearchReport | None = None
    budget_status: BudgetStatus | None = None
    search_rounds_by_subquestion: dict[str, int] = Field(default_factory=dict)
    extraction_rounds_by_subquestion: dict[str, int] = Field(default_factory=dict)
    source_count_at_last_extraction: dict[str, int] = Field(default_factory=dict)
    extracted_source_ids_by_subquestion: dict[str, set[str]] = Field(
        default_factory=dict
    )
    evidence_metrics: dict[str, EvidenceMetrics] = Field(default_factory=dict)
    claim_clusters_by_subquestion: dict[str, list[ClaimCluster]] = Field(
        default_factory=dict
    )
    rejection_reasons_by_subquestion: dict[str, list[str]] = Field(
        default_factory=dict
    )
    stop_reason: str | None = None
    completion_assessment: CompletionAssessment | None = None
