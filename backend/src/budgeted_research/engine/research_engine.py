from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

from budgeted_research.budgeting.ledger import BudgetLedger
from budgeted_research.domain.actions import Action, ActionStatus, ResourceEstimate
from budgeted_research.domain.errors import BudgetExceededError
from budgeted_research.domain.events import ActionRecord, EventSink, InMemoryEventSink
from budgeted_research.domain.models import (
    BudgetStatus,
    ResearchRequest,
    RunStatus,
    RunSummary,
)
from budgeted_research.domain.state import ResearchState
from budgeted_research.engine.executor import ActionExecutor
from budgeted_research.engine.reducer import StateReducer
from budgeted_research.engine.result import ResearchRunResult
from budgeted_research.policies.base import ResearchPolicy


class ResearchEngine:
    """Executes policy-approved actions and owns the budgeted state transition loop."""

    def __init__(
        self,
        policy: ResearchPolicy,
        executor: ActionExecutor,
        reducer: StateReducer | None = None,
        event_sink: EventSink | None = None,
    ) -> None:
        self.policy = policy
        self.executor = executor
        self.reducer = reducer or StateReducer()
        self.event_sink = event_sink or InMemoryEventSink()

    async def run(self, request: ResearchRequest, run_id: str | None = None) -> RunSummary:
        result = await self.run_detailed(request, run_id)
        return result.summary

    async def run_detailed(
        self, request: ResearchRequest, run_id: str | None = None
    ) -> ResearchRunResult:
        state = ResearchState(
            run_id=run_id or str(uuid4()),
            request=request,
            status=RunStatus.RUNNING,
        )
        ledger = BudgetLedger(request.budget)
        sequence = 0

        while state.status is RunStatus.RUNNING:
            state.budget_status = BudgetStatus.model_validate(
                asdict(ledger.snapshot())
            )
            sequence += 1
            action = self.policy.next_action(state, sequence)
            if action is None:
                if state.report is not None:
                    assessment = self.policy.assess_completion(state)
                    state.completion_assessment = assessment
                    state.status = assessment.status
                    state.stop_reason = assessment.reason
                elif not state.evidence:
                    state.status = RunStatus.INSUFFICIENT_EVIDENCE
                    state.stop_reason = "no validated evidence was collected"
                else:
                    state.status = RunStatus.FAILED
                    state.stop_reason = "policy stopped before report generation"
                break

            try:
                ledger.reserve(action.estimated_resources)
            except BudgetExceededError as error:
                state.status = RunStatus.BUDGET_EXHAUSTED
                state.stop_reason = str(error)
                await self._record(
                    sequence, action, ActionStatus.REJECTED, error=str(error)
                )
                break

            try:
                result = await self.executor.execute(action, state)
            except Exception as error:  # provider boundary: preserve a terminal trace
                usage = getattr(error, "usage", None)
                if usage is None:
                    ledger.release(action.estimated_resources)
                    actual_resources = ResourceEstimate()
                else:
                    actual_resources = ResourceEstimate(
                        tokens=usage.total_tokens,
                        cost_usd=usage.cost_usd,
                    )
                    ledger.settle(action.estimated_resources, actual_resources)
                state.status = RunStatus.FAILED
                state.stop_reason = f"{type(error).__name__}: {error}"
                await self._record(
                    sequence,
                    action,
                    ActionStatus.FAILED,
                    actual=actual_resources.model_dump(),
                    error=str(error),
                )
                break

            ledger.settle(action.estimated_resources, result.actual_resources)
            try:
                state = self.reducer.apply(state, action, result)
            except Exception as error:
                state.status = RunStatus.FAILED
                state.stop_reason = f"{type(error).__name__}: {error}"
                await self._record(
                    sequence,
                    action,
                    ActionStatus.FAILED,
                    actual=result.actual_resources.model_dump(),
                    error=str(error),
                )
                break

            await self._record(
                sequence,
                action,
                ActionStatus.COMPLETED,
                actual=result.actual_resources.model_dump(),
            )

        snapshot = ledger.snapshot()
        state.budget_status = BudgetStatus.model_validate(asdict(snapshot))
        summary = RunSummary(
            run_id=state.run_id,
            policy=self.policy.name,
            status=state.status,
            report=state.report,
            evidence=state.evidence,
            total_tokens=snapshot.tokens_used,
            total_cost_usd=snapshot.cost_usd_used,
            search_count=snapshot.searches_used,
            page_fetch_count=snapshot.page_fetches_used,
            elapsed_seconds=snapshot.elapsed_seconds,
            stop_reason=state.stop_reason,
            completion_assessment=state.completion_assessment,
        )
        return ResearchRunResult(state=state, summary=summary)

    async def _record(
        self,
        sequence: int,
        action: Action,
        status: ActionStatus,
        actual: dict[str, int | float] | None = None,
        error: str | None = None,
    ) -> None:
        await self.event_sink.record(
            ActionRecord(
                sequence=sequence,
                action_id=action.id,
                action_type=action.type,
                policy=self.policy.name,
                target=action.target,
                reason=action.reason,
                status=status,
                estimated_resources=action.estimated_resources.model_dump(),
                actual_resources=actual or {},
                decision_context=action.decision_context,
                error=error,
            )
        )
