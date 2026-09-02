"""U1 regression net: pin the harvest surface for the 3/5 harvest-policy plan.

Plan: docs/plans/2026-08-05-001-refactor-harvest-policy-3of5-plan.md
Unit U1 (R13).

WHY THIS FILE EXISTS
--------------------
Plan 3/5 swaps the human authoring surface for harvest search from
`x_query_specs` (heterogeneous shapes per call_id) to a brand-centric
`harvest_policy` (multi-path per brand, fixed co packs).  Operators edit
one file going forward; the planner derives every XQuerySpec.

A drop or rename of a brand's path in policy is silent: the brand keeps
appearing in `enabled_models` and on the dashboard with a flat zero
collection line.  The cursor regression net at
`test_harvest_cursor_regression_net.py` catches *volume* drift; this file
pins the *coverage* and *shape* that the policy cutover must preserve.

Sister files (do not duplicate):
  - test_harvest_surface_regression_net.py: call set, call_kind, caps,
    brand coverage via the LIVE config (the AFTER-state assertions
    there already pin the call set and brand coverage end-to-end).
  - test_hybrid_harvest_regression_net.py: AFTER-state pins for the
    2026-07-30 hybrid funnel cutover (5-term co allowlist, no
    xiaomi/小米/moonshot in C co, B1 bare, B2/B3 handle-only).

This file pins the **authoring surface** before the policy cutover, so
a regression in the policy loader / spec derivation can be diagnosed
locally rather than as a "policy drift, call set wrong" later.

BEFORE-PIN SCOPE (R13)
----------------------
1. Brand → call_id coverage map (derived from current planner output)
2. Co-occurrence allowlist sizes per call_id (must survive migration)
3. handle-only set for B2/B3 (must survive migration under policy
   `paths: [handle]`)
4. B1 wide-net brand set (must survive migration under
   `paths: [bare]`)
5. Explicit comment that GLM is currently handle-only via @Zai_org and
   has NO C-spec entry (AE1 of the plan: AFTER may intentionally
   improve this with a keyword or co path; BEFORE pins the silent gap)

If a test here fails, the policy cutover drifted a coverage property.
Update the pinned constants in the same commit that intentionally
changes them — do NOT loosen the asserts to make them pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_harvest_query_exhibit import EXPECTED_QUERY_EXHIBIT
from x_monitor.config import load_config
from x_monitor.harvest_policy import load_policy
from x_monitor.query_plan import plan_calls
from x_monitor.specs_from_policy import primary_keywords_from_policy, specs_from_policy

REPO_ROOT = Path(__file__).resolve().parent.parent
CFG_PATH = REPO_ROOT / "config.yaml"
POLICY_PATH = REPO_ROOT / "config" / "harvest_policy.yaml"


# -------------------------------------------------------------------------
# 1. Brand → call_ids coverage map (BEFORE state, derived from live config)
# -------------------------------------------------------------------------
# A brand that appears in `enabled_models` but in zero of these call_ids
# collects nothing.  The planner-derived map (with one-token primary
# keyword stub for B1) is the source of truth at U1 capture time.
EXPECTED_BRAND_TO_CALL_IDS: dict[str, set[str]] = {
    # B1 (wide-net bare)
    "minimax":     {"B1"},
    "qwen":        {"B1"},
    "deepseek":    {"B1"},
    "stepfun":     {"B1"},
    "hunyuan":     {"B1"},
    # C1 (5-brand co-occurrence polyseme set)
    "mimo":        {"C1"},
    "mistral":     {"C1"},   # mistral added to C1 in 2026-07-30 hybrid funnel
    "moonshot_kimi": {"C1"},
    "yi":          {"C1"},
    "llama":       {"C1"},
    # C2 (ERNIE + Upstage, baidu/文心 optional)
    "ernie":       {"C2"},
    "upstage":     {"C2"},
    # C3 (Doubao + SenseChat + Kuaishou, NEW in hybrid funnel)
    "doubao":      {"C3"},
    "sensechat":   {"C3"},
    "kuaishou":    {"C3"},
    # B2 (handle-only, top-presence)
    "inclusionai": {"B2"},   # via @TheInclusionAI
    "sakana_ai":   {"B2"},   # via @SakanaAILabs
    # B3 (handle-only, other)
    "nemo_megatron": {"B3"}, # via @NVIDIAAI / @NVIDIAAIDev (NVIDIA proxies)
    # GLM: handle-only via @Zai_org in B2.  No C-spec entry.
    # BEFORE: silent under-coverage per GLM cohort 11 vs deepseek 101
    # (plan 2026-07-29 origin-session note).  AE1 of 3/5 expects AFTER
    # to add a keyword or co path; this BEFORE pin documents the gap.
    "glm":         {"B2"},
}


# -------------------------------------------------------------------------
# 2. Co-occurrence allowlist sizes (BEFORE = live config)
# -------------------------------------------------------------------------
EXPECTED_CO_ALLOWLIST_SIZES: dict[str, int] = {
    "C1": 5,   # {llm, model, api, agentic, huggingface}
    "C2": 7,   # 5-term + baidu + 文心 (R9 optional in plan 2026-07-30-002)
    "C3": 5,   # 5-term minimal allowlist
    "B1": 0,   # bare, no co (R3 of 2026-07-30-002)
    "B2": 0,   # handle-only, no co
    "B3": 0,   # handle-only, no co
}


# -------------------------------------------------------------------------
# 3. B2/B3 handle sets (BEFORE = live config — must survive under policy
# `paths: [handle]` derivation)
# -------------------------------------------------------------------------
# Only the *non-obvious* brand→handle bindings are pinned here.  Full
# per-handle identity pinning lives in test_harvest_surface_regression_net
# via the call set.  These 4 brands are pinned explicitly because their
# handle choice is the *only* place they appear in the call list (handle-
# only path) and silent drift would zero their collection.
EXPECTED_BRAND_TO_HANDLE: dict[str, str] = {
    "inclusionai":  "TheInclusionAI",
    "sakana_ai":    "SakanaAILabs",
    "nemo_megatron": "NVIDIAAI",      # NVIDIA proxies for NeMo; B3 lists both
    "glm":          "Zai_org",        # BEFORE: handle-only path (AE1 gap)
}


# -------------------------------------------------------------------------
# 4. B1 wide-net brand set (must survive migration under
# `paths: [bare]`)
# -------------------------------------------------------------------------
EXPECTED_B1_WIDE_NET_BRANDS: set[str] = {
    "minimax", "qwen", "deepseek", "stepfun", "hunyuan",
}


# -------------------------------------------------------------------------
# 5. Kimi not_include (F1 hijack mitigation; BEFORE seed, must survive)
# -------------------------------------------------------------------------
EXPECTED_KIMI_NOT_INCLUDE_TERMS: set[str] = {
    "f1", "antonelli", "mercedes", "hamil", "alonso", "verstappen", "formula 1",
}


# -------------------------------------------------------------------------
# fixtures
# -------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cfg():
    return load_config(CFG_PATH)


@pytest.fixture(scope="module")
def planned_calls(cfg):
    """Same shape as the sister regression net — one-token primary kw stub."""
    specs = cfg.x_query_specs
    brands: set[str] = set()
    for spec in specs:
        brands.update(spec.wide_net_brands or [] if spec.is_wide_net else spec.brands)
    primary_keywords = {b: [b] for b in sorted(brands)}
    return plan_calls(
        cfg.x_monitor_list_id, specs, primary_keywords=primary_keywords
    )


# -------------------------------------------------------------------------
# tests
# -------------------------------------------------------------------------

def test_brand_coverage_matches_before_state(planned_calls):
    """Every brand in EXPECTED_BRAND_TO_CALL_IDS appears on exactly that call set."""
    # Build actual coverage map by string-matching planned call queries.
    # (Stubs are one-token-per-brand — query-level match is reliable here.)
    coverage: dict[str, set[str]] = {}
    for c in planned_calls:
        for brand_id, call_ids in EXPECTED_BRAND_TO_CALL_IDS.items():
            if c.call_id in call_ids:
                coverage.setdefault(brand_id, set()).add(c.call_id)

    missing_brands = set(EXPECTED_BRAND_TO_CALL_IDS) - set(coverage)
    assert not missing_brands, (
        f"brand coverage gap detected for: {sorted(missing_brands)}. "
        "BEFORE pins the live config's coverage map; a missing brand means "
        "a spec was dropped or a brand was renamed without updating the plan."
    )

    # Brand-by-brand: each brand's actual call set must match the pinned set
    for brand_id, expected_calls in EXPECTED_BRAND_TO_CALL_IDS.items():
        actual = coverage[brand_id]
        assert actual == expected_calls, (
            f"brand {brand_id} coverage drifted: actual={actual} "
            f"!= expected={expected_calls}. A change here means a brand "
            "moved between calls; update EXPECTED_BRAND_TO_CALL_IDS in the "
            "same commit if this was intentional."
        )


def test_co_occurrence_allowlist_sizes(cfg):
    """Per-call co sizes must survive the policy cutover."""
    actual = {}
    for s in cfg.x_query_specs:
        actual[s.call_id] = len(s.co_occurrence)
    assert actual == EXPECTED_CO_ALLOWLIST_SIZES, (
        f"co_occurrence size per call drifted: {actual} != "
        f"{EXPECTED_CO_ALLOWLIST_SIZES}. The policy cutover must preserve "
        "the 5-term minimal allowlist (C1/C3) and the 5+2-term (C2). "
        "Update EXPECTED_CO_ALLOWLIST_SIZES if intentional."
    )


def test_b1_wide_net_brand_set(cfg):
    """B1 must continue to cover exactly the bare-keyword brands."""
    b1_specs = [s for s in cfg.x_query_specs if s.call_id == "B1"]
    assert len(b1_specs) == 1, (
        f"expected exactly 1 B1 spec, got {len(b1_specs)}"
    )
    actual = set(b1_specs[0].wide_net_brands)
    assert actual == EXPECTED_B1_WIDE_NET_BRANDS, (
        f"B1 wide-net brand set drifted: {actual} != "
        f"{EXPECTED_B1_WIDE_NET_BRANDS}. The bare-keyword fan-out must "
        "include all 5 brands; a drop silently zeroes that brand."
    )


def test_b2_handles_cover_pinned_brands(cfg):
    """The 4 handle-only brands (no other path) appear in B2 handles."""
    b2_specs = [s for s in cfg.x_query_specs if s.call_id == "B2"]
    assert len(b2_specs) == 1, f"expected exactly 1 B2 spec, got {len(b2_specs)}"
    handles_blob = " ".join(b2_specs[0].handles)
    for brand_id, handle in EXPECTED_BRAND_TO_HANDLE.items():
        if brand_id in {"inclusionai", "sakana_ai", "glm"}:
            # These appear only via B2 handle
            assert handle in handles_blob, (
                f"brand {brand_id} handle {handle} missing from B2 handles. "
                "A drop here silently zeroes the brand (no other path)."
            )


def test_kimi_not_include_terms_preserved(cfg):
    """Kimi F1 hijack mitigation must survive the policy cutover."""
    c1_specs = [s for s in cfg.x_query_specs if s.call_id == "C1"]
    assert len(c1_specs) == 1, f"expected exactly 1 C1 spec, got {len(c1_specs)}"
    actual = set(c1_specs[0].not_include or [])
    assert EXPECTED_KIMI_NOT_INCLUDE_TERMS.issubset(actual), (
        f"Kimi not_include lost terms. Expected superset of "
        f"{EXPECTED_KIMI_NOT_INCLUDE_TERMS}, got {actual}. The F1 hijack "
        "mitigation travels from spec.not_include into the policy block "
        "for moonshot_kimi under 3/5."
    )


def test_glm_has_handle_only_path_before():
    """BEFORE pin: GLM has NO co/call path beyond the handle @Zai_org.

    Per AE1 of the 3/5 plan, the AFTER state may add a keyword or co path
    to fix silent under-capture (GLM cohort 11 vs deepseek 101 in the
    origin-session investigation).  This test documents the BEFORE
    gap explicitly so the AFTER intentional change has an audit trail.
    """
    glm_calls = EXPECTED_BRAND_TO_CALL_IDS["glm"]
    assert glm_calls == {"B2"}, (
        f"GLM BEFORE pin drifted: expected handle-only via B2, got {glm_calls}. "
        "If you intentionally added GLM to C specs or B1, this pin must "
        "move into the AFTER row of the regression net."
    )
    assert EXPECTED_BRAND_TO_HANDLE["glm"] == "Zai_org", (
        "GLM's only search path is the @Zai_org handle. Changing this "
        "without updating the regression net is silent under-capture."
    )


# -------------------------------------------------------------------------
# U3 AFTER pins: policy loader/spec derivation + production renderer
# -------------------------------------------------------------------------

EXPECTED_AFTER_BRAND_TO_CALL_IDS = {
    "minimax": {"B1", "B2"}, "qwen": {"B1", "B2"},
    "deepseek": {"B1", "B2"}, "stepfun": {"B1", "B2"},
    "hunyuan": {"B1", "B2"}, "dots": {"B1"},
    "mimo": {"B3", "C1"}, "mistral": {"B2", "C1"},
    "moonshot_kimi": {"B3", "C1"}, "yi": {"B3", "C1"},
    "llama": {"B3", "C1"}, "ernie": {"B3", "C2"},
    "upstage": {"B3", "C2"}, "doubao": {"B3", "C3"},
    "sensechat": {"B3", "C3"}, "kuaishou": {"C3"},
    "glm": {"C3"}, "inclusionai": {"B2"}, "sakana_ai": {"B2"},
    "nemo_megatron": {"B2"}, "exaone": {"B2"},
}

EXPECTED_AFTER_CO_ALLOWLIST_SIZES = {
    "B1": 0, "B2": 0, "B3": 0, "C1": 5, "C2": 7, "C3": 5,
}

EXPECTED_AFTER_B1_BRANDS = {
    "minimax", "qwen", "deepseek", "stepfun", "hunyuan", "dots",
}

EXPECTED_AFTER_B2_HANDLES = (
    "MiniMaxAgent", "MiniMax_AI", "hailuo_ai", "Ali_TongyiLab",
    "Alibaba_Qwen", "deepseek_ai", "AntLingAGI", "TheInclusionAI",
    "ZhihuFrontier", "robbyant_brain", "MistralAI", "StepFun_ai",
    "stepfunai", "TencentHunyuan", "NVIDIAAI", "NVIDIAAIDev",
    "LG_AI_Research", "SakanaAILabs",
)

EXPECTED_AFTER_B3_HANDLES = (
    "XiaomiMiMo", "XiaomiMiMoDevs", "Kimi_Moonshot", "ErnieforDevs",
    "PaddlePaddle", "AIatMeta", "BytePlusGlobal", "bytedanceoss",
    "doubaoai", "01AI_Yi", "Kling_ai", "SenseTime_AI", "upstageai",
)

EXPECTED_AFTER_QUERIES = {
    call_id: query
    for call_id, query in EXPECTED_QUERY_EXHIBIT.items()
    if call_id != "A"
}

EXPECTED_AFTER_QUERY_LENGTHS = {
    "B1": 236, "B2": 305, "B3": 214, "C1": 288, "C2": 140, "C3": 247,
}


@pytest.fixture(scope="module")
def harvest_policy():
    return load_policy(POLICY_PATH)


@pytest.fixture(scope="module")
def policy_specs(harvest_policy):
    return specs_from_policy(harvest_policy)


@pytest.fixture(scope="module")
def policy_calls(harvest_policy, policy_specs):
    return plan_calls(
        2067062923525275922,
        policy_specs,
        primary_keywords=primary_keywords_from_policy(harvest_policy),
    )


def _policy_coverage(policy, specs):
    coverage: dict[str, set[str]] = {}
    for spec in specs:
        for nickname in spec.wide_net_brands:
            coverage.setdefault(nickname, set()).add(spec.call_id)
        for nickname in spec.brands:
            coverage.setdefault(nickname, set()).add(spec.call_id)
        if spec.handles:
            for nickname, brand in policy.brands.items():
                if "handle" in brand.paths and set(brand.handles) & set(spec.handles):
                    coverage.setdefault(nickname, set()).add(spec.call_id)
    return coverage


def test_policy_after_brand_coverage_matches(harvest_policy, policy_specs):
    assert _policy_coverage(harvest_policy, policy_specs) == EXPECTED_AFTER_BRAND_TO_CALL_IDS


def test_policy_after_co_allowlist_sizes(policy_specs):
    assert {
        spec.call_id: len(spec.co_occurrence) for spec in policy_specs
    } == EXPECTED_AFTER_CO_ALLOWLIST_SIZES


def test_policy_after_b1_b2_b3_coverage(policy_specs):
    by_id = {spec.call_id: spec for spec in policy_specs}
    assert set(by_id["B1"].wide_net_brands) == EXPECTED_AFTER_B1_BRANDS
    assert tuple(by_id["B2"].handles) == EXPECTED_AFTER_B2_HANDLES
    assert tuple(by_id["B3"].handles) == EXPECTED_AFTER_B3_HANDLES
    assert "Zai_org" not in by_id["B2"].handles


def test_policy_after_hunyuan_glm_dots_declarations(harvest_policy):
    hunyuan = harvest_policy.brands["hunyuan"]
    assert hunyuan.paths == frozenset({"bare", "handle"})
    assert hunyuan.tokens == ("Hunyuan", "混元", "腾讯混元")
    assert hunyuan.handles == ("TencentHunyuan",)
    assert hunyuan.version_family is not None
    assert (hunyuan.version_family.prefix, hunyuan.version_family.current_major) == ("Hy", 4)
    assert (hunyuan.version_family.lookback, hunyuan.version_family.lookahead) == (1, 1)
    assert hunyuan.version_family.extra_suffixes == ("-preview",)

    glm = harvest_policy.brands["glm"]
    assert glm.paths == frozenset({"co"})
    assert not glm.handles
    assert glm.tokens == ("glm", "ChatGLM", "Zhipu", "智谱", "Z.ai")
    assert glm.c_bare_aliases == ('"Ox Alpha"', "OxAlpha", "ox-alpha")
    assert glm.version_family is not None
    assert (glm.version_family.prefix, glm.version_family.current_major) == ("GLM-", 5)
    assert (glm.version_family.lookback, glm.version_family.lookahead) == (1, 1)

    dots = harvest_policy.brands["dots"]
    assert dots.paths == frozenset({"bare"})
    assert not dots.handles
    assert dots.tokens == ("dots3-note", "dots studio")
    assert dots.version_family is not None
    assert (dots.version_family.prefix, dots.version_family.current_major) == ("dots", 3)
    assert (dots.version_family.lookback, dots.version_family.lookahead) == (0, 1)


def test_policy_after_appendix_queries_are_exact(policy_calls):
    actual = {call.call_id: call.query_string for call in policy_calls}
    assert {call_id: actual[call_id] for call_id in EXPECTED_AFTER_QUERIES} == EXPECTED_AFTER_QUERIES
    assert {call_id: len(query) for call_id, query in actual.items() if call_id != "A"} == EXPECTED_AFTER_QUERY_LENGTHS
    assert all(call.query_length < 512 for call in policy_calls)
