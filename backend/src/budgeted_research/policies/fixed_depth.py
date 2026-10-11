from __future__ import annotations

from pydantic import Field

from budgeted_research.domain.actions import Action, ActionType, ResourceEstimate
from budgeted_research.domain.models import (
    CompletionAssessment,
    DomainModel,
    RunStatus,
)
from budgeted_research.domain.state import ResearchState


class FixedDepthConfig(DomainModel):
    subquestion_count: int = Field(default=4, gt=0)
    search_results_per_query: int = Field(default=5, gt=0)
    pages_per_subquestion: int = Field(default=3, gt=0)
    selected_chunks_per_subquestion: int = Field(default=6, gt=0)
    max_evidence_per_subquestion: int = Field(default=5, gt=0)
    planner_token_reservation: int = Field(default=4_000, gt=0)
    extractor_token_reservation: int = Field(default=8_000, gt=0)
    writer_token_reservation: int = Field(default=10_000, gt=0)


class FixedDepthPolicy:
    """A deterministic one-round policy that never reacts to evidence quality."""

    name = "fixed_depth"

    def __init__(self, config: FixedDepthConfig | None = None) -> None:
        self.config = config or FixedDepthConfig()

    def next_action(self, state: ResearchState, sequence: int) -> Action | None:
        if not state.subquestions:
            return self._action(
                sequence,
                ActionType.PLAN,
                reason=f"fixed protocol: generate {self.config.subquestion_count} subquestions",
                payload={"count": self.config.subquestion_count},
                estimate=ResourceEstimate(tokens=self.config.planner_token_reservation),
            )

        for subquestion in state.subquestions:
            if subquestion.id not in state.search_results:
                return self._action(
                    sequence,
                    ActionType.SEARCH,
                    target=subquestion.id,
                    reason="fixed protocol: one search per subquestion",
                    payload={
                        "query": subquestion.search_query,
                        "max_results": self.config.search_results_per_query,
                    },
                    estimate=ResourceEstimate(searches=1),
                )

        for subquestion in state.subquestions:
            source_ids = state.source_ids_by_subquestion.get(subquestion.id, [])
            if len(source_ids) >= self.config.pages_per_subquestion:
                continue
            attempted = set(state.attempted_urls.get(subquestion.id, []))
            next_result = next(
                (
                    result
                    for result in state.search_results[subquestion.id]
                    if str(result.url) not in attempted
                ),
                None,
            )
            if next_result is not None:
                return self._action(
                    sequence,
                    ActionType.FETCH,
                    target=subquestion.id,
                    reason=(
                        "fixed protocol: fetch ranked results until the page quota "
                        "or candidate list is exhausted"
                    ),
                    payload={"result": next_result},
                    estimate=ResourceEstimate(page_fetches=1),
                )

        for subquestion in state.subquestions:
            if subquestion.id not in state.extracted_subquestions:
                return self._action(
                    sequence,
                    ActionType.EXTRACT_EVIDENCE,
                    target=subquestion.id,
                    reason="fixed protocol: one evidence extraction per subquestion",
                    payload={
                        "max_items": self.config.max_evidence_per_subquestion,
                        "selected_chunks": self.config.selected_chunks_per_subquestion,
                    },
                    estimate=ResourceEstimate(tokens=self.config.extractor_token_reservation),
                )

        if state.report is None and state.evidence:
            return self._action(
                sequence,
                ActionType.WRITE_REPORT,
                reason="fixed protocol: one report generation after evidence extraction",
                estimate=ResourceEstimate(tokens=self.config.writer_token_reservation),
            )
        return None

    def assess_completion(self, state: ResearchState) -> CompletionAssessment:
        return CompletionAssessment(
            sufficient=True,
            status=RunStatus.COMPLETED,
            reason="fixed-depth protocol completed",
        )

    @staticmethod
    def _action(
        sequence: int,
        action_type: ActionType,
        reason: str,
        target: str | None = None,
        payload: dict | None = None,
        estimate: ResourceEstimate | None = None,
    ) -> Action:
        return Action(
            id=f"action_{sequence:04d}",
            type=action_type,
            target=target,
            reason=reason,
            payload=payload or {},
            estimated_resources=estimate or ResourceEstimate(),
        )
