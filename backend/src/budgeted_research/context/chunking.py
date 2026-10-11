from __future__ import annotations

import hashlib

from budgeted_research.context.tokenization import token_spans
from budgeted_research.domain.models import DocumentChunk, SourceDocument


class TokenChunker:
    def __init__(self, chunk_size_tokens: int = 800, overlap_tokens: int = 100) -> None:
        if chunk_size_tokens <= 0:
            raise ValueError("chunk_size_tokens must be positive")
        if overlap_tokens < 0 or overlap_tokens >= chunk_size_tokens:
            raise ValueError("overlap_tokens must be non-negative and smaller than chunk size")
        self.chunk_size_tokens = chunk_size_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(self, source: SourceDocument) -> list[DocumentChunk]:
        spans = token_spans(source.content)
        if not spans:
            return []
        chunks: list[DocumentChunk] = []
        step = self.chunk_size_tokens - self.overlap_tokens
        for position, token_start in enumerate(range(0, len(spans), step)):
            token_end = min(token_start + self.chunk_size_tokens, len(spans))
            char_start = spans[token_start][0]
            char_end = spans[token_end - 1][1]
            content = source.content[char_start:char_end]
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            chunks.append(
                DocumentChunk(
                    id=f"chunk_{source.id}_{position:04d}",
                    source_id=source.id,
                    source_url=source.url,
                    source_title=source.title,
                    content=content,
                    position=position,
                    token_count=token_end - token_start,
                    content_hash=content_hash,
                    retrieved_at=source.retrieved_at,
                )
            )
            if token_end == len(spans):
                break
        return chunks

