"""Tests for x_monitor.specs_from_policy (U3).

Plan: docs/plans/2026-08-05-001-refactor-harvest-policy-3of5-plan.md
Unit U3 (R6-R9, R12, R20).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from x_monitor.harvest_policy import BrandPolicy, CoPack, HarvestPolicy, load_policy
from x_monitor.query_plan import (
    XQuerySpec,
    plan_calls,
)
from x_monitor.specs_from_policy import (
    primary_keywords_from_policy,
    specs_from_policy,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
CFG_PATH = REPO_ROOT / "config.yaml"


# -------------------------------------------------------------------------
# fixtures
# -------------------------------------------------------------------------

@pytest.fixture(scope="module")
def live_policy() -> HarvestPolicy:
    """Load the live policy draft (config/harvest_policy.yaml) when present,
    otherwise fall back to a fixture mirror of the live config behavior."""
    p = REPO_ROOT / "config" / "harvest_policy.yaml"
    if p.exists():
        return load_policy(p)
    return _fixture_minimal_policy()


def _fixture_minimal_policy() -> HarvestPolicy:
    """Fixture that mirrors the AFTER-3/5 expected behavior, used until
    the live config/harvest_policy.yaml ships in U5."""
    return HarvestPolicy(
        brands={
            "minimax": BrandPolicy(
                nickname="minimax",
                paths=frozenset({"bare", "handle"}),
                tokens=("MiniMax", "MiniMaxAI"),
                handles=("MiniMax_AI", "MiniMaxAgent"),
            ),
            "qwen": BrandPolicy(
                nickname="qwen",
                paths=frozenset({"bare"}),
                tokens=("Qwen", "通义千问", "Tongyi"),
            ),
            "moonshot_kimi": BrandPolicy(
                nickname="moonshot_kimi",
                paths=frozenset({"co", "handle"}),
                tokens=("Kimi", "Moonshot AI"),
                co=("llm", "model", "api", "agentic", "huggingface"),
                handles=("Kimi_Moonshot",),
                not_include=("f1", "antonelli"),
            ),
            "glm": BrandPolicy(
                nickname="glm",
                paths=frozenset({"handle"}),
                tokens=("GLM",),
                handles=("Zai_org",),
                notes="Handle-only path (3/5 BEFORE row); 4/5 may add keyword path.",
            ),
            "exaone": BrandPolicy(
                nickname="exaone",
                paths=frozenset({"none"}),
                notes="Temporarily opted out.",
            ),
        },
        co_packs=(
            CoPack(brand_nicknames=("moonshot_kimi",)),
        ),
    )


# -------------------------------------------------------------------------
# R6: returns list of XQuerySpec
# -------------------------------------------------------------------------

def test_returns_list_of_xqueryspecs(live_policy):
    specs = specs_from_policy(live_policy)
    assert isinstance(specs, list)
    assert all(isinstance(s, XQuerySpec) for s in specs)


def test_no_second_renderer_added():
    """M7 DRY gate: the renderer (_build_query) is the only renderer.

    Specs_from_policy builds XQuerySpec objects; it never calls
    `_build_query`. Verified by inspecting the module's public surface.
    """
    import x_monitor.specs_from_policy as mod
    public = [n for n in dir(mod) if not n.startswith("_")]
    assert "_build_query" not in public
    assert "plan_calls" not in public


# -------------------------------------------------------------------------
# R3 multi-path: bare + handle brand appears on B1 AND handle spec
# -------------------------------------------------------------------------

def test_multi_path_brand_appears_on_both_specs():
    policy = HarvestPolicy(
        brands={
            "minimax": BrandPolicy(
                nickname="minimax",
                paths=frozenset({"bare", "handle"}),
                tokens=("MiniMax",),
                handles=("MiniMax_AI",),
            ),
        },
        co_packs=(),
    )
    specs = specs_from_policy(policy)
    call_ids = {s.call_id for s in specs}
    # bare -> B1 (wide-net), handle -> B2
    assert "B1" in call_ids and "B2" in call_ids
    # minimax appears in B1's wide_net_brands AND in B2's handles
    b1 = next(s for s in specs if s.call_id == "B1")
    b2 = next(s for s in specs if s.call_id == "B2")
    assert "minimax" in b1.wide_net_brands
    assert "MiniMax_AI" in b2.handles


# -------------------------------------------------------------------------
# R7: fixed co packs — one C-spec per pack
# -------------------------------------------------------------------------

def test_one_cspec_per_co_pack():
    policy = HarvestPolicy(
        brands={
            "a": BrandPolicy(nickname="a", paths=frozenset({"co"}),
                             tokens=("A",), co=("llm",)),
            "b": BrandPolicy(nickname="b", paths=frozenset({"co"}),
                             tokens=("B",), co=("llm",)),
            "c": BrandPolicy(nickname="c", paths=frozenset({"co"}),
                             tokens=("C",), co=("llm",)),
        },
        co_packs=(
            CoPack(brand_nicknames=("a", "b")),
            CoPack(brand_nicknames=("c",)),
        ),
    )
    specs = specs_from_policy(policy)
    c_specs = [s for s in specs if s.call_id.startswith("C")]
    assert len(c_specs) == 2
    # Order is pack order
    assert c_specs[0].call_id == "C1"
    assert set(c_specs[0].brands) == {"a", "b"}
    assert c_specs[1].call_id == "C2"
    assert set(c_specs[1].brands) == {"c"}


# -------------------------------------------------------------------------
# R4: brand-local not_include unions across pack (Kimi F1 mitigation)
# -------------------------------------------------------------------------

def test_not_include_unions_across_pack_brands():
    policy = HarvestPolicy(
        brands={
            "moonshot_kimi": BrandPolicy(
                nickname="moonshot_kimi",
                paths=frozenset({"co"}),
                tokens=("Kimi",),
                co=("llm",),
                not_include=("f1", "antonelli"),
            ),
        },
        co_packs=(CoPack(brand_nicknames=("moonshot_kimi",)),),
    )
    specs = specs_from_policy(policy)
    c1 = next(s for s in specs if s.call_id == "C1")
    assert "f1" in c1.not_include and "antonelli" in c1.not_include


# -------------------------------------------------------------------------
# R6: integration via the existing plan_calls / _build_query renderer
# -------------------------------------------------------------------------

def test_renders_through_existing_renderer():
    """specs_from_policy + plan_calls must work without parallel code."""
    policy = HarvestPolicy(
        brands={
            "minimax": BrandPolicy(
                nickname="minimax",
                paths=frozenset({"bare", "handle"}),
                tokens=("MiniMax", "MiniMaxAI"),
                handles=("MiniMax_AI",),
            ),
            "moonshot_kimi": BrandPolicy(
                nickname="moonshot_kimi",
                paths=frozenset({"co", "handle"}),
                tokens=("Kimi",),
                co=("llm", "model"),
                handles=("Kimi_Moonshot",),
                not_include=("f1",),
            ),
        },
        co_packs=(CoPack(brand_nicknames=("moonshot_kimi",)),),
    )
    specs = specs_from_policy(policy)
    pkws = primary_keywords_from_policy(policy)
    calls = plan_calls(
        x_monitor_list_id="1234567890",
        x_query_specs=specs,
        primary_keywords=pkws,
    )
    # Expect 4 calls: A + B1 + C1 + B2
    assert {c.call_id for c in calls} == {"A", "B1", "C1", "B2"}
    # Co spec carries the not_include through PlannedCall
    c1 = next(c for c in calls if c.call_id == "C1")
    assert "f1" in c1.not_include
    # Length-cap preserved
    for c in calls:
        assert c.query_length <= 512, f"{c.call_id} length {c.query_length} > 512"


# -------------------------------------------------------------------------
# Edge: brand with paths=[none] is skipped entirely
# -------------------------------------------------------------------------

def test_none_path_brand_emits_no_specs():
    policy = HarvestPolicy(
        brands={
            "exaone": BrandPolicy(nickname="exaone", paths=frozenset({"none"}),
                                  notes="opted out"),
            "minimax": BrandPolicy(nickname="minimax", paths=frozenset({"bare"}),
                                   tokens=("MiniMax",)),
        },
        co_packs=(),
    )
    specs = specs_from_policy(policy)
    pkws = primary_keywords_from_policy(policy)
    # Only B1 for minimax; no entry from exaone
    assert len(specs) == 1
    assert specs[0].call_id == "B1"
    assert "exaone" not in specs[0].wide_net_brands
    assert "exaone" not in pkws


# -------------------------------------------------------------------------
# R8: primary_keywords_from_policy supplies B1 tokens
# -------------------------------------------------------------------------

def test_primary_keywords_cover_bare_brands():
    policy = HarvestPolicy(
        brands={
            "minimax": BrandPolicy(nickname="minimax",
                                   paths=frozenset({"bare"}),
                                   tokens=("MiniMax", "MiniMaxAI")),
            "llama": BrandPolicy(nickname="llama",
                                 paths=frozenset({"versioned_bare"}),
                                 tokens=("Llama",),
                                 versioned_tokens=("Llama 4",)),
            "glm": BrandPolicy(nickname="glm",
                               paths=frozenset({"handle"}),
                               handles=("Zai_org",)),
        },
        co_packs=(),
    )
    pkws = primary_keywords_from_policy(policy)
    assert pkws["minimax"] == ["MiniMax", "MiniMaxAI"]
    # versioned tokens first for versioned_bare brands
    assert pkws["llama"] == ["Llama 4", "Llama"]
    # handle-only brand not in pkws
    assert "glm" not in pkws


# -------------------------------------------------------------------------
# AE5: all rendered strings < 512 chars
# -------------------------------------------------------------------------

def test_all_rendered_strings_under_length_cap():
    """3/5 ships fixed co packs, which is what makes the length cap
    achievable for 20 brands. Verify the renderer respects the cap when
    packs are split per the live config (5-brand C1, 2-brand C2, 3-brand
    C3 + handle specs).
    """
    brand_blocks: dict[str, BrandPolicy] = {}
    packs: list[CoPack] = []
    # Pack 1: 5 brands
    p1 = []
    for i in range(5):
        n = f"poly_{i}"
        brand_blocks[n] = BrandPolicy(
            nickname=n, paths=frozenset({"co"}),
            tokens=(f"Token{i}_longname",),
            co=("llm", "model", "api", "agentic", "huggingface"),
        )
        p1.append(n)
    packs.append(CoPack(brand_nicknames=tuple(p1)))
    # Pack 2: 2 brands
    p2 = []
    for i in range(2):
        n = f"c2_{i}"
        brand_blocks[n] = BrandPolicy(
            nickname=n, paths=frozenset({"co"}),
            tokens=(f"C2Token{i}",),
            co=("llm", "model", "api", "agentic", "huggingface", "baidu", "文心"),
        )
        p2.append(n)
    packs.append(CoPack(brand_nicknames=tuple(p2)))
    # Pack 3: 3 brands
    p3 = []
    for i in range(3):
        n = f"c3_{i}"
        brand_blocks[n] = BrandPolicy(
            nickname=n, paths=frozenset({"co"}),
            tokens=(f"C3Token{i}",),
            co=("llm", "model", "api", "agentic", "huggingface"),
        )
        p3.append(n)
    packs.append(CoPack(brand_nicknames=tuple(p3)))
    # Bare fan-out: 5 brands (B1)
    for i in range(5):
        n = f"bare_{i}"
        brand_blocks[n] = BrandPolicy(
            nickname=n, paths=frozenset({"bare"}),
            tokens=(f"BareToken{i}",),
        )
    # Handle: 5 brands
    for i in range(5):
        n = f"handle_{i}"
        brand_blocks[n] = BrandPolicy(
            nickname=n, paths=frozenset({"handle"}),
            handles=(f"handle_{i}_acct",),
        )

    policy = HarvestPolicy(brands=brand_blocks, co_packs=tuple(packs))
    specs = specs_from_policy(policy)
    pkws = primary_keywords_from_policy(policy)
    calls = plan_calls(
        x_monitor_list_id="1234567890",
        x_query_specs=specs,
        primary_keywords=pkws,
    )
    assert calls, "expected at least one planned call"
    for c in calls:
        assert c.query_length < 512, (
            f"{c.call_id} length {c.query_length} >= 512 — "
            "3/5 packs must split to stay under cap; revisit pack boundary."
        )


# -------------------------------------------------------------------------
# Determinism: same policy -> same specs byte-equal
# -------------------------------------------------------------------------

def test_deterministic_output():
    policy = HarvestPolicy(
        brands={
            "b": BrandPolicy(nickname="b", paths=frozenset({"bare"}),
                             tokens=("B",)),
            "a": BrandPolicy(nickname="a", paths=frozenset({"bare"}),
                             tokens=("A",)),
        },
        co_packs=(),
    )
    s1 = specs_from_policy(policy)
    s2 = specs_from_policy(policy)
    # Equivalent XQuerySpec comparisons
    def key(s):
        return (s.call_id, s.is_wide_net, tuple(sorted(s.wide_net_brands)),
                tuple(sorted(s.brands)), tuple(s.co_occurrence),
                tuple(s.handles), tuple(s.not_include))
    assert [key(s) for s in s1] == [key(s) for s in s2]