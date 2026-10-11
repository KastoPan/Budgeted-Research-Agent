import httpx
import pytest

from budgeted_research.providers.search.tavily import TavilySearchProvider


@pytest.mark.asyncio
async def test_tavily_response_is_mapped_to_domain_results() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Official documentation",
                        "url": "https://example.com/docs",
                        "content": "Relevant search snippet",
                        "score": 0.91,
                        "published_date": "Sun, 28 Sep 2026 00:00:00 GMT",
                    }
                ],
                "usage": {"credits": 1},
                "request_id": "request-123",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = TavilySearchProvider(api_key="test-key", client=client)
        results = await provider.search("budget-aware research", max_results=5)

    assert len(results) == 1
    assert results[0].rank == 1
    assert results[0].provider == "tavily"
    assert results[0].provider_request_id == "request-123"
    assert results[0].provider_usage == {"credits": 1}
    assert results[0].snippet == "Relevant search snippet"


@pytest.mark.asyncio
async def test_tavily_retries_one_transient_transport_error() -> None:
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("temporary disconnect", request=request)
        return httpx.Response(200, json={"results": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = TavilySearchProvider(
            api_key="test-key",
            client=client,
            max_retries=1,
            retry_delay_seconds=0,
        )
        results = await provider.search("budget-aware research", max_results=5)

    assert results == []
    assert call_count == 2


@pytest.mark.asyncio
async def test_tavily_does_not_retry_non_retryable_client_error() -> None:
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(400, json={"error": "invalid request"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = TavilySearchProvider(
            api_key="test-key",
            client=client,
            max_retries=1,
            retry_delay_seconds=0,
        )
        with pytest.raises(httpx.HTTPStatusError):
            await provider.search("budget-aware research", max_results=5)

    assert call_count == 1
