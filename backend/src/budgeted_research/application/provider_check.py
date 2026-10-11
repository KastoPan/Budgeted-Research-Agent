from __future__ import annotations

from dataclasses import dataclass

import httpx

from budgeted_research.config import ProviderSettings
from budgeted_research.providers.llm.moonshot import MoonshotChatClient
from budgeted_research.providers.search.tavily import TavilySearchProvider


@dataclass(frozen=True, slots=True)
class ProviderCheckResult:
    model: str
    llm_json_mode: bool
    llm_tokens: int
    tavily_result_count: int
    tavily_request_id: str | None
    tavily_credits: int | float | None


class ProviderCheckService:
    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings

    async def check(self) -> ProviderCheckResult:
        moonshot_api_key, moonshot_model = self.settings.require_moonshot()
        tavily_api_key = self.settings.require_tavily_key()
        llm = MoonshotChatClient(
            api_key=moonshot_api_key,
            model=moonshot_model,
            base_url=self.settings.moonshot_base_url,
            timeout_seconds=self.settings.moonshot_timeout_seconds,
            max_completion_tokens=128,
            default_temperature=self.settings.moonshot_temperature,
            thinking_enabled=self.settings.moonshot_thinking_enabled,
            max_retries=self.settings.provider_max_retries,
        )
        try:
            payload, usage = await llm.generate_json(
                "Return only a JSON object.",
                'Return exactly this object: {"status":"ok"}',
            )
        finally:
            await llm.aclose()

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.request_timeout_seconds)
        ) as http_client:
            results = await TavilySearchProvider(
                api_key=tavily_api_key,
                base_url=self.settings.tavily_base_url,
                timeout_seconds=self.settings.request_timeout_seconds,
                max_retries=self.settings.provider_max_retries,
                retry_delay_seconds=self.settings.provider_retry_delay_seconds,
                client=http_client,
            ).search("Python official documentation", max_results=1)

        request_id = results[0].provider_request_id if results else None
        credits = results[0].provider_usage.get("credits") if results else None
        return ProviderCheckResult(
            model=moonshot_model,
            llm_json_mode=payload == {"status": "ok"},
            llm_tokens=usage.total_tokens,
            tavily_result_count=len(results),
            tavily_request_id=request_id,
            tavily_credits=credits,
        )
