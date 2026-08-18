"""Shared pre-call budget for every outbound enrichment LLM request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class LlmBudgetExhausted(RuntimeError):
    """Raised before an outbound request when the invocation cap is spent."""


@dataclass
class LlmCallBudget:
    max_calls: int | None = None
    used: int = 0

    def __post_init__(self) -> None:
        if self.max_calls is not None and self.max_calls < 0:
            raise ValueError("max_calls must be non-negative")

    @property
    def remaining(self) -> int | None:
        if self.max_calls is None:
            return None
        return max(self.max_calls - self.used, 0)

    def consume(self) -> None:
        if self.max_calls is not None and self.used >= self.max_calls:
            raise LlmBudgetExhausted(
                f"LLM call budget exhausted ({self.used}/{self.max_calls})"
            )
        self.used += 1


class BudgetedLlmClient:
    """Count immediately before each concrete ``messages_create`` call."""

    def __init__(self, client: Any, budget: LlmCallBudget) -> None:
        self._client = client
        self._budget = budget

    def messages_create(self, **kwargs: Any) -> dict[str, Any]:
        self._budget.consume()
        return self._client.messages_create(**kwargs)
