"""Provider-free public DTO for persisted per-brand trend narratives."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.db.models import Prefetch
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext, override

from core.models import (
    Brand,
    BrandTrendNarrative,
    TrendNarrative,
    TrendNarrativeVisibleRun,
)
from monitor.trend_narrative_coverage import selected_coverage
from x_monitor.config import HeadlineNarrativeConfig, load_config

_ZH_LOCALES = frozenset({"zh_cn", "zh-cn", "zh_hans", "zh-hans"})


def project_trend_narrative(
    window_days: int,
    *,
    locale: str,
    selected_brand_keys: Sequence[str] | None = None,
    now=None,
    computed_at: str | None = None,
    config: HeadlineNarrativeConfig | None = None,
) -> dict[str, Any]:
    """Map one visible cutoff to a safe, filter-aware browser projection."""
    if window_days not in {1, 7, 30, 365}:
        raise ValueError("unsupported trend narrative window")
    active_config = config or _load_config()
    requested_at = now or timezone.now()
    response_timestamp = computed_at or requested_at.isoformat()
    is_zh = str(locale).casefold() in _ZH_LOCALES
    selected = _normalize_selected_brands(selected_brand_keys)

    if not active_config.serving_active:
        return _disabled_projection(
            window_days=window_days,
            computed_at=response_timestamp,
            is_zh=is_zh,
        )

    if active_config.publication_source == "legacy_only":
        return _project_legacy_trend_narrative(
            window_days,
            selected_brand_keys=selected,
            is_zh=is_zh,
            now=requested_at,
            computed_at=response_timestamp,
            config=active_config,
        )

    visible = (
        TrendNarrativeVisibleRun.objects.filter(window_days=window_days)
        .select_related("run")
        .prefetch_related(
            Prefetch(
                "run__brand_narratives",
                queryset=BrandTrendNarrative.objects.select_related(
                    "brand", "last_good__brand"
                ).defer(
                    "propositions",
                    "events",
                    "cited_fact_ids",
                    "cited_evidence_ids",
                    "selected_evidence_packet",
                    "final_critic_payload",
                    "last_good__propositions",
                    "last_good__events",
                    "last_good__cited_fact_ids",
                    "last_good__cited_evidence_ids",
                    "last_good__selected_evidence_packet",
                    "last_good__final_critic_payload",
                ),
            )
        )
        .first()
    )
    if visible is not None:
        return _project_visible_run(
            visible,
            selected_brand_keys=selected,
            is_zh=is_zh,
            now=requested_at,
            computed_at=response_timestamp,
            config=active_config,
        )

    if active_config.legacy_fallback_enabled:
        legacy = _project_legacy_trend_narrative(
            window_days,
            selected_brand_keys=selected,
            is_zh=is_zh,
            now=requested_at,
            computed_at=response_timestamp,
            config=active_config,
            require_selected_subject=selected is not None,
        )
        if legacy is not None:
            return legacy

    return _empty_v3_projection(
        window_days=window_days,
        selected_brand_keys=selected,
        is_zh=is_zh,
        now=requested_at,
        computed_at=response_timestamp,
    )


def _project_legacy_trend_narrative(
    window_days: int,
    *,
    selected_brand_keys: list[str] | None,
    is_zh: bool,
    now,
    computed_at: str,
    config: HeadlineNarrativeConfig,
    require_selected_subject: bool = False,
) -> dict[str, Any] | None:
    """Return the bounded legacy DTO for migration fallback or rollback."""
    fallback_body = _fallback_body(is_zh=is_zh, disabled=False)
    base = {
        "schema_version": 2,
        "window_days": window_days,
        "computed_at": computed_at,
        "state": "unavailable",
        "state_label": _state_label("unavailable", is_zh=is_zh),
        "body": fallback_body,
        "body_prefix": "",
        "body_remainder": fallback_body,
        "observations": [],
        "subjects": [],
        "primary_brand": None,
        "generated_at": None,
        "checked_at": None,
        "facts_as_of": None,
        "coverage_state": "unknown",
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
        if selected_brand_keys is not None:
            return None if require_selected_subject else base
        return _no_story_projection(
            base,
            no_story=no_story,
            is_zh=is_zh,
            window_days=window_days,
            config=config,
            now=now,
        )
    if current is None:
        return None if require_selected_subject else base
    subjects = _subject_projection(current, is_zh=is_zh)
    if selected_brand_keys is not None:
        selected_set = set(selected_brand_keys)
        subjects = [subject for subject in subjects if subject["key"] in selected_set]
        if not subjects:
            return None if require_selected_subject else base
        # The legacy row is one shared narrative. Keep one eligible identity
        # rather than duplicating the same copy into multiple pseudo-brand cards.
        subjects = subjects[:1]
    state, checked_at = trend_narrative_state(
        current,
        window_days=window_days,
        config=config,
        now=now,
    )
    body = current.resolved_body_zh_cn if is_zh else current.body_en
    observations = _public_observations(
        current.observations_zh_cn if is_zh else current.observations_en
    )
    if current.coverage_state == "limited":
        body = f"{body} {_coverage_context(current, is_zh=is_zh)}"
    primary_brand = subjects[0] if subjects else None
    body_prefix, body_remainder = _body_parts(
        body,
        primary_brand["display_name"] if primary_brand else "",
    )
    return {
        **base,
        "state": state,
        "state_label": _state_label(state, is_zh=is_zh),
        "body": body,
        "body_prefix": body_prefix,
        "body_remainder": body_remainder,
        "observations": observations,
        "subjects": subjects,
        "primary_brand": primary_brand,
        "generated_at": _iso(current.generated_at),
        "checked_at": _iso(checked_at),
        "facts_as_of": _iso(current.facts_as_of),
        "coverage_state": current.coverage_state or "unknown",
    }


def _project_visible_run(
    visible: TrendNarrativeVisibleRun,
    *,
    selected_brand_keys: list[str] | None,
    is_zh: bool,
    now,
    computed_at: str,
    config: HeadlineNarrativeConfig,
) -> dict[str, Any]:
    """Project rows from exactly the run captured by the visible pointer."""
    run = visible.run
    outcomes = {row.brand_key_snapshot: row for row in run.brand_narratives.all()}
    manifest = _unique_strings(run.brand_manifest)
    manifest_set = set(manifest)
    ranked = [key for key in _unique_strings(run.internal_order) if key in manifest_set]
    ranked_set = set(ranked)
    ranked.extend(key for key in manifest if key not in ranked_set)
    explicit = selected_brand_keys is not None
    if explicit:
        selected_set = set(selected_brand_keys)
        candidates = [key for key in ranked if key in selected_set]
        candidate_set = set(candidates)
        candidates.extend(
            key for key in selected_brand_keys if key not in candidate_set
        )
    else:
        candidates = ranked

    # A one- or two-brand saved view always keeps those explicit brands.
    # Default and truncated sets demote deterministic empty/data-quality rows
    # so a usable narrative is not displaced by a terminal placeholder.
    if not explicit or len(candidates) > 2:
        rank_index = {key: index for index, key in enumerate(candidates)}
        candidates.sort(
            key=lambda key: (
                _non_narrative_sort_key(outcomes.get(key)),
                rank_index[key],
            )
        )
    chosen = candidates[:2]
    missing = [key for key in chosen if key not in outcomes]
    current_brands = {
        brand.nickname: brand for brand in Brand.objects.filter(nickname__in=missing)
    }
    items = [
        _per_brand_item(
            outcomes.get(key),
            fallback_brand=current_brands.get(key),
            brand_key=key,
            window_days=run.window_days,
            is_zh=is_zh,
            now=now,
            config=config,
        )
        for key in chosen
    ]
    requested_count = len(candidates)
    selection = _selection_projection(
        explicit=explicit,
        requested_count=requested_count,
        returned_count=len(items),
        is_zh=is_zh,
    )
    return _v3_projection(
        window_days=run.window_days,
        computed_at=computed_at,
        facts_as_of=_iso(run.facts_as_of),
        items=items,
        selection=selection,
        is_zh=is_zh,
    )


def _empty_v3_projection(
    *,
    window_days: int,
    selected_brand_keys: list[str] | None,
    is_zh: bool,
    now,
    computed_at: str,
) -> dict[str, Any]:
    selected = selected_brand_keys or []
    brands = {
        brand.nickname: brand
        for brand in Brand.objects.filter(nickname__in=selected[:2])
    }
    items = [
        _per_brand_item(
            None,
            fallback_brand=brands.get(key),
            brand_key=key,
            window_days=window_days,
            is_zh=is_zh,
            now=now,
            config=None,
        )
        for key in selected[:2]
    ]
    return _v3_projection(
        window_days=window_days,
        computed_at=computed_at,
        facts_as_of=None,
        items=items,
        selection=_selection_projection(
            explicit=selected_brand_keys is not None,
            requested_count=len(selected),
            returned_count=len(items),
            is_zh=is_zh,
        ),
        is_zh=is_zh,
    )


def _disabled_projection(
    *, window_days: int, computed_at: str, is_zh: bool
) -> dict[str, Any]:
    body = _fallback_body(is_zh=is_zh, disabled=True)
    return {
        "schema_version": 3,
        "window_days": window_days,
        "computed_at": computed_at,
        "facts_as_of": None,
        "state": "disabled",
        "state_label": _state_label("disabled", is_zh=is_zh),
        "items": [],
        "selection": {
            "mode": "all",
            "requested_count": 0,
            "returned_count": 0,
            "truncated": False,
            "summary": "",
        },
        **_v2_compatibility(body=body, items=[]),
    }


def _v3_projection(
    *,
    window_days: int,
    computed_at: str,
    facts_as_of: str | None,
    items: list[dict[str, Any]],
    selection: dict[str, Any],
    is_zh: bool,
) -> dict[str, Any]:
    states = {item["state"] for item in items}
    if not items:
        state = "unavailable"
    elif len(states) == 1:
        state = next(iter(states))
    else:
        state = "mixed"
    body = (
        items[0]["headline"] if items else _fallback_body(is_zh=is_zh, disabled=False)
    )
    return {
        "schema_version": 3,
        "window_days": window_days,
        "computed_at": computed_at,
        "facts_as_of": facts_as_of,
        "state": state,
        "state_label": _v3_state_label(state, is_zh=is_zh),
        "items": items,
        "selection": selection,
        **_v2_compatibility(body=body, items=items),
    }


def _v2_compatibility(*, body: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep the server-rendered strip safe until U6 switches to ``items``."""
    first = items[0] if items else None
    brand = first["brand"] if first else None
    prefix, remainder = _body_parts(body, brand["display_name"] if brand else "")
    subjects = []
    if brand is not None:
        subjects.append(
            {
                "position": 0,
                "support_type": "measured_candidate",
                "entity_type": "brand",
                "identity_type": "brand",
                **brand,
            }
        )
    return {
        "body": body,
        "body_prefix": prefix,
        "body_remainder": remainder,
        "observations": [first["secondary"]] if first and first["secondary"] else [],
        "subjects": subjects,
        "primary_brand": brand,
        "generated_at": first["verified_at"] if first else None,
        "checked_at": (
            first["verified_at"] or first["attempted_at"] if first else None
        ),
        "coverage_state": "unknown",
    }


def _per_brand_item(
    outcome: BrandTrendNarrative | None,
    *,
    fallback_brand: Brand | None,
    brand_key: str,
    window_days: int,
    is_zh: bool,
    now,
    config: HeadlineNarrativeConfig | None,
) -> dict[str, Any]:
    served = outcome
    state = "unavailable"
    if outcome is not None:
        if outcome.status == BrandTrendNarrative.Status.HELD and outcome.last_good:
            served = outcome.last_good
            state = "stale"
        elif outcome.status == BrandTrendNarrative.Status.APPROVED:
            stale = (
                outcome.verified_at is None
                or now
                >= outcome.verified_at
                + timedelta(minutes=config.stale_minutes[window_days] if config else 0)
            )
            state = "stale" if stale else "available"
        elif outcome.status == BrandTrendNarrative.Status.NO_CONTENT:
            state = "no_content"
        elif outcome.status == BrandTrendNarrative.Status.DATA_QUALITY_UNAVAILABLE:
            state = "data_quality_unavailable"
        else:
            state = "unavailable"

    resolved_brand = fallback_brand or (
        outcome.brand if outcome is not None and outcome.brand_id is not None else None
    )
    fallback_name = (
        (resolved_brand.display_name or resolved_brand.nickname)
        if resolved_brand is not None
        else brand_key
    )
    name_en = (
        (outcome.brand_name_en_snapshot if outcome is not None else None)
        or (resolved_brand.display_name_en if resolved_brand is not None else None)
        or fallback_name
    )
    name_zh = (
        (outcome.brand_name_zh_cn_snapshot if outcome is not None else None)
        or (resolved_brand.display_name_zh_cn if resolved_brand is not None else None)
        or name_en
    )
    display_name = name_zh if is_zh else name_en
    brand_exists = (
        outcome.brand_id is not None
        if outcome is not None
        else fallback_brand is not None
    )
    verified_at = served.verified_at if served is not None else None
    attempted_at = outcome.attempted_at if outcome is not None else None
    if state in {"available", "stale"} and served is not None:
        headline = served.headline_zh_cn if is_zh else served.headline_en
        secondary = served.secondary_zh_cn if is_zh else served.secondary_en
        identifier = f"brand-trend:{served.pk}"
    else:
        headline, secondary = _terminal_copy(
            state, display_name=display_name, is_zh=is_zh
        )
        identifier = f"brand-trend:{outcome.pk}" if outcome is not None else None
    freshness = _freshness_projection(
        verified_at=verified_at,
        attempted_at=attempted_at,
        is_zh=is_zh,
        now=now,
    )
    return {
        "id": identifier,
        "brand": {
            "key": brand_key,
            "display_name": display_name,
            "url": reverse("brand_home", args=[brand_key]) if brand_exists else None,
        },
        "state": state,
        "state_label": _item_state_label(state, freshness=freshness, is_zh=is_zh),
        "headline": headline,
        "secondary": secondary,
        "verified_at": _iso(verified_at),
        "attempted_at": _iso(attempted_at),
        "freshness": freshness,
    }


def _terminal_copy(state: str, *, display_name: str, is_zh: bool) -> tuple[str, str]:
    if state == "no_content":
        return (
            (
                f"{display_name}在这一时间段内没有帖子。"
                if is_zh
                else f"{display_name} had no posts in this window."
            ),
            (
                "这一时间段的来源覆盖完整。"
                if is_zh
                else "Source coverage was complete for this period."
            ),
        )
    if state == "data_quality_unavailable":
        return (
            (
                f"{display_name}的趋势摘要暂不可用。"
                if is_zh
                else f"{display_name}'s trend summary is unavailable."
            ),
            (
                "这一时间段的来源数据不完整，因此未对讨论量作出判断。"
                if is_zh
                else "Source data for this window is incomplete; no claim about conversation volume was made."
            ),
        )
    return (
        (
            f"{display_name}的趋势摘要暂不可用。"
            if is_zh
            else f"{display_name}'s trend summary is unavailable."
        ),
        (
            "最近一次审核未生成可发布的趋势摘要。"
            if is_zh
            else "The latest review attempt did not produce a publishable narrative."
        ),
    )


def _freshness_projection(
    *, verified_at, attempted_at, is_zh: bool, now
) -> dict[str, str | None]:
    timestamp = verified_at or attempted_at
    kind = "verified" if verified_at is not None else "attempted"
    if timestamp is None:
        return {
            "kind": None,
            "relative": "",
            "absolute": "",
            "absolute_iso": None,
        }
    relative = _relative_time(timestamp, now=now, is_zh=is_zh)
    if is_zh:
        relative_label = (
            f"上次验证于{relative}" if kind == "verified" else f"上次尝试于{relative}"
        )
    else:
        relative_label = (
            f"last verified {relative}"
            if kind == "verified"
            else f"last attempt {relative}"
        )
    return {
        "kind": kind,
        "relative": relative_label,
        "absolute": _absolute_time(timestamp, is_zh=is_zh),
        "absolute_iso": _iso(timestamp),
    }


def _relative_time(value, *, now, is_zh: bool) -> str:
    seconds = max(0, int((now - value).total_seconds()))
    if seconds < 60:
        return "刚刚" if is_zh else "just now"
    if seconds < 3600:
        amount = max(1, seconds // 60)
        return f"{amount}分钟前" if is_zh else f"{amount} min ago"
    if seconds < 86400:
        amount = max(1, seconds // 3600)
        return f"{amount}小时前" if is_zh else f"{amount} hr ago"
    amount = max(1, seconds // 86400)
    return f"{amount}天前" if is_zh else f"{amount} days ago"


def _absolute_time(value, *, is_zh: bool) -> str:
    utc = value.astimezone(UTC)
    if is_zh:
        return f"{utc.year}年{utc.month}月{utc.day}日 {utc:%H:%M} UTC"
    month = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )[utc.month - 1]
    return f"{month} {utc.day}, {utc.year}, {utc:%H:%M} UTC"


def _item_state_label(state: str, *, freshness: dict[str, Any], is_zh: bool) -> str:
    relative = str(freshness.get("relative") or "")
    if state == "stale":
        return f"过期 · {relative}" if is_zh else f"Stale · {relative}"
    labels = {
        "available": ("可用", "Available"),
        "unavailable": ("暂不可用", "Unavailable"),
        "no_content": ("无内容", "No content"),
        "data_quality_unavailable": ("数据不完整", "Data unavailable"),
    }
    zh, en = labels[state]
    return zh if is_zh else en


def _v3_state_label(state: str, *, is_zh: bool) -> str:
    labels = {
        "available": ("可用", "Available"),
        "stale": ("过期", "Stale"),
        "unavailable": ("暂不可用", "Unavailable"),
        "no_content": ("无内容", "No content"),
        "data_quality_unavailable": ("数据不完整", "Data unavailable"),
        "mixed": ("混合状态", "Mixed"),
    }
    zh, en = labels[state]
    return zh if is_zh else en


def _selection_projection(
    *,
    explicit: bool,
    requested_count: int,
    returned_count: int,
    is_zh: bool,
) -> dict[str, Any]:
    truncated = explicit and requested_count > returned_count
    summary = ""
    if truncated:
        summary = (
            f"已选择{requested_count}个，显示{returned_count}个"
            if is_zh
            else f"{returned_count} of {requested_count} selected"
        )
    return {
        "mode": "explicit" if explicit else "all",
        "requested_count": requested_count,
        "returned_count": returned_count,
        "truncated": truncated,
        "summary": summary,
    }


def _non_narrative_sort_key(outcome: BrandTrendNarrative | None) -> int:
    if outcome is None:
        return 1
    return (
        0
        if outcome.status
        in {
            BrandTrendNarrative.Status.APPROVED,
            BrandTrendNarrative.Status.HELD,
        }
        else 1
    )


def _normalize_selected_brands(
    value: Sequence[str] | None,
) -> list[str] | None:
    if value is None:
        return None
    return _unique_strings(value)


def _unique_strings(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return list(
        dict.fromkeys(
            str(item).strip()
            for item in value
            if item not in (None, "") and str(item).strip()
        )
    )


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
    if not config.serving_active:
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
                    reverse("brand_home", args=[key]) if brand_id is not None else None
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
            "key": (subject.canonical_key_snapshot or subject.observed_name),
            "display_name": (
                subject.name_zh_cn_snapshot if is_zh else subject.name_en_snapshot
            ),
            "url": (
                reverse("brand_home", args=[subject.canonical_key_snapshot])
                if subject.brand_id is not None
                else None
            ),
        }
        for subject in subjects
    ]


def _body_parts(body: str, primary_name: str) -> tuple[str, str]:
    """Split around the first subject occurrence so its link stays in place."""
    if not primary_name:
        return "", body
    for match in re.finditer(re.escape(primary_name), body, flags=re.IGNORECASE):
        preceding = body[match.start() - 1 : match.start()]
        following = body[match.end() : match.end() + 1]
        if (preceding and preceding.isalnum()) or (following and following.isalnum()):
            continue
        return body[: match.start()], body[match.end() :]
    return "", body


def _public_observations(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()][
        :2
    ]
