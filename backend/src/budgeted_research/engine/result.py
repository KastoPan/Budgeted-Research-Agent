from __future__ import annotations

from dataclasses import dataclass

from budgeted_research.domain.models import RunSummary
from budgeted_research.domain.state import ResearchState


@dataclass(frozen=True, slots=True)
class ResearchRunResult:
    state: ResearchState
    summary: RunSummary
