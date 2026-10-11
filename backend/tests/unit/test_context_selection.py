from budgeted_research.context.bm25 import Bm25ContextSelector
from budgeted_research.context.chunking import TokenChunker
from budgeted_research.domain.models import SourceDocument, SubQuestion


def test_chunker_preserves_original_text_and_token_overlap() -> None:
    source = SourceDocument(
        id="src_01",
        url="https://example.com/source",
        title="Source",
        content="alpha beta gamma delta epsilon zeta",
    )
    chunker = TokenChunker(chunk_size_tokens=4, overlap_tokens=2)

    chunks = chunker.chunk(source)

    assert [chunk.content for chunk in chunks] == [
        "alpha beta gamma delta",
        "gamma delta epsilon zeta",
    ]
    assert [chunk.token_count for chunk in chunks] == [4, 4]


def test_bm25_prioritizes_relevant_chunks_and_removes_duplicate_content() -> None:
    relevant = SourceDocument(
        id="src_relevant",
        url="https://example.com/relevant",
        title="Relevant",
        content="Evidence coverage and budget allocation guide research decisions.",
    )
    duplicate = SourceDocument(
        id="src_duplicate",
        url="https://example.com/duplicate",
        title="Duplicate",
        content=relevant.content,
    )
    unrelated = SourceDocument(
        id="src_unrelated",
        url="https://example.com/unrelated",
        title="Unrelated",
        content="Frontend colors and typography define the visual interface.",
    )
    subquestion = SubQuestion(
        id="sq_01",
        question="How should evidence coverage guide budget allocation?",
        search_query="evidence coverage budget allocation",
        rationale="test",
    )
    selector = Bm25ContextSelector(
        TokenChunker(chunk_size_tokens=20, overlap_tokens=0)
    )

    selected = selector.select(
        subquestion,
        [unrelated, duplicate, relevant],
        limit=3,
    )

    assert len(selected) == 2
    assert selected[0].source_id == "src_duplicate"
    assert selected[0].relevance_score > selected[1].relevance_score
    assert len({chunk.content_hash for chunk in selected}) == 2
