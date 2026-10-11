import pytest

from budgeted_research.domain.events import InMemoryEventSink
from budgeted_research.domain.models import ResearchBudget, ResearchRequest, RunStatus
from budgeted_research.engine.executor import ActionExecutor
from budgeted_research.engine.research_engine import ResearchEngine
from budgeted_research.policies.fixed_depth import FixedDepthPolicy
from budgeted_research.providers.fake import (
    FakeEvidenceExtractor,
    FakePageFetcher,
    FakePlanner,
    FakeReportWriter,
    FakeSearchProvider,
)
from tests.factories import documents, evidence, search_results, subquestions


def build_engine(event_sink: InMemoryEventSink) -> ResearchEngine:
    executor = ActionExecutor(
        planner=FakePlanner(subquestions()),
        search=FakeSearchProvider(search_results()),
        fetcher=FakePageFetcher(documents()),
        extractor=FakeEvidenceExtractor(evidence()),
        writer=FakeReportWriter(),
    )
    return ResearchEngine(
        policy=FixedDepthPolicy(),
        executor=executor,
        event_sink=event_sink,
    )


@pytest.mark.asyncio
async def test_fixed_depth_completes_offline_research_with_safe_citations() -> None:
    events = InMemoryEventSink()
    engine = build_engine(events)
    request = ResearchRequest(question="比较四种技术方案的特点与限制")

    summary = await engine.run(request, run_id="run_offline_001")

    assert summary.status is RunStatus.COMPLETED
    assert summary.search_count == 4
    assert summary.page_fetch_count == 4
    assert summary.total_tokens == 1_820
    assert len(summary.evidence) == 4
    assert summary.report is not None
    assert "[ev_01]" not in summary.report.markdown
    assert "[Source 1](https://example.com/source-1)" in summary.report.markdown
    assert len(events.events) == 14
    assert all(event.reason.startswith("fixed protocol:") for event in events.events)


@pytest.mark.asyncio
async def test_hard_budget_stops_before_unaffordable_action() -> None:
    events = InMemoryEventSink()
    engine = build_engine(events)
    request = ResearchRequest(
        question="比较四种技术方案的特点与限制",
        budget=ResearchBudget(
            max_tokens=50_000,
            max_searches=1,
            max_page_fetches=40,
            max_elapsed_seconds=300,
        ),
    )

    summary = await engine.run(request, run_id="run_budget_001")

    assert summary.status is RunStatus.BUDGET_EXHAUSTED
    assert summary.search_count == 1
    assert events.events[-1].status.value == "rejected"
    assert "search budget" in (events.events[-1].error or "")

