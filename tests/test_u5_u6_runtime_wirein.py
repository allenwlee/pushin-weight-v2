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


@pytest.mark.parametrize("call_id", ["A", "B1", "B2", "B3", "C1", "C2", "C3"])
def test_legacy_generic_gate_never_calls_llm(call_id):
    """Role-free routing cannot authorize relevance; U12 resolves staff first."""
    items = [{"text": "anything", "brand_id": "moonshot_kimi"}]
    called = []

    def recording_drop(system, user):
        called.append(user)
        return "DROP"

    out = _apply_relevancy_gate(items, call_id=call_id, llm_call=recording_drop)
    assert out == items
    assert called == []


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
