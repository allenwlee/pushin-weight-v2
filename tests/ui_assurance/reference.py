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
    elif control in {"locale", "timezone", "brand_lens", "nationalism_lens"}:
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
    series: dict[str, int] = {}
    for post in rows:
        for brand in post["brands"]:
            series[brand] = series.get(brand, 0) + 1
    return {
        "controls": deepcopy(state["filters"]),
        "accessibility": {
            "pulse_pressed": list(state["pulse_brands"]),
            "window_pressed": int(state["filters"]["window"]),
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
        "network": {"latest_generation": state["latest_generation"]},
    }
