"""Invocation-wide transport limits and redacted usage for manual recovery."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class BackfillBudgetExhausted(RuntimeError):
    """A physical request cannot fit the operator's remaining allowance."""


class BackfillBudget:
    def __init__(
        self, *, max_api_requests: int, max_llm_calls: int, run_seconds: float,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_api_requests <= 0 or max_llm_calls < 0 or run_seconds <= 0:
            raise ValueError("invalid backfill invocation limits")
        self._clock = monotonic
        self._started = monotonic()
        self._deadline = self._started + run_seconds
        self._api_limit = max_api_requests
        self._llm_limit = max_llm_calls
        self._lock = threading.Lock()
        self._api_requests = 0
        self._llm_requests = 0
        self._api_responses: list[dict[str, Any]] = []
        self._model_responses: list[dict[str, Any]] = []

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self._deadline - self._clock())

    @property
    def remaining_llm_calls(self) -> int:
        with self._lock:
            return max(0, self._llm_limit - self._llm_requests)

    def remaining(self) -> float:
        return self.remaining_seconds

    def can_start(self, worst_case_seconds: float) -> bool:
        return worst_case_seconds <= self.remaining_seconds

    def claim_api_request(self, timeout_seconds: float = 0) -> None:
        with self._lock:
            if self.remaining_seconds <= timeout_seconds:
                raise BackfillBudgetExhausted("backfill API deadline exhausted")
            if self._api_requests >= self._api_limit:
                raise BackfillBudgetExhausted("backfill API request cap exhausted")
            self._api_requests += 1

    def claim_llm_request(self, timeout_seconds: float = 0) -> None:
        with self._lock:
            if self.remaining_seconds <= timeout_seconds:
                raise BackfillBudgetExhausted("backfill model deadline exhausted")
            if self._llm_requests >= self._llm_limit:
                raise BackfillBudgetExhausted("backfill model request cap exhausted")
            self._llm_requests += 1

    def record_api_response(self, response: dict[str, Any]) -> None:
        with self._lock:
            self._api_responses.append(response)

    def record_model_response(self, response: Any) -> None:
        usage = getattr(response, "provider_usage", None)
        with self._lock:
            self._model_responses.append({
                "status": "failed" if isinstance(response, BaseException) else "returned",
                "usage": dict(usage) if isinstance(usage, dict) else None,
            })

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "api_requests": self._api_requests,
                "api_limit": self._api_limit,
                "llm_requests": self._llm_requests,
                "llm_limit": self._llm_limit,
                "elapsed_seconds": round(self._clock() - self._started, 3),
                "remaining_seconds": round(self.remaining_seconds, 3),
                "api_responses": list(self._api_responses),
                "model_responses": list(self._model_responses),
            }


@dataclass
class BackfillContext:
    """Committed continuation passed to the existing runner for one unit."""

    budget: BackfillBudget
    cursor: str | None = None
    seen_cursors: list[str] = field(default_factory=list)
    post_ids: list[str] = field(default_factory=list)
    enrichment_cohort_ids: list[str] = field(default_factory=list)
    enrichment_limit: int = 5
    api_timeout_seconds: int = 30
    query_override: str | None = None


def bounded_backfill_config(cfg: Any, *, enrichment_limit: int) -> Any:
    """Copy resource controls; retain canonical models, queries and policy."""
    from x_monitor.config import EnrichmentConfig

    bounded = cfg.model_copy(deep=True)
    bounded.harvest.enrichment = EnrichmentConfig(
        claim_per_cycle=enrichment_limit,
        current_cycle_claim_per_cycle=0,
        carryover_claim_per_cycle=enrichment_limit,
        attempt_budget_seconds=60,
        request_timeout_seconds=30,
        short_post_budget_seconds=50,
        long_post_budget_seconds=10,
        claim_ttl_seconds=180,
        terminalization_reserve_seconds=20,
    )
    bounded.targeted_extraction.enabled = False
    bounded.synthesis.prewarm_enabled = False
    bounded.discovery.rare_types.enabled = False
    bounded.discovery.rare_types.product_verification_enabled = False
    bounded.discovery.rare_types.targeted_extraction_enabled = False
    return bounded
