from __future__ import annotations

from budgeted_research.domain.actions import (
    Action,
    ActionResult,
    ActionType,
    EvidenceExtractionOutput,
)
from budgeted_research.domain.errors import InvalidProviderOutputError
from budgeted_research.domain.models import (
    EvidenceItem,
    ResearchReport,
    SearchResult,
    SourceDocument,
    SubQuestion,
)
from budgeted_research.domain.state import ResearchState
from budgeted_research.evidence.metrics import EvidenceMetricsEvaluator
from budgeted_research.evidence.source_quality import SourceQualityEvaluator
from budgeted_research.reporting.citations import CitationRenderer


class StateReducer:
    def __init__(
        self,
        citation_renderer: CitationRenderer | None = None,
        metrics_evaluator: EvidenceMetricsEvaluator | None = None,
        source_quality_evaluator: SourceQualityEvaluator | None = None,
    ) -> None:
        self.citation_renderer = citation_renderer or CitationRenderer()
        self.metrics_evaluator = metrics_evaluator or EvidenceMetricsEvaluator()
        self.source_quality_evaluator = (
            source_quality_evaluator or SourceQualityEvaluator()
        )

    def apply(
        self, state: ResearchState, action: Action, result: ActionResult
    ) -> ResearchState:
        if action.type is ActionType.PLAN:
            state.subquestions = [SubQuestion.model_validate(item) for item in result.output]
            self._validate_unique_ids([item.id for item in state.subquestions], "subquestion")
            return state

        if action.type is ActionType.SEARCH:
            assert action.target is not None
            existing = state.search_results.get(action.target, [])
            known_urls = {str(item.url) for item in existing}
            additions: list[SearchResult] = []
            for item in result.output:
                candidate = SearchResult.model_validate(item)
                url = str(candidate.url)
                if url in known_urls:
                    continue
                known_urls.add(url)
                additions.append(candidate)
            state.search_results[action.target] = [*existing, *additions]
            state.search_rounds_by_subquestion[action.target] = (
                state.search_rounds_by_subquestion.get(action.target, 0) + 1
            )
            return state

        if action.type is ActionType.FETCH:
            assert action.target is not None
            search_result = SearchResult.model_validate(action.payload["result"])
            state.attempted_urls.setdefault(action.target, []).append(str(search_result.url))
            if result.output is None:
                return state
            source = SourceDocument.model_validate(result.output)
            source = source.model_copy(
                update={
                    "quality": self.source_quality_evaluator.evaluate(source.url)
                }
            )
            existing = next(
                (item for item in state.sources.values() if item.url == source.url), None
            )
            source = existing or source
            colliding_source = state.sources.get(source.id)
            if colliding_source is not None and colliding_source.url != source.url:
                raise InvalidProviderOutputError(
                    f"source ID {source.id} is already assigned to another URL"
                )
            state.sources[source.id] = source
            source_ids = state.source_ids_by_subquestion.setdefault(action.target, [])
            if source.id not in source_ids:
                source_ids.append(source.id)
            return state

        if action.type is ActionType.EXTRACT_EVIDENCE:
            assert action.target is not None
            extraction = EvidenceExtractionOutput.model_validate(result.output)
            state.selected_chunks[action.target] = extraction.selected_chunks
            extracted_source_ids = state.extracted_source_ids_by_subquestion.setdefault(
                action.target, set()
            )
            extracted_source_ids.update(extraction.processed_source_ids)
            items = [EvidenceItem.model_validate(item) for item in extraction.evidence]
            self._validate_evidence(state, action.target, items)
            existing = [
                item for item in state.evidence if item.subquestion_id == action.target
            ]
            accepted, metrics, claim_clusters = self.metrics_evaluator.evaluate(
                existing,
                items,
                state.evidence_metrics.get(action.target),
                extraction.rejected_evidence_count,
            )
            known_ids = {item.id for item in state.evidence}
            duplicates = known_ids.intersection(item.id for item in accepted)
            if duplicates:
                raise InvalidProviderOutputError(
                    f"duplicate global evidence IDs: {sorted(duplicates)}"
                )
            state.evidence.extend(accepted)
            state.extracted_subquestions.add(action.target)
            state.extraction_rounds_by_subquestion[action.target] = (
                state.extraction_rounds_by_subquestion.get(action.target, 0) + 1
            )
            state.source_count_at_last_extraction[action.target] = len(
                extracted_source_ids
            )
            state.evidence_metrics[action.target] = metrics
            state.claim_clusters_by_subquestion[action.target] = claim_clusters
            state.rejection_reasons_by_subquestion.setdefault(
                action.target, []
            ).extend(extraction.rejection_reasons)
            return state

        if action.type is ActionType.WRITE_REPORT:
            report = ResearchReport.model_validate(result.output)
            state.report = self.citation_renderer.render(
                report,
                state.evidence,
                question=state.request.question,
                subquestions=state.subquestions,
            )
            return state

        raise ValueError(f"unsupported action: {action.type}")

    @staticmethod
    def _validate_unique_ids(ids: list[str], label: str) -> None:
        if len(ids) != len(set(ids)):
            raise InvalidProviderOutputError(f"duplicate {label} IDs")

    @staticmethod
    def _validate_evidence(
        state: ResearchState, subquestion_id: str, items: list[EvidenceItem]
    ) -> None:
        StateReducer._validate_unique_ids([item.id for item in items], "evidence")
        allowed_sources = set(state.source_ids_by_subquestion.get(subquestion_id, []))
        for item in items:
            if item.subquestion_id != subquestion_id:
                raise InvalidProviderOutputError(
                    f"evidence {item.id} belongs to another subquestion"
                )
            if item.source_id not in allowed_sources:
                raise InvalidProviderOutputError(
                    f"evidence {item.id} references an unavailable source"
                )
            source = state.sources[item.source_id]
            if item.source_url != source.url:
                raise InvalidProviderOutputError(
                    f"evidence {item.id} source URL does not match source record"
                )
            if item.support_span not in source.content:
                raise InvalidProviderOutputError(
                    f"evidence {item.id} support span is absent from source"
                )
