from __future__ import annotations

from pathlib import Path

from pydantic import Field

from budgeted_research.config import ProviderSettings
from budgeted_research.context.bm25 import Bm25ContextSelector
from budgeted_research.domain.models import DocumentChunk, DomainModel, EvidenceItem, Usage
from budgeted_research.domain.state import ResearchState
from budgeted_research.engine.reducer import StateReducer
from budgeted_research.policies.fixed_depth import FixedDepthConfig
from budgeted_research.providers.llm.moonshot import (
    MoonshotChatClient,
    MoonshotEvidenceExtractor,
)


class ExtractionCheckResult(DomainModel):
    run_id: str
    subquestion_id: str
    selected_chunks: list[DocumentChunk] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)


class ExtractionCheckService:
    """Retry one extraction from persisted sources without new search or fetch calls."""

    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings

    async def check(
        self, run_directory: Path, subquestion_id: str
    ) -> tuple[ExtractionCheckResult, Path]:
        state_path = run_directory / "state-final.json"
        if not state_path.is_file():
            raise ValueError(f"state artifact does not exist: {state_path}")
        state = ResearchState.model_validate_json(state_path.read_text(encoding="utf-8"))
        subquestion = next(
            (item for item in state.subquestions if item.id == subquestion_id), None
        )
        if subquestion is None:
            known = ", ".join(item.id for item in state.subquestions) or "none"
            raise ValueError(
                f"unknown subquestion {subquestion_id}; available IDs: {known}"
            )

        source_ids = state.source_ids_by_subquestion.get(subquestion_id, [])
        sources = [state.sources[source_id] for source_id in source_ids]
        if not sources:
            raise ValueError(f"no persisted sources for {subquestion_id}")

        config = FixedDepthConfig()
        chunks = Bm25ContextSelector().select(
            subquestion,
            sources,
            limit=config.selected_chunks_per_subquestion,
        )
        moonshot_api_key, moonshot_model = self.settings.require_moonshot()
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
        try:
            evidence, usage = await MoonshotEvidenceExtractor(llm).extract(
                subquestion,
                chunks,
                config.max_evidence_per_subquestion,
            )
        finally:
            await llm.aclose()

        result = ExtractionCheckResult(
            run_id=state.run_id,
            subquestion_id=subquestion_id,
            selected_chunks=chunks,
            evidence=evidence,
            usage=usage,
        )
        candidate_path = (
            run_directory / f"extraction-check-{subquestion_id}-candidate.json"
        )
        candidate_path.write_text(
            result.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        # Keep the candidate artifact for diagnosis even when grounding validation fails.
        StateReducer._validate_evidence(state, subquestion_id, evidence)
        output_path = run_directory / f"extraction-check-{subquestion_id}.json"
        output_path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return result, output_path
