from budgeted_research.domain.models import Usage


class ResearchError(Exception):
    """Base exception for expected research failures."""


class BudgetExceededError(ResearchError):
    """Raised when an action cannot be reserved within the hard budget."""


class InvalidProviderOutputError(ResearchError):
    """Raised when a provider returns data that violates the domain contract."""

    def __init__(self, message: str, usage: Usage | None = None) -> None:
        super().__init__(message)
        self.usage = usage
