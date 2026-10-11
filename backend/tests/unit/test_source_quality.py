import pytest

from budgeted_research.domain.actions import ActionType
from budgeted_research.domain.models import (
    BudgetStatus,
    EvidenceItem,
    EvidenceMetrics,
    ResearchRequest,
    RunStatus,
    SearchResult,
    SourceQualityTier,
    SubQuestion,
)
from budgeted_research.domain.state import ResearchState
from budgeted_research.evidence.source_quality import SourceQualityEvaluator
from budgeted_research.policies.adaptive_budget import (
    AdaptiveBudgetConfig,
    AdaptiveBudgetPolicy,
)


def _quality_only_gap_state(
    candidates: list[SearchResult], *, search_rounds: int = 1
) -> ResearchState:
    subquestion = SubQuestion(
        id="sq_01",
        question="What is the difference?",
        search_query="difference",
        rationale="Cover the main distinction.",
    )
    return ResearchState(
        run_id="run_quality_gap",
        request=ResearchRequest(question="Compare two technologies"),
        subquestions=[subquestion],
        search_results={"sq_01": candidates},
        source_ids_by_subquestion={"sq_01": ["src_01", "src_02"]},
        extracted_source_ids_by_subquestion={"sq_01": {"src_01", "src_02"}},
        source_count_at_last_extraction={"sq_01": 2},
        search_rounds_by_subquestion={"sq_01": search_rounds},
        extraction_rounds_by_subquestion={"sq_01": 1},
        evidence=[
            EvidenceItem(
                id="ev_01",
                subquestion_id="sq_01",
                claim="A supported claim.",
                support_span="A supported claim.",
                source_id="src_01",
                source_url="https://neutral.example.org/source",
                source_title="Neutral source",
            )
        ],
        evidence_metrics={
            "sq_01": EvidenceMetrics(
                evidence_count=3,
                claim_cluster_count=3,
                source_count=2,
                coverage=1.0,
                source_diversity=1.0,
                source_quality_score=0.5,
                conflict_ratio=0.0,
            )
        },
        budget_status=BudgetStatus(
            tokens_remaining=50_000,
            searches_remaining=1,
            page_fetches_remaining=4,
            elapsed_seconds_remaining=300,
        ),
    )


def test_source_quality_recognizes_primary_documentation() -> None:
    quality = SourceQualityEvaluator().evaluate(
        "https://docs.python.org/3/tutorial/datastructures.html"
    )

    assert quality.score == 1.0
    assert quality.tier is SourceQualityTier.PRIMARY


def test_adaptive_bootstrap_source_target_must_fit_source_limit() -> None:
    with pytest.raises(ValueError, match="initial_sources_per_subquestion"):
        AdaptiveBudgetConfig(
            initial_sources_per_subquestion=2,
            max_sources_per_subquestion=1,
        )


def test_source_quality_marks_community_publishers_as_low_confidence() -> None:
    quality = SourceQualityEvaluator().evaluate(
        "https://www.geeksforgeeks.org/python/example"
    )

    assert quality.score == 0.4
    assert quality.tier is SourceQualityTier.COMMUNITY


def test_adaptive_completion_reports_unmet_sufficiency_targets() -> None:
    subquestion = SubQuestion(
        id="sq_01",
        question="What is the difference?",
        search_query="difference",
        rationale="Cover the main distinction.",
    )
    state = ResearchState(
        run_id="run_partial",
        request=ResearchRequest(question="Compare two technologies"),
        subquestions=[subquestion],
        evidence_metrics={
            "sq_01": EvidenceMetrics(
                evidence_count=2,
                claim_cluster_count=2,
                source_count=1,
                coverage=0.6167,
                source_diversity=0.5,
                source_quality_score=0.4,
            )
        },
        budget_status=BudgetStatus(
            tokens_remaining=10_000,
            searches_remaining=0,
            page_fetches_remaining=0,
            elapsed_seconds_remaining=100,
        ),
    )

    assessment = AdaptiveBudgetPolicy().assess_completion(state)

    assert assessment.status is RunStatus.COMPLETED_WITH_LIMITATIONS
    assert not assessment.sufficient
    assert len(assessment.unmet_conditions) == 3


def test_adaptive_policy_prefers_documentation_over_higher_ranked_community_page() -> None:
    subquestion = SubQuestion(
        id="sq_01",
        question="How does Python behave?",
        search_query="python behavior",
        rationale="Find implementation guidance.",
    )
    state = ResearchState(
        run_id="run_quality_selection",
        request=ResearchRequest(question="Explain Python behavior"),
        subquestions=[subquestion],
        search_results={
            "sq_01": [
                SearchResult(
                    title="Community article",
                    url="https://www.geeksforgeeks.org/python/example",
                    rank=1,
                    score=0.95,
                ),
                SearchResult(
                    title="Python documentation",
                    url="https://docs.python.org/3/reference/index.html",
                    rank=2,
                    score=0.8,
                ),
            ]
        },
        search_rounds_by_subquestion={"sq_01": 1},
        budget_status=BudgetStatus(
            tokens_remaining=50_000,
            searches_remaining=1,
            page_fetches_remaining=2,
            elapsed_seconds_remaining=300,
        ),
    )

    action = AdaptiveBudgetPolicy().next_action(state, sequence=1)

    assert action is not None
    assert str(action.payload["result"].url).startswith("https://docs.python.org/")
    assert "expected_quality=1.00" in action.reason


def test_quality_only_gap_skips_low_quality_candidate_and_searches_for_primary_source() -> None:
    state = _quality_only_gap_state(
        [
            SearchResult(
                title="Community article",
                url="https://www.geeksforgeeks.org/python/example",
                rank=1,
                score=0.95,
            )
        ]
    )

    action = AdaptiveBudgetPolicy().next_action(state, sequence=1)

    assert action is not None
    assert action.type is ActionType.SEARCH
    assert "official documentation primary source" in action.payload["query"]


def test_quality_only_gap_stops_instead_of_fetching_low_value_candidate() -> None:
    state = _quality_only_gap_state(
        [
            SearchResult(
                title="Community article",
                url="https://www.geeksforgeeks.org/python/example",
                rank=1,
                score=0.95,
            )
        ],
        search_rounds=2,
    )

    action = AdaptiveBudgetPolicy().next_action(state, sequence=1)

    assert action is not None
    assert action.type is ActionType.WRITE_REPORT
    assert "no eligible action" in action.reason


def test_quality_only_gap_fetches_candidate_with_material_projected_gain() -> None:
    state = _quality_only_gap_state(
        [
            SearchResult(
                title="Python documentation",
                url="https://docs.python.org/3/reference/index.html",
                rank=2,
                score=0.8,
            )
        ]
    )

    action = AdaptiveBudgetPolicy().next_action(state, sequence=1)

    assert action is not None
    assert action.type is ActionType.FETCH
    assert "quality_only=true" in action.reason


def test_adaptive_policy_does_not_fetch_when_extraction_capacity_is_exhausted() -> None:
    state = _quality_only_gap_state(
        [
            SearchResult(
                title="Python documentation",
                url="https://docs.python.org/3/reference/index.html",
                rank=1,
                score=0.9,
            )
        ]
    )
    state.extraction_rounds_by_subquestion["sq_01"] = 3

    action = AdaptiveBudgetPolicy().next_action(state, sequence=1)

    assert action is not None
    assert action.type is ActionType.WRITE_REPORT
    assert "no eligible action" in action.reason


def test_adaptive_policy_does_not_reopen_a_sufficient_subquestion() -> None:
    state = _quality_only_gap_state(
        [
            SearchResult(
                title="Low-value remaining candidate",
                url="https://www.geeksforgeeks.org/python/example",
                rank=1,
            )
        ],
        search_rounds=2,
    )
    sufficient = SubQuestion(
        id="sq_02",
        question="What is already established?",
        search_query="established fact",
        rationale="Exercise completed-target allocation.",
    )
    state.subquestions.append(sufficient)
    state.search_results["sq_02"] = [
        SearchResult(
            title="Unused documentation",
            url="https://docs.python.org/3/reference/index.html",
            rank=1,
        )
    ]
    state.source_ids_by_subquestion["sq_02"] = ["src_03", "src_04"]
    state.source_count_at_last_extraction["sq_02"] = 2
    state.search_rounds_by_subquestion["sq_02"] = 1
    state.extraction_rounds_by_subquestion["sq_02"] = 1
    state.evidence_metrics["sq_02"] = EvidenceMetrics(
        evidence_count=4,
        claim_cluster_count=4,
        source_count=2,
        coverage=1.0,
        source_diversity=1.0,
        source_quality_score=0.65,
        conflict_ratio=0.0,
    )

    action = AdaptiveBudgetPolicy().next_action(state, sequence=1)

    assert action is not None
    assert action.type is ActionType.WRITE_REPORT
    assert "no eligible action" in action.reason


def test_adaptive_bootstrap_degrades_to_one_source_when_candidates_are_exhausted() -> None:
    subquestion = SubQuestion(
        id="sq_01",
        question="What evidence is available?",
        search_query="available evidence",
        rationale="Exercise a sparse result set.",
    )
    exhausted_url = "https://docs.python.org/3/reference/index.html"
    state = ResearchState(
        run_id="run_sparse_bootstrap",
        request=ResearchRequest(question="Explain the available evidence"),
        subquestions=[subquestion],
        search_results={
            "sq_01": [
                SearchResult(
                    title="Only valid source",
                    url=exhausted_url,
                    rank=1,
                )
            ]
        },
        attempted_urls={"sq_01": [exhausted_url]},
        source_ids_by_subquestion={"sq_01": ["src_01"]},
        search_rounds_by_subquestion={"sq_01": 1},
        budget_status=BudgetStatus(
            tokens_remaining=50_000,
            searches_remaining=1,
            page_fetches_remaining=3,
            elapsed_seconds_remaining=300,
        ),
    )

    action = AdaptiveBudgetPolicy().next_action(state, sequence=1)

    assert action is not None
    assert action.type is ActionType.EXTRACT_EVIDENCE
    assert action.target == "sq_01"
    assert action.payload["source_batch_size"] == 1
