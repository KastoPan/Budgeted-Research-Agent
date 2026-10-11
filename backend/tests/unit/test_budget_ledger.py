import pytest

from budgeted_research.budgeting.ledger import BudgetLedger
from budgeted_research.domain.actions import ResourceEstimate
from budgeted_research.domain.errors import BudgetExceededError
from budgeted_research.domain.models import ResearchBudget


def test_reservation_rejects_action_beyond_search_budget() -> None:
    ledger = BudgetLedger(
        ResearchBudget(
            max_tokens=100,
            max_searches=1,
            max_page_fetches=1,
            max_elapsed_seconds=60,
        )
    )
    one_search = ResourceEstimate(searches=1)

    ledger.reserve(one_search)
    ledger.settle(one_search, one_search)

    with pytest.raises(BudgetExceededError, match="search budget"):
        ledger.reserve(one_search)

    assert ledger.snapshot().searches_used == 1


def test_settlement_uses_actual_tokens_instead_of_estimate() -> None:
    ledger = BudgetLedger(
        ResearchBudget(
            max_tokens=1_000,
            max_searches=1,
            max_page_fetches=1,
            max_elapsed_seconds=60,
        )
    )
    estimate = ResourceEstimate(tokens=500)
    actual = ResourceEstimate(tokens=320)

    ledger.reserve(estimate)
    ledger.settle(estimate, actual)

    snapshot = ledger.snapshot()
    assert snapshot.tokens_used == 320
    assert snapshot.tokens_remaining == 680

