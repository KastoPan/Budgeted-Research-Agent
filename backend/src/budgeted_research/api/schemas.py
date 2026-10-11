from __future__ import annotations

from typing import Literal

from pydantic import Field

from budgeted_research.domain.models import (
    DomainModel,
    ResearchBudget,
    ResearchRequest,
)


class CreateRunRequest(DomainModel):
    question: str = Field(min_length=3)
    policy: Literal["fixed", "fixed_depth", "adaptive", "adaptive_budget"] = (
        "adaptive_budget"
    )
    profile: Literal["standard", "smoke"] = "standard"
    budget: ResearchBudget = Field(default_factory=ResearchBudget)

    def research_request(self) -> ResearchRequest:
        return ResearchRequest(question=self.question, budget=self.budget)
