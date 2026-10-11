from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from budgeted_research.domain.events import ActionRecord
from budgeted_research.domain.models import ResearchRequest
from budgeted_research.engine.result import ResearchRunResult


class RunArtifactWriter:
    """Persists one self-contained, human-inspectable research run."""

    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root

    def write(
        self,
        request: ResearchRequest,
        result: ResearchRunResult,
        events: list[ActionRecord],
    ) -> Path:
        run_directory = self.output_root / result.summary.run_id
        run_directory.mkdir(parents=True, exist_ok=False)

        self._write_model(run_directory / "request.json", request)
        self._write_model(run_directory / "state-final.json", result.state)
        self._write_model(run_directory / "summary.json", result.summary)
        self._write_json(
            run_directory / "evidence.json",
            [item.model_dump(mode="json") for item in result.summary.evidence],
        )
        self._write_json(
            run_directory / "metrics.json",
            {
                subquestion_id: metrics.model_dump(mode="json")
                for subquestion_id, metrics in result.state.evidence_metrics.items()
            },
        )
        self._write_json(
            run_directory / "claim-clusters.json",
            {
                subquestion_id: [
                    cluster.model_dump(mode="json") for cluster in clusters
                ]
                for subquestion_id, clusters in (
                    result.state.claim_clusters_by_subquestion.items()
                )
            },
        )
        self._write_json(
            run_directory / "usage.json",
            {
                "total_tokens": result.summary.total_tokens,
                "total_cost_usd": result.summary.total_cost_usd,
                "search_count": result.summary.search_count,
                "page_fetch_count": result.summary.page_fetch_count,
                "elapsed_seconds": result.summary.elapsed_seconds,
            },
        )
        event_lines = "\n".join(event.model_dump_json() for event in events)
        if event_lines:
            event_lines += "\n"
        (run_directory / "events.jsonl").write_text(event_lines, encoding="utf-8")

        if result.summary.report is not None:
            (run_directory / "report.md").write_text(
                result.summary.report.markdown.rstrip() + "\n", encoding="utf-8"
            )
        return run_directory

    @staticmethod
    def _write_model(path: Path, model: BaseModel) -> None:
        path.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _write_json(path: Path, value: object) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
