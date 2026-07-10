# {{AGENT_ATTRIBUTION}}
"""Per-cycle call planning for x-monitor.

v1.7 redesign (2026-06-17):

The v1.6 plan emitted 7-15 calls per cycle (one account call per brand +
3 intent buckets, sometimes split across multiple calls to fit the old
22-OR operator cap). The empirical cap probe on 2026-06-17 confirmed the
real cap is **character length** (~512, per docs.x.com), not operator
count — and that the `list:<id>` operator (~12 chars) returns tweets
from any list (public or private) without scaling the query string.

v1.7 collapses all per-cycle work to **2 calls** by default.

v1.7.x (call_c_specs) and v2 (x_query_specs):

  Every per-cycle TwitterAPI call conforms to the same
  `<tokens> (<co_occurrence>) min_faves:N` shape. The renderer is one
  function (`_build_query`) that handles two spec kinds via one
  documented branch:
    - Call A: `not spec.brands` → `(list:<x_monitor_list_id>) min_faves:1`
    - Call C-body (any other spec): `(<tokens>) (<co_occurrence>) min_faves:N`
  KTD1 forbids additional renderers per call kind; if a future Call D
  is added, it must conform to the same shape or this KTD is revised.

The legacy v1.6 "Call B" (a separate per-brand-wider call with its own
renderer) was retired in plan 2026-07-11-001 — the per-brand yamls are
gone and the curated X-list (Call A) plus the `x_query_specs` co-occurrence
specs (Call C) cover the same ground with one renderer and no runtime
yaml reads.

Configured via `x_query_specs:` in config.yaml; default empty list emits
no calls beyond Call A.

U9 (migration 022): the legacy 6-signal `expected_signal` field was
removed from PlannedCall and XQuerySpec. Per-tweet classification
(post_type × sentiment) is post-fetch in `attribution.classify_post`
and applied per-brand in `store.insert_posts`. The query shape no
longer encodes signal intent — the structure is one wide net, one
targeted net.

Length cap guard: `assert_under_length_cap` is called on every emitted
query so an over-cap query short-circuits to a per-query summary entry
(status: "length_cap_exceeded") and no credits are burned.

The retired v1.6 `INTENT_BUCKETS`, `_split_brands_to_fit_cap`,
`_compose_intent_query`, the v1.7-era `parse_brand_tokens`,
`_parse_first_paren_group`, and `_build_brand_wide_query` are gone.
Tests assert their absence (see test_query_plan_uniform.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .queries import X_LENGTH_CAP, assert_under_length_cap


CallKind = Literal["account", "brand_wide"]


@dataclass
class PlannedCall:
    """A single API call to fire this cycle.

    Attributes:
        call_id: human label for the call ("A", "B", "C1", "C2", ...).
            Stable across cycles; useful for logging/dedup/raw-file
            naming alongside brand_id+call_kind.
        call_kind: "account" = list-based fan-in (Call A in v1.7);
            "brand_wide" = paren-grouped brand-token OR-chain (Call B
            or Call C variants).
        brand_id: brand this call is attributed to. For Call A
            (list-based), this is "*" because the list spans all
            brands — post-fetch `attribute_to_brands` reassigns. For
            Call B, this is the FIRST brand in the input order (used
            as a placeholder for `source_query_id`; same reassignment
            applies). For Call C, this is the spec's brand_id (the
            call's primary target).
        bucket: None for both v1.7 call kinds. Retained for schema
            stability with the v1.6 contract.
        query_string: the actual X advanced-search query.
        query_length: len(query_string) in characters. Verified under
            `X_LENGTH_CAP` (512) before being returned.

    U9 (migration 022): `expected_signal` was REMOVED. The legacy
        6-signal taxonomy is gone; per-tweet classification
        (post_type × sentiment) happens post-fetch and is not encoded
        in the query shape.
    """

    call_id: str
    call_kind: CallKind
    brand_id: str
    bucket: str | None
    query_string: str
    query_length: int


@dataclass
class XQuerySpec:
    """One entry in config.yaml's `x_query_specs:` block.

    Plan 2026-07-11-001 retires the v1.7-era CallCBrandSpec name. The
    schema is identical — only the type name changed so that Call A
    (list-based wide net) and Call C (co-occurrence-constrained) can
    share the same uniform renderer.

    Attributes:
        brands: {brand_id: [tokens, ...]} mapping. Empty for Call A
            (the renderer substitutes the curated X-list). For Call C
            (and any future call kind with a per-brand token group),
            each brand's tokens are OR-joined inside a paren; the
            per-brand paren groups are then OR-joined into the outer
            primary group.
        co_occurrence: list of co-occurrence terms to OR-join in the
            secondary group. Shared across all brands in this spec.
            For Call A, this list is semantically inert — the renderer
            substitutes the list-based form. Posts must match at least
            one term from the primary group AND at least one term from
            the co_occurrence group (implicit AND between the two
            parenthesised groups in X advanced-search syntax).
        min_faves: lower bound on the call's min_faves. 0 by default
            (no lower bound). For Call A the renderer hard-codes 1
            regardless of this field.
        call_id: stable label for this spec ("A", "C1", "C2", ...).
            For Call A, the planner auto-assigns "A" if empty.

    U9 (migration 022): `expected_signal` was REMOVED. The legacy
        6-signal taxonomy is gone.
    """
    brands: dict[str, list[str]]
    co_occurrence: list[str]
    min_faves: int = 0
    call_id: str = ""


# Backwards-compat alias for any external imports still using the
# v1.7-era name. Marked deprecated; will be removed when the
# `data/queries/` runtime read path is fully retired (U3).
CallCBrandSpec = XQuerySpec


def _build_query(
    spec: XQuerySpec,
    *,
    x_monitor_list_id: int | str | None = None,
) -> str:
    """Compose one query from an XQuerySpec — the uniform renderer.

    Two documented spec kinds (KTD1):
      - Call A: `not spec.brands` → `(list:<x_monitor_list_id>) min_faves:1`
      - Call C-body (any other spec): `(<tokens>) (<co_occurrence>) min_faves:N`

    The Call A branch requires `x_monitor_list_id` to be passed in
    (the renderer doesn't read config itself). The Call C body branch
    is the legacy v1.7 `_build_call_c_query` logic with no other
    behavioral change.

    Brands with empty token lists are skipped (defensive — should not
    happen in practice).
    """
    if not spec.brands:
        # Call A — the curated X-list wide net.
        if x_monitor_list_id is None:
            raise ValueError(
                "_build_query: Call A spec (empty brands) requires "
                "x_monitor_list_id to be passed in"
            )
        return f"(list:{x_monitor_list_id}) min_faves:1"

    parts: list[str] = []
    for _brand_id, toks in spec.brands.items():
        if not toks:
            continue
        parts.append(f"({' OR '.join(toks)})")
    if not parts:
        # Defensive — should not happen at the operator baseline, but
        # an all-empty configuration still returns a syntactically
        # valid (if useless) query.
        primary = "(empty)"
    else:
        primary = f"({' OR '.join(parts)})"
    secondary = f"({' OR '.join(spec.co_occurrence)})"
    return f"{primary} {secondary} min_faves:{spec.min_faves}"


# Retired v1.7-era helpers — removed in plan 2026-07-11-001 (U2).
# The runtime no longer reads `data/queries/<brand>.yaml`; per-brand
# tokens come from `brand_keywords` (DB) via `Store.read_brand_keywords`.
# Kept as `hasattr() == False` markers in test_query_plan_uniform.py.
# def parse_brand_tokens(...): ...
# def _parse_first_paren_group(...): ...
# def _build_brand_wide_query(...): ...


def plan_calls(
    x_monitor_list_id: int | str,
    x_query_specs: list[XQuerySpec] | None = None,
) -> list[PlannedCall]:
    """Build the per-cycle call list.

    v2 (plan 2026-07-11-001): a single uniform renderer handles every
    spec kind. The planner iterates ``x_query_specs`` and emits one
    ``PlannedCall`` per spec via ``_build_query``:
      - Call A: an XQuerySpec with empty `brands` and empty
        `co_occurrence`. Renders `(list:<x_monitor_list_id>) min_faves:1`.
      - Call C-body (and any future call kind with the same shape):
        the legacy `(<tokens>) (<co_occurrence>) min_faves:N` form.

    Args:
        x_monitor_list_id: numeric X list ID for Call A. Required — v2
            does not operate without a list, because Call A is the
            only place we get "faved by official handles" signal at
            scale. Pass through to `_build_query` for the Call A
            branch.
        x_query_specs: list of XQuerySpec (C1/C2/etc.) — each spec
            emits one extra API call per cycle. Default: empty list
            (only Call A fires).

    Returns:
        [Call A, *x_query_specs]. Each call has already been
        length-capped.

    Raises:
        TypeError: if x_monitor_list_id is not provided.
        ValueError: if any emitted query exceeds 512 chars
            (propagated from `assert_under_length_cap`).
    """
    if x_monitor_list_id is None:
        raise TypeError(
            "plan_calls() requires x_monitor_list_id (v2's Call A is "
            "list-based; no fallback to per-brand account calls)."
        )

    result: list[PlannedCall] = []

    # Call A — synthesized from the configured list ID. It is NOT
    # carried in x_query_specs; the spec field is reserved for
    # per-cycle co-occurrence specs. Render the Call A degenerate
    # case via the same uniform renderer so the dispatch is
    # well-tested.
    call_a_spec = XQuerySpec(
        brands={}, co_occurrence=[], min_faves=1, call_id="A"
    )
    call_a_query = _build_query(
        call_a_spec, x_monitor_list_id=x_monitor_list_id
    )
    assert_under_length_cap(call_a_query)
    result.append(
        PlannedCall(
            call_id="A",
            call_kind="account",
            brand_id="*",
            bucket=None,
            query_string=call_a_query,
            query_length=len(call_a_query),
        )
    )

    for i, spec in enumerate(x_query_specs or []):
        call_query = _build_query(
            spec, x_monitor_list_id=x_monitor_list_id
        )
        assert_under_length_cap(call_query)
        # Pick a placeholder brand_id for raw-file naming
        # (one raw file per call) — prefer an explicit `call_id` from
        # the spec, else the first brand in iteration order, else "*".
        if spec.call_id:
            c_label = spec.call_id
            c_brand_placeholder = next(iter(spec.brands), "*")
        else:
            c_label = f"C{i+1}"
            c_brand_placeholder = next(iter(spec.brands), "*")
        result.append(
            PlannedCall(
                call_id=c_label,
                call_kind="brand_wide",
                brand_id=c_brand_placeholder,
                bucket=None,
                query_string=call_query,
                query_length=len(call_query),
            )
        )
    return result


# Retired v1.7-era symbols — referenced in tests as `hasattr() == False`.
# Kept here ONLY as a structural marker; do not uncomment or call.
# def _split_brands_to_fit_cap(...): ...
# INTENT_BUCKETS: dict = {}  # removed in v1.7
# _build_call_c_query(...) -- removed in v2 (renamed to _build_query)
# _build_brand_wide_query(...) -- removed in v2 (Call B retired)
# parse_brand_tokens(...) -- removed in v2 (no runtime yaml read)
# _parse_first_paren_group(...) -- removed in v2 (no runtime yaml read)
