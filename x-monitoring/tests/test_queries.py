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
    estimated_cost,
    load_queries,
    validate_query_syntax,
)


def _write_query_yaml(
    tmp: Path,
    model_id: str,
    body: str,
) -> Path:
    qdir = tmp / "queries"
    qdir.mkdir(exist_ok=True)
    p = qdir / f"{model_id}.yaml"
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
            "xiaomi_mimo",
            "moonshot_kimi",
            "inclusionai",
        ]
        for mid in all_ids:
            body = f"""
queries:
  - id: Q1
    query_string: 'from:{mid} min_faves:5'
    expected_signal: release
  - id: Q2
    query_string: '{mid} how min_faves:2'
    expected_signal: community_question
  - id: Q3
    query_string: '{mid} broken min_faves:1'
    expected_signal: criticism
  - id: Q4
    query_string: 'to:{mid} min_faves:5'
    expected_signal: commenter_capture
  - id: Q5
    query_string: '{mid} benchmark min_faves:3'
    expected_signal: other
  - id: Q6
    query_string: '{mid} amazing min_faves:5'
    expected_signal: praise
"""
            _write_query_yaml(root, mid, body)
        for mid in all_ids:
            qs = load_queries(mid, root)
            assert len(qs) == 6
            assert {q.id for q in qs} == set(QUERY_IDS)


def test_rejects_missing_query_string():
    with pytest.raises(ValidationError):
        Query(id="Q1", expected_signal="release")  # type: ignore[call-arg]


def test_rejects_blank_query_string():
    with pytest.raises(ValidationError):
        Query(id="Q1", query_string="   ", expected_signal="release")


def test_rejects_unknown_expected_signal():
    with pytest.raises(ValidationError):
        Query(id="Q1", query_string="from:x", expected_signal="foo")  # type: ignore[arg-type]


def test_validate_catches_unbalanced_parens():
    q = Query(id="Q2", query_string="(foo OR bar", expected_signal="community_question")
    errors = validate_query_syntax(q)
    assert any("unbalanced" in e for e in errors)


def test_validate_catches_stray_colon_in_from():
    q = Query(id="Q1", query_string="from:@handle", expected_signal="release")
    errors = validate_query_syntax(q)
    assert any("stray colon" in e for e in errors)


def test_validate_catches_unknown_operator():
    q = Query(id="Q1", query_string="min_faves:notanumber", expected_signal="release")
    errors = validate_query_syntax(q)
    # 'min_faves:' is a known operator, but the value 'notanumber' is not a
    # number — this is a runtime check Apify does, not a syntax check we
    # own. So this should NOT raise a syntax error.
    # Reverse case: an actually unknown token
    q2 = Query(id="Q1", query_string="bogus:val", expected_signal="release")
    errors2 = validate_query_syntax(q2)
    assert any("unknown operator" in e for e in errors2)


def test_validate_warns_on_lang_filter():
    q = Query(id="Q1", query_string="from:x lang:en", expected_signal="release")
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
    expected_signal: release
  - id: Q2
    query_string: 'minimax how'
    expected_signal: community_question
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
    expected_signal: release
  - id: Q1
    query_string: 'b'
    expected_signal: release
""",
        )
        with pytest.raises(ValueError, match="duplicate"):
            load_queries("minimax", root)


def test_estimated_cost_skips_disabled():
    qs = [
        Query(id="Q1", query_string="x", expected_signal="release", max_results=50, enabled=True),
        Query(id="Q2", query_string="y", expected_signal="community_question", max_results=50, enabled=False),
        Query(id="Q3", query_string="z", expected_signal="criticism", max_results=50, enabled=True),
    ]
    assert estimated_cost(qs) == 100
