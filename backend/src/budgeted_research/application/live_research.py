from __future__ import annotations

from pathlib import Path

import httpx

from budgeted_research.config import ProviderSettings
from budgeted_research.domain.events import (
    CompositeEventSink,
    EventSink,
    InMemoryEventSink,
)
from budgeted_research.domain.models import ResearchRequest
from budgeted_research.engine.executor import ActionExecutor
from budgeted_research.engine.research_engine import ResearchEngine
from budgeted_research.engine.result import ResearchRunResult
from budgeted_research.policies.base import ResearchPolicy
from budgeted_research.policies.fixed_depth import FixedDepthConfig, FixedDepthPolicy
from budgeted_research.providers.fetch.http import HttpPageFetcher
from budgeted_research.providers.llm.moonshot import (
    MoonshotChatClient,
    MoonshotEvidenceExtractor,
    MoonshotPlanner,
    MoonshotReportWriter,
)
from budgeted_research.providers.search.tavily import TavilySearchProvider
from budgeted_research.storage.artifacts import RunArtifactWriter


class LiveResearchService:
    def __init__(
        self,
        settings: ProviderSettings,
        policy_config: FixedDepthConfig | None = None,
        policy: ResearchPolicy | None = None,
    ) -> None:
        if policy_config is not None and policy is not None:
            raise ValueError("policy_config and policy cannot both be provided")
        self.settings = settings
        self.policy = policy or FixedDepthPolicy(policy_config)

    async def run(
        self,
        request: ResearchRequest,
        output_root: Path,
        *,
        run_id: str | None = None,
        event_sink: EventSink | None = None,
    ) -> tuple[ResearchRunResult, Path, int]:
        moonshot_api_key, moonshot_model = self.settings.require_moonshot()
        tavily_api_key = self.settings.require_tavily_key()
        llm = MoonshotChatClient(
            api_key=moonshot_api_key,
            model=moonshot_model,
            base_url=self.settings.moonshot_base_url,
            timeout_seconds=self.settings.moonshot_timeout_seconds,
            default_temperature=self.settings.moonshot_temperature,
            thinking_enabled=self.settings.moonshot_thinking_enabled,
            input_cost_per_million=(
                self.settings.moonshot_input_cost_per_million_usd or 0.0
            ),
            output_cost_per_million=(
                self.settings.moonshot_output_cost_per_million_usd or 0.0
            ),
            max_retries=self.settings.provider_max_retries,
        )
        memory_sink = InMemoryEventSink()
        sink: EventSink = (
            CompositeEventSink(event_sink, memory_sink)
            if event_sink is not None
            else memory_sink
        )
        timeout = httpx.Timeout(self.settings.request_timeout_seconds)
        limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
        try:
            async with httpx.AsyncClient(timeout=timeout, limits=limits) as http_client:
                engine = ResearchEngine(
                    policy=self.policy,
                    executor=ActionExecutor(
                        planner=MoonshotPlanner(
                            llm,
                            max_schema_retries=self.settings.provider_max_retries,
                        ),
                        search=TavilySearchProvider(
                            api_key=tavily_api_key,
                            base_url=self.settings.tavily_base_url,
                            timeout_seconds=self.settings.request_timeout_seconds,
                            max_retries=self.settings.provider_max_retries,
                            retry_delay_seconds=(
                                self.settings.provider_retry_delay_seconds
                            ),
                            client=http_client,
                        ),
                        fetcher=HttpPageFetcher(
                            timeout_seconds=self.settings.request_timeout_seconds,
                            client=http_client,
                        ),
                        extractor=MoonshotEvidenceExtractor(llm),
                        writer=MoonshotReportWriter(llm),
                    ),
                    event_sink=sink,
                )
                result = await engine.run_detailed(request, run_id=run_id)
        finally:
            await llm.aclose()

        artifact_directory = RunArtifactWriter(output_root).write(
            request, result, memory_sink.events
        )
        return result, artifact_directory, len(memory_sink.events)
