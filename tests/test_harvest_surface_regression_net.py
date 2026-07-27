"""U6 regression net: pin the harvest surface that must NOT drift.

Plan: docs/plans/2026-07-27-002-fix-v2-harvest-cursor-regression-plan.md
Unit U6 (R10).

WHY THIS FILE EXISTS
--------------------
In July 2026 the v2 harvest silently collected ~half of what v1 collected
(~1,150/day vs ~2,000-2,400/day).  A stage-by-stage diff of the two
implementations found the causes were behavioral (a missing incremental
cursor, and a missing quote-tweet channel) -- but it also confirmed a long
list of surface values that were *identical* between v1 and v2 and therefore
innocent: the call set, the per-call caps, brand coverage, and query length.

Those innocent values are exactly the things that can drift later without
anyone noticing, because none of them fail loudly:

  * drop a call from the plan   -> collection falls, nothing errors
  * lower max_pages             -> per-call ceiling falls, nothing errors
  * add a brand but no query    -> that brand collects zero, nothing errors
  * push a query over 512 chars -> TwitterAPI.io returns ZERO RESULTS with
                                   NO ERROR (see x_monitor/queries.py)

So this module pins them.  Sibling file
`test_harvest_cursor_regression_net.py` (U3) pins the cursor behavior that
actually *broke*; this file pins the parts that were *fine* and must stay
fine.

THESE ARE DELIBERATE CHANGE-DETECTOR ASSERTIONS.
If you changed one of these values on purpose, update the pinned constant
below in the same commit -- that edit is the audit trail proving the volume
change was intended.  Do not "fix" a failure here by loosening the assert.

WHAT IS DELIBERATELY *NOT* PINNED
---------------------------------
The rendered query text.  Keyword edits are normal, expected, and frequent;
pinning the exact string would make this file pure noise and it would get
deleted.  We pin the *shape* and the *budget*, not the content.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from x_monitor.config import load_config
from x_monitor.queries import X_LENGTH_CAP
from x_monitor.query_plan import MIN_FAVES_FOR_LIST_CALL, plan_calls


REPO_ROOT = Path(__file__).resolve().parent.parent
CFG_PATH = REPO_ROOT / "config.yaml"

# The core models declare db_collation="case_insensitive", a Postgres ICU
# collation SQLite cannot create, so every django_db test in this repo errors
# on a SQLite DATABASE_URL (pre-existing condition, not specific to this
# module -- see tests/test_classification_labels.py).  The DB-backed
# assertions below are the *stronger* form of the config-only ones, so we skip
# rather than fail when the DB cannot be built: the config-only tests still
# pin the surface everywhere, and CI/Postgres runs get the full check.


# --- pinned baseline, measured 2026-07-27 ----------------------------------

# The 6 calls fired per cycle: Call A (list-based fan-in) + 5 B/C specs.
EXPECTED_CALL_IDS = {"A", "C1", "C2", "B1", "B2", "B3"}

# Call A is the list fan-in; every B/C spec is a paren-grouped token query.
EXPECTED_CALL_KINDS = {
    "A": "account",
    "C1": "brand_wide",
    "C2": "brand_wide",
    "B1": "brand_wide",
    "B2": "brand_wide",
    "B3": "brand_wide",
}

# B* specs read tokens from brand_keywords (wide net); C* specs carry their
# own explicit brand->token map.  A flipped flag silently changes the token
# source for that call.
EXPECTED_WIDE_NET = {"B1": True, "B2": True, "B3": True, "C1": False, "C2": False}

# Per-call ceiling is max_pages * max_per_page = 100 tweets.  Lowering any of
# these directly caps collection volume.
EXPECTED_MAX_RESULTS = 50
EXPECTED_MAX_PAGES = 5
EXPECTED_MAX_PER_PAGE = 20

# Union of brands covered across the 5 specs.
EXPECTED_BRAND_COVERAGE_COUNT = 20

# The exact set, so swapping a brand for a typo of the same length still fails.
EXPECTED_COVERED_BRANDS = {
    # C1
    "llama", "mimo", "moonshot_kimi", "yi",
    # C2
    "ernie", "upstage",
    # B1
    "deepseek", "hunyuan", "minimax", "mistral", "qwen", "stepfun",
    # B2
    "doubao", "glm", "inclusionai", "sensechat",
    # B3
    "exaone", "kuaishou", "nemo_megatron", "sakana_ai",
}

# The two inline time operators the cursor fix injects into every scheduled
# query.  Epoch seconds are 10 digits until 2286, so this width is stable.
TIME_OPERATOR_OVERHEAD = len(" since_time:1784700000 until_time:1784700060")
EXPECTED_TIME_OPERATOR_OVERHEAD = 44

# C1 is the canary: the longest query, with the least room for the operators.
TIGHTEST_CALL_ID = "C1"
EXPECTED_TIGHTEST_HEADROOM = 7


@pytest.fixture(scope="module")
def cfg():
    return load_config(CFG_PATH)


@pytest.fixture(scope="module")
def planned_calls(cfg):
    """Build the real per-cycle call list through the production planner.

    Deriving through `plan_calls` (rather than reading config directly) means
    a planner regression -- a dropped call, a changed call_kind -- fails here
    too, not just a config edit.

    Primary keywords are stubbed one-token-per-brand: this module asserts on
    call *shape* and *budget*, and the headroom test below re-derives real
    lengths from the live keyword table separately.
    """
    specs = cfg.x_query_specs
    brands: set[str] = set()
    for spec in specs:
        brands.update(spec.wide_net_brands or [] if spec.is_wide_net else spec.brands)
    primary_keywords = {b: [b] for b in sorted(brands)}
    return plan_calls(
        cfg.x_monitor_list_id, specs, primary_keywords=primary_keywords
    )


# --- call set ------------------------------------------------------------


def test_call_set_is_exactly_six(planned_calls):
    """Adding or dropping a call changes collection volume directly.

    If this fails, a call was added or removed from the cycle. Update
    EXPECTED_CALL_IDS in the same commit to record that the volume change
    was intentional.
    """
    actual = {c.call_id for c in planned_calls}
    assert actual == EXPECTED_CALL_IDS, (
        f"per-cycle call set changed: {actual} != {EXPECTED_CALL_IDS}. "
        "Each call is an independent search; adding/removing one moves daily "
        "collection volume. Update EXPECTED_CALL_IDS if this was intended."
    )
    assert len(planned_calls) == len(EXPECTED_CALL_IDS), (
        f"expected {len(EXPECTED_CALL_IDS)} planned calls, got "
        f"{len(planned_calls)} (duplicate call_id?)"
    )


def test_call_kinds_are_pinned(planned_calls):
    """call_kind selects the query renderer AND is part of the cursor key."""
    actual = {c.call_id: c.call_kind for c in planned_calls}
    assert actual == EXPECTED_CALL_KINDS, (
        f"call_kind mapping changed: {actual} != {EXPECTED_CALL_KINDS}. "
        "call_kind is part of the call_state cursor identity tuple, so a "
        "change here orphans existing cursor rows."
    )


def test_wide_net_flags_are_pinned(cfg):
    """Wide-net specs read tokens from the DB; non-wide-net carry their own."""
    actual = {
        s.call_id: bool(s.is_wide_net) for s in cfg.x_query_specs
    }
    assert actual == EXPECTED_WIDE_NET, (
        f"is_wide_net flags changed: {actual} != {EXPECTED_WIDE_NET}. "
        "Flipping this silently changes which tokens a call searches for."
    )


# --- caps ----------------------------------------------------------------


def test_per_call_caps_are_pinned(cfg):
    """Per-call ceiling is max_pages * max_per_page; lowering caps volume."""
    search = cfg.search
    assert search.max_results == EXPECTED_MAX_RESULTS, (
        f"search.max_results {search.max_results} != {EXPECTED_MAX_RESULTS}; "
        "this caps tweets returned per call."
    )
    assert search.max_pages == EXPECTED_MAX_PAGES, (
        f"search.max_pages {search.max_pages} != {EXPECTED_MAX_PAGES}; "
        "per-call ceiling is max_pages * max_per_page."
    )
    assert search.max_per_page == EXPECTED_MAX_PER_PAGE, (
        f"search.max_per_page {search.max_per_page} != "
        f"{EXPECTED_MAX_PER_PAGE}; this is the platform page size."
    )


def test_min_faves_is_zero_across_specs(cfg):
    """A raised min_faves silently drops posts that qualify today."""
    for spec in cfg.x_query_specs:
        assert spec.min_faves == 0, (
            f"spec {spec.call_id} has min_faves={spec.min_faves}; a non-zero "
            "threshold excludes low-engagement posts we currently collect."
        )
    assert MIN_FAVES_FOR_LIST_CALL == 0, (
        f"MIN_FAVES_FOR_LIST_CALL is {MIN_FAVES_FOR_LIST_CALL}; Call A would "
        "stop returning low-engagement posts from the list."
    )


# --- brand coverage ------------------------------------------------------


def test_every_spec_brand_is_covered_exactly_once_or_more(cfg):
    """A brand present in config but wired into no query collects zero.

    This is a silent failure mode: the brand shows up in the dashboard with a
    flat zero line and nothing errors.

    Pins the SET, not just the count. An earlier version asserted only
    `len(covered) == 20`, which would happily pass if `minimax` were dropped
    from every spec and a misspelled `minimaxx` added somewhere else -- the
    exact drift this test exists to catch.
    """
    covered: set[str] = set()
    for spec in cfg.x_query_specs:
        covered.update(
            spec.wide_net_brands or [] if spec.is_wide_net else spec.brands
        )
    missing = EXPECTED_COVERED_BRANDS - covered
    added = covered - EXPECTED_COVERED_BRANDS
    assert not missing and not added, (
        f"search-spec brand coverage drifted. Missing (now collect nothing): "
        f"{sorted(missing) or 'none'}. Added: {sorted(added) or 'none'}. "
        "A brand wired into no spec silently collects zero forever; update "
        "EXPECTED_COVERED_BRANDS in the same commit if this was intended."
    )
    assert len(covered) == EXPECTED_BRAND_COVERAGE_COUNT


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_enabled_db_brands_are_all_covered_by_some_spec(cfg):
    """Every non-sentinel brand in the DB must appear in some spec.

    Skips when the brand table is unseeded (fresh test DB) -- the coverage
    count above still pins the config side.
    """
    from core.models import Brand

    db_brands = set(
        Brand.objects.filter(is_sentinel=False).values_list("nickname", flat=True)
    )
    if not db_brands:
        pytest.skip("brands table not seeded in this test DB")

    covered: set[str] = set()
    for spec in cfg.x_query_specs:
        covered.update(
            spec.wide_net_brands or [] if spec.is_wide_net else spec.brands
        )
    uncovered = {b for b in db_brands if b not in covered}
    assert not uncovered, (
        f"brands in DB but wired into no search spec: {sorted(uncovered)}. "
        "These collect zero posts forever and fail silently."
    )


# --- query length budget (the highest-value assertion here) --------------


def test_time_operator_overhead_is_pinned():
    """If the operator format changes, the headroom math must be re-derived."""
    assert TIME_OPERATOR_OVERHEAD == EXPECTED_TIME_OPERATOR_OVERHEAD, (
        f"time-operator overhead is {TIME_OPERATOR_OVERHEAD} chars, expected "
        f"{EXPECTED_TIME_OPERATOR_OVERHEAD}. The headroom assertions below "
        "budget for this exact width."
    )


def test_every_query_fits_the_cap_after_time_operators(planned_calls):
    """THE CANARY.

    `assert_under_length_cap` runs inside plan_calls on the PRE-injection
    query, so it cannot see the ~44 chars the cursor's time operators add.
    An over-cap query is the worst failure mode in this system:
    TwitterAPI.io returns zero results with NO error, the call looks like a
    quiet window, and the cursor advances straight past the skipped span.

    If this fails, a query grew too long. Shorten that spec's tokens -- do
    NOT raise the cap; 512 is the platform limit.
    """
    for call in planned_calls:
        post_injection = call.query_length + TIME_OPERATOR_OVERHEAD
        assert post_injection <= X_LENGTH_CAP, (
            f"call {call.call_id} is {call.query_length} chars, "
            f"{post_injection} after time operators -- over the "
            f"{X_LENGTH_CAP} cap by {post_injection - X_LENGTH_CAP}. "
            "TwitterAPI.io will return ZERO RESULTS with no error and the "
            "cursor will skip that window permanently. Shorten the spec."
        )


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_tightest_call_headroom_with_real_keywords(cfg):
    """Pin the actual margin on the tightest call using real DB keywords.

    The stubbed keywords in `planned_calls` understate B* query lengths, so
    this test rebuilds the plan from the live brand_keywords table -- the
    same source production uses -- and asserts the real margin.

    C1 measured 461 base -> 505 post-injection -> 7 chars spare on
    2026-07-27. A ~10-char keyword addition to C1 trips this.
    """
    from monitor.cycle import _load_primary_keywords

    primary_keywords = _load_primary_keywords()
    if not primary_keywords:
        pytest.skip("brand_keywords not seeded in this test DB")

    calls = plan_calls(
        cfg.x_monitor_list_id, cfg.x_query_specs, primary_keywords=primary_keywords
    )
    headroom = {
        c.call_id: X_LENGTH_CAP - (c.query_length + TIME_OPERATOR_OVERHEAD)
        for c in calls
    }
    tightest = min(headroom, key=lambda k: headroom[k])
    assert all(v >= 0 for v in headroom.values()), (
        f"a query exceeds the {X_LENGTH_CAP} cap after time operators: "
        f"{headroom}. See test_every_query_fits_the_cap_after_time_operators."
    )
    assert tightest == TIGHTEST_CALL_ID, (
        f"tightest call is now {tightest} (headroom {headroom}), expected "
        f"{TIGHTEST_CALL_ID}. Update TIGHTEST_CALL_ID and "
        "EXPECTED_TIGHTEST_HEADROOM together."
    )
    assert headroom[TIGHTEST_CALL_ID] == EXPECTED_TIGHTEST_HEADROOM, (
        f"{TIGHTEST_CALL_ID} headroom is {headroom[TIGHTEST_CALL_ID]}, pinned "
        f"at {EXPECTED_TIGHTEST_HEADROOM}. If you shortened the query that is "
        "good news -- update the constant. If you lengthened it, you are "
        f"{EXPECTED_TIGHTEST_HEADROOM - headroom[TIGHTEST_CALL_ID]} chars "
        "closer to a silent zero-result call."
    )
