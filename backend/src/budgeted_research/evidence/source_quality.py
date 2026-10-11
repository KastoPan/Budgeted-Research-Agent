from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import HttpUrl

from budgeted_research.domain.models import SourceQuality, SourceQualityTier


class SourceQualityEvaluator:
    """Classifies transparent URL-level source signals without an extra LLM call."""

    _primary_domains = {
        "docs.python.org",
        "peps.python.org",
        "rfc-editor.org",
        "www.rfc-editor.org",
    }
    _community_domains = {
        "dev.to",
        "geeksforgeeks.org",
        "www.geeksforgeeks.org",
        "medium.com",
        "www.medium.com",
    }

    def evaluate(self, url: HttpUrl | str) -> SourceQuality:
        parsed = urlsplit(str(url))
        host = (parsed.hostname or "").casefold()
        path = parsed.path.casefold()

        if host == "example.com" or host.endswith(".example.com"):
            return SourceQuality(
                score=1.0,
                tier=SourceQualityTier.PRIMARY,
                reasons=["reserved synthetic test domain"],
            )
        if host in self._primary_domains:
            return SourceQuality(
                score=1.0,
                tier=SourceQualityTier.PRIMARY,
                reasons=["recognized primary documentation domain"],
            )
        if host.endswith(".gov") or ".gov." in host:
            return SourceQuality(
                score=0.95,
                tier=SourceQualityTier.AUTHORITATIVE,
                reasons=["government domain"],
            )
        if host.endswith(".edu") or ".edu." in host or ".ac." in host:
            return SourceQuality(
                score=0.9,
                tier=SourceQualityTier.AUTHORITATIVE,
                reasons=["academic domain"],
            )
        if host.startswith("docs.") or "/docs/" in path or "/documentation/" in path:
            return SourceQuality(
                score=0.8,
                tier=SourceQualityTier.DOCUMENTATION,
                reasons=["documentation URL pattern"],
            )
        if host in {"github.com", "www.github.com"}:
            return SourceQuality(
                score=0.7,
                tier=SourceQualityTier.DOCUMENTATION,
                reasons=["source repository domain"],
            )
        if host in self._community_domains:
            return SourceQuality(
                score=0.4,
                tier=SourceQualityTier.COMMUNITY,
                reasons=["community-authored publishing domain"],
            )
        return SourceQuality(
            score=0.5,
            tier=SourceQualityTier.UNKNOWN,
            reasons=["no recognized authority signal"],
        )
