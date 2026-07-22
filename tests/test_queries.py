# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.queries."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from x_monitor.queries import (
    QUERY_IDS,
    Query,
    X_OPERATOR_CAP,
    assert_under_operator_cap,
    count_x_operators,
    estimated_cost,
    load_queries,
    validate_query_syntax,
)


def _write_query_yaml(
    tmp: Path,
    brand_id: str,
    body: str,
) -> Path:
    qdir = tmp / "queries"
    qdir.mkdir(exist_ok=True)
    p = qdir / f"{brand_id}.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_loads_5_queries_per_model():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # All 9 model query files
        all_ids = [
            "minimax",
            "qwen",
            "deepseek",
            "glm",
            "mimo",
            "moonshot_kimi",
            "inclusionai",
        ]
        for mid in all_ids:
            # U9: the `expected_signal` field was removed from Query
            # entirely. The yaml schema is now id+query_string only.
            body = f"""
queries:
  - id: Q1
    query_string: 'from:{mid} min_faves:5'
  - id: Q2
    query_string: '{mid} how min_faves:2'
  - id: Q3
    query_string: '{mid} broken min_faves:1'
  - id: Q4
    query_string: 'to:{mid} min_faves:5'
  - id: Q5
    query_string: '{mid} benchmark min_faves:3'
  - id: Q6
    query_string: '{mid} amazing min_faves:5'
"""
            _write_query_yaml(root, mid, body)
        for mid in all_ids:
            qs = load_queries(mid, root)
            assert len(qs) == 6
            assert {q.id for q in qs} == set(QUERY_IDS)


def test_rejects_missing_query_string():
    with pytest.raises(ValidationError):
        Query(id="Q1")  # type: ignore[call-arg]


def test_rejects_blank_query_string():
    with pytest.raises(ValidationError):
        Query(id="Q1", query_string="   ")


# U9 (migration 022): the `expected_signal` field was removed from
# `Query` entirely — the 6-signal taxonomy is gone, replaced by
# (post_type, sentiment) classification on each post. The validator
# test is no longer applicable.

def test_validate_catches_unbalanced_parens():
    q = Query(id="Q2", query_string="(foo OR bar")
    errors = validate_query_syntax(q)
    assert any("unbalanced" in e for e in errors)


def test_validate_catches_stray_colon_in_from():
    q = Query(id="Q1", query_string="from:@handle")
    errors = validate_query_syntax(q)
    assert any("stray colon" in e for e in errors)


def test_validate_catches_unknown_operator():
    q = Query(id="Q1", query_string="min_faves:notanumber")
    errors = validate_query_syntax(q)
    # 'min_faves:' is a known operator, but the value 'notanumber' is not a
    # number — this is a runtime check Apify does, not a syntax check we
    # own. So this should NOT raise a syntax error.
    # Reverse case: an actually unknown token
    q2 = Query(id="Q1", query_string="bogus:val")
    errors2 = validate_query_syntax(q2)
    assert any("unknown operator" in e for e in errors2)


def test_validate_warns_on_lang_filter():
    q = Query(id="Q1", query_string="from:x lang:en")
    errors = validate_query_syntax(q)
    assert any("lang" in e for e in errors)


def test_rejects_yaml_missing_query_id():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _write_query_yaml(
            root,
            "minimax",
            """
queries:
  - id: Q1
    query_string: 'from:minimax min_faves:5'
  - id: Q2
    query_string: 'minimax how'
  # missing Q3, Q4, Q5
""",
        )
        with pytest.raises(ValueError, match="missing"):
            load_queries("minimax", root)


def test_rejects_yaml_with_duplicate_query_ids():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _write_query_yaml(
            root,
            "minimax",
            """
queries:
  - id: Q1
    query_string: 'a'
  - id: Q1
    query_string: 'b'
""",
        )
        with pytest.raises(ValueError, match="duplicate"):
            load_queries("minimax", root)


def test_estimated_cost_skips_disabled():
    qs = [
        Query(id="Q1", query_string="x", max_results=50, enabled=True),
        Query(id="Q2", query_string="y", max_results=50, enabled=False),
        Query(id="Q3", query_string="z", max_results=50, enabled=True),
    ]
    assert estimated_cost(qs) == 100



# --- v1.6: operator-cap helpers -------------------------------------------


class TestCountXOperators:
    """count_x_operators counts top-level OR tokens (paren-stripped)."""

    def test_zero_for_single_term(self):
        assert count_x_operators("from:MiniMaxAI") == 0

    def test_n_minus_1_for_n_ored_terms(self):
        # 3 terms ORed => 2 OR tokens at the top level.
        assert count_x_operators("foo OR bar OR baz") == 2

    def test_counts_nested_paren_ors(self):
        # Paren-nested ORs DO count toward the cap (X's cap is total OR
        # operators per query, not top-level). This is important for the
        # v1.6 plan_calls architecture where brand clauses are wrapped
        # in `(BrandA OR BrandB) OR (BrandC OR BrandD)`.
        assert count_x_operators("(foo OR bar) (a OR b)") == 2
        assert count_x_operators("(foo OR bar) baz") == 1

    def test_counts_mixed_top_and_nested(self):
        # count_x_operators counts ALL \bOR\b tokens regardless of
        # paren nesting — X treats each from:/to:/OR as one operator and
        # we conservatively sum them. (foo OR bar) baz OR qux = 2 ORs.
        assert count_x_operators("(foo OR bar) baz OR qux") == 2

    def test_is_case_insensitive(self):
        assert count_x_operators("foo or bar") == 1
        assert count_x_operators("foo Or bar") == 1

    def test_handles_exactly_at_cap(self):
        # 22 OR tokens (23 terms) => 22.
        assert count_x_operators(" OR ".join(f"t{i}" for i in range(23))) == 22

    def test_handles_over_cap(self):
        # 29 OR tokens (30 terms) => 29, triggers the cap check.
        assert count_x_operators(" OR ".join(f"t{i}" for i in range(30))) == 29

    def test_empty_string(self):
        assert count_x_operators("") == 0


class TestAssertUnderOperatorCap:
    """assert_under_operator_cap raises ValueError over the cap, silent at/under."""

    def test_silent_when_zero(self):
        # Should not raise.
        assert_under_operator_cap("from:MiniMaxAI min_faves:5")

    def test_silent_at_exact_cap(self):
        # Exactly 22 ORs is still under the cap (cap is > 22, not >=).
        assert_under_operator_cap(" OR ".join(f"t{i}" for i in range(23)))

    def test_raises_over_cap_with_message(self):
        with pytest.raises(ValueError, match="OR operators at the top level"):
            assert_under_operator_cap(" OR ".join(f"t{i}" for i in range(30)))

    def test_cap_constant_is_22(self):
        # Lock the constant. If we ever bump X_OPERATOR_CAP, this test forces
        # an explicit decision.
        assert X_OPERATOR_CAP == 22
