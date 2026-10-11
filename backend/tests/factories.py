from __future__ import annotations

from budgeted_research.domain.models import (
    EvidenceItem,
    SearchResult,
    SourceDocument,
    SubQuestion,
)


def subquestions() -> list[SubQuestion]:
    return [
        SubQuestion(
            id=f"sq_{index:02d}",
            question=f"子问题 {index}",
            search_query=f"query {index}",
            rationale="覆盖主问题的一个独立方面",
        )
        for index in range(1, 5)
    ]


def search_results() -> dict[str, list[SearchResult]]:
    return {
        f"query {index}": [
            SearchResult(
                title=f"Source {index}",
                url=f"https://example.com/source-{index}",
                snippet=f"summary {index}",
                rank=1,
            )
        ]
        for index in range(1, 5)
    }


def documents() -> dict[str, SourceDocument]:
    return {
        f"https://example.com/source-{index}": SourceDocument(
            id=f"src_{index:02d}",
            title=f"Source {index}",
            url=f"https://example.com/source-{index}",
            content=f"Verified fact number {index} appears in this source.",
        )
        for index in range(1, 5)
    }


def evidence() -> dict[str, list[EvidenceItem]]:
    return {
        f"sq_{index:02d}": [
            EvidenceItem(
                id=f"ev_{index:02d}",
                subquestion_id=f"sq_{index:02d}",
                claim=f"结论 {index}",
                support_span=f"Verified fact number {index}",
                source_id=f"src_{index:02d}",
                source_url=f"https://example.com/source-{index}",
                source_title=f"Source {index}",
            )
        ]
        for index in range(1, 5)
    }

