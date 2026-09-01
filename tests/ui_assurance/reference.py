"""Pure reference model for homepage controls and observable projections."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

ALL = "__all__"
MULTI_CONTROLS = {
    "brands": "brands",
    "sentiment": "sentiments",
    "post_type": "post_types",
    "lang": "lang",
    "role": "role",
    "nationalism_cn": "cn_nationalism",
    "nationalism_us": "us_nationalism",
    "discourse": "discourse",
}


@dataclass(frozen=True)
class RequestResult:
    generation: int
    committed: bool
    warning_visible: bool


def initial_state() -> dict[str, Any]:
    return {
        "filters": {
            "brands": ALL,
            "sentiment": ALL,
            "post_type": ALL,
            "lang": ALL,
            "role": ALL,
            "nationalism_cn": ALL,
            "nationalism_us": ALL,
            "discourse": ALL,
            "unsanctioned": "off",
            "window": 1,
        },
        "locale": "en",
        "timezone": "local",
        "brand_lens": "open",
        "nationalism_lens": "us",
        "pulse_brands": [],
        "feed_text": "synthesis_collapsed",
        "headline_detail": "collapsed",
        "role_badge": "none",
        "account_geography": "none",
        "feed_inspection": "closed",
        "feed_navigation": "row",
        "feed_pagination": "first",
        "chart_hover_freeze": "idle",
        "freeze_point": "none",
        "latest_generation": 0,
        "committed_generation": 0,
    }


def set_control(state: dict[str, Any], control: str, value: Any) -> dict[str, Any]:
    """Apply one legal user intent without consulting browser/runtime code."""

    next_state = deepcopy(state)
    if control in MULTI_CONTROLS:
        if value == ALL:
            selected: str | list[str] = ALL
        elif isinstance(value, (list, tuple)):
            selected = list(dict.fromkeys(value))
        else:
            selected = [str(value)]
        next_state["filters"][control] = selected
        if control == "brands":
            next_state["pulse_brands"] = []
    elif control in {"unsanctioned", "window"}:
        next_state["filters"][control] = int(value) if control == "window" else value
    elif control in {
        "locale",
        "timezone",
        "brand_lens",
        "nationalism_lens",
        "feed_text",
        "headline_detail",
        "role_badge",
        "account_geography",
        "feed_inspection",
        "feed_navigation",
        "feed_pagination",
        "chart_hover_freeze",
        "freeze_point",
    }:
        next_state[control] = value
    else:
        raise KeyError(f"unknown UI assurance control: {control}")
    return next_state


def toggle_pulse_brand(state: dict[str, Any], brand: str) -> dict[str, Any]:
    next_state = deepcopy(state)
    selected = next_state["pulse_brands"]
    if brand in selected:
        selected.remove(brand)
    else:
        selected.append(brand)
    next_state["filters"]["brands"] = list(selected) if selected else ALL
    return next_state


def bulk_action(state: dict[str, Any], control: str, action: str) -> dict[str, Any]:
    if control not in MULTI_CONTROLS:
        raise KeyError(f"bulk action is unavailable for {control}")
    if action == "all":
        return set_control(state, control, ALL)
    if action == "clear":
        return set_control(state, control, [])
    raise ValueError(f"unknown bulk action: {action}")


def begin_request(state: dict[str, Any]) -> tuple[dict[str, Any], int]:
    next_state = deepcopy(state)
    next_state["latest_generation"] += 1
    return next_state, next_state["latest_generation"]


def settle_request(
    state: dict[str, Any], generation: int, *, succeeded: bool, aborted: bool = False
) -> tuple[dict[str, Any], RequestResult]:
    """Only the latest request may commit data or surface a failure warning."""

    next_state = deepcopy(state)
    latest = generation == next_state["latest_generation"]
    committed = latest and succeeded
    if committed:
        next_state["committed_generation"] = generation
    return next_state, RequestResult(
        generation=generation,
        committed=committed,
        warning_visible=latest and not succeeded and not aborted,
    )


def _matches_value(post: dict[str, Any], field: str, selected: Any) -> bool:
    if selected == ALL:
        return True
    selected_values = set(selected)
    actual = post[field]
    if isinstance(actual, list):
        return bool(selected_values.intersection(actual))
    return actual in selected_values


def filter_posts(
    fixture: dict[str, Any], state: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return the exact OR-within/AND-across reference partition."""

    filters = state["filters"]
    matches = []
    for post in fixture["posts"]:
        if post["age_hours"] > int(filters["window"]) * 24:
            continue
        if filters["unsanctioned"] == "off" and post["flagged"]:
            continue
        if filters["unsanctioned"] == "only" and not post["flagged"]:
            continue
        if not all(
            _matches_value(post, field, filters[control])
            for control, field in MULTI_CONTROLS.items()
        ):
            continue
        matches.append(post)
    return matches


def projection(fixture: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    rows = filter_posts(fixture, state)
    geography = state["account_geography"]
    geography_flags = {
        "none": [],
        "country": ["US"],
        "hierarchy": ["CN", "HK"],
        "taiwan": ["CN"],
        "region": [],
    }[geography]
    geography_labels = {
        "none": {"en": None, "zh_cn": None},
        "country": {"en": "United States of America", "zh_cn": "美利坚合众国"},
        "hierarchy": {"en": "Hong Kong", "zh_cn": "香港"},
        "taiwan": {"en": "Taiwan", "zh_cn": "台湾"},
        "region": {"en": "Europe", "zh_cn": "欧洲"},
    }
    metadata_order = ["followers"]
    if state["role_badge"] == "official":
        metadata_order.append("role-official")
    if geography != "none":
        metadata_order.append("geography")
    if state["role_badge"] in {"staff", "community"}:
        metadata_order.append(f"role-{state['role_badge']}")
    hover_freeze_active = (
        state["chart_hover_freeze"] == "frozen"
        and int(state["filters"]["window"]) == 1
        and state["freeze_point"] in {"first", "same"}
    )
    series: dict[str, int] = {}
    for post in rows:
        for brand in post["brands"]:
            series[brand] = series.get(brand, 0) + 1
    return {
        "controls": deepcopy(state["filters"]),
        "accessibility": {
            "pulse_pressed": list(state["pulse_brands"]),
            "window_pressed": int(state["filters"]["window"]),
            "feed_text": state["feed_text"],
            "headline_detail": state["headline_detail"],
            "headline_expanded": state["headline_detail"] == "expanded",
            "role_badge": state["role_badge"],
            "role_label": None if state["role_badge"] == "none" else state["role_badge"],
            "account_geography": geography,
            "feed_inspection": state["feed_inspection"],
            "inspection_open": state["feed_inspection"] != "closed",
            "inspection_pinned": state["feed_inspection"] in {"pinned", "transferred"},
            "feed_navigation": state["feed_navigation"],
            "row_opens_original": False,
            "x_opens_original": state["feed_navigation"] == "x",
            "feed_pagination": state["feed_pagination"],
            "geography_flags": geography_flags,
            "geography_label": geography_labels[geography].get(
                state["locale"], geography_labels[geography]["en"]
            ),
            "geography_uses_tw_flag": False,
            "metadata_order": metadata_order,
            "chart_hover_freeze": state["chart_hover_freeze"],
            "freeze_point": state["freeze_point"],
            "locale_selected": [] if hover_freeze_active else [state["locale"]],
            "feed_title": "bucket_datetime" if hover_freeze_active else "default",
        },
        "persistence": {
            "locale": state["locale"],
            "timezone": state["timezone"],
            "brand_lens": state["brand_lens"],
            "nationalism_lens": state["nationalism_lens"],
            "filters": deepcopy(state["filters"]),
            "pulse_brands": list(state["pulse_brands"]),
        },
        "feed": [post["id"] for post in rows],
        "counts": len(rows),
        "chart": {
            "window": int(state["filters"]["window"]),
            "series": series,
        },
        "network": {
            "latest_generation": state["latest_generation"],
            "chart_refresh_paused": hover_freeze_active,
            "feed_refresh_paused": hover_freeze_active,
            "effective_feed_filters": (
                {
                    "brands": deepcopy(state["filters"]["brands"]),
                    "window": 1,
                }
                if hover_freeze_active
                else deepcopy(state["filters"])
            ),
            "bucket": "five-minute-half-open" if hover_freeze_active else None,
            "original_post_owner": "x" if state["feed_navigation"] == "x" else None,
            "pagination_has_total_ceiling": False,
            "pagination_exhausted": state["feed_pagination"] == "exhausted",
        },
    }
