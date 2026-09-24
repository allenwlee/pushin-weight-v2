"""Keep the actual source distinctions and bad drafts in the live regression net."""

import json

import pytest

from monitor.trend_narrative_candidates import _source_brand_relevance
from monitor.trend_narrative_generation import (
    HeadlineGenerationError,
    _align_omitted_independent_ledger_clause,
    _chinese_discount_glosses,
    _explicit_past_event_date,
    _neutralize_unverified_benchmark_operator,
    _neutralize_unverified_cross_source_link,
    _neutralize_unverified_post_link,
    _normalize_source_attribution,
    _unsupported_unverified_post_link,
    _unverified_benchmark_operator,
    _validate_literal_source_links,
    build_per_brand_editor_request,
    validate_per_brand_editor_response,
    validate_per_brand_critic_response,
)
from monitor.trend_narrative_packet import evidence_support_spans
from scripts.headline_0731_regressions import FIXTURE, regression_request
from x_monitor.config import HeadlineNarrativeConfig
from x_monitor.deepinfra import DEEPSEEK_0731_MODEL, DeepInfraChatCompletionsClient

NEW_FIXTURE = FIXTURE.with_name("headline_cycle6_source_regressions.json")


def test_brand_relevance_reads_supplied_translation_when_excerpt_omits_middle():
    evidence = {"excerpt": "A long model-perk post with its middle omitted.",
                "text_en": "B.AI will move Hy3 out of the 90% OFF tier tomorrow."}
    result = _source_brand_relevance(evidence, "hunyuan", {"hunyuan": ["Hy3"]})
    assert result["status"] == "explicit_mention"
    assert result["matched_aliases"] == ["Hy3"]


def test_shared_author_requires_matching_observed_handles():
    case = next(c for c in json.loads(FIXTURE.read_text())["cases"]
                if c["case_id"] == "separate_author_attribution")
    dossier = case["packet"]["dossiers"][0]
    cited = ["e_71d8245fa048ac0e3a86bf0b", "e_efa6461e0dc120e045f0ea8c"]
    narrative = {"headline_en": "A post lists StepFun at $10.",
                 "secondary_en": "Another post from the same test author praises its usage.",
                 "propositions": [{"evidence_ids": [source]} for source in cited]}
    assert _unsupported_unverified_post_link(narrative, dossier)
    narrative["secondary_en"] = "Another post praises its usage."
    assert not _unsupported_unverified_post_link(narrative, dossier)
    for source in dossier["evidence"]:
        if source["evidence_id"] in cited:
            source["handle_snapshot"] = "same_reviewer"
    narrative["secondary_en"] = "Another post from the same test author praises its usage."
    assert not _unsupported_unverified_post_link(narrative, dossier)


def test_unverified_author_neutralization_keeps_both_source_claims_in_three_languages():
    case = next(c for c in json.loads(FIXTURE.read_text())["cases"]
                if c["case_id"] == "separate_author_attribution")
    dossier = case["packet"]["dossiers"][0]
    secondary = {
        "en": "Another post from the same test author says StepFun seems generous in usage.",
        "zh_cn": "同一测试作者的另一个帖子称StepFun在用量上似乎相当慷慨。",
        "ja": "同じテスト作者による別の投稿はStepFunの利用量が寛大と述べている。",
    }
    decision = {"source_check": {"subject": secondary["en"],
                                 "supported_secondary_en": secondary["en"]},
                "narrative": {"headline_en": "A post lists StepFun at $10.",
                              "secondary_en": secondary["en"],
                              "secondary_zh_cn": secondary["zh_cn"],
                              "secondary_ja": secondary["ja"],
                              "propositions": [
                                  {"evidence_ids": ["e_71d8245fa048ac0e3a86bf0b"],
                                   "claim_en": "A post lists StepFun at $10."},
                                  {"evidence_ids": ["e_efa6461e0dc120e045f0ea8c"],
                                   "claim_en": secondary["en"],
                                   "claim_zh_cn": secondary["zh_cn"],
                                   "claim_ja": secondary["ja"]}]}}
    _neutralize_unverified_post_link(decision, dossier)
    result = decision["narrative"]
    assert result["secondary_en"] == "Another post says StepFun seems generous in usage."
    assert result["secondary_zh_cn"] == "另一个帖子称StepFun在用量上似乎相当慷慨。"
    assert result["secondary_ja"] == "別の投稿はStepFunの利用量が寛大と述べている。"
    assert result["headline_en"] == "A post lists StepFun at $10."
    assert result["secondary_en"] == decision["source_check"]["supported_secondary_en"]
    assert not _unsupported_unverified_post_link(result, dossier)
    result["secondary_ja"] = "同じテスト投稿者が別の投稿で、StepFunは寛大と述べた。"
    _neutralize_unverified_post_link(decision, dossier)
    assert result["secondary_ja"] == "別の投稿で、StepFunは寛大と述べた。"


def test_separate_platform_posts_keep_both_offers_without_claiming_same_platform():
    case = next(c for c in json.loads(NEW_FIXTURE.read_text())["cases"]
                if c["case_id"] == "Q26")
    sources = case["packet"]["dossiers"][0]["evidence"]
    first = next(row["evidence_id"] for row in sources if "faQJkhTOkU" in row["excerpt"])
    second = next(row["evidence_id"] for row in sources if "X0ursd187c" in row["excerpt"])
    secondary = {
        "en": "Another post says the same platform offers DeepSeek at 50% off.",
        "zh_cn": "另一帖子称，同一平台提供五折优惠。",
        "ja": "別の投稿は、同じプラットフォームが50%オフを提供すると報じる。",
    }
    narrative = {
        "headline_en": "A post says a platform opened DeepSeek Web Chat.",
        **{f"secondary_{locale}": value for locale, value in secondary.items()},
        "propositions": [
            {"output_section": "headline", "evidence_ids": [first]},
            {"output_section": "secondary", "evidence_ids": [second],
             **{f"claim_{locale}": value for locale, value in secondary.items()}},
        ],
    }
    decision = {"narrative": narrative,
                "source_check": {"subject": secondary["en"],
                                 "supported_secondary_en": secondary["en"]}}
    _neutralize_unverified_cross_source_link(decision)
    assert narrative["secondary_en"] == "Another post says a platform offers DeepSeek at 50% off."
    assert narrative["secondary_zh_cn"] == "另一帖子称，某平台提供五折优惠。"
    assert narrative["secondary_ja"] == "別の投稿は、あるプラットフォームが50%オフを提供すると報じる。"
    assert narrative["secondary_en"] == decision["source_check"]["supported_secondary_en"]
    assert narrative["headline_en"] == "A post says a platform opened DeepSeek Web Chat."
    narrative["secondary_en"] = secondary["en"]
    narrative["propositions"][1]["evidence_ids"] = [first]
    _neutralize_unverified_cross_source_link(decision)
    assert narrative["secondary_en"] == secondary["en"]


def test_separate_sources_cannot_be_described_as_the_same_post():
    secondary = {"en": "The same post says no human operator is needed.",
                 "zh_cn": "同一帖子称不需要人类操作员。",
                 "ja": "同じ投稿は人間のオペレーターが不要と述べる。"}
    decision = {"source_check": {"subject": secondary["en"],
                                 "supported_secondary_en": secondary["en"]},
                "narrative": {**{f"secondary_{key}": value for key, value in secondary.items()},
                              "propositions": [
                                  {"output_section": "headline", "evidence_ids": ["post_one"]},
                                  {"output_section": "secondary", "evidence_ids": ["post_two"],
                                   **{f"claim_{key}": value for key, value in secondary.items()}}]}}
    _neutralize_unverified_cross_source_link(decision)
    narrative = decision["narrative"]
    assert narrative["secondary_en"] == "Another post says no human operator is needed."
    assert narrative["secondary_zh_cn"] == "另一帖子称不需要人类操作员。"
    assert narrative["secondary_ja"] == "別の投稿は人間のオペレーターが不要と述べる。"
    assert narrative["secondary_en"] == decision["source_check"]["supported_secondary_en"]


def test_model_name_from_another_post_cannot_complete_official_win_claim():
    dossier = {"evidence": [
        {"evidence_id": "win", "excerpt": "@greptile @nvidia Huge win for our engineering teams 🙌"},
        {"evidence_id": "model", "excerpt": "@dakshgup @nvidia And using Nemotron 3 Ultra 👊"},
    ]}
    headline = "NVIDIA's official account says its engineering teams achieved a win using Nemotron 3 Ultra."
    narrative = {"narrative_kind": "content_shift", "headline_en": headline,
                 "headline_zh_cn": "NVIDIA 官方称工程团队用 Nemotron 3 Ultra 获胜。",
                 "headline_ja": "NVIDIAの公式投稿はNemotron 3 Ultraで勝利したと述べる。",
                 "secondary_en": "Another post names Nemotron 3 Ultra.",
                 "secondary_zh_cn": "另一帖子提到 Nemotron 3 Ultra。",
                 "secondary_ja": "別の投稿はNemotron 3 Ultraに言及する。",
                 "headline_proposition_ids": ["p1"], "secondary_proposition_ids": ["p2"]}
    propositions = {"p1": {"evidence_ids": ["win"], "fact_ids": [],
                           "claim_en": headline},
                    "p2": {"evidence_ids": ["model"], "fact_ids": [],
                           "claim_en": narrative["secondary_en"]}}
    with pytest.raises(HeadlineGenerationError, match="cross_source_identifier_invalid"):
        _validate_literal_source_links(narrative, dossier, propositions)
    corrected = "NVIDIA's official account says its engineering teams achieved a win."
    narrative["headline_en"] = corrected
    propositions["p1"]["claim_en"] = corrected
    _validate_literal_source_links(narrative, dossier, propositions)


def test_q26_production_critic_validation_removes_only_unsupported_platform_link():
    case = next(c for c in json.loads(NEW_FIXTURE.read_text())["cases"]
                if c["case_id"] == "Q26")
    config = HeadlineNarrativeConfig.model_validate({**_direct_config().model_dump(),
        "critic_prompt_version": "headline-critic-finance-source-audit-source-ledger-only-v50-ja"})
    envelope, _ = regression_request(case, config)
    raw = json.loads(FIXTURE.with_name("headline_q26_critic_raw.json").read_text())
    assert "same platform" in raw["decisions"][0]["narrative"]["secondary_en"]
    final = validate_per_brand_critic_response(raw, envelope)["decisions"][0]
    narrative = final["narrative"]
    assert narrative["secondary_en"] == (
        "Another post reports a platform offers DeepSeek-V4-Flash and "
        "DeepSeek-V4-Flash-Vision-Exp at 50% off.")
    assert "同一平台" not in narrative["secondary_zh_cn"]
    assert "同じプラットフォーム" not in narrative["secondary_ja"]
    assert narrative["headline_en"].startswith("A post reports a platform opened")
    assert final["source_check"]["supported_secondary_en"] == narrative["secondary_en"]


def test_unverified_series_link_is_removed_even_for_matching_author_handles():
    case = next(c for c in json.loads(FIXTURE.read_text())["cases"]
                if c["case_id"] == "separate_author_attribution")
    dossier = case["packet"]["dossiers"][0]
    cited = ["e_71d8245fa048ac0e3a86bf0b", "e_efa6461e0dc120e045f0ea8c"]
    for source in dossier["evidence"]:
        if source["evidence_id"] in cited:
            source["handle_snapshot"] = "same_reviewer"
    secondary = {
        "en": "Another post from the same test series says StepFun seems generous.",
        "zh_cn": "同一测试系列的另一篇帖子称StepFun似乎慷慨。",
        "ja": "同じテストシリーズの別の投稿はStepFunが寛大と述べる。",
    }
    decision = {"source_check": {"subject": secondary["en"],
                                 "supported_secondary_en": secondary["en"]},
                "narrative": {"headline_en": "A post lists StepFun at $10.",
                              "secondary_en": secondary["en"],
                              "secondary_zh_cn": secondary["zh_cn"],
                              "secondary_ja": secondary["ja"],
                              "propositions": [{"evidence_ids": [source]} for source in cited]}}
    assert _unsupported_unverified_post_link(decision["narrative"], dossier)
    _neutralize_unverified_post_link(decision, dossier)
    narrative = decision["narrative"]
    assert narrative["secondary_en"] == "Another post says StepFun seems generous."
    assert narrative["secondary_zh_cn"] == "另一篇帖子称StepFun似乎慷慨。"
    assert narrative["secondary_ja"] == "別の投稿はStepFunが寛大と述べる。"
    assert not _unsupported_unverified_post_link(narrative, dossier)
    narrative["secondary_en"] = "Another post says StepFun seems generous in the same test."
    narrative["secondary_zh_cn"] = "另一篇帖子称，StepFun 在同一测试中的用量似乎慷慨。"
    narrative["secondary_ja"] = "別の投稿は、同じテストでStepFunの使用量が寛大と述べる。"
    decision["source_check"]["supported_secondary_en"] = narrative["secondary_en"]
    assert _unsupported_unverified_post_link(narrative, dossier)
    _neutralize_unverified_post_link(decision, dossier)
    assert narrative["secondary_en"] == "Another post says StepFun seems generous."
    assert narrative["secondary_zh_cn"] == "另一篇帖子称，StepFun 的用量似乎慷慨。"
    assert narrative["secondary_ja"] == "別の投稿は、StepFunの使用量が寛大と述べる。"
    assert narrative["secondary_en"] == decision["source_check"]["supported_secondary_en"]


def test_short_secondary_alias_does_not_turn_another_companys_ring_into_inclusionai():
    case = next(c for c in json.loads(FIXTURE.read_text())["cases"]
                if c["case_id"] == "unsupported_named_event")
    envelope, request = regression_request(case, _direct_config())
    provider = json.loads(request["messages"][0]["content"].split("\n", 1)[1])
    dossier = provider["analysis_packet"]["dossiers"][0]
    ring = next(source for source in dossier["evidence"]
                if source["evidence_id"] == "e_437b76bc49a444f7d9571739")
    assert ring["brand_relevance"]["matched_aliases"] == ["Ring"]
    assert ring["brand_relevance"]["status"] == "uncertain"
    assert ring["brand_relevance"]["reason"] == "short_nonidentity_alias_only"
    assert "Ring" not in dossier["tracked_aliases_in_evidence"]
    assert "inclusionai" in envelope["must_narrate_brand_keys"]


def test_unverified_benchmark_operator_is_removed_without_losing_result():
    case = next(c for c in json.loads(FIXTURE.read_text())["cases"]
                if c["case_id"] == "ranking_comparison_class")
    dossier = case["packet"]["dossiers"][0]
    phrase = {
        "en": "The layer model ran 4.3× faster in the poster's benchmark setup.",
        "zh_cn": "图层模型在发帖者的基准测试设置中快了 4.3 倍。",
        "ja": "レイヤーモデルは投稿者のベンチマーク設定で4.3倍速かった。",
    }
    decision = {"source_check": {"subject": phrase["en"],
                                 "supported_headline_en": phrase["en"]},
                "narrative": {"headline_en": phrase["en"],
                              "headline_zh_cn": phrase["zh_cn"],
                              "headline_ja": phrase["ja"],
                              "propositions": [{"evidence_ids": ["e_9f269d633c8d665e0f034a60"],
                                                "claim_en": phrase["en"],
                                                "claim_zh_cn": phrase["zh_cn"],
                                                "claim_ja": phrase["ja"]}]}}
    assert _unverified_benchmark_operator(decision["narrative"], dossier)
    _neutralize_unverified_benchmark_operator(decision, dossier)
    result = decision["narrative"]
    assert result["headline_en"] == "The layer model ran 4.3× faster in a benchmark setup."
    assert result["headline_zh_cn"] == "图层模型在基准测试设置中快了 4.3 倍。"
    assert result["headline_ja"] == "レイヤーモデルはベンチマーク設定で4.3倍速かった。"
    assert result["headline_en"] == decision["source_check"]["supported_headline_en"]
    assert not _unverified_benchmark_operator(result, dossier)


def test_separate_post_addendum_may_be_omitted_but_a_caveat_may_not():
    final = "Another post reports DeepSeek-V4-Flash at a 50% discount."
    decision = {"source_check": {"supported_secondary_en": final[:-1]
                + ", and a post announces a separate Go match."},
                "narrative": {"secondary_en": final}}
    _align_omitted_independent_ledger_clause(decision)
    assert decision["source_check"]["supported_secondary_en"] == final
    decision["source_check"]["supported_secondary_en"] = (
        final[:-1] + ", and a third reports 36k tokens per request."
    )
    _align_omitted_independent_ledger_clause(decision)
    assert decision["source_check"]["supported_secondary_en"] == final
    decision["source_check"]["supported_secondary_en"] = (
        final[:-1] + "; a third announces a separate Go match."
    )
    _align_omitted_independent_ledger_clause(decision)
    assert decision["source_check"]["supported_secondary_en"] == final
    decision["source_check"]["supported_secondary_en"] = (
        "Another post reports DeepSeek-V4-Flash at a 50% discount, "
        "but only until Friday."
    )
    _align_omitted_independent_ledger_clause(decision)
    assert decision["source_check"]["supported_secondary_en"].endswith(
        "but only until Friday."
    )


def _direct_config():
    return HeadlineNarrativeConfig(
        provider="deepinfra", model=DEEPSEEK_0731_MODEL, base_url="https://api.deepinfra.com/v1/openai",
        editor_prompt_version="headline-editor-finance-v9-ja", editor_request_profile="headline_editor_v4",
        critic_prompt_version="headline-critic-finance-source-audit-source-ledger-only-v31-ja", critic_request_profile="headline_critic_v6",
    )


@pytest.mark.parametrize("case_id,expected_source", [
    ("accusation_actor_action", "e_ff9b718e0103e547689c0e8e"),
    ("group_ranking_to_member", "e_93fc67560e680085f041666f"),
    ("Q32", "e_50e916dedb99abd719768785"),
    ("Q41", "e_44abe152cce584ababb7d4f7"),
])
def test_lead_picker_uses_brand_centric_editor_evidence(case_id, expected_source):
    from monitor.trend_narrative_generation import (
        _editor_source_hints,
        _lead_evidence_id,
    )

    combined = FIXTURE.with_name("headline_all_source_regressions.json")
    case = next(row for row in json.loads(combined.read_text())["cases"]
                if row["case_id"] == case_id)
    hints = _editor_source_hints(json.dumps({"brands": [case["incorrect_narrative"]]}),
                                 case["packet"])
    preferred = tuple(hints[0]["evidence_ids"]) if hints else ()
    assert _lead_evidence_id(case["packet"]["dossiers"][0],
                             preferred_ids=preferred) == expected_source


def test_official_handle_mention_recovers_supported_product_story_without_bare_short_alias():
    from monitor.trend_narrative_candidates import _source_brand_relevance
    from monitor.trend_narrative_generation import _lead_evidence_id

    dossier = next(row for row in json.loads(
        FIXTURE.with_name("headline_cycle9_lead_regressions.json").read_text()
    )["cases"] if row["brand_key"] == "inclusionai")
    aliases = {"inclusionai": ["InclusionAI", "@AntLingAGI"]}
    for source in dossier["evidence"]:
        source["brand_relevance"] = _source_brand_relevance(
            source, "inclusionai", aliases,
        )
    assert _lead_evidence_id(dossier) == "e_d1defb88748f40889e412f18"


def test_short_opinion_only_cluster_does_not_promote_a_joke_to_headline():
    from monitor.trend_narrative_generation import _lead_evidence_id
    from monitor.trend_narrative_packet import project_evidence

    dossier = next(row for row in json.loads(
        FIXTURE.with_name("headline_cycle9_lead_regressions.json").read_text()
    )["cases"] if row["brand_key"] == "sakana_ai")
    assert _lead_evidence_id(dossier) is None
    for source in dossier["evidence"]:
        source["taxonomy"] = {"post_types": {"status": "available",
                                              "values": source["post_type_keys"]}}
    projected = {**dossier, "evidence": [project_evidence(row) for row in dossier["evidence"]]}
    assert _lead_evidence_id(projected) is None


def test_metric_source_span_keeps_sibling_product_as_pronoun_antecedent():
    case = next(c for c in json.loads(NEW_FIXTURE.read_text())["cases"] if c["case_id"] == "Q41")
    source = next(row for row in case["packet"]["dossiers"][0]["evidence"]
                  if row["evidence_id"] == "e_44abe152cce584ababb7d4f7")
    spans = evidence_support_spans(source)
    metric = next(span["text"] for span in spans if "4.3x faster" in span["text"]
                  and span["source_field"] == "excerpt")
    assert "Ming-Image-0.1-Design-Layer goes a step further" in metric
    assert "".join(span["text"] for span in spans if span["source_field"] == "excerpt") == source["excerpt"]


def test_one_day_rank_change_does_not_become_daily_return_in_translations():
    from monitor.trend_narrative_generation import (
        _remove_misattached_daily_return_modifier,
    )

    source = {"e1": {"excerpt": "Nemotron（+5.55%）单日狂飙11名。"}}
    headline_zh = "Nemotron 单日上涨 5.55% 并跃升 11 位。"
    headline_ja = "Nemotron は1日に5.55%上昇し、11位順位を上げた。"
    decision = {
        "source_check": {"number_ownership": [
            {"figure": "+5.55%", "meaning_and_status": "reported return"},
            {"figure": "11 places", "meaning_and_status": "rank improvement in one day"},
        ]},
        "narrative": {"headline_zh_cn": headline_zh, "headline_ja": headline_ja,
                      "propositions": [{"evidence_ids": ["e1"],
                                        "claim_zh_cn": headline_zh, "claim_ja": headline_ja}]},
    }
    _remove_misattached_daily_return_modifier(decision, source)
    assert decision["narrative"]["headline_zh_cn"] == "Nemotron 上涨 5.55% 并跃升 11 位。"
    assert decision["narrative"]["headline_ja"] == "Nemotron は5.55%上昇し、11位順位を上げた。"
    assert decision["narrative"]["propositions"][0]["claim_zh_cn"] == decision["narrative"]["headline_zh_cn"]

    # A genuine daily return must retain its time period.
    decision["source_check"]["number_ownership"][0]["meaning_and_status"] = "one-day return"
    decision["narrative"]["headline_zh_cn"] = headline_zh
    _remove_misattached_daily_return_modifier(decision, source)
    assert decision["narrative"]["headline_zh_cn"] == headline_zh


def test_model_usage_tokens_do_not_become_crypto_tokens_in_chinese():
    from monitor.trend_narrative_generation import _normalize_source_attribution

    def decision():
        return {"source_check": {}, "narrative": {
            "narrative_kind": "quiet_context",
            "headline_zh_cn": "ZCode 提供 3 亿代币。",
            "propositions": [{"output_section": "headline", "evidence_ids": ["e1"],
                              "fact_ids": [], "claim_zh_cn": "ZCode 提供 3 亿代币。"}],
        }}

    ai_source = {"evidence_id": "e1", "excerpt":
                 "3 亿 GLM-5.3-Flash Tokens / 人；只能在 ZCode 里用，不是 API Token。"}
    result = decision()
    _normalize_source_attribution(result, {"evidence": [ai_source]})
    assert result["narrative"]["headline_zh_cn"] == "ZCode 提供 3 亿Token。"
    assert result["narrative"]["propositions"][0]["claim_zh_cn"] == "ZCode 提供 3 亿Token。"

    crypto_source = {"evidence_id": "e1", "excerpt":
                     "Crypto API Token promotion with blockchain rewards."}
    result = decision()
    _normalize_source_attribution(result, {"evidence": [crypto_source]})
    assert result["narrative"]["headline_zh_cn"] == "ZCode 提供 3 亿代币。"


def test_chinese_discount_guard_rejects_mistranslated_english():
    case = next(c for c in json.loads(NEW_FIXTURE.read_text())["cases"] if c["case_id"] == "Q26")
    envelope, _ = build_per_brand_editor_request(case["packet"], _direct_config())
    response = {"editor_response_schema_version": 3, "packet_hash": envelope["packet_hash"],
                "batch_key": envelope["batch_key"], "brands": [case["incorrect_narrative"]]}
    with pytest.raises(HeadlineGenerationError, match="discount_meaning_invalid"):
        validate_per_brand_editor_response(response, envelope)


def test_two_digit_chinese_discount_is_repaired_across_visible_locales():
    source = {"evidence_id": "e_discount", "original_text":
              "目前还打 48 折。Deepseek-v4.1-Flash，欢迎使用我的邀请码。"}
    assert _chinese_discount_glosses(source) == [{
        "evidence_id": "e_discount", "original_term": "48 折",
        "pay_percent": "48", "discount_percent": "52",
    }]
    wrong_en = "The post says the service is currently 48% off."
    wrong_ja = "投稿は、サービスが現在48%オフと述べている。"
    narrative = {
        "headline_en": wrong_en, "headline_ja": wrong_ja,
        "secondary_en": "", "secondary_ja": "", "narrative_kind": "quiet_context",
        "headline_proposition_ids": ["p1"], "secondary_proposition_ids": [],
        "propositions": [{"proposition_id": "p1", "output_section": "headline",
                          "fact_ids": [], "evidence_ids": ["e_discount"],
                          "claim_en": wrong_en, "claim_ja": wrong_ja}],
    }
    dossier = {"evidence": [source]}
    decision = {"narrative": narrative,
                "source_check": {"supported_headline_en": wrong_en}}
    with pytest.raises(HeadlineGenerationError, match="discount_meaning_invalid"):
        _validate_literal_source_links(narrative, dossier, {"p1": narrative["propositions"][0]})
    _normalize_source_attribution(decision, dossier)
    assert narrative["headline_en"] == "The post says the service is currently 52% off."
    assert narrative["headline_ja"] == "投稿は、サービスが現在52%オフと述べている。"
    assert narrative["propositions"][0]["claim_en"] == narrative["headline_en"]
    assert narrative["propositions"][0]["claim_ja"] == narrative["headline_ja"]
    assert decision["source_check"]["supported_headline_en"] == narrative["headline_en"]
    _validate_literal_source_links(narrative, dossier, {"p1": narrative["propositions"][0]})


def test_old_event_date_is_kept_in_a_recent_post_headline():
    source = {"evidence_id": "e_hackathon", "created_at": "2026-09-21T05:16:15Z",
              "original_text": ("Won 3 prizes at the Llama Impact Hackathon in SF. "
                                "We built Llama Navigator. Hackathon win 11 "
                                "Date: Nov 10, 2024")}
    assert _explicit_past_event_date(source).isoformat() == "2024-11-10"
    headline = {"en": "A post reports winning three prizes at the Llama Impact Hackathon.",
                "zh_cn": "一篇帖子称在Llama Impact黑客松中赢得三个奖项。",
                "ja": "ある投稿はLlama Impactハッカソンで3つの賞を受賞したと報じている。"}
    proposition = {"proposition_id": "p1", "output_section": "headline",
                   "fact_ids": [], "evidence_ids": ["e_hackathon"],
                   **{f"claim_{locale}": text for locale, text in headline.items()}}
    narrative = {"narrative_kind": "event_led", "propositions": [proposition],
                 **{f"headline_{locale}": text for locale, text in headline.items()}}
    decision = {"narrative": narrative,
                "source_check": {"supported_headline_en": headline["en"]}}
    _normalize_source_attribution(decision, {"evidence": [source]})
    assert narrative["headline_en"].endswith("(Nov 10, 2024).")
    assert narrative["headline_zh_cn"].endswith("（2024年11月10日）。")
    assert narrative["headline_ja"].endswith("（2024年11月10日）。")
    assert proposition["claim_en"] == narrative["headline_en"]
    assert decision["source_check"]["supported_headline_en"] == narrative["headline_en"]
    assert _explicit_past_event_date({**source, "created_at": "2024-11-12T00:00:00Z"}) is None


def test_final_writer_discount_gloss_preserves_japanese_amount():
    case = next(c for c in json.loads(NEW_FIXTURE.read_text())["cases"] if c["case_id"] == "Q26")
    dossier = case["packet"]["dossiers"][0]
    source = next(row for row in dossier["evidence"] if "1 折优惠" in row["excerpt"] or "1折优惠" in row["excerpt"])
    japanese = "DeepSeekのAPIが1割（価格の10%）の割引で開放された。"
    decision = {
        "source_check": {"supported_headline_en": "DeepSeek is offered at 10% of price."},
        "narrative": {
            "headline_en": "DeepSeek is offered at 10% of price.",
            "headline_zh_cn": "DeepSeek叠加了1折优惠。", "headline_ja": japanese,
            "secondary_en": "Other news.", "secondary_zh_cn": "其他新闻。", "secondary_ja": "他のニュース。",
            "narrative_kind": "quiet_context",
            "headline_proposition_ids": ["p1"], "secondary_proposition_ids": ["p2"],
            "propositions": [
                {"proposition_id": "p1", "output_section": "headline", "fact_ids": [],
                 "evidence_ids": [source["evidence_id"]], "claim_ja": japanese},
                {"proposition_id": "p2", "output_section": "secondary", "fact_ids": [],
                 "evidence_ids": [], "claim_ja": "他のニュース。"},
            ],
        },
    }
    by_id = {row["proposition_id"]: row for row in decision["narrative"]["propositions"]}
    with pytest.raises(HeadlineGenerationError, match="discount_meaning_invalid"):
        _validate_literal_source_links(decision["narrative"], dossier, by_id)
    _normalize_source_attribution(decision, dossier)
    assert decision["narrative"]["headline_ja"] == "DeepSeekのAPIが調整後の価格の10%となる割引で開放された。"
    assert decision["narrative"]["propositions"][0]["claim_ja"] == decision["narrative"]["headline_ja"]
    _validate_literal_source_links(decision["narrative"], dossier, by_id)
    decision["narrative"]["headline_ja"] = "DeepSeekのAPIが1割（10%支払い）の割引で開放された。"
    decision["narrative"]["propositions"][0]["claim_ja"] = decision["narrative"]["headline_ja"]
    with pytest.raises(HeadlineGenerationError, match="discount_meaning_invalid"):
        _validate_literal_source_links(decision["narrative"], dossier, by_id)
    _normalize_source_attribution(decision, dossier)
    assert decision["narrative"]["headline_ja"] == "DeepSeekのAPIが調整後の価格の10%となる割引で開放された。"
    _validate_literal_source_links(decision["narrative"], dossier, by_id)
    decision["narrative"]["headline_ja"] = "DeepSeekのAPIが1 割（価格の10%）の割引で開放された。"
    decision["narrative"]["propositions"][0]["claim_ja"] = decision["narrative"]["headline_ja"]
    with pytest.raises(HeadlineGenerationError, match="discount_meaning_invalid"):
        _validate_literal_source_links(decision["narrative"], dossier, by_id)
    _normalize_source_attribution(decision, dossier)
    assert decision["narrative"]["headline_ja"] == "DeepSeekのAPIが調整後の価格の10%となる割引で開放された。"
    _validate_literal_source_links(decision["narrative"], dossier, by_id)


def test_final_writer_corpus_count_is_never_attributed_to_one_post():
    case = next(c for c in json.loads(NEW_FIXTURE.read_text())["cases"] if c["case_id"] == "Q27")
    dossier = case["packet"]["dossiers"][0]
    source = dossier["evidence"][0]
    count = next(row for row in dossier["facts"] if ":corpus_phrases:document_count:" in row["fact_id"])
    english = ("A post reports the phrase '飞机账号 tg账号' appears in 49 of 58 collected posts, "
               "but no post provides substantive news about Baidu ERNIE.")
    chinese = ("有帖子报告，短语“飞机账号 tg账号”出现在58条收集帖中的49条中，"
               "但没有帖子提供关于百度ERNIE的实质性新闻。")
    japanese = ("ある投稿は、「飞机账号 tg账号」が58件のうち49件に出現すると報告しています"
                "が、どの投稿も百度ERNIEに関する実質的なニュースを提供していない。")
    decision = {
        "source_check": {"supported_secondary_en": english},
        "narrative": {
            "headline_en": "Baidu ERNIE appears in account-sale spam.",
            "headline_zh_cn": "文心一言出现在账号销售广告中。", "headline_ja": "ERNIEがアカウント販売広告に現れる。",
            "secondary_en": english, "secondary_zh_cn": chinese, "secondary_ja": japanese,
            "narrative_kind": "quiet_context",
            "headline_proposition_ids": ["p1"], "secondary_proposition_ids": ["p2"],
            "propositions": [
                {"proposition_id": "p1", "output_section": "headline", "fact_ids": [],
                 "evidence_ids": [source["evidence_id"]]},
                {"proposition_id": "p2", "output_section": "secondary",
                 "fact_ids": [count["fact_id"]], "evidence_ids": [source["evidence_id"]],
                 "claim_en": english, "claim_zh_cn": chinese, "claim_ja": japanese},
            ],
        },
    }
    by_id = {row["proposition_id"]: row for row in decision["narrative"]["propositions"]}
    with pytest.raises(HeadlineGenerationError, match="sample_scope_invalid|corpus_count_attribution_invalid"):
        _validate_literal_source_links(decision["narrative"], dossier, by_id)
    _normalize_source_attribution(decision, dossier)
    assert decision["narrative"]["secondary_en"].startswith("In the collected posts, the phrase")
    assert decision["narrative"]["secondary_zh_cn"].startswith("短语")
    assert decision["narrative"]["secondary_ja"].startswith("「飞机账号 tg账号」")
    assert "no post provides" not in decision["narrative"]["secondary_en"]
    assert "没有帖子提供" not in decision["narrative"]["secondary_zh_cn"]
    assert "どの投稿も" not in decision["narrative"]["secondary_ja"]
    assert decision["source_check"]["supported_secondary_en"] == decision["narrative"]["secondary_en"]
    _validate_literal_source_links(decision["narrative"], dossier, by_id)


@pytest.mark.parametrize("case_id,source_id,clauses", [
    ("ranking_comparison_class", "e_9f269d633c8d665e0f034a60", [
        "ranks #1 among open weight models", "4.3× faster than a 20B Qwen baseline",
    ]),
    ("accusation_actor_action", "e_bc9de9759694be9eda6fa43f", [
        "the three called for the AI frontier to be “paced.”",
        "the sudden alignment", "protect profits and slow Chinese competitors",
        "Days earlier, Anthropic published a report", "such as DeepSeek and Kimi K3",
    ]),
    ("separate_author_attribution", "e_71d8245fa048ac0e3a86bf0b", [
        "I just ran the largest speed and capacity test", "Every sub was tested",
    ]),
    ("group_ranking_to_member", "e_93fc67560e680085f041666f", [
        "9 of the 10 best AI video models", "Kuaishou's Kling",
        "These names top Artificial Analysis",
    ]),
    ("unsupported_named_event", "e_ace264588da7ca7529cee436", [
        "The benchmark question is a strong hook", "I have a few marketing ideas",
        "Open to discussing them in DM?",
    ]),
])
def test_critic_receives_source_qualifiers_and_original_semantic_failure(case_id, source_id, clauses):
    case = next(c for c in json.loads(FIXTURE.read_text())["cases"] if c["case_id"] == case_id)
    config = _direct_config()
    envelope, request = regression_request(case, config)
    provider = json.loads(request["messages"][0]["content"].split("\n", 1)[1])
    dossier = (provider["review_bundles"][0]["dossier"]
               if "review_bundles" in provider else provider["analysis_packet"]["dossiers"][0])
    source = next(e for e in dossier["evidence"] if e["evidence_id"] == source_id)
    retained = "".join(s["text"] for s in source["source_spans"])
    assert all(clause in retained for clause in clauses)
    assert "corpus_signals" not in dossier
    assert "review_bundles" not in provider
    assert "editor_response_raw" not in provider
    assert case["incorrect_narrative"]["headline_en"] not in request["messages"][0]["content"]
    if case_id == "group_ranking_to_member":
        assert "kuaishou" in envelope["must_narrate_brand_keys"]
    if case_id == "unsupported_named_event":
        assert not provider.get("editor_source_hints")
    else:
        assert all(set(hint["evidence_ids"]).issubset(
            {source["evidence_id"] for source in dossier["evidence"]}
        ) for hint in provider.get("editor_source_hints", []))
    if "review_bundles" in envelope:
        assert envelope["review_bundles"][0]["draft"] == case["incorrect_narrative"]
    else:
        assert json.loads(envelope["editor_response_raw"])["brands"] == [case["incorrect_narrative"]]
    expected_status = ("invalid" if case_id in {
        "separate_author_attribution", "unsupported_named_event",
    } else "valid")
    assert envelope["editor_parse"]["status"] == expected_status
    # Mechanical guards catch only literal errors. The paid replay still needs
    # source-grounded semantic review before this regression can pass.


@pytest.mark.parametrize("case_id", ["Q26", "Q27", "Q30", "Q32", "Q41"])
def test_new_failure_cases_keep_source_and_direct_mentions(case_id):
    case = next(c for c in json.loads(NEW_FIXTURE.read_text())["cases"] if c["case_id"] == case_id)
    envelope, request = regression_request(case, _direct_config())
    provider = json.loads(request["messages"][0]["content"].split("\n", 1)[1])
    dossier = provider["analysis_packet"]["dossiers"][0]
    assert dossier["brand_key"] == case["packet"]["manifest_brand_keys"][0]
    assert "corpus_signals" not in dossier
    assert "review_bundles" not in provider
    if case_id == "Q26":
        assert any(note["original_term"] == "1 折" or note["original_term"] == "1折"
                   for note in dossier["resolved_discounts"])
        assert any(note["discount_percent"] == "90" for note in dossier["resolved_discounts"])
        assert "10% discount" not in " ".join(
            span["text"] for source in dossier["evidence"] for span in source["source_spans"]
        )
    if case_id in {"Q27", "Q32", "Q41"}:
        assert dossier["brand_key"] in envelope["must_narrate_brand_keys"]
        wire = DeepInfraChatCompletionsClient(api_key="test", model=DEEPSEEK_0731_MODEL,
            request_profile="headline_critic_v6").build_request(
                model=request["model"], system=request["system"], messages=request["messages"],
                max_tokens=request["max_tokens"])
        variants = wire["response_format"]["json_schema"]["schema"]["properties"]["decisions"]["items"]["anyOf"]
        assert {row["properties"]["decision"]["enum"][0] for row in variants} == {"repair"}
        assert variants[0]["properties"]["narrative"]["properties"]["headline_en"]["minLength"] == 1
        if case_id == "Q27":
            assert dossier["dominant_phrase_hint"]["document_count"] == "49"
            assert dossier["dominant_phrase_hint"]["post_count"] == "58"
