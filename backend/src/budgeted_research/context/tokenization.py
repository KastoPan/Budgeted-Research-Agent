from __future__ import annotations

import re

_TOKEN_PATTERN = re.compile(r"[\u3400-\u9fff]|[A-Za-z0-9_]+|[^\s]", re.UNICODE)


def token_spans(text: str) -> list[tuple[int, int]]:
    """Return deterministic approximate-token character spans.

    This tokenizer intentionally serves context sizing and BM25 only. Provider
    usage remains the authority for billable model tokens.
    """

    return [(match.start(), match.end()) for match in _TOKEN_PATTERN.finditer(text)]


def tokenize(text: str) -> list[str]:
    return [text[start:end].casefold() for start, end in token_spans(text)]

