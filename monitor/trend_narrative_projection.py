"""Provider-free public DTO for persisted shared trend narratives."""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext, override

from core.models import TrendNarrative
from monitor.trend_narrative_coverage import selected_coverage
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
    fallback_body = _fallback_body(is_zh=is_zh, disabled=False)
    base = {
        "schema_version": 2,
        "window_days": window_days,
        "computed_at": response_timestamp,
        "state": "unavailable",
        "state_label": _state_label("unavailable", is_zh=is_zh),
        "body": fallback_body,
        "body_remainder": fallback_body,
        "observations": [],
        "subjects": [],
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
            "body_remainder": _fallback_body(is_zh=is_zh, disabled=True),
        }
    current = (
        TrendNarrative.objects.filter(
            window_days=window_days,
            is_current=True,
            status=TrendNarrative.Status.PUBLISHED,
        )
        .select_related("primary_brand")
        .prefetch_related("subjects")
        .first()
    )
    no_story = (
        TrendNarrative.objects.filter(
            window_days=window_days,
            status=TrendNarrative.Status.CHECKED,
            error_code="insufficient_data",
        )
        .order_by("-facts_as_of", "-latest_checked_at", "-created_at", "-pk")
        .first()
    )
    if no_story is not None and (
        current is None or _freshness_key(no_story) > _freshness_key(current)
    ):
        return _no_story_projection(
            base,
            no_story=no_story,
            is_zh=is_zh,
            window_days=window_days,
            config=active_config,
            now=requested_at,
        )
    if current is None:
        return base
    state, checked_at = trend_narrative_state(
        current,
        window_days=window_days,
        config=active_config,
        now=requested_at,
    )
    body = current.resolved_body_zh_cn if is_zh else current.body_en
    observations = _public_observations(
        current.observations_zh_cn if is_zh else current.observations_en
    )
    if current.coverage_state == "limited":
        body = f"{body} {_coverage_context(current, is_zh=is_zh)}"
    subjects = _subject_projection(current, is_zh=is_zh)
    primary_brand = subjects[0] if subjects else None
    body_remainder = _body_remainder(
        body,
        primary_brand["display_name"] if primary_brand else "",
    )
    return {
        **base,
        "state": state,
        "state_label": _state_label(state, is_zh=is_zh),
        "body": body,
        "body_remainder": body_remainder,
        "observations": observations,
        "subjects": subjects,
        "primary_brand": primary_brand,
        "generated_at": _iso(current.generated_at),
        "checked_at": _iso(checked_at),
        "facts_as_of": _iso(current.facts_as_of),
        "coverage_state": current.coverage_state or "unknown",
    }


def _freshness_key(row: TrendNarrative) -> tuple[Any, Any, int]:
    return (
        row.latest_checked_as_of or row.facts_as_of,
        row.latest_checked_at or row.generated_at or row.created_at,
        int(row.pk),
    )


def _no_story_projection(
    base: dict[str, Any],
    *,
    no_story: TrendNarrative,
    is_zh: bool,
    window_days: int,
    config: HeadlineNarrativeConfig,
    now,
) -> dict[str, Any]:
    state, checked_at = trend_narrative_state(
        no_story,
        window_days=window_days,
        config=config,
        now=now,
    )
    body = _localized(
        "No clear conversation story emerged in this window.",
        is_zh=is_zh,
    )
    return {
        **base,
        "state": state,
        "state_label": _state_label(state, is_zh=is_zh),
        "body": body,
        "body_remainder": body,
        "checked_at": _iso(checked_at),
        "facts_as_of": _iso(no_story.facts_as_of),
        "coverage_state": no_story.coverage_state or "unknown",
    }


def trend_narrative_state(
    current: TrendNarrative | None,
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


def _coverage_context(current: TrendNarrative, *, is_zh: bool) -> str:
    coverage = selected_coverage(current.generation_facts)
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
    return _localized(labels[state], is_zh=is_zh)


def _localized(message: str, *, is_zh: bool) -> str:
    with override("zh-hans" if is_zh else "en"):
        return gettext(message)


def _subject_projection(
    current: TrendNarrative,
    *,
    is_zh: bool,
) -> list[dict[str, Any]]:
    subjects = list(current.subjects.all())
    if not subjects:
        legacy = [
            (
                current.primary_brand_id,
                current.primary_brand_key,
                current.primary_brand_name_en,
                current.primary_brand_name_zh_hans,
            ),
            (
                current.secondary_brand_id,
                current.secondary_brand_key,
                current.secondary_brand_name_en,
                current.secondary_brand_name_zh_hans,
            ),
        ]
        return [
            {
                "position": position,
                "support_type": "measured_candidate",
                "entity_type": "brand",
                "identity_type": "brand",
                "key": key,
                "display_name": name_zh_cn if is_zh else name_en,
                "url": (
                    reverse("brand_home", args=[key])
                    if brand_id is not None
                    else None
                ),
            }
            for position, (brand_id, key, name_en, name_zh_cn) in enumerate(legacy)
            if key and name_en and name_zh_cn
        ]
    return [
        {
            "position": subject.position,
            "support_type": subject.support_type,
            "entity_type": subject.entity_type,
            "identity_type": subject.identity_type,
            "key": (
                subject.canonical_key_snapshot or subject.observed_name
            ),
            "display_name": (
                subject.name_zh_cn_snapshot
                if is_zh
                else subject.name_en_snapshot
            ),
            "url": (
                reverse("brand_home", args=[subject.canonical_key_snapshot])
                if subject.brand_id is not None
                else None
            ),
        }
        for subject in subjects
    ]


def _body_remainder(body: str, leading_name: str) -> str:
    if not leading_name or not body.casefold().startswith(leading_name.casefold()):
        return body
    boundary = body[len(leading_name) : len(leading_name) + 1]
    if boundary and boundary.isalnum():
        return body
    return body[len(leading_name) :].lstrip()


def _public_observations(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()][
        :2
    ]
