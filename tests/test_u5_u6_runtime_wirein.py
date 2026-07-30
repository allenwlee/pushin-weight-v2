"""U5 + U6 runtime wire-in tests.

Plan: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
Units U5 (post-fetch ban) + U6 (binary LLM relevancy gate).

The helpers _matches_any_term and _apply_relevancy_gate are the
runtime entry points. Tested with fake llm_call injection to avoid
network dependence.
"""

from __future__ import annotations

import pytest

from monitor.cycle import _apply_relevancy_gate, _matches_any_term
from x_monitor.query_plan import PlannedCall


def test_matches_any_term_empty_terms():
    assert _matches_any_term("hello world", "", []) is False
    assert _matches_any_term("hello world", "quote", [""]) is False


def test_matches_any_term_basic():
    terms = ["f1", "antonelli"]
    assert _matches_any_term("Kimi wins F1 race today", "", terms)
    assert _matches_any_term("", "Antonelli wins", terms)


def test_matches_any_term_case_insensitive():
    terms = ["f1"]
    assert _matches_any_term("F1 racing", "", terms)
    assert _matches_any_term("f1 racing", "", terms)
    assert _matches_any_term("F1 RACING", "", terms)


def test_matches_any_term_quoted_text():
    terms = ["mercedes"]
    # quoted_text alone is enough
    assert _matches_any_term("", "Mercedes wins F1", terms)
    # body + quoted combined
    assert _matches_any_term(
        "Kim wins", "via Mercedes F1 team", terms
    )


def test_matches_any_term_no_match():
    terms = ["f1", "antonelli"]
    assert _matches_any_term("Kimi K2.5 release today", "", terms) is False


def test_matches_any_term_empty_strings():
    """Empty text/quote with empty terms is False, not True."""
    assert _matches_any_term("", "", []) is False
    assert _matches_any_term("", "", ["f1"]) is False


# --- _apply_relevancy_gate --------------------------------------------------


def test_apply_relevancy_gate_no_op_when_llm_call_is_none():
    items = [{"text": "anything", "brand_id": "kimi"}]
    out = _apply_relevancy_gate(items, call_id="C1", llm_call=None)
    assert out == items


def test_apply_relevancy_gate_skips_a_call():
    """Call A bypasses the gate (handled by should_apply_binary_gate)."""
    items = [{"text": "anything", "brand_id": "*"}]

    def always_drop(system, user):
        return "DROP"

    out = _apply_relevancy_gate(items, call_id="A", llm_call=always_drop)
    # The gate's `should_apply_binary_gate` returns False for A → no LLM call.
    assert out == items


def test_apply_relevancy_gate_drops_on_llm_drop():
    items = [
        {"text": "Kimi wins F1 race", "brand_id": "moonshot_kimi"},
        {"text": "real Kimi 2.5 release", "brand_id": "moonshot_kimi"},
    ]

    def drop_first_only(system, user):
        # Drop if "F1" in the post text; KEEP otherwise.
        if "F1" in user:
            return "DROP\nF1 hijack"
        return "KEEP"

    out = _apply_relevancy_gate(items, call_id="C1", llm_call=drop_first_only)
    assert len(out) == 1
    assert out[0]["text"] == "real Kimi 2.5 release"


def test_apply_relevancy_gate_keeps_on_llm_keep():
    items = [{"text": "Kimi 2.5 release", "brand_id": "moonshot_kimi"}]

    def always_keep(system, user):
        return "KEEP"

    out = _apply_relevancy_gate(items, call_id="C1", llm_call=always_keep)
    assert len(out) == 1


def test_apply_relevancy_gate_keep_on_parse_failure():
    """Parse failure → keep bias (multilingual, per R19a)."""
    items = [{"text": "weird stuff", "brand_id": "mimo"}]

    def malformed(system, user):
        return "I think this is fine"

    out = _apply_relevancy_gate(items, call_id="C1", llm_call=malformed)
    assert len(out) == 1


def test_apply_relevancy_gate_b_call_with_c_tier_brand_fires():
    """B-call that routes to a C-tier brand (e.g., moonshot_kimi) still
    triggers the gate — plan R19."""
    items = [{"text": "F1 race winner", "brand_id": "moonshot_kimi"}]

    called = []

    def recording_drop(system, user):
        called.append(user)
        return "DROP"

    _apply_relevancy_gate(
        items, call_id="B1", llm_call=recording_drop
    )
    assert len(called) == 1, "B1 with moonshot_kimi brand must fire the gate"


def test_apply_relevancy_gate_b_call_pure_brand_skipped():
    """B-call routed to a pure brand (e.g., deepseek) does NOT fire."""
    items = [{"text": "DeepSeek-V3 release", "brand_id": "deepseek"}]

    called = []

    def recording_drop(system, user):
        called.append(user)
        return "DROP"

    out = _apply_relevancy_gate(
        items, call_id="B1", llm_call=recording_drop
    )
    assert out == items  # unchanged
    assert len(called) == 0, "Pure brand B-call must not fire the gate"


def test_apply_relevancy_gate_no_brand_id_still_fires_on_c_call():
    """An item with empty brand_id routed through a C-path call STILL
    triggers the gate — the gate fires on call_id alone (R19). This
    is intentional: the bare-co C specs admit everyday language that
    the LLM needs to filter."""
    items = [{"text": "everyday English", "brand_id": ""}]

    called = []

    def recording_drop(system, user):
        called.append(user)
        return "DROP"

    out = _apply_relevancy_gate(
        items, call_id="C1", llm_call=recording_drop
    )
    assert out == []  # dropped
    assert len(called) == 1


# --- PlannedCall.not_include propagation ------------------------------------


def test_planned_call_carries_not_include():
    """PlannedCall must carry not_include from XQuerySpec so the runtime
    ban match can fire without re-reading config."""
    pc = PlannedCall(
        call_id="C1",
        call_kind="brand_wide",
        brand_id="moonshot_kimi",
        bucket=None,
        query_string="(...)",
        query_length=10,
        not_include=["f1", "antonelli"],
    )
    assert pc.not_include == ["f1", "antonelli"]


def test_planned_call_default_not_include_empty():
    pc = PlannedCall(
        call_id="A",
        call_kind="account",
        brand_id="*",
        bucket=None,
        query_string="(list:1) min_faves:1",
        query_length=20,
    )
    assert pc.not_include == []