from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import httpx

from budgeted_research.domain.errors import InvalidProviderOutputError
from budgeted_research.domain.models import SearchResult


class TavilySearchProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.tavily.com",
        timeout_seconds: float = 20.0,
        max_retries: int = 1,
        retry_delay_seconds: float = 0.5,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be non-negative")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_delay_seconds = retry_delay_seconds
        self._client = client

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        if not 1 <= max_results <= 20:
            raise ValueError("max_results must be between 1 and 20")
        response = await self._post(
            "/search",
            {
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                "topic": "general",
                "include_answer": False,
                "include_raw_content": False,
                "include_images": False,
                "include_usage": True,
            },
        )
        payload = response.json()
        if not isinstance(payload, Mapping) or not isinstance(payload.get("results"), list):
            raise InvalidProviderOutputError("Tavily response is missing results")

        request_id = _optional_string(payload.get("request_id"))
        usage = payload.get("usage") if isinstance(payload.get("usage"), Mapping) else {}
        normalized_usage = {
            str(key): value
            for key, value in usage.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        results: list[SearchResult] = []
        for rank, item in enumerate(payload["results"], start=1):
            if not isinstance(item, Mapping):
                raise InvalidProviderOutputError("Tavily result must be an object")
            try:
                results.append(
                    SearchResult(
                        title=str(item["title"]),
                        url=str(item["url"]),
                        snippet=str(item.get("content") or ""),
                        rank=rank,
                        score=_optional_float(item.get("score")),
                        published_at=_optional_string(item.get("published_date")),
                        provider="tavily",
                        provider_request_id=request_id,
                        provider_usage=normalized_usage,
                    )
                )
            except (KeyError, ValueError) as error:
                raise InvalidProviderOutputError(
                    f"invalid Tavily result at rank {rank}: {error}"
                ) from error
        return results

    async def _post(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        for attempt in range(self._max_retries + 1):
            try:
                if self._client is not None:
                    response = await self._client.post(
                        self._base_url + path,
                        headers=headers,
                        json=payload,
                        timeout=self._timeout_seconds,
                    )
                else:
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            self._base_url + path,
                            headers=headers,
                            json=payload,
                            timeout=self._timeout_seconds,
                        )
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as error:
                status_code = error.response.status_code
                if (
                    attempt >= self._max_retries
                    or (status_code not in {408, 429} and status_code < 500)
                ):
                    raise
            except httpx.TransportError:
                if attempt >= self._max_retries:
                    raise
            if self._retry_delay_seconds > 0:
                await asyncio.sleep(self._retry_delay_seconds * (attempt + 1))
        raise RuntimeError("unreachable Tavily retry state")


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None
