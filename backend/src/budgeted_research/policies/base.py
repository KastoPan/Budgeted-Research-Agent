from __future__ import annotations

from typing import Protocol

from budgeted_research.domain.actions import Action
from budgeted_research.domain.models import CompletionAssessment
from budgeted_research.domain.state import ResearchState


class ResearchPolicy(Protocol):
    name: str

    def next_action(self, state: ResearchState, sequence: int) -> Action | None: ...

    def assess_completion(self, state: ResearchState) -> CompletionAssessment: ...
