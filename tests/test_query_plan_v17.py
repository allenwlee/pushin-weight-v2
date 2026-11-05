"""Grouping, token-source and length guards through the current planner API.

The former tests called a removed data-directory/YAML interface and failed
before reaching these guards. Callers now pass explicit specs and primary
keywords; the scheduled caller's policy loading is covered by the cycle tests.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from x_monitor.queries import X_LENGTH_CAP, assert_under_length_cap
from x_monitor.query_plan import PlannedCall, XQuerySpec, plan_calls

LIST_ID = 1234567890
MODELS = ["minimax", "qwen", "deepseek", "glm", "mimo", "moonshot_kimi", "inclusionai"]


@pytest.fixture
def keywords():
    return {
        "minimax": ["MiniMax", "海螺", "Hailuo"],
        "qwen": ["Qwen", "通义千问", "通义"],
        "deepseek": ["DeepSeek", "深度求索"],
        "glm": ["GLM", "智谱", "ChatGLM"],
        "mimo": ["MiMo", "Xiaomi MiMo", "小米 MiMo"],
        "moonshot_kimi": ["Kimi", "月之暗面"],
        "inclusionai": ["InclusionAI", "Ling", "Ring", "Ming"],
    }


def wide_spec(brands=MODELS, call_id="B1"):
    return XQuerySpec(call_id=call_id, is_wide_net=True, wide_net_brands=tuple(brands))


def test_default_without_specs_emits_only_list_call():
    assert [c.call_id for c in plan_calls(LIST_ID, [])] == ["A"]


def test_explicit_wide_spec_emits_exactly_two_calls(keywords):
    calls = plan_calls(LIST_ID, [wide_spec()], primary_keywords=keywords)
    assert [c.call_id for c in calls] == ["A", "B1"]


def test_explicit_wide_and_constrained_specs_compose_without_extra_calls(keywords):
    spec = XQuerySpec(call_id="C1", brands={
        "mimo": ["MiMo", "Xiaomi MiMo", "小米 MiMo"],
        "moonshot_kimi": ["Kimi", "月之暗面", "暗面"],
    }, co_occurrence=["api", "llm", "model"])
    calls = plan_calls(LIST_ID, [wide_spec(), spec], primary_keywords=keywords)
    assert [c.call_id for c in calls] == ["A", "B1", "C1"]
    constrained = calls[2]
    assert constrained.call_kind == "brand_wide"
    assert constrained.brand_id in {"mimo", "moonshot_kimi"}
    assert constrained.query_string == (
        "((MiMo OR Xiaomi MiMo OR 小米 MiMo) OR (Kimi OR 月之暗面 OR 暗面)) "
        "(api OR llm OR model) min_faves:0"
    )
    assert constrained.query_length < X_LENGTH_CAP


def test_constrained_query_keeps_per_brand_parentheses():
    spec = XQuerySpec(call_id="C1", brands={"a": ["alpha", "al"], "b": ["beta", "be"]},
                      co_occurrence=["ctx"])
    calls = plan_calls(LIST_ID, [spec])
    assert [c.call_id for c in calls] == ["A", "C1"]
    assert calls[1].query_string == "((alpha OR al) OR (beta OR be)) (ctx) min_faves:0"


def test_constrained_length_cap_raises():
    spec = XQuerySpec(call_id="C1", brands={"oversized": ["x" * 200] * 10},
                      co_occurrence=["api", "llm", "model"])
    with pytest.raises(ValueError, match="length"):
        plan_calls(LIST_ID, [spec])


def test_list_query_keeps_current_zero_like_floor(keywords):
    # The shipped list policy admits zero-like posts; keep that explicit.
    call = plan_calls(LIST_ID, [wide_spec()], primary_keywords=keywords)[0]
    assert call.call_kind == "account"
    assert call.query_string == f"(list:{LIST_ID}) min_faves:0"
    assert call.query_length == len(call.query_string) == 29


def test_wide_query_keeps_seven_brand_groups(keywords):
    call = plan_calls(LIST_ID, [wide_spec()], primary_keywords=keywords)[1]
    assert call.call_kind == "brand_wide"
    assert call.query_string.count("(") == call.query_string.count(")") == 8
    inner = call.query_string[1:call.query_string.rindex(")")]
    assert inner.count("(") == 7
    assert call.query_string.endswith(" min_faves:0")
    assert 180 <= call.query_length <= 400


def test_wide_query_uses_all_caller_supplied_tokens(keywords):
    query = plan_calls(LIST_ID, [wide_spec()], primary_keywords=keywords)[1].query_string
    for tokens in keywords.values():
        for token in tokens:
            assert token in query


def test_wide_query_stays_under_cap(keywords):
    call = plan_calls(LIST_ID, [wide_spec()], primary_keywords=keywords)[1]
    assert call.query_length == len(call.query_string) <= X_LENGTH_CAP


def test_list_id_is_required(keywords):
    with pytest.raises((TypeError, ValueError)):
        plan_calls(None, [wide_spec()], primary_keywords=keywords)


def test_wide_groups_follow_declared_brand_order(keywords):
    query = plan_calls(LIST_ID, [wide_spec(reversed(MODELS))], primary_keywords=keywords)[1].query_string
    groups = re.findall(r"\(([^()]*)\)", query)
    assert "InclusionAI" in groups[0]
    assert "MiniMax" in groups[-1]


def test_missing_primary_keywords_do_not_fabricate_groups(keywords):
    selected = {brand: keywords[brand] for brand in MODELS[:5]}
    query = plan_calls(LIST_ID, [wide_spec()], primary_keywords=selected)[1].query_string
    assert query.count("(") == query.count(")") == 6
    assert query[1:query.rindex(")")].count("(") == 5
    assert "Kimi" not in query and "InclusionAI" not in query


def test_explicit_groups_emit_one_call_each(keywords):
    groups = [MODELS[:2], MODELS[2:4], MODELS[4:]]
    specs = [wide_spec(group, f"B{i}") for i, group in enumerate(groups, 1)]
    assert [c.call_id for c in plan_calls(LIST_ID, specs, primary_keywords=keywords)] == ["A", "B1", "B2", "B3"]


def test_each_explicit_group_stays_under_cap(keywords):
    specs = [wide_spec(MODELS[:4], "B1"), wide_spec(MODELS[4:], "B2")]
    for call in plan_calls(LIST_ID, specs, primary_keywords=keywords):
        assert call.query_length <= X_LENGTH_CAP


def test_groups_do_not_leak_other_brand_tokens(keywords):
    calls = plan_calls(LIST_ID, [wide_spec(["minimax"], "B1"), wide_spec(["glm"], "B2")],
                       primary_keywords=keywords)
    first, second = calls[1].query_string, calls[2].query_string
    assert "MiniMax" in first and "GLM" not in first
    assert "GLM" in second and "MiniMax" not in second


@pytest.mark.parametrize("size", [50, 512])
def test_length_guard_accepts_up_to_exact_cap(size):
    assert_under_length_cap("x" * size)


def test_length_guard_rejects_over_cap():
    with pytest.raises(ValueError, match="512"):
        assert_under_length_cap("x" * 513)


def test_length_cap_remains_512():
    assert X_LENGTH_CAP == 512


def test_query_plan_keeps_removed_intent_and_recursive_split_paths_retired():
    import x_monitor.query_plan as module
    assert not hasattr(module, "INTENT_BUCKETS")
    assert not hasattr(module, "_split_brands_to_fit_cap")
    assert "count_x_operators" not in Path(module.__file__).read_text()


def test_planned_call_supports_brand_wide_queries():
    call = PlannedCall(call_id="B1", call_kind="brand_wide", brand_id="*", bucket=None,
                       query_string="(x) min_faves:0", query_length=14)
    assert call.call_kind == "brand_wide"


@pytest.mark.parametrize("size", [511, 512])
def test_unicode_length_guard_accepts_utf8_boundary(size):
    assert_under_length_cap("测" + "x" * (size - 3))


def test_unicode_length_guard_rejects_short_character_string():
    query = "测" + "x" * 510
    assert len(query) == 511
    with pytest.raises(ValueError, match="513 UTF-8 bytes"):
        assert_under_length_cap(query)
