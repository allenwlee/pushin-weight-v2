"""U5 tests - C minimal co + not_include.

Plan: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
Unit U5.

WHY THIS FILE EXISTS
--------------------
The hybrid funnel R10 forbids xiaomi/小米/moonshot in any co-occurrence
list. The hybrid funnel R12 introduces an optional `not_include` field on
each spec for stable hijack post-fetch bans. U3 already landed the
config-level co changes; U5 seeds the C1 F1/Kimi not_include list and
pins both invariants.

This file does NOT test the runtime enforcement path (post-fetch ban
matching in monitor/cycle.py). That wire-in is a follow-up; pinning the
config + dataclass is the U5 deliverable.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from x_monitor.query_plan import XQuerySpec


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.yaml"

EXPECTED_FORBIDDEN_CO_TERMS = {"xiaomi", "小米", "moonshot"}

EXPECTED_MINIMAL_CO_ALLOWLIST = {"llm", "model", "api", "agentic", "huggingface"}

EXPECTED_C1_NOT_INCLUDE_F1_TERMS = {
    "f1", "antonelli", "mercedes",
}


def _load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _x_query_specs(cfg):
    return cfg.get("x_query_specs", []) or []


# --- R10: xiaomi/moonshot never in any co ---------------------------------


def test_no_xiaomi_in_any_co():
    cfg = _load_config()
    for spec in _x_query_specs(cfg):
        cid = spec.get("call_id")
        co = spec.get("co_occurrence", []) or []
        co_lower = {t.lower() for t in co}
        forbidden = EXPECTED_FORBIDDEN_CO_TERMS & co_lower
        assert not forbidden, (
            f"{cid} co contains forbidden term(s) {forbidden}; R10 violation. "
            f"Full co: {co}."
        )


# --- R12: C1 seeded with F1/Kimi not_include -----------------------------


def test_c1_has_not_include():
    cfg = _load_config()
    c1 = next((s for s in _x_query_specs(cfg) if s.get("call_id") == "C1"), None)
    assert c1 is not None, "C1 spec missing"
    not_include = c1.get("not_include", []) or []
    assert not_include, (
        "C1 must have a non-empty not_include list (U5 seeds F1/Kimi terms). "
        "If intentionally removed, update this assertion."
    )


def test_c1_not_include_contains_f1_terms():
    cfg = _load_config()
    c1 = next((s for s in _x_query_specs(cfg) if s.get("call_id") == "C1"), None)
    assert c1 is not None
    not_include = set(c1.get("not_include", []))
    missing = EXPECTED_C1_NOT_INCLUDE_F1_TERMS - not_include
    assert not missing, (
        f"C1 not_include missing F1 hijack terms: {missing}. "
        f"Full not_include: {not_include}."
    )


# --- XQuerySpec field ------------------------------------------------------


def test_xqueryspec_has_not_include_field():
    spec = XQuerySpec(call_id="TEST")
    assert hasattr(spec, "not_include"), (
        "XQuerySpec must carry `not_include` per U5 R12."
    )
    assert spec.not_include == [], (
        f"Default not_include should be empty list, got {spec.not_include!r}"
    )


def test_xqueryspec_not_include_constructor():
    spec = XQuerySpec(call_id="C1", not_include=["f1", "antonelli"])
    assert spec.not_include == ["f1", "antonelli"]


# --- Minimal co allowlist pin ---------------------------------------------


def test_c_spec_co_uses_minimal_allowlist():
    """Every C* spec's co_occurrence is a subset of the 5-term allowlist
    plus the C2-only optional {baidu, 文心}."""
    cfg = _load_config()
    allowed = EXPECTED_MINIMAL_CO_ALLOWLIST | {"baidu", "文心"}
    for spec in _x_query_specs(cfg):
        cid = spec.get("call_id")
        if cid and cid.startswith("C"):
            co = spec.get("co_occurrence", []) or []
            extra = set(co) - allowed
            assert not extra, (
                f"{cid} co has terms outside the allowlist: {extra}."
            )


def test_co_count_under_cap():
    """Each C* spec's co must be ≤ 8 terms (R9 cap)."""
    cfg = _load_config()
    for spec in _x_query_specs(cfg):
        cid = spec.get("call_id")
        if cid and cid.startswith("C"):
            co = spec.get("co_occurrence", []) or []
            assert len(co) <= 8, (
                f"{cid} co has {len(co)} terms; R9 cap is 8."
            )