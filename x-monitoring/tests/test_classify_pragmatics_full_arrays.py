"""U2a + U2b: parser return shape change + array reshape for
classify_pragmatics_full.

Plan: docs/plans/2026-07-03-003-feat-post-fetch-taxonomy-and-multi-discourse-plan.md
Units U2a + U2b.

Verifies:
- U2a: _parse_pragmatics_full_response returns {"by_brand": ..., "unsanctioned_flags": ...}
- U2a: top-level unsanctioned_flags is filtered against the allow-list
- U2a: unknown post_type / sentiment / discourse_role coerce to defaults
- U2b: _parse_pragmatics_full_response_arrays returns {"rows": ..., "unsanctioned_flags": ...}
- U2b: post_types array emits one row per post_type
- U2b: discourse_roles array emits one row per discourse_role
- U2b: Cartesian expansion (post_types × discourse_roles) per brand
- U2b: hard cap at 6 entries truncates with warning
- U2b: unknown values in arrays are filtered out
- U2b: missing arrays default to ["hands_on_usage"] / ["uncategorized"]
"""

from __future__ import annotations

import pytest

from x_monitor.attribution import (
    _VALID_POST_TYPES,
    _VALID_DISCOURSE,
    _VALID_UNSANCTIONED_FLAGS,
    _parse_pragmatics_full_response,
    _parse_pragmatics_full_response_arrays,
    _ARRAY_HARD_CAP,
)


# --- fixtures --------------------------------------------------------


REGISTRY = {"glm", "moonshot_kimi", "minimax"}


# ===========================================================================
# U2a: scalar parser
# ===========================================================================


def test_u2a_returns_by_brand_and_unsanctioned_flags_shape():
    """U2a: parser returns the new shape, not the old dict-only shape."""
    response = {
        "classifications": [
            {"brand_id": "glm", "post_type": "hands_on_usage",
             "sentiment": "positive", "discourse_role": "genuine_hype",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
        "unsanctioned_flags": ["scam"],
    }
    result = _parse_pragmatics_full_response(response, REGISTRY)
    assert set(result.keys()) == {"by_brand", "unsanctioned_flags"}
    assert "glm" in result["by_brand"]
    assert result["by_brand"]["glm"]["sentiment"] == "positive"
    assert result["unsanctioned_flags"] == ["scam"]


def test_u2a_empty_response_returns_empty_shape():
    """Empty LLM response still returns the new shape, not {}."""
    result = _parse_pragmatics_full_response({}, REGISTRY)
    assert result == {"by_brand": {}, "unsanctioned_flags": []}


def test_u2a_unsanctioned_flags_filtered_to_allow_list():
    """Unknown flag values are dropped; valid values pass through."""
    response = {
        "classifications": [],
        "unsanctioned_flags": ["scam", "crypto", "marketing_spam",
                                "unauthorized", "bogus_value", None, 42],
    }
    result = _parse_pragmatics_full_response(response, REGISTRY)
    assert result["unsanctioned_flags"] == [
        "scam", "crypto", "marketing_spam", "unauthorized",
    ]


def test_u2a_unsanctioned_flags_missing_defaults_to_empty():
    """Missing unsanctioned_flags key returns empty list, not None."""
    response = {"classifications": []}
    result = _parse_pragmatics_full_response(response, REGISTRY)
    assert result["unsanctioned_flags"] == []


def test_u2a_unknown_post_type_coerces_to_hands_on_usage():
    """Bogus post_type falls back to 'hands_on_usage' (the defensive default)."""
    response = {
        "classifications": [
            {"brand_id": "glm", "post_type": "totally_made_up",
             "sentiment": "positive", "discourse_role": "genuine_hype",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    result = _parse_pragmatics_full_response(response, REGISTRY)
    assert result["by_brand"]["glm"]["post_type"] == "hands_on_usage"


def test_u2a_new_post_types_accepted():
    """advertising_marketing + event_announcement are valid post_types."""
    response = {
        "classifications": [
            {"brand_id": "glm", "post_type": "advertising_marketing",
             "sentiment": "positive", "discourse_role": "genuine_hype",
             "china_nationalism": "none", "us_nationalism": "none"},
            {"brand_id": "moonshot_kimi", "post_type": "event_announcement",
             "sentiment": "neutral", "discourse_role": "uncategorized",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    result = _parse_pragmatics_full_response(response, REGISTRY)
    assert result["by_brand"]["glm"]["post_type"] == "advertising_marketing"
    assert result["by_brand"]["moonshot_kimi"]["post_type"] == "event_announcement"


def test_u2a_advertising_marketing_discourse_hyphenated():
    """The new discourse key 'advertising-marketing' (hyphenated) is valid."""
    response = {
        "classifications": [
            {"brand_id": "glm", "post_type": "hands_on_usage",
             "sentiment": "positive", "discourse_role": "advertising-marketing",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    result = _parse_pragmatics_full_response(response, REGISTRY)
    assert result["by_brand"]["glm"]["discourse_role"] == "advertising-marketing"
    # Confirm the underscore variant is NOT in the allow-list.
    assert "advertising_marketing" not in _VALID_DISCOURSE
    assert "advertising-marketing" in _VALID_DISCOURSE


def test_u2a_brand_not_in_registry_skipped():
    """brand_id not in the registry is silently dropped."""
    response = {
        "classifications": [
            {"brand_id": "unknown_brand", "post_type": "hands_on_usage",
             "sentiment": "positive", "discourse_role": "genuine_hype",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    result = _parse_pragmatics_full_response(response, REGISTRY)
    assert "unknown_brand" not in result["by_brand"]
    assert result["by_brand"] == {}


# ===========================================================================
# U2b: array parser
# ===========================================================================


def test_u2b_returns_rows_and_unsanctioned_flags_shape():
    """U2b parser returns {'rows': [...], 'unsanctioned_flags': [...]}."""
    response = {
        "classifications": [
            {"brand_id": "glm",
             "post_types": ["performance_comparisons", "feedback_questions"],
             "discourse_roles": ["self_deprecation"],
             "sentiment": "neutral",
             "china_nationalism": "mild_pro", "us_nationalism": "none"},
        ],
        "unsanctioned_flags": ["scam"],
    }
    result = _parse_pragmatics_full_response_arrays(response, REGISTRY)
    assert set(result.keys()) == {"rows", "unsanctioned_flags"}
    assert result["unsanctioned_flags"] == ["scam"]
    # Cartesian: 2 post_types × 1 discourse_role = 2 rows.
    assert len(result["rows"]) == 2


def test_u2b_multiple_post_types_per_brand():
    """A brand with 2 post_types and 1 discourse_role emits 2 rows."""
    response = {
        "classifications": [
            {"brand_id": "glm",
             "post_types": ["performance_comparisons", "feedback_questions"],
             "discourse_roles": ["self_deprecation"],
             "sentiment": "neutral",
             "china_nationalism": "mild_pro", "us_nationalism": "none"},
        ],
    }
    result = _parse_pragmatics_full_response_arrays(response, REGISTRY)
    rows = result["rows"]
    assert len(rows) == 2
    pt_set = {r["post_type"] for r in rows}
    assert pt_set == {"performance_comparisons", "feedback_questions"}
    assert all(r["brand_id"] == "glm" for r in rows)
    assert all(r["discourse_role"] == "self_deprecation" for r in rows)


def test_u2b_multiple_discourse_roles_per_brand():
    """A brand with 1 post_type and 2 discourse_roles emits 2 rows."""
    response = {
        "classifications": [
            {"brand_id": "glm",
             "post_types": ["performance_comparisons"],
             "discourse_roles": ["genuine_hype", "advertising-marketing"],
             "sentiment": "positive",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    result = _parse_pragmatics_full_response_arrays(response, REGISTRY)
    assert len(result["rows"]) == 2
    rows = result["rows"]
    dr_set = {r["discourse_role"] for r in rows}
    assert dr_set == {"genuine_hype", "advertising-marketing"}


def test_u2b_cartesian_expansion():
    """2 post_types × 2 discourse_roles = 4 rows for one brand."""
    response = {
        "classifications": [
            {"brand_id": "glm",
             "post_types": ["performance_comparisons", "feedback_questions"],
             "discourse_roles": ["genuine_hype", "advertising-marketing"],
             "sentiment": "positive",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    result = _parse_pragmatics_full_response_arrays(response, REGISTRY)
    assert len(result["rows"]) == 4


def test_u2b_hard_cap_on_post_types():
    """post_types with >6 entries are truncated to 6."""
    response = {
        "classifications": [
            {"brand_id": "glm",
             "post_types": ["hands_on_usage"] * 100,  # 100 copies
             "discourse_roles": ["genuine_hype"],
             "sentiment": "positive",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    result = _parse_pragmatics_full_response_arrays(response, REGISTRY)
    # Cap at 6 → 6 rows.
    assert len(result["rows"]) == _ARRAY_HARD_CAP
    assert _ARRAY_HARD_CAP == 6  # hard cap value is part of the contract


def test_u2b_hard_cap_on_discourse_roles():
    """discourse_roles with >6 entries are truncated to 6."""
    response = {
        "classifications": [
            {"brand_id": "glm",
             "post_types": ["hands_on_usage"],
             "discourse_roles": ["genuine_hype"] * 50,
             "sentiment": "positive",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    result = _parse_pragmatics_full_response_arrays(response, REGISTRY)
    assert len(result["rows"]) == _ARRAY_HARD_CAP


def test_u2b_unknown_values_in_post_types_filtered():
    """Unknown post_type values are dropped from the array."""
    response = {
        "classifications": [
            {"brand_id": "glm",
             "post_types": ["hands_on_usage", "totally_made_up", "performance_comparisons"],
             "discourse_roles": ["genuine_hype"],
             "sentiment": "positive",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    result = _parse_pragmatics_full_response_arrays(response, REGISTRY)
    pt_set = {r["post_type"] for r in result["rows"]}
    assert pt_set == {"hands_on_usage", "performance_comparisons"}


def test_u2b_unknown_values_in_discourse_roles_filtered():
    """Unknown discourse_role values are dropped from the array."""
    response = {
        "classifications": [
            {"brand_id": "glm",
             "post_types": ["hands_on_usage"],
             "discourse_roles": ["genuine_hype", "totally_made_up"],
             "sentiment": "positive",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    result = _parse_pragmatics_full_response_arrays(response, REGISTRY)
    dr_set = {r["discourse_role"] for r in result["rows"]}
    assert dr_set == {"genuine_hype"}


def test_u2b_missing_post_types_defaults_to_hands_on_usage():
    """Missing post_types falls back to ['hands_on_usage']."""
    response = {
        "classifications": [
            {"brand_id": "glm",
             "post_types": None,
             "discourse_roles": ["genuine_hype"],
             "sentiment": "positive",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    result = _parse_pragmatics_full_response_arrays(response, REGISTRY)
    pt_set = {r["post_type"] for r in result["rows"]}
    assert pt_set == {"hands_on_usage"}


def test_u2b_missing_discourse_roles_defaults_to_uncategorized():
    """Missing discourse_roles falls back to ['uncategorized']."""
    response = {
        "classifications": [
            {"brand_id": "glm",
             "post_types": ["hands_on_usage"],
             "discourse_roles": None,
             "sentiment": "positive",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    result = _parse_pragmatics_full_response_arrays(response, REGISTRY)
    dr_set = {r["discourse_role"] for r in result["rows"]}
    assert dr_set == {"uncategorized"}


def test_u2b_empty_post_types_defaults_to_hands_on_usage():
    """Empty post_types list (not missing, but []) falls back to ['hands_on_usage']."""
    response = {
        "classifications": [
            {"brand_id": "glm",
             "post_types": [],
             "discourse_roles": ["genuine_hype"],
             "sentiment": "positive",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    result = _parse_pragmatics_full_response_arrays(response, REGISTRY)
    pt_set = {r["post_type"] for r in result["rows"]}
    assert pt_set == {"hands_on_usage"}


def test_u2b_multiple_brands():
    """Two brands each with arrays → rows for both."""
    response = {
        "classifications": [
            {"brand_id": "glm",
             "post_types": ["performance_comparisons"],
             "discourse_roles": ["genuine_hype"],
             "sentiment": "positive",
             "china_nationalism": "none", "us_nationalism": "none"},
            {"brand_id": "moonshot_kimi",
             "post_types": ["hands_on_usage", "feedback_questions"],
             "discourse_roles": ["absurdist_meme"],
             "sentiment": "mixed",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    result = _parse_pragmatics_full_response_arrays(response, REGISTRY)
    glm_rows = [r for r in result["rows"] if r["brand_id"] == "glm"]
    kimi_rows = [r for r in result["rows"] if r["brand_id"] == "moonshot_kimi"]
    assert len(glm_rows) == 1
    assert len(kimi_rows) == 2


def test_u2b_scalar_legacy_keys_fall_back_to_defaults():
    """Legacy scalar post_type / discourse_role keys (U1 shape) → defaults.

    The arrays parser expects the new array contract; scalar values are
    not auto-promoted to single-element arrays. The scalar parser
    (_parse_pragmatics_full_response) is the legacy compat path.
    """
    response = {
        "classifications": [
            {"brand_id": "glm",
             "post_type": "hands_on_usage",  # scalar (legacy)
             "discourse_role": "genuine_hype",  # scalar (legacy)
             "sentiment": "positive",
             "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }
    result = _parse_pragmatics_full_response_arrays(response, REGISTRY)
    assert len(result["rows"]) == 1
    # post_types was a scalar (not a list) → defaulted to [hands_on_usage].
    assert result["rows"][0]["post_type"] == "hands_on_usage"
    # discourse_roles was a scalar (not a list) → defaulted to [uncategorized].
    assert result["rows"][0]["discourse_role"] == "uncategorized"


def test_u2b_unsanctioned_flags_in_arrays_parser():
    """The array parser also surfaces top-level unsanctioned_flags."""
    response = {
        "classifications": [],
        "unsanctioned_flags": ["scam", "crypto", "bogus"],
    }
    result = _parse_pragmatics_full_response_arrays(response, REGISTRY)
    assert result["unsanctioned_flags"] == ["scam", "crypto"]
    assert result["rows"] == []


# ===========================================================================
# Constants exposed
# ===========================================================================


def test_u2a_allow_list_includes_new_post_types():
    """Migration 027 added 2 post_types — they're in the allow-list."""
    assert "advertising_marketing" in _VALID_POST_TYPES
    assert "event_announcement" in _VALID_POST_TYPES


def test_u2a_allow_list_includes_advertising_marketing_discourse():
    """advertising-marketing (hyphen) is in the discourse allow-list."""
    assert "advertising-marketing" in _VALID_DISCOURSE


def test_u2a_unsanctioned_flags_allow_list_has_four_values():
    """The four flag values from the brainstorm are in the allow-list."""
    assert _VALID_UNSANCTIONED_FLAGS == frozenset(
        {"marketing_spam", "scam", "crypto", "unauthorized"}
    )