from __future__ import annotations

import asyncio
import hashlib
import html
import ipaddress
import re
import socket
from typing import Protocol

import httpx
import trafilatura

from budgeted_research.domain.models import SearchResult, SourceDocument


class HostResolver(Protocol):
    async def resolve(self, host: str) -> set[str]: ...


class SocketHostResolver:
    async def resolve(self, host: str) -> set[str]:
        records = await asyncio.to_thread(
            socket.getaddrinfo, host, None, type=socket.SOCK_STREAM
        )
        return {record[4][0] for record in records}


class HttpPageFetcher:
    _title_pattern = re.compile(
        r"<title[^>]*>(?P<title>.*?)</title>", re.IGNORECASE | re.DOTALL
    )

    def __init__(
        self,
        timeout_seconds: float = 20.0,
        max_response_bytes: int = 5_000_000,
        max_redirects: int = 3,
        user_agent: str = "BudgetedResearchAgent/0.1",
        client: httpx.AsyncClient | None = None,
        resolver: HostResolver | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._max_redirects = max_redirects
        self._user_agent = user_agent
        self._client = client
        self._resolver = resolver or SocketHostResolver()

    async def fetch(self, result: SearchResult) -> SourceDocument | None:
        try:
            if self._client is not None:
                return await self._fetch_with_client(self._client, result)
            async with httpx.AsyncClient() as client:
                return await self._fetch_with_client(client, result)
        except (httpx.HTTPError, OSError, UnicodeError, ValueError):
            return None

    async def _fetch_with_client(
        self, client: httpx.AsyncClient, result: SearchResult
    ) -> SourceDocument | None:
        url = str(result.url)
        for _ in range(self._max_redirects + 1):
            if not await self._is_public_http_url(url):
                return None
            async with client.stream(
                "GET",
                url,
                headers={"User-Agent": self._user_agent, "Accept": "text/html"},
                timeout=self._timeout_seconds,
                follow_redirects=False,
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        return None
                    url = str(response.url.join(location))
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                    return None
                declared_length = response.headers.get("content-length")
                if declared_length and int(declared_length) > self._max_response_bytes:
                    return None
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > self._max_response_bytes:
                        return None
                encoding = response.encoding or "utf-8"
                raw_html = body.decode(encoding, errors="replace")
                content = await asyncio.to_thread(
                    trafilatura.extract,
                    raw_html,
                    include_comments=False,
                    include_tables=True,
                )
                if not content or not content.strip():
                    return None
                title = self._extract_title(raw_html) or result.title
                source_id = "src_" + hashlib.sha256(url.encode()).hexdigest()[:16]
                return SourceDocument(
                    id=source_id,
                    url=url,
                    title=title,
                    content=content.strip(),
                )
        return None

    async def _is_public_http_url(self, url: str) -> bool:
        parsed = httpx.URL(url)
        if parsed.scheme not in {"http", "https"} or not parsed.host:
            return False
        if parsed.username or parsed.password:
            return False
        try:
            addresses = await self._resolver.resolve(parsed.host)
        except socket.gaierror:
            return False
        if not addresses:
            return False
        return all(self._is_public_address(address) for address in addresses)

    @staticmethod
    def _is_public_address(value: str) -> bool:
        address = ipaddress.ip_address(value)
        return not (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        )

    @classmethod
    def _extract_title(cls, raw_html: str) -> str | None:
        match = cls._title_pattern.search(raw_html)
        if match is None:
            return None
        title = re.sub(r"\s+", " ", html.unescape(match.group("title"))).strip()
        return title or None
