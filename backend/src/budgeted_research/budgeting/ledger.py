from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from budgeted_research.domain.actions import ResourceEstimate
from budgeted_research.domain.errors import BudgetExceededError
from budgeted_research.domain.models import ResearchBudget


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    tokens_used: int
    searches_used: int
    page_fetches_used: int
    cost_usd_used: float
    elapsed_seconds: float
    tokens_remaining: int
    searches_remaining: int
    page_fetches_remaining: int
    cost_usd_remaining: float | None
    elapsed_seconds_remaining: float


class BudgetLedger:
    """Hard-budget accounting with pre-action reservation and post-action settlement."""

    def __init__(self, limits: ResearchBudget) -> None:
        self.limits = limits
        self._tokens = 0
        self._searches = 0
        self._page_fetches = 0
        self._cost_usd = 0.0
        self._reserved = ResourceEstimate()
        self._started_at = monotonic()

    @property
    def elapsed_seconds(self) -> float:
        return monotonic() - self._started_at

    def reserve(self, estimate: ResourceEstimate) -> None:
        projected = ResourceEstimate(
            tokens=self._tokens + self._reserved.tokens + estimate.tokens,
            searches=self._searches + self._reserved.searches + estimate.searches,
            page_fetches=self._page_fetches
            + self._reserved.page_fetches
            + estimate.page_fetches,
            cost_usd=self._cost_usd + self._reserved.cost_usd + estimate.cost_usd,
        )
        reasons: list[str] = []
        if projected.tokens > self.limits.max_tokens:
            reasons.append("token budget")
        if projected.searches > self.limits.max_searches:
            reasons.append("search budget")
        if projected.page_fetches > self.limits.max_page_fetches:
            reasons.append("page-fetch budget")
        if (
            self.limits.max_cost_usd is not None
            and projected.cost_usd > self.limits.max_cost_usd
        ):
            reasons.append("cost budget")
        if self.elapsed_seconds >= self.limits.max_elapsed_seconds:
            reasons.append("time budget")
        if reasons:
            raise BudgetExceededError("would exceed " + ", ".join(reasons))
        self._reserved = self._add(self._reserved, estimate)

    def settle(self, estimate: ResourceEstimate, actual: ResourceEstimate) -> None:
        self._reserved = self._subtract(self._reserved, estimate)
        self._tokens += actual.tokens
        self._searches += actual.searches
        self._page_fetches += actual.page_fetches
        self._cost_usd += actual.cost_usd

    def release(self, estimate: ResourceEstimate) -> None:
        self._reserved = self._subtract(self._reserved, estimate)

    def snapshot(self) -> BudgetSnapshot:
        cost_remaining = None
        if self.limits.max_cost_usd is not None:
            cost_remaining = max(self.limits.max_cost_usd - self._cost_usd, 0.0)
        return BudgetSnapshot(
            tokens_used=self._tokens,
            searches_used=self._searches,
            page_fetches_used=self._page_fetches,
            cost_usd_used=self._cost_usd,
            elapsed_seconds=self.elapsed_seconds,
            tokens_remaining=max(self.limits.max_tokens - self._tokens, 0),
            searches_remaining=max(self.limits.max_searches - self._searches, 0),
            page_fetches_remaining=max(
                self.limits.max_page_fetches - self._page_fetches, 0
            ),
            cost_usd_remaining=cost_remaining,
            elapsed_seconds_remaining=max(
                self.limits.max_elapsed_seconds - self.elapsed_seconds, 0.0
            ),
        )

    @staticmethod
    def _add(left: ResourceEstimate, right: ResourceEstimate) -> ResourceEstimate:
        return ResourceEstimate(
            tokens=left.tokens + right.tokens,
            searches=left.searches + right.searches,
            page_fetches=left.page_fetches + right.page_fetches,
            cost_usd=left.cost_usd + right.cost_usd,
        )

    @staticmethod
    def _subtract(left: ResourceEstimate, right: ResourceEstimate) -> ResourceEstimate:
        return ResourceEstimate(
            tokens=max(left.tokens - right.tokens, 0),
            searches=max(left.searches - right.searches, 0),
            page_fetches=max(left.page_fetches - right.page_fetches, 0),
            cost_usd=max(left.cost_usd - right.cost_usd, 0.0),
        )

