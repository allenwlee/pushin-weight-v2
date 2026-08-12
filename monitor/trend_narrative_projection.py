"""Provider-free public DTO for persisted shared trend narratives."""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext, override

from core.models import TrendNarrativeVersion
from x_monitor.config import HeadlineNarrativeConfig, load_config

_ZH_LOCALES = frozenset({"zh_cn", "zh-cn", "zh_hans", "zh-hans"})


def project_trend_narrative(
    window_days: int,
    *,
    locale: str,
    now=None,
    computed_at: str | None = None,
    config: HeadlineNarrativeConfig | None = None,
) -> dict[str, Any]:
    """Map current durable state to a safe, versioned browser projection."""
    if window_days not in {1, 7, 30, 365}:
        raise ValueError("unsupported trend narrative window")
    active_config = config or _load_config()
    requested_at = now or timezone.now()
    response_timestamp = computed_at or requested_at.isoformat()
    is_zh = str(locale).casefold() in _ZH_LOCALES
    base = {
        "schema_version": 1,
        "window_days": window_days,
        "computed_at": response_timestamp,
        "state": "unavailable",
        "state_label": _state_label("unavailable", is_zh=is_zh),
        "body": _fallback_body(is_zh=is_zh, disabled=False),
        "primary_brand": None,
        "generated_at": None,
        "checked_at": None,
        "facts_as_of": None,
        "coverage_state": "unknown",
    }
    if not active_config.serving_enabled:
        return {
            **base,
            "state": "disabled",
            "state_label": _state_label("disabled", is_zh=is_zh),
            "body": _fallback_body(is_zh=is_zh, disabled=True),
        }
    current = (
        TrendNarrativeVersion.objects.filter(
            window_days=window_days,
            is_current=True,
            status=TrendNarrativeVersion.Status.PUBLISHED,
        )
        .select_related("primary_brand")
        .first()
    )
    if current is None:
        return base
    state, checked_at = trend_narrative_state(
        current,
        window_days=window_days,
        config=active_config,
        now=requested_at,
    )
    display_name = (
        current.primary_brand_name_zh_hans if is_zh else current.primary_brand_name_en
    )
    body = current.body_zh_hans if is_zh else current.body_en
    if current.coverage_state == "limited":
        body = f"{body} {_coverage_context(current, is_zh=is_zh)}"
    return {
        **base,
        "state": state,
        "state_label": _state_label(state, is_zh=is_zh),
        "body": body,
        "primary_brand": {
            "key": current.primary_brand_key,
            "display_name": display_name,
            "url": (
                reverse("brand_home", args=[current.primary_brand_key])
                if current.primary_brand_id is not None
                else None
            ),
        },
        "generated_at": _iso(current.generated_at),
        "checked_at": _iso(checked_at),
        "facts_as_of": _iso(current.facts_as_of),
        "coverage_state": current.coverage_state or "unknown",
    }


def trend_narrative_state(
    current: TrendNarrativeVersion | None,
    *,
    window_days: int,
    config: HeadlineNarrativeConfig,
    now,
) -> tuple[str, Any]:
    """Return the shared public/operator state and its freshness timestamp."""
    checked_at = (
        current.latest_checked_at or current.generated_at
        if current is not None
        else None
    )
    if not config.serving_enabled:
        return "disabled", checked_at
    if current is None:
        return "unavailable", None
    stale = checked_at is None or now >= checked_at + timedelta(
        minutes=config.stale_minutes[window_days]
    )
    return ("stale" if stale else "available"), checked_at


@lru_cache(maxsize=1)
def _load_config() -> HeadlineNarrativeConfig:
    return load_config(Path("config.yaml")).headline_narrative


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _fallback_body(*, is_zh: bool, disabled: bool) -> str:
    if disabled:
        return "趋势摘要暂不可用。" if is_zh else "Trend summary is unavailable."
    return (
        "该时段的趋势摘要正在准备中。"
        if is_zh
        else "Trend summary is warming up for this window."
    )


def _coverage_context(current: TrendNarrativeVersion, *, is_zh: bool) -> str:
    coverage = (current.generation_facts or {}).get("coverage") or {}
    raw_earliest = coverage.get("earliest_at")
    try:
        earliest = datetime.fromisoformat(str(raw_earliest))
        date = earliest.date().isoformat()
    except (TypeError, ValueError):
        date = "the available-data start" if not is_zh else "可用数据起点"
    return (
        f"Based on available data since {date}."
        if not is_zh
        else f"以上摘要基于自 {date} 起的可用数据。"
    )


def _state_label(state: str, *, is_zh: bool) -> str:
    labels = {
        "available": "Available",
        "stale": "Stale",
        "unavailable": "Warming up",
        "disabled": "Disabled",
    }
    with override("zh-hans" if is_zh else "en"):
        return gettext(labels[state])
