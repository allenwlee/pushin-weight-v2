"""Tests for x_monitor.harvest_policy (U2).

Plan: docs/plans/2026-08-05-001-refactor-harvest-policy-3of5-plan.md
Unit U2 (R1-R5, R22).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from x_monitor.harvest_policy import (
    CoPack,
    HarvestPolicy,
    VersionFamily,
    load_policy,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write(tmp_path: Path, name: str, doc: dict) -> Path:
    p = tmp_path / name
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f)
    return p


# -------------------------------------------------------------------------
# Happy-path fixtures
# -------------------------------------------------------------------------

MULTI_PATH_DOC = {
    "brands": {
        "minimax": {
            "paths": ["bare", "handle"],
            "tokens": ["MiniMax", "MiniMaxAI"],
            "handles": ["MiniMax_AI"],
            "notes": "Top-presence bare + official handle.",
        },
        "moonshot_kimi": {
            "paths": ["co", "handle"],
            "tokens": ["Kimi"],
            "co": ["llm", "model"],
            "handles": ["Kimi_Moonshot"],
            "not_include": ["f1", "antonelli"],
        },
    },
    "co_packs": [
        ["moonshot_kimi"],  # single-brand pack — its own co chunk
    ],
}


NONE_OPT_OUT_DOC = {
    "brands": {
        "exaone": {
            "paths": ["none"],
            "notes": "Temporarily opted out; legal review pending 2026-Q3.",
        },
    },
}


# -------------------------------------------------------------------------
# Happy: load multi-path brand
# -------------------------------------------------------------------------

def test_loads_multi_path_brand(tmp_path):
    p = _write(tmp_path, "policy.yaml", MULTI_PATH_DOC)
    policy = load_policy(p)
    assert isinstance(policy, HarvestPolicy)
    assert set(policy.brands) == {"minimax", "moonshot_kimi"}

    m = policy.brand("minimax")
    assert m.paths == frozenset({"bare", "handle"})
    assert m.tokens == ("MiniMax", "MiniMaxAI")
    assert m.handles == ("MiniMax_AI",)
    assert m.not_include == ()

    k = policy.brand("moonshot_kimi")
    assert k.paths == frozenset({"co", "handle"})
    assert k.co == ("llm", "model")
    assert k.not_include == ("f1", "antonelli")


def test_loads_co_packs(tmp_path):
    p = _write(tmp_path, "policy.yaml", MULTI_PATH_DOC)
    policy = load_policy(p)
    assert len(policy.co_packs) == 1
    pack = policy.co_packs[0]
    assert isinstance(pack, CoPack)
    assert pack.brand_nicknames == ("moonshot_kimi",)


# -------------------------------------------------------------------------
# Edge: empty paths allowed only with explicit "none"
# -------------------------------------------------------------------------

def test_none_path_is_allowed_with_documentation(tmp_path):
    p = _write(tmp_path, "policy.yaml", NONE_OPT_OUT_DOC)
    policy = load_policy(p)
    exaone = policy.brand("exaone")
    assert exaone.paths == frozenset({"none"})
    assert "legal review" in exaone.notes


# -------------------------------------------------------------------------
# Errors: prefer fail over warn (R2)
# -------------------------------------------------------------------------

def test_unknown_path_name_fails(tmp_path):
    doc = {"brands": {"minimax": {"paths": ["barrier"], "tokens": ["MiniMax"]}}}
    p = _write(tmp_path, "policy.yaml", doc)
    with pytest.raises(ValueError, match="unknown paths"):
        load_policy(p)


def test_bare_path_without_tokens_fails(tmp_path):
    doc = {"brands": {"minimax": {"paths": ["bare"]}}}
    p = _write(tmp_path, "policy.yaml", doc)
    with pytest.raises(ValueError, match="'bare' path requires non-empty tokens"):
        load_policy(p)


def test_versioned_bare_without_tokens_fails(tmp_path):
    doc = {"brands": {"llama": {"paths": ["versioned_bare"]}}}
    p = _write(tmp_path, "policy.yaml", doc)
    with pytest.raises(ValueError, match="'versioned_bare' path requires"):
        load_policy(p)


def test_co_path_without_co_list_fails(tmp_path):
    doc = {
        "brands": {"moonshot_kimi": {"paths": ["co"], "tokens": ["Kimi"]}},
    }
    p = _write(tmp_path, "policy.yaml", doc)
    with pytest.raises(ValueError, match="'co' path requires non-empty co list"):
        load_policy(p)


def test_handle_path_without_handles_fails(tmp_path):
    doc = {"brands": {"glm": {"paths": ["handle"]}}}
    p = _write(tmp_path, "policy.yaml", doc)
    with pytest.raises(ValueError, match="'handle' path requires non-empty handles"):
        load_policy(p)


def test_none_mutually_exclusive_with_other_paths(tmp_path):
    doc = {"brands": {"minimax": {"paths": ["none", "bare"], "tokens": ["MiniMax"]}}}
    p = _write(tmp_path, "policy.yaml", doc)
    with pytest.raises(ValueError, match="'none' path is mutually exclusive"):
        load_policy(p)


def test_paths_required(tmp_path):
    doc = {"brands": {"minimax": {}}}
    p = _write(tmp_path, "policy.yaml", doc)
    with pytest.raises(ValueError, match="'paths' is required"):
        load_policy(p)


def test_co_brand_must_appear_in_some_co_pack(tmp_path):
    """Cross-check (R2): a brand using 'co' but absent from any co_pack
    would be silently dropped by the planner. Fail loud at load."""
    doc = {
        "brands": {"moonshot_kimi": {
            "paths": ["co"], "tokens": ["Kimi"], "co": ["llm"],
        }},
        "co_packs": [],  # brand not in any pack
    }
    p = _write(tmp_path, "policy.yaml", doc)
    with pytest.raises(ValueError, match="not in any co_pack"):
        load_policy(p)


def test_co_pack_references_unknown_brand_fails(tmp_path):
    doc = {
        "brands": {"minimax": {"paths": ["co"], "tokens": ["MiniMax"], "co": ["llm"]}},
        "co_packs": [["minimax", "ghost_brand"]],
    }
    p = _write(tmp_path, "policy.yaml", doc)
    with pytest.raises(ValueError, match="co_pack references unknown brand"):
        load_policy(p)


def test_empty_policy_file_fails(tmp_path):
    p = tmp_path / "empty.yaml"
    p.write_text("")
    with pytest.raises(ValueError, match="is empty"):
        load_policy(p)


def test_unknown_brand_lookup_raises_with_known_list(tmp_path):
    p = _write(tmp_path, "policy.yaml", MULTI_PATH_DOC)
    policy = load_policy(p)
    with pytest.raises(KeyError, match="brand 'ghost' not present"):
        policy.brand("ghost")


def test_token_list_rejects_non_string_entries(tmp_path):
    doc = {
        "brands": {"minimax": {"paths": ["bare"], "tokens": ["MiniMax", 42]}},
    }
    p = _write(tmp_path, "policy.yaml", doc)
    with pytest.raises(TypeError, match="must be list"):
        load_policy(p)


def test_brand_entry_must_be_mapping(tmp_path):
    doc = {"brands": {"minimax": "not a mapping"}}
    p = _write(tmp_path, "policy.yaml", doc)
    with pytest.raises(TypeError, match="must be a mapping"):
        load_policy(p)


def test_loads_version_family_with_defaults(tmp_path):
    doc = {
        "brands": {
            "hunyuan": {
                "paths": ["bare"],
                "tokens": ["Hunyuan"],
                "version_family": {"prefix": "Hy", "current_major": 4},
            }
        }
    }
    policy = load_policy(_write(tmp_path, "policy.yaml", doc))

    assert policy.brand("hunyuan").version_family == VersionFamily(
        prefix="Hy", current_major=4, lookback=1, lookahead=1
    )


def test_version_family_requires_non_empty_prefix(tmp_path):
    doc = {
        "brands": {
            "hunyuan": {
                "paths": ["bare"],
                "tokens": ["Hunyuan"],
                "version_family": {"prefix": "", "current_major": 4},
            }
        }
    }

    with pytest.raises(ValueError, match="version_family.*prefix"):
        load_policy(_write(tmp_path, "policy.yaml", doc))


def test_versioned_bare_family_is_a_valid_token_source(tmp_path):
    doc = {
        "brands": {
            "hunyuan": {
                "paths": ["versioned_bare"],
                "version_family": {
                    "prefix": "Hy",
                    "current_major": 4,
                    "lookback": 1,
                    "lookahead": 1,
                },
            }
        }
    }

    policy = load_policy(_write(tmp_path, "policy.yaml", doc))

    assert policy.brand("hunyuan").tokens == ()
    assert policy.brand("hunyuan").version_family is not None


def test_version_family_rejects_lookback_beyond_current_major(tmp_path):
    doc = {
        "brands": {
            "hunyuan": {
                "paths": ["bare"],
                "version_family": {
                    "prefix": "Hy",
                    "current_major": 1,
                    "lookback": 2,
                },
            }
        }
    }

    with pytest.raises(ValueError, match="lookback cannot exceed current_major"):
        load_policy(_write(tmp_path, "policy.yaml", doc))


@pytest.mark.parametrize("prefix", ["   ", " Hy"])
def test_version_family_rejects_prefix_whitespace(tmp_path, prefix):
    doc = {
        "brands": {
            "hunyuan": {
                "paths": ["bare"],
                "tokens": ["Hunyuan"],
                "version_family": {"prefix": prefix, "current_major": 4},
            }
        }
    }

    with pytest.raises(ValueError, match="version_family.*prefix"):
        load_policy(_write(tmp_path, "policy.yaml", doc))


@pytest.mark.parametrize("field", ["current_major", "lookback", "lookahead"])
def test_version_family_rejects_negative_numeric_values(tmp_path, field):
    version_family = {
        "prefix": "Hy",
        "current_major": 4,
        "lookback": 1,
        "lookahead": 1,
    }
    version_family[field] = -1
    doc = {
        "brands": {
            "hunyuan": {
                "paths": ["bare"],
                "tokens": ["Hunyuan"],
                "version_family": version_family,
            }
        }
    }

    with pytest.raises(ValueError, match="version_family.*non-negative"):
        load_policy(_write(tmp_path, "policy.yaml", doc))
