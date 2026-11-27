"""Reserve a conservative charge before every physical enrichment request."""

from __future__ import annotations

import hashlib
import json
from decimal import ROUND_CEILING, Decimal

from django.db import transaction
from django.utils import timezone

from core.models import EnrichmentBudgetWindow
from x_monitor.attribution import LLMCallBudgetExhausted

# Verified 2026-10-27 against each model's DeepInfra page. Reserve priority
# prices (1.5x standard), even though the current clients request standard.
# No cache discount or refund: a lost response cannot renew the allowance.
PRICING_REVISION = "deepinfra-2026-10-27-priority-bound-v1"
PRICES = {
    "google/gemma-4-31B-it-turbo": (Decimal("0.135"), Decimal("0.51")),
    "deepseek-ai/DeepSeek-V4-Flash-0731": (Decimal("0.09"), Decimal("0.27")),
}


def config_fingerprint(cfg) -> str:
    enrichment = cfg.harvest.enrichment.model_dump(
        exclude={"mode", "provider_calls_active", "budget_window_id"}
    )
    llm = cfg.llm.model_dump()
    pricing = PRICING_REVISION
    if llm.pop("classifier_pipeline", "two_role") == "compressed8_pulse_v1":
        llm["classifier_pipeline"] = "compressed8_pulse_v1"
        pricing += "+typesafe-2026-11-17-bound-v1"
    else:
        enrichment.pop("pulse_classification_concurrency", None)
    payload = {
        "enrichment": enrichment,
        "llm": llm,
        "synthesis_concurrency": cfg.synthesis.concurrency,
        "targeted_extraction": cfg.targeted_extraction.model_dump(),
        "pricing": pricing,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def request_cost_bound(request: dict) -> Decimal:
    model = request.get("model")
    if model == "jev-1.14.0":
        from x_monitor.jev_classifier import (
            INPUT_PRICE_PER_MILLION,
            MAX_INPUT_TOKENS,
            request_document,
        )

        try:
            request_document(request.get("messages"), model=model)
        except (ValueError, TypeError) as exc:
            raise LLMCallBudgetExhausted("enrichment_token_bound_unknown") from exc
        # Reserve the documented non-long-context maximum before extraction,
        # since the second request depends on the first response. No refund or
        # optimistic tokenizer estimate can renew this budget after a lost reply.
        return (MAX_INPUT_TOKENS * INPUT_PRICE_PER_MILLION / 1_000_000).quantize(
            Decimal("0.000001"), rounding=ROUND_CEILING,
        )
    if model not in PRICES:
        raise LLMCallBudgetExhausted("enrichment_price_unknown")
    messages = request.get("messages")
    output = request.get("max_tokens")
    if (
        not isinstance(messages, list)
        or not messages
        or type(output) is not int
        or output <= 0
    ):
        raise LLMCallBudgetExhausted("enrichment_token_bound_unknown")
    system = request.get("system", "")
    if not isinstance(system, str):
        raise LLMCallBudgetExhausted("enrichment_token_bound_unknown")
    # One token per UTF-8 byte is conservative for these text tokenizers.
    # Extra allowance covers chat templates, role headers and response format.
    input_bound = len(system.encode("utf-8")) + 4096
    for message in messages:
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise LLMCallBudgetExhausted("enrichment_token_bound_unknown")
        input_bound += len(message["content"].encode("utf-8")) + 1024
    input_rate, output_rate = PRICES[model]
    return ((input_bound * input_rate + output * output_rate) / 1_000_000).quantize(
        Decimal("0.000001"),
        rounding=ROUND_CEILING,
    )


def reserve_request(
    *, window_id, fingerprint: str, request: dict, scope: str, now=None
) -> Decimal:
    return reserve_charge(
        window_id=window_id, fingerprint=fingerprint, cost=request_cost_bound(request),
        scope=scope, now=now,
    )


def reserve_charge(
    *, window_id, fingerprint: str, cost: Decimal, scope: str,
    now=None, window_ceiling: Decimal | None = None,
) -> Decimal:
    """Debit the same finite allowance before a provider can incur this charge."""
    if not cost.is_finite() or cost <= 0:
        raise LLMCallBudgetExhausted("enrichment_price_unknown")
    now = now or timezone.now()
    with transaction.atomic():
        window = (
            EnrichmentBudgetWindow.objects.select_for_update()
            .filter(pk=window_id)
            .first()
        )
        if window is None or window.enrichment_window_kind != scope:
            raise LLMCallBudgetExhausted("enrichment_budget_missing")
        if window_ceiling is not None and window.usd_limit > window_ceiling:
            raise LLMCallBudgetExhausted("enrichment_budget_exceeds_cap")
        if window.config_fingerprint != fingerprint:
            raise LLMCallBudgetExhausted("enrichment_config_changed")
        if not window.starts_at <= now < window.ends_at:
            raise LLMCallBudgetExhausted("enrichment_budget_expired")
        if (
            EnrichmentBudgetWindow.objects.filter(
                enrichment_window_kind=scope,
                starts_at__lte=now,
                ends_at__gt=now,
            )
            .exclude(config_fingerprint=fingerprint)
            .exists()
        ):
            raise LLMCallBudgetExhausted("enrichment_capacity_window_conflict")
        if (
            window.reserved_requests >= window.request_limit
            or window.reserved_usd + cost > window.usd_limit
        ):
            raise LLMCallBudgetExhausted("enrichment_budget_exhausted")
        window.reserved_requests += 1
        window.reserved_usd += cost
        window.save(update_fields=["reserved_requests", "reserved_usd"])
    return cost
