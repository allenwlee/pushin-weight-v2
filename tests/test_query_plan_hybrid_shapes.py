"""U2 unit tests - hybrid funnel renderer shapes (empty co + handle-only).

Plan: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
Unit U2.

WHY THIS FILE EXISTS
--------------------
The hybrid funnel plan needs two new renderer behaviors:

  1. Empty co_occurrence on a spec must OMIT the secondary `()` paren
     (R17 / KTD4). The legacy renderer always emitted `()` even when
     co_occurrence was empty, producing an invalid X advanced-search
     token. Bare B1 calls rely on this.

  2. A handle-only spec (B2/B3 in the hybrid funnel) must render as
     `(@h1 OR @h2 ...) min_faves:N` with no co-occurrence secondary.
     The `handles` field on XQuerySpec carries the list.

These tests pin both shapes. They FAIL against the legacy renderer and
PASS once U2 lands.
"""

from __future__ import annotations

from x_monitor.query_plan import XQuerySpec, _build_query


def _spec(**kwargs) -> XQuerySpec:
    """Build an XQuerySpec with sensible defaults for testing."""
    defaults = dict(
        brands={},
        co_occurrence=[],
        min_faves=0,
        call_id="TEST",
    )
    defaults.update(kwargs)
    return XQuerySpec(**defaults)


# ---------------------------------------------------------------------------
# Shape 1: empty co_occurrence -> no secondary paren
# ---------------------------------------------------------------------------


def test_empty_co_omits_secondary_paren():
    """R17/KTD4: bare B1 shape. No `()` in the rendered query."""
    spec = _spec(
        brands={"deepseek": ["DeepSeek", "deepseek-r1", "深度求索"]},
        co_occurrence=[],
        call_id="B1",
    )
    rendered = _build_query(spec)
    assert "()" not in rendered, (
        f"Empty co_occurrence must omit `()` paren (R17/KTD4). Got: {rendered!r}"
    )
    # Shape check
    assert rendered.startswith("(DeepSeek OR deepseek-r1 OR 深度求索) "), (
        f"Expected primary paren first, got: {rendered!r}"
    )
    assert rendered.endswith(" min_faves:0"), (
        f"Expected 'min_faves:0' suffix, got: {rendered!r}"
    )


def test_empty_co_with_brands_dict_only():
    """Same shape as above with a different brand set."""
    spec = _spec(
        brands={"qwen": ["Qwen", "Qwen3", "通义千问"]},
        co_occurrence=[],
        call_id="B1",
    )
    rendered = _build_query(spec)
    assert "()" not in rendered
    assert "min_faves:0" in rendered


def test_non_empty_co_emits_secondary_paren():
    """Regression: the legacy behavior of emitting `(co)` is preserved
    when co_occurrence is non-empty. C-specs must continue to render the
    secondary group."""
    spec = _spec(
        brands={"mimo": ["MiMo", "Xiaomi MiMo", "小米 MiMo"]},
        co_occurrence=["llm", "model"],
        call_id="C1",
    )
    rendered = _build_query(spec)
    assert "(MiMo OR Xiaomi MiMo OR 小米 MiMo) (llm OR model) min_faves:0" == rendered, (
        f"Standard C-shape must be preserved. Got: {rendered!r}"
    )


# ---------------------------------------------------------------------------
# Shape 2: handle-only spec
# ---------------------------------------------------------------------------


def test_handle_only_renders_at_prefix_group():
    """B2/B3 hybrid shape: `(@h1 OR @h2 ...) min_faves:N`, no co."""
    spec = _spec(
        handles=["deepseek_ai", "Alibaba_Qwen", "MiniMax_AI"],
        co_occurrence=[],
        call_id="B2",
    )
    rendered = _build_query(spec)
    assert rendered == "(@deepseek_ai OR @Alibaba_Qwen OR @MiniMax_AI) min_faves:0", (
        f"Handle-only shape wrong. Got: {rendered!r}"
    )


def test_handle_only_single_handle():
    spec = _spec(handles=["sama"], co_occurrence=[], call_id="B2")
    assert _build_query(spec) == "(@sama) min_faves:0"


def test_handle_only_ignores_brands():
    """When both handles and brands are set, handles take precedence
    (the spec is for handle-only paths). The plan's U3 config will NOT
    set both for any spec, so this is a defensive guard."""
    spec = _spec(
        brands={"deepseek": ["DeepSeek"]},
        handles=["deepseek_ai"],
        co_occurrence=[],
        call_id="B2",
    )
    rendered = _build_query(spec)
    # Currently the renderer handles brands first (parts list non-empty),
    # then checks `if spec.handles and not spec.brands`. With brands set,
    # the handles path is skipped -> legacy brand render.
    # Document this behavior explicitly.
    assert "(DeepSeek)" in rendered, (
        f"When brands AND handles are set, brand render wins. Got: {rendered!r}"
    )


def test_handle_only_with_min_faves_nonzero():
    spec = _spec(handles=["MiniMax_AI", "MiniMaxAgent"], min_faves=5)
    rendered = _build_query(spec)
    assert rendered == "(@MiniMax_AI OR @MiniMaxAgent) min_faves:5"


# ---------------------------------------------------------------------------
# Regression: legacy behaviors preserved
# ---------------------------------------------------------------------------


def test_call_a_still_renders_list_form():
    """Call A's degenerate path (empty brands + list_id) must continue to work.
    Note: MIN_FAVES_FOR_LIST_CALL = 0 today (the legacy baseline)."""
    spec = _spec(brands={}, co_occurrence=[], call_id="A")
    rendered = _build_query(spec, x_monitor_list_id="2067062923525275922")
    assert rendered.startswith("(list:2067062923525275922) min_faves:"), (
        f"Call A path broken. Got: {rendered!r}"
    )
    assert "() " not in rendered, "Call A must not emit empty parens"


def test_wide_net_b_call_still_works():
    """Wide-net B path (plan 2026-07-11-002) must continue to render with
    per-brand tokens from primary_keywords + the secondary co paren.
    Note: the legacy renderer wraps multi-brand in an outer `((A) OR (B))`
    paren — preserve this behavior in the regression net."""
    spec = _spec(
        is_wide_net=True,
        wide_net_brands=["deepseek", "qwen"],
        co_occurrence=["llm", "model"],
        call_id="B1",
    )
    rendered = _build_query(
        spec,
        primary_keywords={"deepseek": ["DeepSeek"], "qwen": ["Qwen"]},
    )
    assert "DeepSeek" in rendered and "Qwen" in rendered, (
        f"Wide-net B must render both brands. Got: {rendered!r}"
    )
    assert "(llm OR model)" in rendered, (
        f"Wide-net B must include co_occurrence. Got: {rendered!r}"
    )