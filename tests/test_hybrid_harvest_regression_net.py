"""U8 regression net - pin the harvest surface AFTER the hybrid funnel ships.

Plan: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
Unit U8 (formerly U1).

WHY THIS FILE EXISTS
--------------------
The hybrid funnel plan (formerly plan 2026-07-28-001, amended and merged into
2026-07-30-002) reshapes the live harvest:

  - B1 must become bare (no co)
  - B2/B3 must be handle-only (no co, OR-group of @handles)
  - C1/C2/C3 must collapse from the full 22-term co-occurrence list to a
    5-term minimal co allowlist
  - xiaomi/小米/moonshot must NEVER appear in C co
  - Optional not_include for stable hijacks (F1/Kimi) is new (U5)
  - C-only binary LLM relevancy is new (U6)

This file pins the AFTER state (post-U3). U1 originally pinned the BEFORE
state; the flip happened on 2026-07-30 when U3 shipped.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from x_monitor.harvest_policy import load_policy
from x_monitor.query_plan import plan_calls
from x_monitor.specs_from_policy import primary_keywords_from_policy, specs_from_policy

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.yaml"
POLICY_PATH = REPO_ROOT / "config" / "harvest_policy.yaml"


# Pinned AFTER-state values (live as of 2026-07-30 post-U3)
EXPECTED_CO_COUNTS_AFTER: dict = {
    "B1": 0,   # bare
    "B2": 0,   # handle-only
    "B3": 0,   # handle-only
    "C1": 5,   # 5-term minimal allowlist
    "C2": 7,   # 5-term + baidu + 文心 (R9 optional)
    "C3": 5,   # 5-term minimal allowlist
}

EXPECTED_MINIMAL_CO_ALLOWLIST = {
    "llm", "model", "api", "agentic", "huggingface",
}

EXPECTED_FORBIDDEN_CO_TERMS = {
    "xiaomi", "小米", "moonshot",
}

EXPECTED_CALL_IDS_AFTER_U3 = {"A", "B1", "B2", "B3", "C1", "C2", "C3"}

EXPECTED_C3_AFTER_POLICY = '(((Doubao OR ByteDance) OR (Kuaishou OR KwaiYii) OR (SenseChat OR SenseTime) OR (glm OR ChatGLM OR Zhipu OR 智谱 OR Z.ai OR GLM-4 OR GLM-5 OR GLM-6)) (llm OR model OR api OR agentic OR huggingface) OR ("Ox Alpha" OR OxAlpha OR ox-alpha)) min_faves:0'


def _load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _x_query_specs(cfg):
    return cfg.get("x_query_specs", []) or []


def _call_b_groups(cfg):
    return cfg.get("call_b_groups", []) or []


def test_policy_c3_is_glm_pack_with_bare_ox_alpha():
    """U3 policy path: GLM joins C3; its aliases bypass the co gate."""
    policy = load_policy(POLICY_PATH)
    specs = specs_from_policy(policy)
    calls = plan_calls(
        "2067062923525275922",
        specs,
        primary_keywords=primary_keywords_from_policy(policy),
    )
    c3 = next(call for call in calls if call.call_id == "C3")
    assert c3.query_string == EXPECTED_C3_AFTER_POLICY
    assert c3.query_length == 247
    assert "Zai_org" not in next(spec for spec in specs if spec.call_id == "B2").handles


def test_policy_after_state_has_exact_seven_logical_calls():
    policy = load_policy(POLICY_PATH)
    calls = plan_calls(
        "2067062923525275922",
        specs_from_policy(policy),
        primary_keywords=primary_keywords_from_policy(policy),
    )
    assert {call.call_id for call in calls} == EXPECTED_CALL_IDS_AFTER_U3




def test_config_yaml_loads():
    cfg = _load_config()
    assert cfg is not None
    assert "x_query_specs" in cfg


def test_call_ids_present_in_x_query_specs():
    """AFTER U3: x_query_specs contains B1/B2/B3/C1/C2/C3 (A is implicit)."""
    cfg = _load_config()
    spec_ids = {s.get("call_id") for s in _x_query_specs(cfg)}
    expected = EXPECTED_CALL_IDS_AFTER_U3 - {"A"}
    assert spec_ids == expected, (
        f"AFTER state: expected {expected}, got {spec_ids}. "
        f"This means the config has drifted; update EXPECTED_CALL_IDS_AFTER_U3 "
        f"or check whether a unit broke the call layout."
    )


def test_call_b_groups_brand_split_unchanged():
    cfg = _load_config()
    groups = _call_b_groups(cfg)
    assert len(groups) == 3, (
        f"Expected 3 call_b_groups, got {len(groups)}: {groups}. "
        f"Hybrid funnel plan preserves the 3-group split."
    )
    assert len(groups[0]) == 5, "B1 group should have 5 brands (post-2026-07-31 Mistral demotion to C1; plan 2026-07-31-002 U1)"
    assert len(groups[1]) == 4, "B2 group should have 4 brands"
    assert len(groups[2]) == 4, "B3 group should have 4 brands"


@pytest.mark.parametrize(
    "call_id,expected_count",
    [(k, v) for k, v in EXPECTED_CO_COUNTS_AFTER.items()],
)
def test_co_occurrence_count_after(call_id, expected_count):
    cfg = _load_config()
    spec = next((s for s in _x_query_specs(cfg) if s.get("call_id") == call_id), None)
    if spec is None:
        pytest.skip(f"call_id {call_id} not in x_query_specs")
    co = spec.get("co_occurrence", []) or []
    assert len(co) == expected_count, (
        f"{call_id} co_count drifted from AFTER expectation: "
        f"expected {expected_count}, got {len(co)}. "
        f"Update EXPECTED_CO_COUNTS_AFTER or investigate."
    )


def test_no_xiaomi_in_any_co_after():
    """AFTER U3: xiaomi/小米/moonshot MUST NOT appear in any co-occurrence list
    (R10). Drift detector for the poison pattern."""
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


def test_minimal_co_allowlist_is_5_terms():
    assert len(EXPECTED_MINIMAL_CO_ALLOWLIST) == 5
    assert EXPECTED_MINIMAL_CO_ALLOWLIST == {
        "llm", "model", "api", "agentic", "huggingface",
    }


def test_c_spec_co_is_subset_of_allowlist_plus_optional():
    """AFTER U3: each C* spec's co_occurrence MUST be a subset of
    {llm, model, api, agentic, huggingface} + the optional C2 add-ons
    {baidu, 文心}."""
    cfg = _load_config()
    c_allowed = EXPECTED_MINIMAL_CO_ALLOWLIST | {"baidu", "文心"}
    for spec in _x_query_specs(cfg):
        cid = spec.get("call_id")
        if cid and cid.startswith("C"):
            co = spec.get("co_occurrence", []) or []
            co_set = set(co)
            extra = co_set - c_allowed
            assert not extra, (
                f"{cid} co has terms outside the allowlist: {extra}. "
                f"R10 violation."
            )


def test_b2_b3_have_handles_no_co():
    """AFTER U3: B2 and B3 use the `handles` field and have NO co-occurrence."""
    cfg = _load_config()
    for cid in ("B2", "B3"):
        spec = next((s for s in _x_query_specs(cfg) if s.get("call_id") == cid), None)
        assert spec is not None, f"{cid} spec missing"
        handles = spec.get("handles", []) or []
        co = spec.get("co_occurrence", []) or []
        assert handles, f"{cid} must have non-empty handles list"
        assert not co, f"{cid} must have empty co_occurrence (handles-only)"
