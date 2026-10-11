import asyncio
from pathlib import Path

from budgeted_research.application.run_manager import RunManager
from budgeted_research.domain.actions import ActionStatus, ActionType
from budgeted_research.domain.events import ActionRecord, EventSink
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


class StubRunner:
    async def run(
        self,
        request: ResearchRequest,
        output_root: Path,
        *,
        run_id: str | None = None,
        event_sink: EventSink | None = None,
    ) -> tuple[ResearchRunResult, Path, int]:
        assert run_id is not None
        assert event_sink is not None
        await event_sink.record(
            ActionRecord(
                sequence=1,
                action_id="write-1",
                action_type=ActionType.WRITE_REPORT,
                policy="adaptive_budget",
                reason="test completion",
                status=ActionStatus.COMPLETED,
            )
        )
        report = ResearchReport(title="Result", markdown="# Result")
        state = ResearchState(
            run_id=run_id,
            request=request,
            status=RunStatus.COMPLETED,
            report=report,
            stop_reason="completed",
        )
        result = ResearchRunResult(
            state=state,
            summary=RunSummary(
                run_id=run_id,
                policy="adaptive_budget",
                status=RunStatus.COMPLETED,
                report=report,
                total_tokens=10,
                stop_reason="completed",
            ),
        )
        return result, output_root / run_id, 1


class BlockingRunner:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def run(
        self,
        request: ResearchRequest,
        output_root: Path,
        *,
        run_id: str | None = None,
        event_sink: EventSink | None = None,
    ) -> tuple[ResearchRunResult, Path, int]:
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("cancelled runner unexpectedly resumed")


async def test_run_manager_persists_background_run_without_real_providers(
    tmp_path: Path,
) -> None:
    database = Database.sqlite_file(tmp_path / "manager.db")
    database.create_schema()
    repository = RunRepository(database)
    manager = RunManager(
        repository,
        tmp_path / "runs",
        runner_factory=lambda _policy, _profile: StubRunner(),
    )

    pending = await manager.start(
        ResearchRequest(question="Compare Python list and tuple"),
        "adaptive",
        "smoke",
    )
    await manager.wait(pending.run_id)

    stored = repository.get_run(pending.run_id)
    assert stored is not None
    assert stored.status is RunStatus.COMPLETED
    assert stored.policy == "adaptive_budget"
    assert stored.profile == "smoke"
    assert stored.action_count == 1
    assert stored.total_tokens == 10

    await manager.close()
    database.dispose()


async def test_run_manager_cancels_active_run(tmp_path: Path) -> None:
    database = Database.sqlite_file(tmp_path / "manager.db")
    database.create_schema()
    repository = RunRepository(database)
    runner = BlockingRunner()
    manager = RunManager(
        repository,
        tmp_path / "runs",
        runner_factory=lambda _policy, _profile: runner,
    )

    pending = await manager.start(
        ResearchRequest(question="Compare Python list and tuple"),
        "adaptive",
        "smoke",
    )
    await runner.started.wait()
    cancelled = await manager.cancel(pending.run_id)

    assert cancelled.status is RunStatus.CANCELLED
    assert cancelled.stop_reason == "cancelled by user"

    await manager.close()
    database.dispose()
