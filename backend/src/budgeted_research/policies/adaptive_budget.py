from __future__ import annotations

from pydantic import Field, model_validator

from budgeted_research.domain.actions import Action, ActionType, ResourceEstimate
from budgeted_research.domain.models import (
    BudgetStatus,
    CompletionAssessment,
    DomainModel,
    EvidenceMetrics,
    RunStatus,
)
from budgeted_research.domain.state import ResearchState
from budgeted_research.evidence.source_quality import SourceQualityEvaluator


class AdaptiveBudgetConfig(DomainModel):
    subquestion_count: int = Field(default=4, gt=0)
    search_results_per_query: int = Field(default=5, gt=0)
    initial_sources_per_subquestion: int = Field(default=2, gt=0)
    max_sources_per_subquestion: int = Field(default=4, gt=0)
    max_search_rounds_per_subquestion: int = Field(default=2, gt=0)
    max_extraction_rounds_per_subquestion: int = Field(default=3, gt=0)
    selected_chunks_per_extraction: int = Field(default=6, gt=0)
    max_evidence_per_extraction: int = Field(default=5, gt=0)
    target_coverage: float = Field(default=0.7, ge=0.0, le=1.0)
    minimum_source_diversity: float = Field(default=0.75, ge=0.0, le=1.0)
    minimum_source_quality: float = Field(default=0.65, ge=0.0, le=1.0)
    minimum_quality_candidate_score: float = Field(default=0.75, ge=0.0, le=1.0)
    minimum_projected_quality_gain: float = Field(default=0.03, ge=0.0, le=1.0)
    quality_improvement_source_allowance: int = Field(default=1, ge=0)
    max_conflict_ratio: float = Field(default=0.2, ge=0.0, le=1.0)
    max_low_novelty_streak: int = Field(default=2, gt=0)
    max_claim_clusters_per_subquestion: int = Field(default=6, gt=0)
    planner_token_reservation: int = Field(default=4_000, gt=0)
    extractor_token_reservation: int = Field(default=8_000, gt=0)
    writer_token_reservation: int = Field(default=10_000, gt=0)
    minimum_writer_time_seconds: float = Field(default=30.0, gt=0)

    @model_validator(mode="after")
    def bootstrap_sources_fit_source_limit(self) -> AdaptiveBudgetConfig:
        if self.initial_sources_per_subquestion > self.max_sources_per_subquestion:
            raise ValueError(
                "initial_sources_per_subquestion cannot exceed "
                "max_sources_per_subquestion"
            )
        return self


class AdaptiveBudgetPolicy:
    """Explainable V1 policy driven by evidence quality and remaining budget."""

    name = "adaptive_budget"

    def __init__(
        self,
        config: AdaptiveBudgetConfig | None = None,
        source_quality_evaluator: SourceQualityEvaluator | None = None,
    ) -> None:
        self.config = config or AdaptiveBudgetConfig()
        self.source_quality_evaluator = (
            source_quality_evaluator or SourceQualityEvaluator()
        )

    def next_action(self, state: ResearchState, sequence: int) -> Action | None:
        budget = state.budget_status or self._initial_budget(state)
        if state.report is not None:
            return None
        if not state.subquestions:
            return self._action(
                sequence,
                ActionType.PLAN,
                reason=(
                    "adaptive bootstrap: create candidate subquestions before "
                    "evidence-aware allocation"
                ),
                payload={"count": self.config.subquestion_count},
                estimate=ResourceEstimate(
                    tokens=self.config.planner_token_reservation
                ),
                budget=budget,
            )

        for subquestion in state.subquestions:
            if state.search_rounds_by_subquestion.get(subquestion.id, 0) == 0:
                if budget.searches_remaining <= 0:
                    break
                return self._search_action(
                    state,
                    sequence,
                    subquestion.id,
                    subquestion.search_query,
                    "adaptive bootstrap: give each subquestion one initial search",
                    budget,
                )

        for subquestion in state.subquestions:
            subquestion_id = subquestion.id
            if state.extraction_rounds_by_subquestion.get(subquestion_id, 0) > 0:
                continue
            source_ids = state.source_ids_by_subquestion.get(subquestion_id, [])
            if len(source_ids) < self.config.initial_sources_per_subquestion:
                fetch = self._next_fetch(state, sequence, subquestion_id, budget)
                if fetch is not None:
                    return fetch
                continue
            if self._can_afford_extraction(budget):
                return self._extract_action(
                    state,
                    sequence,
                    subquestion_id,
                    budget,
                    (
                        "adaptive bootstrap: batch initial valid sources before "
                        "measuring evidence coverage"
                    ),
                )
            if state.evidence:
                return self._write_or_stop(
                    state,
                    sequence,
                    budget,
                    "adaptive stop: preserve the remaining token budget for report writing",
                )

        write_reason = self._write_reason(state, budget)
        if write_reason is not None:
            return self._write_or_stop(state, sequence, budget, write_reason)

        for subquestion_id in self._rank_targets(state):
            metrics = state.evidence_metrics.get(subquestion_id, EvidenceMetrics())
            extraction_rounds = state.extraction_rounds_by_subquestion.get(
                subquestion_id, 0
            )
            source_count = len(
                state.source_ids_by_subquestion.get(subquestion_id, [])
            )
            last_extracted_source_count = state.source_count_at_last_extraction.get(
                subquestion_id, 0
            )
            can_extract_more = (
                extraction_rounds
                < self.config.max_extraction_rounds_per_subquestion
                and self._can_afford_extraction(budget)
            )
            if (
                source_count > last_extracted_source_count
                and can_extract_more
            ):
                return self._extract_action(
                    state,
                    sequence,
                    subquestion_id,
                    budget,
                    (
                        "adaptive deepen: a new source is available for an "
                        "evidence-insufficient subquestion"
                    ),
                )

            if not can_extract_more:
                continue
            if metrics.low_novelty_streak >= self.config.max_low_novelty_streak:
                continue
            quality_only = self._quality_is_only_gap(metrics)
            source_limit = self.config.max_sources_per_subquestion
            if quality_only:
                source_limit += self.config.quality_improvement_source_allowance
            if source_count < source_limit:
                fetch = self._next_fetch(state, sequence, subquestion_id, budget)
                if fetch is not None:
                    return fetch

            search_rounds = state.search_rounds_by_subquestion.get(
                subquestion_id, 0
            )
            if (
                search_rounds < self.config.max_search_rounds_per_subquestion
                and source_count < source_limit
                and budget.searches_remaining > 0
                and budget.page_fetches_remaining > 0
            ):
                subquestion = next(
                    item for item in state.subquestions if item.id == subquestion_id
                )
                query = (
                    f"{subquestion.search_query} official documentation primary "
                    "source limitations trade-offs independent evidence"
                )
                return self._search_action(
                    state,
                    sequence,
                    subquestion_id,
                    query,
                    (
                        "adaptive deepen: existing candidates are exhausted while "
                        f"coverage={metrics.coverage:.2f}, "
                        f"quality={metrics.source_quality_score:.2f}, "
                        f"conflict={metrics.conflict_ratio:.2f}"
                    ),
                    budget,
                )

        return self._write_or_stop(
            state,
            sequence,
            budget,
            "adaptive stop: no eligible action has positive expected information gain",
        )

    def assess_completion(self, state: ResearchState) -> CompletionAssessment:
        unmet: list[str] = []
        for subquestion in state.subquestions:
            metrics = state.evidence_metrics.get(subquestion.id, EvidenceMetrics())
            prefix = subquestion.id
            if metrics.coverage < self.config.target_coverage:
                unmet.append(
                    f"{prefix}: coverage {metrics.coverage:.2f} is below "
                    f"{self.config.target_coverage:.2f}"
                )
            if metrics.source_diversity < self.config.minimum_source_diversity:
                unmet.append(
                    f"{prefix}: source diversity {metrics.source_diversity:.2f} is "
                    f"below {self.config.minimum_source_diversity:.2f}"
                )
            if metrics.source_quality_score < self.config.minimum_source_quality:
                unmet.append(
                    f"{prefix}: source quality {metrics.source_quality_score:.2f} is "
                    f"below {self.config.minimum_source_quality:.2f}"
                )
            if metrics.conflict_ratio > self.config.max_conflict_ratio:
                unmet.append(
                    f"{prefix}: conflict ratio {metrics.conflict_ratio:.2f} exceeds "
                    f"{self.config.max_conflict_ratio:.2f}"
                )

        if not unmet:
            return CompletionAssessment(
                sufficient=True,
                status=RunStatus.COMPLETED,
                reason="adaptive evidence sufficiency targets were reached",
            )
        return CompletionAssessment(
            sufficient=False,
            status=RunStatus.COMPLETED_WITH_LIMITATIONS,
            reason="adaptive report generated from evidence below sufficiency targets",
            unmet_conditions=unmet,
        )

    def _write_reason(
        self, state: ResearchState, budget: BudgetStatus
    ) -> str | None:
        if not state.evidence:
            return None
        measured = [
            state.evidence_metrics.get(item.id, EvidenceMetrics())
            for item in state.subquestions
        ]
        if measured and all(self._meets_targets(item) for item in measured):
            return "adaptive stop: every subquestion reached all sufficiency targets"
        if (
            budget.tokens_remaining
            < self.config.writer_token_reservation
            + self.config.extractor_token_reservation
        ):
            return "adaptive stop: preserve the remaining token budget for report writing"
        if budget.elapsed_seconds_remaining <= self.config.minimum_writer_time_seconds:
            return "adaptive stop: preserve the remaining time budget for report writing"
        if budget.page_fetches_remaining == 0 and all(
            len(state.source_ids_by_subquestion.get(item.id, []))
            <= state.source_count_at_last_extraction.get(item.id, 0)
            for item in state.subquestions
        ):
            return "adaptive stop: page-fetch budget is exhausted"
        return None

    def _rank_targets(self, state: ResearchState) -> list[str]:
        return [
            item.id
            for item in sorted(
                (
                    item
                    for item in state.subquestions
                    if not self._meets_targets(
                        state.evidence_metrics.get(item.id, EvidenceMetrics())
                    )
                ),
                key=lambda item: (
                    -state.evidence_metrics.get(
                        item.id, EvidenceMetrics()
                    ).conflict_ratio,
                    state.evidence_metrics.get(item.id, EvidenceMetrics()).coverage,
                    state.evidence_metrics.get(
                        item.id, EvidenceMetrics()
                    ).source_diversity,
                    state.evidence_metrics.get(
                        item.id, EvidenceMetrics()
                    ).source_quality_score,
                    item.id,
                ),
            )
        ]

    def _next_fetch(
        self,
        state: ResearchState,
        sequence: int,
        subquestion_id: str,
        budget: BudgetStatus,
    ) -> Action | None:
        if budget.page_fetches_remaining <= 0:
            return None
        attempted = set(state.attempted_urls.get(subquestion_id, []))
        candidates = [
            item
            for item in state.search_results.get(subquestion_id, [])
            if str(item.url) not in attempted
        ]
        if not candidates:
            return None
        metrics = state.evidence_metrics.get(subquestion_id, EvidenceMetrics())
        quality_only = self._quality_is_only_gap(metrics)
        scored_candidates = [
            (item, self.source_quality_evaluator.evaluate(item.url))
            for item in candidates
        ]
        if quality_only:
            scored_candidates = [
                (item, quality)
                for item, quality in scored_candidates
                if quality.score >= self.config.minimum_quality_candidate_score
                and self._projected_quality_gain(metrics, quality.score)
                >= self.config.minimum_projected_quality_gain
            ]
        if not scored_candidates:
            return None
        result, expected_quality = max(
            scored_candidates,
            key=lambda pair: (
                pair[1].score,
                pair[0].score or 0.0,
                -pair[0].rank,
            ),
        )
        projected_quality_gain = self._projected_quality_gain(
            metrics, expected_quality.score
        )
        return self._action(
            sequence,
            ActionType.FETCH,
            target=subquestion_id,
            reason=(
                "adaptive allocation: fetch the next ranked source for "
                f"coverage={metrics.coverage:.2f}, "
                f"diversity={metrics.source_diversity:.2f}, "
                f"expected_quality={expected_quality.score:.2f}, "
                f"projected_quality_gain={projected_quality_gain:.2f}, "
                f"quality_only={str(quality_only).lower()}"
            ),
            payload={"result": result},
            estimate=ResourceEstimate(page_fetches=1),
            budget=budget,
            metrics=metrics,
        )

    def _extract_action(
        self,
        state: ResearchState,
        sequence: int,
        subquestion_id: str,
        budget: BudgetStatus,
        reason: str,
    ) -> Action:
        metrics = state.evidence_metrics.get(subquestion_id, EvidenceMetrics())
        source_ids = set(
            state.source_ids_by_subquestion.get(subquestion_id, [])
        )
        extracted_source_ids = state.extracted_source_ids_by_subquestion.get(
            subquestion_id, set()
        )
        pending_source_count = len(source_ids - extracted_source_ids) or len(
            source_ids
        )
        remaining_cluster_capacity = max(
            1,
            self.config.max_claim_clusters_per_subquestion
            - metrics.claim_cluster_count,
        )
        return self._action(
            sequence,
            ActionType.EXTRACT_EVIDENCE,
            target=subquestion_id,
            reason=f"{reason}; source_batch={pending_source_count}",
            payload={
                "max_items": min(
                    self.config.max_evidence_per_extraction,
                    remaining_cluster_capacity,
                ),
                "selected_chunks": self.config.selected_chunks_per_extraction,
                "source_batch_size": pending_source_count,
            },
            estimate=ResourceEstimate(
                tokens=self.config.extractor_token_reservation
            ),
            budget=budget,
            metrics=metrics,
        )

    def _quality_is_only_gap(self, metrics: EvidenceMetrics) -> bool:
        return (
            metrics.coverage >= self.config.target_coverage
            and metrics.source_diversity >= self.config.minimum_source_diversity
            and metrics.conflict_ratio <= self.config.max_conflict_ratio
            and metrics.source_quality_score < self.config.minimum_source_quality
        )

    def _meets_targets(self, metrics: EvidenceMetrics) -> bool:
        return (
            metrics.coverage >= self.config.target_coverage
            and metrics.source_diversity >= self.config.minimum_source_diversity
            and metrics.source_quality_score >= self.config.minimum_source_quality
            and metrics.conflict_ratio <= self.config.max_conflict_ratio
        )

    @staticmethod
    def _projected_quality_gain(
        metrics: EvidenceMetrics, candidate_quality: float
    ) -> float:
        projected = (
            metrics.source_quality_score * metrics.source_count + candidate_quality
        ) / (metrics.source_count + 1)
        return projected - metrics.source_quality_score

    def _search_action(
        self,
        state: ResearchState,
        sequence: int,
        subquestion_id: str,
        query: str,
        reason: str,
        budget: BudgetStatus,
    ) -> Action:
        metrics = state.evidence_metrics.get(subquestion_id, EvidenceMetrics())
        return self._action(
            sequence,
            ActionType.SEARCH,
            target=subquestion_id,
            reason=reason,
            payload={
                "query": query,
                "max_results": self.config.search_results_per_query,
            },
            estimate=ResourceEstimate(searches=1),
            budget=budget,
            metrics=metrics,
        )

    def _write_or_stop(
        self,
        state: ResearchState,
        sequence: int,
        budget: BudgetStatus,
        reason: str,
    ) -> Action | None:
        if not state.evidence:
            return None
        return self._action(
            sequence,
            ActionType.WRITE_REPORT,
            reason=reason,
            estimate=ResourceEstimate(tokens=self.config.writer_token_reservation),
            budget=budget,
        )

    def _can_afford_extraction(self, budget: BudgetStatus) -> bool:
        return (
            budget.tokens_remaining
            >= self.config.extractor_token_reservation
            + self.config.writer_token_reservation
        )

    @staticmethod
    def _initial_budget(state: ResearchState) -> BudgetStatus:
        limits = state.request.budget
        return BudgetStatus(
            tokens_remaining=limits.max_tokens,
            searches_remaining=limits.max_searches,
            page_fetches_remaining=limits.max_page_fetches,
            cost_usd_remaining=limits.max_cost_usd,
            elapsed_seconds_remaining=limits.max_elapsed_seconds,
        )

    @staticmethod
    def _action(
        sequence: int,
        action_type: ActionType,
        reason: str,
        budget: BudgetStatus,
        target: str | None = None,
        payload: dict | None = None,
        estimate: ResourceEstimate | None = None,
        metrics: EvidenceMetrics | None = None,
    ) -> Action:
        context: dict[str, int | float | str | bool] = {
            "tokens_remaining": budget.tokens_remaining,
            "searches_remaining": budget.searches_remaining,
            "page_fetches_remaining": budget.page_fetches_remaining,
            "elapsed_seconds_remaining": round(
                budget.elapsed_seconds_remaining, 3
            ),
        }
        if metrics is not None:
            context.update(
                {
                    "coverage": metrics.coverage,
                    "claim_cluster_count": metrics.claim_cluster_count,
                    "novelty": metrics.novelty,
                    "source_diversity": metrics.source_diversity,
                    "source_quality_score": metrics.source_quality_score,
                    "conflict_ratio": metrics.conflict_ratio,
                    "low_novelty_streak": metrics.low_novelty_streak,
                    "rejected_evidence_count": metrics.rejected_evidence_count,
                    "duplicate_evidence_count": metrics.duplicate_evidence_count,
                }
            )
        return Action(
            id=f"action_{sequence:04d}",
            type=action_type,
            target=target,
            reason=reason,
            payload=payload or {},
            estimated_resources=estimate or ResourceEstimate(),
            decision_context=context,
        )
