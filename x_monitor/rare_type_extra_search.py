"""Rare-type extra-search query in harvest PlannedCall shape.

Harvest renders ``(<groups OR-ed>) min_faves:N`` then CycleRunner injects
``since_time`` / ``until_time`` via TwitterApiClient.run_search kwargs.
A bare ``A OR B OR C min_faves:0 since_time:T`` only time-filters the last
clause (X AND binds tighter than OR). The outer paren is the same wrap
``query_plan._build_query`` uses when there is more than one brand group.
"""

from __future__ import annotations

import re

from x_monitor.apify import TwitterApiClient
from x_monitor.queries import assert_under_length_cap

QUERY_VERSION = "rare-types-v3-provisional-2026-09-23"

# This matrix proves only inspectable local query shape. Provider interpretation
# must be established separately with trial evidence.
QUERY_COVERAGE: tuple[dict[str, str], ...] = tuple(
    {
        "coverage": coverage,
        "proof": "local_query_shape",
        "provider_semantics": "unverified",
        "overlap_boundary": (
            "current_policy_B2_overlap_known"
            if coverage == "catalog_handle_only"
            else "no_zero_overlap_claim"
        ),
    }
    for coverage in (
        "personnel_en",
        "personnel_zh_cn",
        "personnel_ja",
        "catalog_handle_only",
        "unknown_ai_employer",
        "narrow_ml_jobs",
        "bounded_events",
        "bounded_opportunities",
        "unbranded_release_token",
    )
)

# Inner groups are AND-shaped like co-occurrence calls. The historical seed is
# retained under tests/fixtures. Its named labs remain context terms while the
# first-person family can also match an unknown employer when the post supplies
# AI/LLM/ML context.
RARE_TYPE_EXTRA_SEARCH_GROUPS: tuple[str, ...] = (
    (
        '("I\'ve joined" OR "I joined" OR "I left" OR "我加入" OR "我离开" '
        'OR 出任 OR 换帅 OR に入社 OR を退職) '
        '(AI OR LLM OR OpenAI OR Anthropic)'
    ),
    '("I\'ve joined @deepseek_ai")',
    (
        '("we\'re hiring" OR "currently hiring" OR 招聘 OR 募集中) '
        '(engineer OR researcher)'
    ),
    '("we\'ll be at" OR 登壇) ("AI conference" OR summit)',
    (
        '("applications open" OR "apply by" OR 申请) '
        '(hackathon OR fellowship) (AI OR LLM)'
    ),
    '(introducing OR 开源 OR 发布) (model OR weights OR Preview)',
    '("step 5 preview")',
)

_INLINE_OPERATOR_RE = re.compile(
    r"\b(?:since_time|until_time|min_faves):", re.IGNORECASE
)
_UNSUPPORTED_EXCLUSION_RE = re.compile(r"(^|\s)-[@A-Za-z]", re.IGNORECASE)


def _validate_query_inputs(*, since_time: int, until_time: int, min_faves: int) -> None:
    for name, value in (("since_time", since_time), ("until_time", until_time)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} time must be an integer epoch")
        if value <= 0 or len(str(value)) > 11:
            raise ValueError(
                f"{name} time must be a positive epoch of at most 11 digits"
            )
    if since_time >= until_time:
        raise ValueError("since_time time must be earlier than until_time")
    if isinstance(min_faves, bool) or not isinstance(min_faves, int):
        raise TypeError("min_faves must be an integer")
    if min_faves != 0:
        raise ValueError("rare-type extra search requires min_faves:0")

    body = " OR ".join(RARE_TYPE_EXTRA_SEARCH_GROUPS)
    if _INLINE_OPERATOR_RE.search(body):
        raise ValueError("query body contains a misplaced inline operator")
    if _UNSUPPORTED_EXCLUSION_RE.search(body):
        raise ValueError("query body contains an unsupported exclusion operator")


def planned_query_string(*, min_faves: int = 0) -> str:
    """Return the PlannedCall.query_string (no time operators)."""

    primary = f"({' OR '.join(RARE_TYPE_EXTRA_SEARCH_GROUPS)})"
    return f"{primary} min_faves:{int(min_faves)}"


def render_rare_type_extra_search_query(
    *,
    since_time: int,
    until_time: int,
    min_faves: int = 0,
) -> str:
    """Return the provider-rendered query after time-operator injection."""

    _validate_query_inputs(
        since_time=since_time,
        until_time=until_time,
        min_faves=min_faves,
    )
    query_string = planned_query_string(min_faves=min_faves)
    rendered = TwitterApiClient._effective_search_query(
        query_string,
        since=None,
        since_time=int(since_time),
        until_time=int(until_time),
    )
    assert_under_length_cap(rendered)
    return rendered
