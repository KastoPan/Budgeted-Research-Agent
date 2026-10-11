from __future__ import annotations

from budgeted_research.domain.actions import (
    Action,
    ActionResult,
    ActionStatus,
    ActionType,
    EvidenceExtractionOutput,
    ResourceEstimate,
)
from budgeted_research.context.bm25 import Bm25ContextSelector
from budgeted_research.domain.errors import InvalidProviderOutputError
from budgeted_research.domain.models import SearchResult, Usage
from budgeted_research.domain.state import ResearchState
from budgeted_research.providers.base import (
    EvidenceExtractor,
    PageFetcher,
    Planner,
    ReportWriter,
    SearchProvider,
)


class ActionExecutor:
    def __init__(
        self,
        planner: Planner,
        search: SearchProvider,
        fetcher: PageFetcher,
        extractor: EvidenceExtractor,
        writer: ReportWriter,
        context_selector: Bm25ContextSelector | None = None,
    ) -> None:
        self.planner = planner
        self.search = search
        self.fetcher = fetcher
        self.extractor = extractor
        self.writer = writer
        self.context_selector = context_selector or Bm25ContextSelector()

    async def execute(self, action: Action, state: ResearchState) -> ActionResult:
        if action.type is ActionType.PLAN:
            output, usage = await self.planner.plan(
                state.request.question, action.payload["count"]
            )
            if len(output) != action.payload["count"]:
                raise InvalidProviderOutputError(
                    f"planner returned {len(output)} subquestions; "
                    f"expected {action.payload['count']}"
                )
            return self._llm_result(action, output, usage)

        if action.type is ActionType.SEARCH:
            output = await self.search.search(
                action.payload["query"], action.payload["max_results"]
            )
            return ActionResult(
                action_id=action.id,
                status=ActionStatus.COMPLETED,
                output=output[: action.payload["max_results"]],
                actual_resources=ResourceEstimate(searches=1),
            )

        if action.type is ActionType.FETCH:
            result = action.payload["result"]
            if not isinstance(result, SearchResult):
                result = SearchResult.model_validate(result)
            existing = next(
                (source for source in state.sources.values() if source.url == result.url),
                None,
            )
            if existing is not None:
                return ActionResult(
                    action_id=action.id,
                    status=ActionStatus.COMPLETED,
                    output=existing,
                    actual_resources=ResourceEstimate(),
                )
            output = await self.fetcher.fetch(result)
            return ActionResult(
                action_id=action.id,
                status=ActionStatus.COMPLETED,
                output=output,
                actual_resources=ResourceEstimate(page_fetches=1),
            )

        if action.type is ActionType.EXTRACT_EVIDENCE:
            subquestion = next(
                item for item in state.subquestions if item.id == action.target
            )
            source_ids = state.source_ids_by_subquestion.get(subquestion.id, [])
            extracted_source_ids = state.extracted_source_ids_by_subquestion.get(
                subquestion.id, set()
            )
            pending_source_ids = [
                source_id
                for source_id in source_ids
                if source_id not in extracted_source_ids
            ]
            active_source_ids = pending_source_ids or source_ids
            sources = [state.sources[source_id] for source_id in active_source_ids]
            chunks = self.context_selector.select(
                subquestion,
                sources,
                limit=action.payload["selected_chunks"],
            )
            evidence, usage = await self.extractor.extract(
                subquestion, chunks, action.payload["max_items"]
            )
            valid_evidence = []
            rejection_reasons: list[str] = []
            allowed_source_ids = {chunk.source_id for chunk in chunks}
            for item in evidence:
                source = state.sources.get(item.source_id)
                if source is None or item.source_id not in allowed_source_ids:
                    rejection_reasons.append(
                        f"{item.id}: unavailable source {item.source_id}"
                    )
                    continue
                if item.source_url != source.url:
                    rejection_reasons.append(f"{item.id}: source URL mismatch")
                    continue
                if item.support_span not in source.content:
                    rejection_reasons.append(
                        f"{item.id}: support span is absent from source"
                    )
                    continue
                item = item.model_copy(
                    update={
                        "source_title": source.title,
                        "retrieved_at": source.retrieved_at,
                        "source_quality": source.quality,
                    }
                )
                valid_evidence.append(item)
            known_ids = {item.id for item in state.evidence}
            next_index = len(
                [
                    item
                    for item in state.evidence
                    if item.subquestion_id == subquestion.id
                ]
            ) + 1
            normalized_evidence = []
            for item in valid_evidence:
                if item.id in known_ids:
                    while f"ev_{subquestion.id}_{next_index:02d}" in known_ids:
                        next_index += 1
                    item = item.model_copy(
                        update={"id": f"ev_{subquestion.id}_{next_index:02d}"}
                    )
                    next_index += 1
                known_ids.add(item.id)
                normalized_evidence.append(item)
            output = EvidenceExtractionOutput(
                selected_chunks=chunks,
                processed_source_ids=active_source_ids,
                evidence=normalized_evidence,
                rejected_evidence_count=len(rejection_reasons),
                rejection_reasons=rejection_reasons,
            )
            return self._llm_result(action, output, usage)

        if action.type is ActionType.WRITE_REPORT:
            output, usage = await self.writer.write(
                state.request.question, state.subquestions, state.evidence
            )
            return self._llm_result(action, output, usage)

        raise ValueError(f"unsupported action: {action.type}")

    @staticmethod
    def _llm_result(action: Action, output: object, usage: Usage) -> ActionResult:
        return ActionResult(
            action_id=action.id,
            status=ActionStatus.COMPLETED,
            output=output,
            usage=usage,
            actual_resources=ResourceEstimate(
                tokens=usage.total_tokens,
                cost_usd=usage.cost_usd,
            ),
        )
