import httpx
import pytest

from budgeted_research.domain.models import SearchResult
from budgeted_research.providers.fetch.http import HttpPageFetcher


class StaticResolver:
    def __init__(self, *addresses: str) -> None:
        self._addresses = set(addresses)

    async def resolve(self, host: str) -> set[str]:
        return self._addresses


@pytest.mark.asyncio
async def test_fetcher_extracts_readable_html_from_public_page() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(
                "<html><head><title>Research Page</title></head><body><article>"
                "<h1>Budget-aware research</h1>"
                "<p>A research agent should allocate limited resources according "
                "to evidence gaps and stop when marginal information gain is low.</p>"
                "</article></body></html>"
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetcher = HttpPageFetcher(
            client=client,
            resolver=StaticResolver("93.184.216.34"),
        )
        document = await fetcher.fetch(
            SearchResult(
                title="Fallback title",
                url="https://example.com/research",
                rank=1,
            )
        )

    assert document is not None
    assert document.title == "Research Page"
    assert "marginal information gain" in document.content


@pytest.mark.asyncio
async def test_fetcher_rejects_private_network_targets_before_request() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("private URL must not be requested")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetcher = HttpPageFetcher(
            client=client,
            resolver=StaticResolver("127.0.0.1"),
        )
        document = await fetcher.fetch(
            SearchResult(title="Private", url="http://localhost/admin", rank=1)
        )

    assert document is None

