import pytest

from budgeted_research.domain.events import InMemoryEventSink
from budgeted_research.domain.actions import ActionType
from budgeted_research.domain.models import (
    EvidenceItem,
    ResearchBudget,
    ResearchRequest,
    RunStatus,
    SearchResult,
    SourceDocument,
    SubQuestion,
)
from budgeted_research.engine.executor import ActionExecutor
from budgeted_research.engine.research_engine import ResearchEngine
from budgeted_research.policies.adaptive_budget import (
    AdaptiveBudgetConfig,
    AdaptiveBudgetPolicy,
)
from budgeted_research.providers.fake import (
    FakeEvidenceExtractor,
    FakePageFetcher,
    FakePlanner,
    FakeReportWriter,
    FakeSearchProvider,
)


@pytest.mark.asyncio
async def test_adaptive_policy_batches_initial_sources_before_extraction() -> None:
    subquestion = SubQuestion(
        id="sq_01",
        question="Which option is suitable?",
        search_query="option comparison",
        rationale="Compare the main trade-offs.",
    )
    results = [
        SearchResult(
            title=f"Source {index}",
            url=f"https://example.com/source-{index}",
            rank=index,
        )
        for index in (1, 2)
    ]
    documents = {
        str(result.url): SourceDocument(
            id=f"src_{index:02d}",
            title=result.title,
            url=result.url,
            content=f"Verified independent fact {index} about the option.",
        )
        for index, result in enumerate(results, start=1)
    }
    evidence = [
        EvidenceItem(
            id=f"ev_{index:02d}",
            subquestion_id="sq_01",
            claim=f"Independent conclusion {index}",
            support_span=f"Verified independent fact {index}",
            source_id=f"src_{index:02d}",
            source_url=f"https://example.com/source-{index}",
            source_title=f"Source {index}",
        )
        for index in (1, 2)
    ]
    evidence.append(
        EvidenceItem(
            id="ev_invalid",
            subquestion_id="sq_01",
            claim="Unsupported generated conclusion",
            support_span="This sentence does not occur in the fetched page.",
            source_id="src_01",
            source_url="https://example.com/source-1",
            source_title="Source 1",
        )
    )
    events = InMemoryEventSink()
    engine = ResearchEngine(
        policy=AdaptiveBudgetPolicy(
            AdaptiveBudgetConfig(
                subquestion_count=1,
                search_results_per_query=2,
                max_search_rounds_per_subquestion=1,
                max_sources_per_subquestion=2,
            )
        ),
        executor=ActionExecutor(
            planner=FakePlanner([subquestion]),
            search=FakeSearchProvider({"option comparison": results}),
            fetcher=FakePageFetcher(documents),
            extractor=FakeEvidenceExtractor({"sq_01": evidence}),
            writer=FakeReportWriter(),
        ),
        event_sink=events,
    )
    request = ResearchRequest(
        question="Compare one option using independent sources",
        budget=ResearchBudget(
            max_tokens=50_000,
            max_searches=2,
            max_page_fetches=4,
            max_elapsed_seconds=300,
        ),
    )

    result = await engine.run_detailed(request, run_id="run_adaptive_001")

    assert result.summary.status is RunStatus.COMPLETED
    assert result.summary.policy == "adaptive_budget"
    assert result.summary.search_count == 1
    assert result.summary.page_fetch_count == 2
    assert result.summary.total_tokens == 920
    assert len(result.summary.evidence) == 2
    metrics = result.state.evidence_metrics["sq_01"]
    assert metrics.coverage >= 0.7
    assert metrics.claim_cluster_count == 2
    assert metrics.duplicate_evidence_count == 0
    assert metrics.source_diversity == 1.0
    assert metrics.source_quality_score == 1.0
    assert metrics.rejected_evidence_count == 1
    assert len(result.state.rejection_reasons_by_subquestion["sq_01"]) == 1
    assert {
        chunk.source_id for chunk in result.state.selected_chunks["sq_01"]
    } == {"src_01", "src_02"}
    extraction_events = [
        event
        for event in events.events
        if event.action_type is ActionType.EXTRACT_EVIDENCE
    ]
    assert len(extraction_events) == 1
    assert "batch initial valid sources" in extraction_events[0].reason
    assert "source_batch=2" in extraction_events[0].reason
    assert all(event.policy == "adaptive_budget" for event in events.events)
    assert events.events[-1].decision_context["tokens_remaining"] > 0
    assert sum(
        event.action_type is ActionType.WRITE_REPORT for event in events.events
    ) == 1
