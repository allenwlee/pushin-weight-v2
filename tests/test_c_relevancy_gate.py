"""U6 tests - C-only binary LLM relevancy gate.

Plan: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
Unit U6 (KTD6).

WHY THIS FILE EXISTS
--------------------
The binary relevancy gate must:
  1. Parse KEEP/DROP correctly (case-insensitive, first-line protocol).
  2. Apply keep bias on parse failure (multilingual keep bias per R19a).
  3. Fire only for C-path / C-tier brand attribution (not A/B).
  4. Carry the R19a system + user prompt as module constants (source of
     truth for the LLM call site).
"""

from __future__ import annotations

import pytest

from x_monitor.relevancy import (
    BINARY_RELEVANCY_SYSTEM,
    BinaryRelevancyVerdict,
    GATED_CALL_IDS,
    binary_relevancy_user_template,
    call_binary_relevancy_llm,
    parse_binary_relevancy,
    should_apply_binary_gate,
)


# ---------------------------------------------------------------------------
# Prompt constants (R19a)
# ---------------------------------------------------------------------------


def test_binary_relevancy_system_prompt_present():
    assert BINARY_RELEVANCY_SYSTEM
    assert "KEEP or DROP" in BINARY_RELEVANCY_SYSTEM
    assert "KEEP" in BINARY_RELEVANCY_SYSTEM and "DROP" in BINARY_RELEVANCY_SYSTEM
    assert "multilingual keep bias" in BINARY_RELEVANCY_SYSTEM or "uncertain" in BINARY_RELEVANCY_SYSTEM.lower()


def test_user_template_includes_brand_and_call():
    text = binary_relevancy_user_template(
        brand_hints="kimi",
        call_id="C1",
        post_text="Kimi K2 is fast",
    )
    assert "kimi" in text
    assert "C1" in text
    assert "Kimi K2 is fast" in text
    assert "Reply KEEP or DROP" in text


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_parse_keep_only():
    v = parse_binary_relevancy("KEEP")
    assert v.decision == "KEEP"
    assert not v.parse_failed
    assert v.reason == ""


def test_parse_drop_only():
    v = parse_binary_relevancy("DROP")
    assert v.decision == "DROP"
    assert not v.parse_failed


def test_parse_keep_with_reason():
    v = parse_binary_relevancy("KEEP\nclear AI discussion")
    assert v.decision == "KEEP"
    assert v.reason == "clear AI discussion"
    assert not v.parse_failed


def test_parse_drop_with_reason():
    v = parse_binary_relevancy("DROP\nF1 racing coverage")
    assert v.decision == "DROP"
    assert v.reason == "F1 racing coverage"


def test_parse_case_insensitive():
    v = parse_binary_relevancy("keep")
    assert v.decision == "KEEP"
    v = parse_binary_relevancy("Drop")
    assert v.decision == "DROP"


def test_parse_empty_response_keeps():
    v = parse_binary_relevancy("")
    assert v.decision == "KEEP"
    assert v.parse_failed


def test_parse_unparseable_first_line_keeps():
    v = parse_binary_relevancy("I think this is about AI\nmaybe keep it")
    assert v.decision == "KEEP"
    assert v.parse_failed


def test_parse_whitespace_tolerated():
    v = parse_binary_relevancy("  KEEP  \n  reason text  ")
    assert v.decision == "KEEP"
    assert v.reason == "reason text"


# ---------------------------------------------------------------------------
# Gate (which call_ids + brand_hints trigger)
# ---------------------------------------------------------------------------


def test_gate_fires_for_c_call_ids():
    for cid in ("C1", "C2", "C3"):
        assert should_apply_binary_gate(call_id=cid, brand_hints="")
        assert should_apply_binary_gate(call_id=cid, brand_hints="kimi")


def test_gate_skips_a_call():
    assert not should_apply_binary_gate(call_id="A", brand_hints="")


def test_gate_skips_b_calls_without_c_brand():
    assert not should_apply_binary_gate(call_id="B1", brand_hints="")
    assert not should_apply_binary_gate(call_id="B2", brand_hints="deepseek_ai")


def test_gate_fires_for_b_calls_with_c_brand_attribution():
    """A B-call post that routes to a C-tier brand (e.g., B1's wide-net
    match attribution points at the moonshot_kimi brand) still goes
    through the gate. brand_hints carries the canonical brand_id."""
    assert should_apply_binary_gate(call_id="B1", brand_hints="moonshot_kimi")
    assert should_apply_binary_gate(call_id="B2", brand_hints="mimo,llama")
    assert should_apply_binary_gate(call_id="B3", brand_hints="ernie")


def test_gated_call_ids_constant():
    assert GATED_CALL_IDS == frozenset({"C1", "C2", "C3"})


# ---------------------------------------------------------------------------
# LLM caller (stub)
# ---------------------------------------------------------------------------


def test_call_with_stub_llm_returns_keep_by_default():
    v = call_binary_relevancy_llm(
        post_text="test",
        call_id="C1",
        brand_hints="kimi",
    )
    assert v.decision == "KEEP"
    assert v.parse_failed
    assert "no llm_call" in v.reason


def test_call_with_injected_llm_parses_response():
    def fake_llm(system, user):
        return "DROP\nF1 hijack"

    v = call_binary_relevancy_llm(
        post_text="Kimi wins F1 race",
        call_id="C1",
        brand_hints="kimi",
        llm_call=fake_llm,
    )
    assert v.decision == "DROP"
    assert v.reason == "F1 hijack"
    assert not v.parse_failed


def test_call_with_injected_llm_keep():
    def fake_llm(system, user):
        return "KEEP\nclear AI tool discussion"

    v = call_binary_relevancy_llm(
        post_text="Kimi 2 is fast and cheap",
        call_id="C1",
        brand_hints="kimi",
        llm_call=fake_llm,
    )
    assert v.decision == "KEEP"
    assert not v.parse_failed