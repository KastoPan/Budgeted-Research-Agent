from __future__ import annotations

from typing import Protocol, TypeVar

from budgeted_research.domain.models import (
    DocumentChunk,
    EvidenceItem,
    ResearchReport,
    SearchResult,
    SourceDocument,
    SubQuestion,
    Usage,
)

T = TypeVar("T")
ProviderResult = tuple[T, Usage]


class Planner(Protocol):
    async def plan(self, question: str, count: int) -> ProviderResult[list[SubQuestion]]: ...


class SearchProvider(Protocol):
    async def search(self, query: str, max_results: int) -> list[SearchResult]: ...


class PageFetcher(Protocol):
    async def fetch(self, result: SearchResult) -> SourceDocument | None: ...


class EvidenceExtractor(Protocol):
    async def extract(
        self,
        subquestion: SubQuestion,
        chunks: list[DocumentChunk],
        max_items: int,
    ) -> ProviderResult[list[EvidenceItem]]: ...


class ReportWriter(Protocol):
    async def write(
        self,
        question: str,
        subquestions: list[SubQuestion],
        evidence: list[EvidenceItem],
    ) -> ProviderResult[ResearchReport]: ...
