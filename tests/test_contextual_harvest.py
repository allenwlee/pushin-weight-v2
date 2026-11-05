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
    assert set(queries) == {"B1", "B2", "B3", "C1", "C2", "C3", "C4", "B4"}
    assert "Llama" in queries["B1"] and '"Muse Voice"' in queries["B1"]
    assert "海螺" in queries["C3"] and "歌曲" in queries["C3"]
    assert "混元" in queries["C4"]
    for call, query in queries.items():
        bounded = query + " -from:xxyweb3 since_time:1792807200 until_time:1792808100"
        assert len(bounded.encode("utf-8")) <= 512, (call, len(bounded), bounded)


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


def test_subset_keeps_packed_identity():
    policy = load_policy(POLICY)
    specs = specs_from_policy(policy, brand_nicknames=["llama"])
    assert {s.call_id for s in specs} == {"B1"}
    assert {s.call_id for s in specs_from_policy(policy, brand_nicknames=["qwen"])} == {"C3"}


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


def test_new_routes_preserve_frozen_eight_and_nine_route_recipes():
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
    nvidia = copy.deepcopy(new)
    nv_units = nvidia["template"]["windows"][0]["collection_definition"]["scope"]["units"]
    nv = copy.deepcopy(nv_units[-1])
    nv["scope_key"] = "C5"
    nv["ownership"].update(call_id="C5", query="new NVIDIA AI query")
    nv_units.append(nv)
    assert len(month.daily_manifest(nvidia, 0)["windows"][0]["collection_definition"]["scope"]["units"]) == 720
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


@pytest.mark.parametrize("text,expected", [
    ("Nemotron 3 Ultra released", {"nemo_megatron"}),
    ("NVIDIA/TensorRT-LLM brings up DeepSeek-V4.1-Flash-NVFP4", {"nemo_megatron", "deepseek"}),
    ("NVIDIA Cosmos released", {"nemo_megatron"}),
    ("Isaac GR00T robot policy", {"nemo_megatron"}),
    ("Parakeet ASR benchmark", {"nemo_megatron"}),
    ("Canary speech model", {"nemo_megatron"}),
    ("NVIDIA NIM deployment", {"nemo_megatron"}),
    ("英伟达新模型发布", {"nemo_megatron"}),
    ("NVIDIA stock split tomorrow", {"nemo_megatron"}),
    ("Cosmos staking rewards", {"nemo_megatron"}),
    ("Finding Nemo movie", {"nemo_megatron"}),
    ("a yellow canary sings", {"nemo_megatron"}),
])
def test_nvidia_company_scope_prioritizes_recall(text, expected):
    policy = load_policy(POLICY)
    rows = [(brand, token, False) for brand, tokens in active_policy_tokens(policy).items() for token in tokens]
    index = compile_keyword_index(rows, policy=policy)
    assert set(detect_brand_mentions(text, index)) == expected


def test_nvidia_has_named_bounded_search_and_keeps_handles():
    policy = load_policy(POLICY)
    specs = specs_from_policy(policy, brand_nicknames=["nemo_megatron"])
    queries = {name: _build_query(spec) for spec in specs for name in spec.component_names}
    assert "Nemotron" in queries["nemo_megatron/models"]
    assert "Parakeet" in queries["nemo_megatron/models"]
    assert "NVIDIA" in queries["nemo_megatron/company"]
    assert "@NVIDIAAI" in queries["nemo_megatron/company"]
    assert "@NVIDIAAIDev" in queries["nemo_megatron/company"]
    assert all(len((q + " -from:xxyweb3 since_time:1792807200 until_time:1792808100").encode("utf-8")) <= 512 for q in queries.values())


@pytest.mark.parametrize("text", [
    "Triton Inference Server now supports this backend", "cuDNN improves attention performance",
    "RAPIDS cuML accelerates training", "Isaac Lab adds robot learning environments",
    "Cosmos world model weights are out", "Parakeet v3 released", "NIM deployment guide",
    "NVIDIA releases a robotics toolkit", "NeMo deployment guide", "エヌビディアの新製品",
])
def test_nvidia_recall_does_not_require_context(text):
    policy = load_policy(POLICY)
    rows = [(b, t, False) for b, ts in active_policy_tokens(policy).items() for t in ts]
    assert "nemo_megatron" in detect_brand_mentions(text, compile_keyword_index(rows, policy=policy))


def test_nvidia_link_evidence_keeps_body_and_other_brands_unchanged():
    from copy import deepcopy

    from x_monitor.attribution import attribute_to_brands
    policy = load_policy(POLICY)
    rows = [(b, t, False) for b, ts in active_policy_tokens(policy).items() for t in ts]
    index = compile_keyword_index(rows, policy=policy)
    post = {"tweet_id": "2117953000870379787", "created_at": "2026-11-04T12:11:59Z",
            "text": "Hand data questions to an agent https://t.co/example",
            "entities": {"urls": [
                {"url": "https://t.co/example", "expanded_url": "https://github.com/NVIDIA/auto-ontology"},
                {"expanded_url": "https://qwen.ai/"},
                {"expanded_url": "https://example.com/?brand=NVIDIA"},
            ]}}
    original = deepcopy(post)
    mentions = attribute_to_brands(post, {}, {}, index, [], {})
    assert post == original
    linked = [m for m in mentions if m.brand_id]
    assert [(m.brand_id, m.source, m.raw_token) for m in linked] == [
        ("nemo_megatron", "url_keyword", "https://github.com/NVIDIA/auto-ontology")]


@pytest.mark.parametrize("groups", ["not-a-list", [[]], [[True]], [["NVIDIA"], ["nvidia"]], [["from:nvidia"]]])
def test_invalid_bare_alias_groups_fail_closed(tmp_path, groups):
    import yaml
    raw = yaml.safe_load(POLICY.read_text())
    raw["brands"]["nemo_megatron"]["c_bare_alias_groups"] = groups
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises((TypeError, ValueError)):
        load_policy(path)


def test_nvidia_groups_keep_call_identity_and_every_alias():
    policy = load_policy(POLICY)
    specs = specs_from_policy(policy, brand_nicknames=["nemo_megatron"])
    assert {s.call_id for s in specs} == {"C1", "C2"}
    assert {n for s in specs for n in s.component_names} == {
        "nemo_megatron/models", "nemo_megatron/software", "nemo_megatron/company", "nemo_megatron/product-names"}
    aliases = policy.brands["nemo_megatron"].all_c_bare_aliases
    assert len(aliases) == len(set(aliases)) == 78
    assert {t.casefold() for t in aliases} == active_policy_tokens(policy)["nemo_megatron"]
    assert {"Triton", "cuDNN", "RAPIDS", "Isaac", "NeMo", "NIM"} <= set(aliases)


@pytest.mark.parametrize("entity", [
    {"expanded_url": "javascript:NVIDIA"}, {"expanded_url": "https://[bad/NVIDIA"},
    {"expanded_url": "https://example.com/?brand=NVIDIA"},
    {"display_url": "https://github.com/NVIDIA/auto-ontology"},
])
def test_url_keyword_requires_observed_http_destination(entity):
    from x_monitor.attribution import attribute_to_brands
    policy = load_policy(POLICY)
    index = compile_keyword_index([("nemo_megatron", "NVIDIA", False)], policy=policy)
    post = {"tweet_id": "1", "created_at": "now", "text": "https://t.co/x", "entities": {"urls": [entity]}}
    assert not any(m.brand_id for m in attribute_to_brands(post, {}, {}, index, [], {}))
