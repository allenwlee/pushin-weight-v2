"""Regression net for the Mistral B1->C1 demotion.

Plan: docs/plans/2026-07-31-002-fix-demote-mistral-from-b1-to-c1-plan.md
Units U1, U2, U3.

WHY THIS FILE EXISTS
--------------------
The 2026-07-31 demotion plan moves `mistral` out of the B1 bare wide-net
(where its polysemous token collides with weather/common-noun noise) and
into C1, where it shares the 5-term minimal co allowlist already proven
against the same class of ambiguity (MiMo/Kimi/Yi/Llama). BEFORE this
plan: B1.wide_net_brands contained `mistral`; C1.brands did NOT contain
`mistral`. AFTER this plan: B1.wide_net_brands is 5 brands without
`mistral`; C1.brands has `mistral: [Mistral, Mixtral]` and the C1 total
is 5 brands. The 7-call shape (A + B1 + B2 + B3 + C1 + C2 + C3) is
preserved.

This file pins the AFTER state. If a future change reintroduces mistral
in B1, drops it from C1, breaks the C1 token set, or breaks the 7-call
shape, these tests fail loudly.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.yaml"

# Pinned AFTER-state values for the Mistral move (live as of 2026-07-31 post-U3).
EXPECTED_B1_WIDE_NET_BRANDS_AFTER: list = [
    "minimax", "qwen", "deepseek", "stepfun", "hunyuan",
]
EXPECTED_B1_WIDE_NET_LEN_AFTER: int = 5

EXPECTED_C1_BRAND_KEYS_AFTER: set = {"mimo", "mistral", "moonshot_kimi", "yi", "llama"}
EXPECTED_C1_MISTRAL_TOKENS_AFTER: set = {"Mistral", "Mixtral"}
EXPECTED_C1_BRAND_COUNT_AFTER: int = 5

EXPECTED_CALL_IDS_AFTER_U3: set = {"A", "B1", "B2", "B3", "C1", "C2", "C3"}


def _load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _find_spec(config: dict, call_id: str) -> dict:
    specs = config.get("x_query_specs") or []
    matches = [s for s in specs if s.get("call_id") == call_id]
    assert len(matches) == 1, (
        f"expected exactly one x_query_spec with call_id={call_id!r}, "
        f"found {len(matches)}"
    )
    return matches[0]


def test_mistral_in_c1_brand_group():
    """R2: mistral MUST appear in C1's brand group with the primary tokens."""
    config = _load_config()
    c1 = _find_spec(config, "C1")
    brands = c1.get("brands") or {}
    assert "mistral" in brands, (
        f"mistral must be in C1 brands (R2). Found keys: {sorted(brands.keys())}"
    )
    actual_tokens = set(brands["mistral"])
    assert actual_tokens == EXPECTED_C1_MISTRAL_TOKENS_AFTER, (
        f"C1.brands.mistral tokens must be {sorted(EXPECTED_C1_MISTRAL_TOKENS_AFTER)}, "
        f"got {sorted(actual_tokens)}"
    )


def test_mistral_not_in_b1_wide_net():
    """R1: mistral MUST NOT be in B1's wide_net_brands; list length is 5."""
    config = _load_config()
    b1 = _find_spec(config, "B1")
    wnb = b1.get("wide_net_brands") or []
    assert "mistral" not in wnb, (
        f"mistral must NOT be in B1 wide_net_brands (R1). Found: {wnb}"
    )
    assert wnb == EXPECTED_B1_WIDE_NET_BRANDS_AFTER, (
        f"B1 wide_net_brands must equal {EXPECTED_B1_WIDE_NET_BRANDS_AFTER}, got {wnb}"
    )
    assert len(wnb) == EXPECTED_B1_WIDE_NET_LEN_AFTER, (
        f"B1 wide_net_brands must have {EXPECTED_B1_WIDE_NET_LEN_AFTER} brands, got {len(wnb)}"
    )


def test_call_b_groups_first_group_drops_mistral():
    """R1 (defense in depth): call_b_groups[0] mirrors B1 wide_net_brands."""
    config = _load_config()
    cb = config.get("call_b_groups") or []
    assert len(cb) >= 1, "call_b_groups must be non-empty"
    first = cb[0] or []
    assert "mistral" not in first, (
        f"mistral must NOT be in call_b_groups[0]. Found: {first}"
    )
    assert first == EXPECTED_B1_WIDE_NET_BRANDS_AFTER, (
        f"call_b_groups[0] must equal {EXPECTED_B1_WIDE_NET_BRANDS_AFTER}, got {first}"
    )


def test_c1_brand_count_and_keys():
    """R2 + R8: C1 covers the 5 polysemous brands with the shared thin co."""
    config = _load_config()
    c1 = _find_spec(config, "C1")
    brands = c1.get("brands") or {}
    assert set(brands.keys()) == EXPECTED_C1_BRAND_KEYS_AFTER, (
        f"C1.brands keys must be {sorted(EXPECTED_C1_BRAND_KEYS_AFTER)}, "
        f"got {sorted(brands.keys())}"
    )
    assert len(brands) == EXPECTED_C1_BRAND_COUNT_AFTER, (
        f"C1 must cover {EXPECTED_C1_BRAND_COUNT_AFTER} brands, got {len(brands)}"
    )


def test_c1_co_occurrence_unchanged():
    """R3: C1 co_occurrence stays at the 5-term minimal allowlist."""
    config = _load_config()
    c1 = _find_spec(config, "C1")
    co = c1.get("co_occurrence") or []
    expected = ["llm", "model", "api", "agentic", "huggingface"]
    assert co == expected, (
        f"C1 co_occurrence must be {expected} (5-term minimal allowlist, R3), got {co}"
    )


def test_seven_call_shape_invariant():
    """R5: the 7-call hybrid layout survives the Mistral move.

    Call A is implicit (emitted from x_monitor_list_id, not in
    x_query_specs). The 6 explicit specs must cover B1-B3 and C1-C3.
    """
    config = _load_config()
    specs = config.get("x_query_specs") or []
    actual_ids = {s.get("call_id") for s in specs}
    expected_explicit = EXPECTED_CALL_IDS_AFTER_U3 - {"A"}
    assert actual_ids == expected_explicit, (
        f"x_query_specs call_ids must be {sorted(expected_explicit)} (A is implicit), "
        f"got {sorted(actual_ids)}"
    )


def test_b1_co_occurrence_still_empty():
    """R4: B1 stays bare (no co paren)."""
    config = _load_config()
    b1 = _find_spec(config, "B1")
    assert b1.get("co_occurrence") == [], (
        f"B1 co_occurrence must remain empty (R4), got {b1.get('co_occurrence')}"
    )
