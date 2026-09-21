"""U1: pin the versioned rare-type query before any provider call."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from x_monitor.harvest_policy import load_policy
from x_monitor.queries import X_LENGTH_CAP, assert_under_length_cap
from x_monitor.rare_type_extra_search import (
    QUERY_COVERAGE,
    QUERY_VERSION,
    planned_query_string,
    render_rare_type_extra_search_query,
)
from x_monitor.specs_from_policy import specs_from_policy

FIXTURES = Path(__file__).parent / "fixtures" / "rare_type_extra_search"


def test_planned_query_has_required_outer_shape() -> None:
    query = planned_query_string()
    assert query.startswith("((")
    assert query.endswith(")) min_faves:0")
    assert "since_time:" not in query
    assert "until_time:" not in query


def test_versioned_query_covers_required_local_shapes() -> None:
    cases = json.loads((FIXTURES / "query_cases.json").read_text())
    query = planned_query_string()

    assert QUERY_VERSION == cases["query_version"]
    for case in cases["positive_shapes"]:
        assert case["query_fragment"] in query, case["id"]
    for case in cases["forbidden_broad_alternatives"]:
        assert case["query_fragment"] not in query, case["id"]

    assert {row["coverage"] for row in QUERY_COVERAGE} == {
        "personnel_en",
        "personnel_zh_cn",
        "personnel_ja",
        "catalog_handle_only",
        "unknown_ai_employer",
        "narrow_ml_jobs",
        "bounded_events",
        "bounded_opportunities",
        "unbranded_release_token",
    }
    assert all(row["proof"] == "local_query_shape" for row in QUERY_COVERAGE)
    assert all(row["provider_semantics"] == "unverified" for row in QUERY_COVERAGE)


def test_old_appendix_seed_is_retained_only_as_historical_fixture() -> None:
    seed = json.loads((FIXTURES / "historical_seed.json").read_text())
    assert seed["status"] == "historical_seed_not_live"
    assert seed["planner_query"] != planned_query_string()
    assert "I left OpenAI" in seed["planner_query"]
    assert len(seed["rendered_query_example"]) <= X_LENGTH_CAP


def test_query_overlap_audit_uses_current_policy_specs() -> None:
    policy = load_policy(Path("config/harvest_policy.yaml"))
    specs = specs_from_policy(policy)
    b1 = next(spec for spec in specs if spec.call_id == "B1")
    b2 = next(spec for spec in specs if spec.call_id == "B2")

    assert {"minimax", "qwen", "deepseek", "stepfun", "hunyuan"} <= set(
        b1.wide_net_brands
    )
    query = planned_query_string()
    # R5 is a shape guard, not a promise of zero semantic overlap. The extra
    # query must not add the current B1 brands as broad standalone alternatives.
    for fragment in (" OR MiniMax OR ", " OR Qwen OR ", " OR DeepSeek OR "):
        assert fragment not in query
    assert '"I\'ve joined @deepseek_ai"' in query  # explicit R4 exception
    assert "deepseek_ai" in b2.handles  # known overlap; not claimed as a B miss
    handle_row = next(
        row for row in QUERY_COVERAGE if row["coverage"] == "catalog_handle_only"
    )
    assert handle_row["overlap_boundary"] == "current_policy_B2_overlap_known"


@pytest.mark.parametrize(
    ("since_time", "until_time"),
    [(1726900000, 1726900900), (10_000_000_000, 10_000_000_900)],
)
def test_rendered_query_uses_provider_renderer_and_stays_under_512(
    monkeypatch: pytest.MonkeyPatch,
    since_time: int,
    until_time: int,
) -> None:
    import x_monitor.rare_type_extra_search as mod

    real_renderer = mod.TwitterApiClient._effective_search_query
    captured: dict[str, object] = {}

    def capture(query, *, since, since_time, until_time):
        captured.update(
            query=query,
            since=since,
            since_time=since_time,
            until_time=until_time,
        )
        return real_renderer(
            query,
            since=since,
            since_time=since_time,
            until_time=until_time,
        )

    monkeypatch.setattr(mod.TwitterApiClient, "_effective_search_query", capture)
    rendered = render_rare_type_extra_search_query(
        since_time=since_time,
        until_time=until_time,
    )

    assert captured == {
        "query": planned_query_string(),
        "since": None,
        "since_time": since_time,
        "until_time": until_time,
    }
    assert len(rendered) <= X_LENGTH_CAP
    assert rendered.endswith(f"since_time:{since_time} until_time:{until_time}")
    assert_under_length_cap(rendered)


@pytest.mark.parametrize(
    ("groups", "match"),
    [
        (("x" * 500,), "length"),
        (("alpha since_time:1",), "operator"),
        (("alpha until_time:2",), "operator"),
        (("alpha min_faves:1",), "operator"),
        (("alpha -DeepSeek",), "unsupported exclusion"),
    ],
)
def test_invalid_query_body_rejected_before_transport(
    monkeypatch: pytest.MonkeyPatch,
    groups: tuple[str, ...],
    match: str,
) -> None:
    import x_monitor.rare_type_extra_search as mod

    monkeypatch.setattr(mod, "RARE_TYPE_EXTRA_SEARCH_GROUPS", groups)
    with pytest.raises(ValueError, match=match):
        mod.render_rare_type_extra_search_query(since_time=1, until_time=2)


@pytest.mark.parametrize(
    ("since_time", "until_time"),
    [(2, 1), (1, 1), (0, 2), (True, 2), (1.5, 2)],
)
def test_invalid_time_window_rejected(since_time, until_time) -> None:
    with pytest.raises((TypeError, ValueError), match="time"):
        render_rare_type_extra_search_query(
            since_time=since_time,
            until_time=until_time,
        )
