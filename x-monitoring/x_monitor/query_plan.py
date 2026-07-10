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

v2 (plan 2026-07-11-002) — wide-net B-call revival:

  Post-U3, only 6 of 20 `enabled_models` brands had a per-cycle call
  (C1 covers 5 brands, C2 covers 1; the other 14 depended on Call A's
  curated X-list rate). Plan 2026-07-11-002 restores the v1.7 B1/B2/B3
  fan-out as additional `x_query_specs` entries — three specs that
  share the same `<tokens> (<co_occurrence>) min_faves:N` shape but
  source per-brand tokens from `brand_keywords.is_primary=1` rows via
  the new `primary_keywords` kwarg on `_build_query` / `plan_calls`.

  A new `is_wide_net: bool` flag on `XQuerySpec` (default False) lets
  the planner pick between two token sources at planning time:
    - `is_wide_net=False` (C-specs, the default): read from `spec.brands`.
    - `is_wide_net=True` (B1/B2/B3): read from `primary_keywords`
      pre-loaded by `RunPipeline.execute` via `Store.read_primary_brand_keywords`.

  KTD1 still holds: ONE renderer function, ONE union-of-paren-groups
  shape, ONE co-occurrence second group. See KTD2 in
  docs/plans/2026-07-11-002-feat-call-b-revival-via-x-query-specs-plan.md.

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

from dataclasses import dataclass, field
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

    Plan 2026-07-11-002 (U2) adds two new fields for the wide-net
    B-call revival:
        - `is_wide_net`: when True, the renderer reads per-brand tokens
          from a pre-loaded `primary_keywords` dict instead of `brands`.
        - `wide_net_brands`: the ordered list of brand_ids the planner
          iterates over when reading from `primary_keywords`. Each
          brand's primary tokens become one paren group; the union is
          rendered as the primary group, AND-filtered against
          `co_occurrence` as usual.

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
        call_id: stable label for this spec ("A", "B1", "B2", "B3",
            "C1", "C2", ...). For Call A, the planner auto-assigns "A"
            if empty.
        is_wide_net: when True, read per-brand tokens from
            `primary_keywords` (passed by the planner via the kwarg on
            `_build_query`/`plan_calls`) instead of from `spec.brands`.
            Default False. The renderer validates that `primary_keywords`
            is supplied when True — operator misconfiguration raises.
        wide_net_brands: ordered list of brand_ids the planner iterates
            when `is_wide_net=True`. Empty by default. Brands in this
            list that are missing from `primary_keywords` render as an
            empty paren (defensive — matches the existing all-empty
            branch).

    U9 (migration 022): `expected_signal` was REMOVED. The legacy
        6-signal taxonomy is gone.
    """
    brands: dict[str, list[str]]
    co_occurrence: list[str]
    min_faves: int = 0
    call_id: str = ""
    is_wide_net: bool = False
    wide_net_brands: list[str] = field(default_factory=list)


# Backwards-compat alias for any external imports still using the
# v1.7-era name. Marked deprecated; will be removed when the
# `data/queries/` runtime read path is fully retired (U3).
CallCBrandSpec = XQuerySpec


def _build_query(
    spec: XQuerySpec,
    *,
    x_monitor_list_id: int | str | None = None,
    primary_keywords: dict[str, list[str]] | None = None,
) -> str:
    """Compose one query from an XQuerySpec — the uniform renderer.

    Three documented spec kinds (KTD1 + plan 2026-07-11-002 KTD2):
      - Call A: `not spec.brands and not spec.is_wide_net`
                → `(list:<x_monitor_list_id>) min_faves:1`
      - Call C-body (default co-occurrence-constrained):
                → `(<spec.brands tokens>) (<co_occurrence>) min_faves:N`
      - Wide-net B-call (plan 2026-07-11-002, `spec.is_wide_net=True`):
                reads per-brand tokens from `primary_keywords` for
                each brand in `spec.wide_net_brands`. Renders the same
                `(<tokens>) (<co_occurrence>) min_faves:N` shape; the
                only difference is the token source.

    The Call A branch requires `x_monitor_list_id` to be passed in
    (the renderer doesn't read config itself). The wide-net branch
    requires `primary_keywords` (operator misconfiguration raises).
    Brands with empty token lists are skipped (defensive — should not
    happen in practice).
    """
    # Call A: list-based wide net (curated X-list). The
    # `is_wide_net=True` branch handles the wide-net path below; this
    # branch stays for the Call A degenerate (empty brands, empty
    # co_occurrence, list_id supplied).
    if not spec.is_wide_net and not spec.brands:
        if x_monitor_list_id is None:
            raise ValueError(
                "_build_query: Call A spec (empty brands) requires "
                "x_monitor_list_id to be passed in"
            )
        return f"(list:{x_monitor_list_id}) min_faves:1"

    # Wide-net B-call path (plan 2026-07-11-002): read per-brand
    # tokens from a pre-loaded primary_keywords dict instead of from
    # spec.brands. The renderer iterates spec.wide_net_brands (so the
    # brand order is operator-controlled via config.yaml, not
    # database iteration order).
    if spec.is_wide_net:
        if primary_keywords is None:
            raise ValueError(
                f"_build_query: wide-net spec {spec.call_id or '<unnamed>'} "
                f"requires primary_keywords to be passed in (load via "
                f"Store.read_primary_brand_keywords)"
            )
        parts: list[str] = []
        for brand_id in spec.wide_net_brands:
            toks = primary_keywords.get(brand_id, [])
            if not toks:
                continue
            parts.append(f"({' OR '.join(toks)})")
    else:
        parts = []
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
    *,
    primary_keywords: dict[str, list[str]] | None = None,
) -> list[PlannedCall]:
    """Build the per-cycle call list.

    v2 (plan 2026-07-11-001 + 2026-07-11-002 U2): a single uniform
    renderer handles every spec kind. The planner iterates
    ``x_query_specs`` and emits one ``PlannedCall`` per spec via
    ``_build_query``:
      - Call A: an XQuerySpec with empty `brands` and empty
        `co_occurrence`. Renders `(list:<x_monitor_list_id>) min_faves:1`.
      - Call C-body (and any future call kind with the same shape):
        the legacy `(<tokens>) (<co_occurrence>) min_faves:N` form.
      - Wide-net B-call (plan 2026-07-11-002): reads per-brand tokens
        from `primary_keywords` for each brand in `wide_net_brands`,
        renders the same `<tokens> (<co_occurrence>) min_faves:N`
        shape. The token source differs; the rendered form is identical.

    Args:
        x_monitor_list_id: numeric X list ID for Call A. Required — v2
            does not operate without a list, because Call A is the
            only place we get "faved by official handles" signal at
            scale. Pass through to `_build_query` for the Call A
            branch.
        x_query_specs: list of XQuerySpec (B1/B2/B3/C1/C2/etc.) — each
            spec emits one extra API call per cycle. Default: empty
            list (only Call A fires).
        primary_keywords: pre-loaded mapping of brand_id → primary
            tokens (read from `brand_keywords WHERE is_primary=1`).
            Required when any spec in `x_query_specs` has
            `is_wide_net=True`. Not used by non-wide-net specs. The
            planner does not load DB itself — the caller (typically
            `RunPipeline.execute`) loads once via
            `Store.read_primary_brand_keywords` and threads the result
            through.

    Returns:
        [Call A, *x_query_specs]. Each call has already been
        length-capped.

    Raises:
        TypeError: if x_monitor_list_id is not provided.
        ValueError: if any emitted query exceeds 512 chars
            (propagated from `assert_under_length_cap`), or if a
            wide-net spec is missing `primary_keywords`.
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
            spec,
            x_monitor_list_id=x_monitor_list_id,
            primary_keywords=primary_keywords,
        )
        assert_under_length_cap(call_query)
        # Pick a placeholder brand_id for raw-file naming
        # (one raw file per call) — prefer an explicit `call_id` from
        # the spec, else the first brand in iteration order, else "*".
        if spec.call_id:
            c_label = spec.call_id
            if spec.is_wide_net and spec.wide_net_brands:
                c_brand_placeholder = spec.wide_net_brands[0]
            else:
                c_brand_placeholder = next(iter(spec.brands), "*")
        else:
            c_label = f"C{i+1}"
            if spec.is_wide_net and spec.wide_net_brands:
                c_brand_placeholder = spec.wide_net_brands[0]
            else:
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
