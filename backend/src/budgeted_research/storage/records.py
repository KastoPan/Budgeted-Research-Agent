from __future__ import annotations

from datetime import datetime

from budgeted_research.domain.models import DomainModel, ResearchRequest, RunStatus


class StoredRun(DomainModel):
    run_id: str
    question: str
    policy: str
    profile: str = "standard"
    status: RunStatus
    request: ResearchRequest
    stop_reason: str | None = None
    artifact_directory: str | None = None
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    search_count: int = 0
    page_fetch_count: int = 0
    elapsed_seconds: float = 0.0
    action_count: int = 0
    created_at: datetime
    updated_at: datetime
