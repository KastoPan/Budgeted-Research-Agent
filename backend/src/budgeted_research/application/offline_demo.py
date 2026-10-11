from __future__ import annotations

from pathlib import Path

from budgeted_research.domain.events import InMemoryEventSink
from budgeted_research.domain.models import (
    EvidenceItem,
    ResearchRequest,
    SearchResult,
    SourceDocument,
    SubQuestion,
)
from budgeted_research.engine.executor import ActionExecutor
from budgeted_research.engine.research_engine import ResearchEngine
from budgeted_research.engine.result import ResearchRunResult
from budgeted_research.policies.fixed_depth import FixedDepthPolicy
from budgeted_research.providers.fake import (
    FakeEvidenceExtractor,
    FakePageFetcher,
    FakePlanner,
    FakeReportWriter,
    FakeSearchProvider,
)
from budgeted_research.storage.artifacts import RunArtifactWriter


class OfflineDemoService:
    """Runs the complete engine without network access or paid providers."""

    async def run(
        self, question: str, output_root: Path
    ) -> tuple[ResearchRunResult, Path, int]:
        subquestions = self._subquestions()
        sink = InMemoryEventSink()
        engine = ResearchEngine(
            policy=FixedDepthPolicy(),
            executor=ActionExecutor(
                planner=FakePlanner(subquestions),
                search=FakeSearchProvider(self._search_results()),
                fetcher=FakePageFetcher(self._documents()),
                extractor=FakeEvidenceExtractor(self._evidence()),
                writer=FakeReportWriter(),
            ),
            event_sink=sink,
        )
        request = ResearchRequest(question=question)
        result = await engine.run_detailed(request)
        artifact_directory = RunArtifactWriter(output_root).write(
            request, result, sink.events
        )
        return result, artifact_directory, len(sink.events)

    @staticmethod
    def _subquestions() -> list[SubQuestion]:
        topics = (
            "架构设计",
            "成本控制",
            "证据可靠性",
            "工程适用性",
        )
        return [
            SubQuestion(
                id=f"sq_{index:02d}",
                question=f"方案的{topic}表现如何？",
                search_query=f"research agent {topic}",
                rationale=f"从{topic}维度回答主问题",
            )
            for index, topic in enumerate(topics, start=1)
        ]

    @staticmethod
    def _search_results() -> dict[str, list[SearchResult]]:
        return {
            subquestion.search_query: [
                SearchResult(
                    title=f"Offline Source {index}",
                    url=f"https://example.com/offline-source-{index}",
                    snippet=f"Offline fixture for {subquestion.question}",
                    rank=1,
                )
            ]
            for index, subquestion in enumerate(
                OfflineDemoService._subquestions(), start=1
            )
        }

    @staticmethod
    def _documents() -> dict[str, SourceDocument]:
        return {
            f"https://example.com/offline-source-{index}": SourceDocument(
                id=f"src_{index:02d}",
                url=f"https://example.com/offline-source-{index}",
                title=f"Offline Source {index}",
                content=(
                    f"Offline verified statement {index}. "
                    "This deterministic page is used only for the local demo."
                ),
            )
            for index in range(1, 5)
        }

    @staticmethod
    def _evidence() -> dict[str, list[EvidenceItem]]:
        return {
            f"sq_{index:02d}": [
                EvidenceItem(
                    id=f"ev_{index:02d}",
                    subquestion_id=f"sq_{index:02d}",
                    claim=f"离线样例结论 {index}",
                    support_span=f"Offline verified statement {index}",
                    source_id=f"src_{index:02d}",
                    source_url=f"https://example.com/offline-source-{index}",
                    source_title=f"Offline Source {index}",
                )
            ]
            for index in range(1, 5)
        }
