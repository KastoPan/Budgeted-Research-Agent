from __future__ import annotations

from collections.abc import Mapping

from budgeted_research.domain.models import (
    DocumentChunk,
    EvidenceItem,
    ReportAssertion,
    ReportSection,
    ResearchReport,
    SearchResult,
    SourceDocument,
    SubQuestion,
    Usage,
)


class FakePlanner:
    def __init__(self, subquestions: list[SubQuestion], usage: Usage | None = None) -> None:
        self._subquestions = subquestions
        self._usage = usage or Usage(input_tokens=80, output_tokens=120)

    async def plan(self, question: str, count: int) -> tuple[list[SubQuestion], Usage]:
        if len(self._subquestions) != count:
            raise ValueError(f"fake planner requires exactly {count} subquestions")
        return list(self._subquestions), self._usage


class FakeSearchProvider:
    def __init__(self, results_by_query: Mapping[str, list[SearchResult]]) -> None:
        self._results_by_query = results_by_query

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        return list(self._results_by_query.get(query, []))[:max_results]


class FakePageFetcher:
    def __init__(self, documents_by_url: Mapping[str, SourceDocument | None]) -> None:
        self._documents_by_url = documents_by_url

    async def fetch(self, result: SearchResult) -> SourceDocument | None:
        return self._documents_by_url.get(str(result.url))


class FakeEvidenceExtractor:
    def __init__(
        self,
        evidence_by_subquestion: Mapping[str, list[EvidenceItem]],
        usage_per_call: Usage | None = None,
    ) -> None:
        self._evidence_by_subquestion = evidence_by_subquestion
        self._usage = usage_per_call or Usage(input_tokens=200, output_tokens=100)

    async def extract(
        self,
        subquestion: SubQuestion,
        chunks: list[DocumentChunk],
        max_items: int,
    ) -> tuple[list[EvidenceItem], Usage]:
        allowed_source_ids = {chunk.source_id for chunk in chunks}
        evidence = [
            item
            for item in self._evidence_by_subquestion.get(subquestion.id, [])
            if item.source_id in allowed_source_ids
        ]
        return evidence[:max_items], self._usage


class FakeReportWriter:
    def __init__(self, usage: Usage | None = None) -> None:
        self._usage = usage or Usage(input_tokens=240, output_tokens=180)

    async def write(
        self,
        question: str,
        subquestions: list[SubQuestion],
        evidence: list[EvidenceItem],
    ) -> tuple[ResearchReport, Usage]:
        evidence_by_subquestion = {
            subquestion.id: [
                item for item in evidence if item.subquestion_id == subquestion.id
            ]
            for subquestion in subquestions
        }
        sections: list[ReportSection] = []
        for subquestion in subquestions:
            items = evidence_by_subquestion[subquestion.id]
            sections.append(
                ReportSection(
                    subquestion_id=subquestion.id,
                    heading=subquestion.question,
                    assertions=[
                        ReportAssertion(text=item.claim, evidence_ids=[item.id])
                        for item in items
                    ],
                )
            )
        return ResearchReport(sections=sections), self._usage
