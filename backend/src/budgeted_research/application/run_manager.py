from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from budgeted_research.application.live_research import LiveResearchService
from budgeted_research.application.policy_factory import (
    PolicyProfile,
    build_research_policy,
    normalize_policy_name,
)
from budgeted_research.config import ProviderSettings
from budgeted_research.domain.events import EventSink
from budgeted_research.domain.models import ResearchRequest, RunStatus
from budgeted_research.engine.result import ResearchRunResult
from budgeted_research.storage.events import PersistentEventSink
from budgeted_research.storage.records import StoredRun
from budgeted_research.storage.repository import RunRepository


class ResearchRunner(Protocol):
    async def run(
        self,
        request: ResearchRequest,
        output_root: Path,
        *,
        run_id: str | None = None,
        event_sink: EventSink | None = None,
    ) -> tuple[ResearchRunResult, Path, int]: ...


RunnerFactory = Callable[[str, PolicyProfile], ResearchRunner]


class RunManager:
    """Owns in-process background runs while SQLite remains the source of truth."""

    def __init__(
        self,
        repository: RunRepository,
        output_root: Path,
        runner_factory: RunnerFactory | None = None,
    ) -> None:
        self.repository = repository
        self.output_root = output_root
        self.runner_factory = runner_factory or self._default_runner_factory()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._cancel_reasons: dict[str, str] = {}

    async def start(
        self,
        request: ResearchRequest,
        policy: str,
        profile: PolicyProfile = "standard",
    ) -> StoredRun:
        normalized_policy = normalize_policy_name(policy)
        run_id = str(uuid4())
        stored = await asyncio.to_thread(
            self.repository.create_run,
            run_id,
            request,
            normalized_policy,
            profile,
        )
        task = asyncio.create_task(
            self._execute(run_id, request, normalized_policy, profile),
            name=f"research-run-{run_id}",
        )
        self._tasks[run_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run_id, None))
        return stored

    async def wait(self, run_id: str) -> None:
        task = self._tasks.get(run_id)
        if task is not None:
            await task

    async def cancel(self, run_id: str) -> StoredRun:
        stored = await asyncio.to_thread(self.repository.get_run, run_id)
        if stored is None:
            raise KeyError(run_id)
        if stored.status not in {RunStatus.PENDING, RunStatus.RUNNING}:
            raise RuntimeError(f"run is already terminal: {stored.status.value}")

        task = self._tasks.get(run_id)
        if task is None:
            await asyncio.to_thread(
                self.repository.mark_cancelled,
                run_id,
                "cancelled by user",
            )
        else:
            self._cancel_reasons[run_id] = "cancelled by user"
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            # A task cancelled before its coroutine starts never reaches
            # _execute's cancellation handler, so persist the terminal state here too.
            await asyncio.to_thread(
                self.repository.mark_cancelled,
                run_id,
                "cancelled by user",
            )
            self._cancel_reasons.pop(run_id, None)

        cancelled = await asyncio.to_thread(self.repository.get_run, run_id)
        if cancelled is None:
            raise KeyError(run_id)
        return cancelled

    async def close(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute(
        self,
        run_id: str,
        request: ResearchRequest,
        policy: str,
        profile: PolicyProfile,
    ) -> None:
        await asyncio.to_thread(self.repository.mark_running, run_id)
        try:
            runner = self.runner_factory(policy, profile)
            result, artifact_directory, _ = await runner.run(
                request,
                self.output_root,
                run_id=run_id,
                event_sink=PersistentEventSink(run_id, self.repository),
            )
            await asyncio.to_thread(
                self.repository.complete_run,
                result,
                artifact_directory,
            )
        except asyncio.CancelledError:
            reason = self._cancel_reasons.pop(run_id, None)
            if reason is None:
                await asyncio.to_thread(
                    self.repository.mark_failed,
                    run_id,
                    "API process stopped before the run completed",
                )
            else:
                await asyncio.to_thread(
                    self.repository.mark_cancelled,
                    run_id,
                    reason,
                )
            raise
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"
            await asyncio.to_thread(self.repository.mark_failed, run_id, reason)

    @staticmethod
    def _default_runner_factory() -> RunnerFactory:
        settings = ProviderSettings.from_environment()

        def create(policy: str, profile: PolicyProfile) -> LiveResearchService:
            return LiveResearchService(
                settings,
                policy=build_research_policy(policy, profile),
            )

        return create
