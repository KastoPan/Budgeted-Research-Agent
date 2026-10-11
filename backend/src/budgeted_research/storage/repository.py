from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, func, select, update

from budgeted_research.domain.events import ActionRecord
from budgeted_research.domain.models import (
    EvidenceItem,
    ResearchReport,
    ResearchRequest,
    RunStatus,
)
from budgeted_research.engine.result import ResearchRunResult
from budgeted_research.storage.database import (
    ActionEventRow,
    Database,
    DocumentChunkRow,
    EvidenceRow,
    ReportRow,
    RunRow,
    SourceRow,
    SubquestionRow,
    UsageRecordRow,
)
from budgeted_research.storage.records import StoredRun


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunRepository:
    """Synchronous persistence boundary; async callers run methods in a worker thread."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create_run(
        self,
        run_id: str,
        request: ResearchRequest,
        policy: str,
        profile: str = "standard",
    ) -> StoredRun:
        now = _utc_now()
        with self.database.session_factory.begin() as session:
            row = RunRow(
                id=run_id,
                question=request.question,
                policy=policy,
                profile=profile,
                status=RunStatus.PENDING.value,
                request_json=request.model_dump(mode="json"),
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        stored = self.get_run(run_id)
        if stored is None:  # defensive guard around the just-committed insert
            raise RuntimeError(f"failed to load newly created run: {run_id}")
        return stored

    def mark_running(self, run_id: str) -> None:
        self._set_status(run_id, RunStatus.RUNNING)

    def mark_failed(self, run_id: str, reason: str) -> None:
        now = _utc_now()
        with self.database.session_factory.begin() as session:
            session.execute(
                update(RunRow)
                .where(RunRow.id == run_id)
                .values(
                    status=RunStatus.FAILED.value,
                    stop_reason=reason,
                    updated_at=now,
                )
            )

    def mark_cancelled(self, run_id: str, reason: str = "cancelled by user") -> bool:
        """Mark active work cancelled without overwriting an already terminal run."""
        now = _utc_now()
        with self.database.session_factory.begin() as session:
            row = session.get(RunRow, run_id)
            if row is None or row.status not in {
                RunStatus.PENDING.value,
                RunStatus.RUNNING.value,
            }:
                return False
            payloads = session.scalars(
                select(ActionEventRow.payload_json).where(
                    ActionEventRow.run_id == run_id
                )
            ).all()
            usage = _sum_actual_resources(payloads)
            created_at = row.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            row.status = RunStatus.CANCELLED.value
            row.stop_reason = reason
            row.total_tokens = int(usage["tokens"])
            row.total_cost_usd = float(usage["cost_usd"])
            row.search_count = int(usage["searches"])
            row.page_fetch_count = int(usage["page_fetches"])
            row.elapsed_seconds = max(0.0, (now - created_at).total_seconds())
            row.updated_at = now
            return True

    def recover_interrupted_runs(self) -> int:
        """Make stale in-process work explicit after an API process restart."""
        now = _utc_now()
        with self.database.session_factory.begin() as session:
            result = session.execute(
                update(RunRow)
                .where(
                    RunRow.status.in_(
                        [RunStatus.PENDING.value, RunStatus.RUNNING.value]
                    )
                )
                .values(
                    status=RunStatus.FAILED.value,
                    stop_reason="API process restarted before the run completed",
                    updated_at=now,
                )
            )
            return int(result.rowcount or 0)

    def append_event(self, run_id: str, event: ActionRecord) -> None:
        with self.database.session_factory.begin() as session:
            session.add(
                ActionEventRow(
                    run_id=run_id,
                    sequence=event.sequence,
                    payload_json=event.model_dump(mode="json"),
                    occurred_at=event.occurred_at,
                )
            )

    def complete_run(
        self,
        result: ResearchRunResult,
        artifact_directory: Path,
    ) -> None:
        state = result.state
        summary = result.summary
        now = _utc_now()
        with self.database.session_factory.begin() as session:
            row = session.get(RunRow, summary.run_id)
            if row is None:
                raise KeyError(f"unknown run: {summary.run_id}")
            row.status = summary.status.value
            row.state_json = state.model_dump(mode="json")
            row.summary_json = summary.model_dump(mode="json")
            row.stop_reason = summary.stop_reason
            row.artifact_directory = str(artifact_directory.resolve())
            row.total_tokens = summary.total_tokens
            row.total_cost_usd = summary.total_cost_usd
            row.search_count = summary.search_count
            row.page_fetch_count = summary.page_fetch_count
            row.elapsed_seconds = summary.elapsed_seconds
            row.updated_at = now

            self._replace_final_children(session, result)

    def get_run(self, run_id: str) -> StoredRun | None:
        with self.database.session_factory() as session:
            row = session.get(RunRow, run_id)
            if row is None:
                return None
            action_count = session.scalar(
                select(func.count(ActionEventRow.id)).where(
                    ActionEventRow.run_id == run_id
                )
            )
            return self._stored_run(row, int(action_count or 0))

    def list_runs(self, *, limit: int = 50, offset: int = 0) -> list[StoredRun]:
        with self.database.session_factory() as session:
            rows = session.scalars(
                select(RunRow)
                .order_by(RunRow.created_at.desc())
                .limit(limit)
                .offset(offset)
            ).all()
            counts = (
                dict(
                    session.execute(
                        select(ActionEventRow.run_id, func.count(ActionEventRow.id))
                        .where(ActionEventRow.run_id.in_([row.id for row in rows]))
                        .group_by(ActionEventRow.run_id)
                    ).all()
                )
                if rows
                else {}
            )
            return [self._stored_run(row, int(counts.get(row.id, 0))) for row in rows]

    def list_events(self, run_id: str, *, after: int = 0) -> list[ActionRecord]:
        with self.database.session_factory() as session:
            payloads = session.scalars(
                select(ActionEventRow.payload_json)
                .where(
                    ActionEventRow.run_id == run_id,
                    ActionEventRow.sequence > after,
                )
                .order_by(ActionEventRow.sequence)
            ).all()
            return [ActionRecord.model_validate(payload) for payload in payloads]

    def list_evidence(self, run_id: str) -> list[EvidenceItem]:
        with self.database.session_factory() as session:
            payloads = session.scalars(
                select(EvidenceRow.payload_json)
                .where(EvidenceRow.run_id == run_id)
                .order_by(EvidenceRow.subquestion_id, EvidenceRow.id)
            ).all()
            return [EvidenceItem.model_validate(payload) for payload in payloads]

    def get_report(self, run_id: str) -> ResearchReport | None:
        with self.database.session_factory() as session:
            row = session.get(ReportRow, run_id)
            return (
                ResearchReport.model_validate(row.payload_json)
                if row is not None
                else None
            )

    def _set_status(self, run_id: str, status: RunStatus) -> None:
        with self.database.session_factory.begin() as session:
            session.execute(
                update(RunRow)
                .where(RunRow.id == run_id)
                .values(status=status.value, updated_at=_utc_now())
            )

    @staticmethod
    def _stored_run(row: RunRow, action_count: int) -> StoredRun:
        return StoredRun(
            run_id=row.id,
            question=row.question,
            policy=row.policy,
            profile=row.profile,
            status=RunStatus(row.status),
            request=ResearchRequest.model_validate(row.request_json),
            stop_reason=row.stop_reason,
            artifact_directory=row.artifact_directory,
            total_tokens=row.total_tokens,
            total_cost_usd=row.total_cost_usd,
            search_count=row.search_count,
            page_fetch_count=row.page_fetch_count,
            elapsed_seconds=row.elapsed_seconds,
            action_count=action_count,
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
        )

    @staticmethod
    def _replace_final_children(session, result: ResearchRunResult) -> None:
        run_id = result.summary.run_id
        for model in (
            SubquestionRow,
            SourceRow,
            DocumentChunkRow,
            EvidenceRow,
            ReportRow,
            UsageRecordRow,
        ):
            session.execute(delete(model).where(model.run_id == run_id))

        session.add_all(
            SubquestionRow(
                run_id=run_id,
                id=item.id,
                payload_json=item.model_dump(mode="json"),
            )
            for item in result.state.subquestions
        )
        session.add_all(
            SourceRow(
                run_id=run_id,
                id=item.id,
                payload_json=item.model_dump(mode="json"),
            )
            for item in result.state.sources.values()
        )
        chunks = {
            item.id: item
            for selected in result.state.selected_chunks.values()
            for item in selected
        }
        session.add_all(
            DocumentChunkRow(
                run_id=run_id,
                id=item.id,
                source_id=item.source_id,
                payload_json=item.model_dump(mode="json"),
            )
            for item in chunks.values()
        )
        session.add_all(
            EvidenceRow(
                run_id=run_id,
                id=item.id,
                subquestion_id=item.subquestion_id,
                source_id=item.source_id,
                payload_json=item.model_dump(mode="json"),
            )
            for item in result.summary.evidence
        )
        if result.summary.report is not None:
            session.add(
                ReportRow(
                    run_id=run_id,
                    markdown=result.summary.report.markdown,
                    payload_json=result.summary.report.model_dump(mode="json"),
                )
            )
        session.add(
            UsageRecordRow(
                run_id=run_id,
                payload_json={
                    "total_tokens": result.summary.total_tokens,
                    "total_cost_usd": result.summary.total_cost_usd,
                    "search_count": result.summary.search_count,
                    "page_fetch_count": result.summary.page_fetch_count,
                    "elapsed_seconds": result.summary.elapsed_seconds,
                },
            )
        )


def _sum_actual_resources(payloads: list[dict]) -> dict[str, float]:
    totals = {
        "tokens": 0.0,
        "cost_usd": 0.0,
        "searches": 0.0,
        "page_fetches": 0.0,
    }
    for payload in payloads:
        actual = payload.get("actual_resources", {})
        for key in totals:
            totals[key] += float(actual.get(key, 0) or 0)
    return totals


def _as_utc(value: datetime) -> datetime:
    """SQLite drops timezone metadata even for timezone-aware columns."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
