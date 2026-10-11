from __future__ import annotations

import math
from collections import Counter

from budgeted_research.context.chunking import TokenChunker
from budgeted_research.context.tokenization import tokenize
from budgeted_research.domain.models import DocumentChunk, SourceDocument, SubQuestion


class Bm25ContextSelector:
    def __init__(
        self,
        chunker: TokenChunker | None = None,
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.chunker = chunker or TokenChunker()
        self.k1 = k1
        self.b = b

    def select(
        self,
        subquestion: SubQuestion,
        sources: list[SourceDocument],
        limit: int,
    ) -> list[DocumentChunk]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        candidates: list[DocumentChunk] = []
        seen_hashes: set[str] = set()
        for source in sources:
            for chunk in self.chunker.chunk(source):
                if chunk.content_hash in seen_hashes:
                    continue
                seen_hashes.add(chunk.content_hash)
                candidates.append(chunk)
        if not candidates:
            return []

        query_tokens = tokenize(
            f"{subquestion.question} {subquestion.search_query}"
        )
        documents = [tokenize(chunk.content) for chunk in candidates]
        scores = self._score(query_tokens, documents)
        ranked = [
            chunk.model_copy(update={"relevance_score": score})
            for chunk, score in zip(candidates, scores, strict=True)
        ]
        ranked.sort(
            key=lambda chunk: (
                -chunk.relevance_score,
                chunk.source_id,
                chunk.position,
            )
        )
        return ranked[:limit]

    def _score(self, query: list[str], documents: list[list[str]]) -> list[float]:
        document_count = len(documents)
        average_length = sum(len(document) for document in documents) / document_count
        document_frequency = Counter(
            token for document in documents for token in set(document)
        )
        query_terms = set(query)
        scores: list[float] = []
        for document in documents:
            frequencies = Counter(document)
            length_normalization = 1 - self.b + self.b * len(document) / average_length
            score = 0.0
            for term in query_terms:
                frequency = frequencies[term]
                if frequency == 0:
                    continue
                frequency_in_documents = document_frequency[term]
                inverse_document_frequency = math.log(
                    1
                    + (document_count - frequency_in_documents + 0.5)
                    / (frequency_in_documents + 0.5)
                )
                score += inverse_document_frequency * (
                    frequency * (self.k1 + 1)
                    / (frequency + self.k1 * length_normalization)
                )
            scores.append(score)
        return scores

