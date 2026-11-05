"""U10: the same alias eligibility must govern search and persisted attribution."""
from pathlib import Path

import pytest

from x_monitor.attribution import (
    compile_keyword_index,
    detect_brand_mentions,
    extract_body_keywords,
)
from x_monitor.harvest_policy import load_policy
from x_monitor.query_plan import _build_query
from x_monitor.specs_from_policy import (
    active_policy_tokens,
    primary_keywords_from_policy,
    specs_from_policy,
)

POLICY = Path(__file__).resolve().parents[1] / "config/harvest_policy.yaml"


@pytest.mark.parametrize("text,expected", [
    ("Qwen Code news 海螺贝壳", {"qwen"}),
    ("Qwen 混元太極拳", {"qwen"}),
    ("有一段时间yt的ai视频好多都是海螺的模型", {"minimax"}),
    ("可以跑海螺H3 做视频、漫剧无压力", {"minimax"}),
    ("原来还有海螺AI", {"minimax"}),
    ("海螺 歌曲", {"minimax"}),
    ("海螺 air", set()),
    ("AI 混元3D建模", {"hunyuan"}),
    ("腾讯混元", {"hunyuan"}),
    ("Hunyuan", {"hunyuan"}),
    ("MiniMax", {"minimax"}),
    ("Meta acquired a company", set()),
    ("Muse concert", set()),
    ("meta AI invitation referral code", {"llama"}),
    ("Museモデルへの招待 code", {"llama"}),
    ("Muse Wonder", {"llama"}),
    ("Muse Voice", {"llama"}),
    ("Llama 4 model", {"llama"}),
])
def test_policy_context_controls_shared_attribution(text, expected):
    policy = load_policy(POLICY)
    rows = [(brand, token, False) for brand, tokens in active_policy_tokens(policy).items() for token in tokens]
    index = compile_keyword_index(rows, policy=policy)
    assert set(detect_brand_mentions(text, index)) == expected
    mentions = extract_body_keywords({"tweet_id": "1", "created_at": "2026-10-24T00:00:00Z", "text": text}, index)
    assert {m.brand_id for m in mentions} == expected


def test_selected_layout_and_bound_lengths():
    policy = load_policy(POLICY)
    primary = primary_keywords_from_policy(policy)
    queries = {s.call_id: _build_query(s, primary_keywords=primary) for s in specs_from_policy(policy)}
    assert set(queries) == {"B1", "B2", "B3", "C1", "C2", "C3", "C4"}
    assert "Llama" not in queries["C1"]
    assert "Llama" in queries["C4"] and '"Muse Wonder"' in queries["C4"]
    assert "(海螺 (AI OR 模型 OR H3 OR 歌曲))" in queries["B1"]
    assert "(混元 (AI OR 模型 OR 3D OR 腾讯))" in queries["B1"]
    for call, query in queries.items():
        bounded = query + " -from:xxyweb3 since_time:1792807200 until_time:1792808100"
        assert len(bounded) <= 512, (call, len(bounded), bounded)


@pytest.mark.parametrize("rule", [
    {"alias": "海螺", "any_of": []},
    {"alias": "unknown", "any_of": ["AI"]},
    {"alias": "海螺", "any_of": "AI"},
    {"alias": "海螺", "any_of": ["from:someone"]},
    {"alias": "海螺", "any_of": ["AI OR spam"]},
    {"alias": "海螺", "any_of": [True]},
    {"alias": "海螺", "any_of": [".*"]},
    {"alias": "海螺", "any_of": ["AI -spam"]},
    {"alias": "海螺", "any_of": ["AI"], "ignore": True},
])
def test_invalid_context_fails_closed(tmp_path, rule):
    import yaml
    raw = yaml.safe_load(POLICY.read_text())
    raw["brands"]["minimax"]["alias_context"] = [rule]
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises((TypeError, ValueError)):
        load_policy(path)


def test_strong_alias_wins_over_shorter_contextual_alias():
    from dataclasses import replace

    from x_monitor.harvest_policy import AliasContext
    policy = load_policy(POLICY)
    brands = dict(policy.brands)
    brands["hunyuan"] = replace(brands["hunyuan"], alias_context=(AliasContext("混元", ("AI",)),))
    index = compile_keyword_index(
        [("hunyuan", "混元", False), ("hunyuan", "腾讯混元", False)],
        policy=replace(policy, brands=brands),
    )
    mentions = extract_body_keywords({"tweet_id": "1", "created_at": "now", "text": "腾讯混元"}, index)
    assert [(m.brand_id, m.raw_token) for m in mentions] == [("hunyuan", "腾讯混元")]


def test_subset_keeps_c4_identity():
    policy = load_policy(POLICY)
    specs = specs_from_policy(policy, brand_nicknames=["llama"])
    assert {s.call_id for s in specs} == {"C4", "B3"}
    assert all(s.call_id != "C4" for s in specs_from_policy(policy, brand_nicknames=["qwen"]))


@pytest.mark.parametrize("wide_net", [False, True])
def test_literal_context_phrases_match_query_and_attribution(wide_net):
    from dataclasses import replace

    from x_monitor.harvest_policy import AliasContext
    from x_monitor.query_plan import XQuerySpec

    rule = AliasContext("Muse", ("machine learning",))
    spec = XQuerySpec(
        call_id="B1" if wide_net else "C4",
        brands={} if wide_net else {"llama": ["Muse"]},
        is_wide_net=wide_net,
        wide_net_brands=("llama",) if wide_net else (),
        alias_context={"llama": (rule,)},
    )
    query = _build_query(spec, primary_keywords={"llama": ["Muse"]})
    assert 'Muse ("machine learning")' in query or '(Muse) ("machine learning")' in query
    policy = load_policy(POLICY)
    brands = dict(policy.brands)
    brands["llama"] = replace(brands["llama"], alias_context=(rule,))
    index = compile_keyword_index([("llama", "muse", False)], policy=replace(policy, brands=brands))
    assert detect_brand_mentions("Muse machine learning", index) == ["llama"]
    assert detect_brand_mentions("Muse machine assisted learning", index) == []


def test_new_month_has_nine_routes_and_old_recipe_stays_eight():
    from scripts import backfill_month as month
    from tests.test_backfill_month import recipe
    old = recipe()
    assert len(month.daily_manifest(old, 0)["windows"][0]["collection_definition"]["scope"]["units"]) == 576
    import copy
    new = copy.deepcopy(old)
    units = new["template"]["windows"][0]["collection_definition"]["scope"]["units"]
    added = copy.deepcopy(units[-1])
    added["scope_key"] = "C4"
    added["ownership"].update(call_id="C4", query="new Meta Muse query")
    units.append(added)
    assert len(month.daily_manifest(new, 0)["windows"][0]["collection_definition"]["scope"]["units"]) == 648
    assert old == recipe()


def test_saved_79_wanted_referrals_remain_attributable():
    import json
    policy = load_policy(POLICY)
    rows = [(brand, token, False) for brand, tokens in active_policy_tokens(policy).items() for token in tokens]
    index = compile_keyword_index(rows, policy=policy)
    cohort = json.loads((Path(__file__).parent / "fixtures/u10_muse_referrals.json").read_text())
    assert len(cohort) == 79
    assert any(row["tweet_id"] == "2113940624651006275" for row in cohort)
    missed = [row["tweet_id"] for row in cohort if "llama" not in detect_brand_mentions(
        (row["text"] or "") + "\n" + (row["quoted_text"] or ""), index,
    )]
    assert not missed
