from datetime import timezone
from pathlib import Path

from budgeted_research.domain.events import ActionRecord
from budgeted_research.domain.actions import ActionStatus, ActionType
from budgeted_research.domain.models import (
    ResearchReport,
    ResearchRequest,
    RunStatus,
    RunSummary,
)
from budgeted_research.domain.state import ResearchState
from budgeted_research.engine.result import ResearchRunResult
from budgeted_research.storage.database import Database
from budgeted_research.storage.repository import RunRepository
from tests import factories


def test_repository_persists_run_events_evidence_and_report(tmp_path: Path) -> None:
    database = Database.sqlite_file(tmp_path / "research.db")
    database.create_schema()
    repository = RunRepository(database)
    request = ResearchRequest(question="Compare Python list and tuple")
    repository.create_run("run-1", request, "adaptive_budget")
    repository.mark_running("run-1")
    repository.append_event(
        "run-1",
        ActionRecord(
            sequence=1,
            action_id="action-1",
            action_type=ActionType.PLAN,
            policy="adaptive_budget",
            reason="test plan",
            status=ActionStatus.COMPLETED,
        ),
    )

    evidence = [item for items in factories.evidence().values() for item in items]
    report = ResearchReport(
        title="Result",
        markdown="# Result\n\nGrounded answer.",
        citation_ids=[item.id for item in evidence],
    )
    state = ResearchState(
        run_id="run-1",
        request=request,
        status=RunStatus.COMPLETED,
        subquestions=factories.subquestions(),
        sources={item.id: item for item in factories.documents().values()},
        evidence=evidence,
        report=report,
        stop_reason="completed",
    )
    result = ResearchRunResult(
        state=state,
        summary=RunSummary(
            run_id="run-1",
            policy="adaptive_budget",
            status=RunStatus.COMPLETED,
            report=report,
            evidence=evidence,
            total_tokens=123,
            stop_reason="completed",
        ),
    )
    repository.complete_run(result, tmp_path / "runs" / "run-1")

    stored = repository.get_run("run-1")
    assert stored is not None
    assert stored.created_at.utcoffset() == timezone.utc.utcoffset(stored.created_at)
    assert stored.status is RunStatus.COMPLETED
    assert stored.action_count == 1
    assert stored.total_tokens == 123
    assert repository.list_events("run-1")[0].action_id == "action-1"
    assert len(repository.list_evidence("run-1")) == 4
    assert repository.get_report("run-1") == report

    database.dispose()


def test_repository_marks_interrupted_runs_failed(tmp_path: Path) -> None:
    database = Database.sqlite_file(tmp_path / "research.db")
    database.create_schema()
    repository = RunRepository(database)
    request = ResearchRequest(question="Compare Python list and tuple")
    repository.create_run("pending", request, "fixed_depth")
    repository.create_run("running", request, "adaptive_budget")
    repository.mark_running("running")

    assert repository.recover_interrupted_runs() == 2
    assert repository.get_run("pending").status is RunStatus.FAILED  # type: ignore[union-attr]
    assert repository.get_run("running").status is RunStatus.FAILED  # type: ignore[union-attr]

    database.dispose()


def test_repository_only_cancels_active_runs(tmp_path: Path) -> None:
    database = Database.sqlite_file(tmp_path / "research.db")
    database.create_schema()
    repository = RunRepository(database)
    request = ResearchRequest(question="Compare Python list and tuple")
    repository.create_run("run-1", request, "adaptive_budget")

    assert repository.mark_cancelled("run-1") is True
    assert repository.get_run("run-1").status is RunStatus.CANCELLED  # type: ignore[union-attr]
    assert repository.mark_cancelled("run-1") is False

    database.dispose()
