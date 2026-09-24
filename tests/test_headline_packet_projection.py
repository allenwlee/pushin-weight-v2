"""The provider sees a closed, source-preserving view of private snapshots."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from monitor import trend_narrative_candidates as candidates


def dossier():
    return {
        "brand_key": "yi", "display_name_en": "01.AI",
        "outcome": "narrative_eligible", "private_future_field": "secret",
        "source_row_provenance": {
            "start_at": "2026-09-23T00:00:00Z", "end_at": "2026-09-24T00:00:00Z",
        },
        "comparison_status": {
            "allowed": False, "current_post_count": 10, "prior_post_count": 99,
            "suppression_reasons": ["backlog"], "private_future_field": "secret",
        },
        "family_summaries": {"sentiment": {
            "status": "partial", "covered_post_count": 3, "total_post_count": 10,
            "current_leader": "negative", "largest_change": "positive",
            "private_future_field": "secret",
        }},
        "facts": [
            {"fact_id": "f:yi:count", "family": "volume", "metric": "post_count",
             "current_value": "10", "source_value": "10", "baseline_value": "99",
             "unit": "posts", "direction": "increase", "display_en": "10 posts",
             "coverage_scope": {"status": "complete", "covered_post_count": 10,
                                "total_post_count": 10, "private_future_field": "secret"}},
            {"fact_id": "f:yi:change", "family": "volume", "metric": "post_count_change_pct",
             "source_value": "-90", "unit": "percent"},
        ],
        "evidence": [{
            "evidence_id": "e1", "excerpt": "I did not say Yi is twice as fast as yesterday.",
            "original_text": "I did not say Yi is twice as fast as yesterday.",
            "text_en": "I did not say Yi is twice as fast as yesterday.",
            "text_zh_cn": "我没说 Yi 比昨天快一倍。", "source_language": "en",
            "first_party_role": "public_opaque", "handle_snapshot": "private_handle",
            "_ranks": {"top": 1}, "_role_eligible": {"top": True},
            "private_future_field": "secret", "taxonomy": {
                "sentiment": {"status": "available", "values": ["negative"],
                              "private_future_field": "secret"},
                "private_future_field": {"secret": "secret"},
            },
        }],
        "corpus_signals": [{"corpus_signal_id": "cs1", "phrase": "yi speed",
                            "prevalence": 2, "prior_prevalence": 8,
                            "peer_brand_count": 2, "private_future_field": "secret"}],
    }


def test_suppressed_comparisons_and_unknown_fields_never_reach_provider():
    source = dossier()
    before = deepcopy(source)
    projected = candidates._provider_dossier(source)
    serialized = candidates.canonical_snapshot_json(projected)
    for forbidden in ("secret", "prior_post_count", "baseline_value", "prior_prevalence",
                      "largest_change", "f:yi:change", "_ranks", "_role_eligible",
                      "private_handle"):
        assert forbidden not in serialized
    fact = projected["facts"][0]
    assert fact["value"] == "10"
    assert "direction" not in fact
    scope = projected["scopes"][fact["scope_ref"]]
    assert scope["brand_key"] == "yi"
    assert scope["start_at"] == "2026-09-23T00:00:00Z"
    assert scope["denominator"] == 10
    assert source == before


def test_deduplication_preserves_negation_languages_and_source_identity():
    source = dossier()
    row = candidates._provider_dossier(source)["evidence"][0]
    assert row["excerpt"] == source["evidence"][0]["excerpt"]
    assert row["text_aliases"] == {"original_text": "excerpt", "text_en": "excerpt"}
    assert "original_text" not in row and "text_en" not in row
    assert row["text_zh_cn"] == source["evidence"][0]["text_zh_cn"]
    assert row["source_language"] == "en" and row["evidence_id"] == "e1"


def test_rank_uses_same_boundary_and_keeps_every_brand_and_owned_citations():
    source = dossier()
    empty = {**dossier(), "brand_key": "empty", "outcome": "no_content", "evidence": []}
    packet = candidates.project_provider_packet({
        "packet_schema_version": 3, "window_days": 1,
        "as_of": "2026-09-24T00:00:00Z", "baseline_context": {},
        "dossiers": [source, empty],
    })
    assert [r["brand_key"] for r in packet["dossiers"]] == ["yi", "empty"]
    assert all(row["facts"] for row in packet["dossiers"])
    assert "baseline_value" not in candidates.canonical_snapshot_json(packet)
    assert "shape_summary" not in packet["dossiers"][0]


def test_phrase_extraction_removes_urls_and_stopword_only_pairs_before_ranking():
    start = datetime(2026, 9, 23, tzinfo=UTC)
    spec = {"start_at": start, "end_at": start + timedelta(days=1),
            "upper_at": start + timedelta(days=1), "lower_at": start - timedelta(days=1)}
    rows = [("1", "1", start, "of the in the https://t.co/xyz GLM-5.3 is not reliable 开源 模型")]
    phrases = next(candidates._iter_corpus_documents(rows, spec))["phrases"]
    assert "of the" not in phrases and "in the" not in phrases
    assert not any("https" in p or "xyz" in p or "co " in p for p in phrases)
    assert "not reliable" in phrases
    assert "glm-5.3 is" in phrases and "开源 模型" in phrases


def test_source_relevance_does_not_treat_a_turkish_suffix_as_a_brand():
    aliases = {"yi": ["Yi", "01.AI", "Yi-1.5"], "kling": ["Kling"], "deepseek": ["DeepSeek"]}
    suffix = candidates._source_brand_relevance(
        {"excerpt": "Türkiye'yi seviyorum", "first_party_role": "public_opaque"}, "yi", aliases
    )
    assert suffix["status"] == "uncertain"
    both = candidates._source_brand_relevance(
        {"excerpt": "DeepSeek raised $500m. Kling is fast.", "first_party_role": "public_opaque"},
        "kling", aliases,
    )
    assert both["status"] == "multiple_brands"
    assert both["matched_aliases"] == ["Kling"]
    assert both["other_brand_keys"] == ["deepseek"]


def test_snapshot_aliases_skip_short_nonprimary_product_words(monkeypatch):
    class Keywords:
        def filter(self, **kwargs):
            assert kwargs["is_regex"] is False
            return self

        def order_by(self, *args):
            return self

        def values_list(self, *fields):
            assert fields == ("brand_id", "pattern", "is_primary")
            return [("inclusionai", "Ring", False),
                    ("inclusionai", "Ming-Image", False),
                    ("inclusionai", "Ling", True)]

    monkeypatch.setattr(candidates.BrandKeyword, "objects", Keywords())
    class Accounts:
        def filter(self, **kwargs):
            assert kwargs["role_id"] == "official"
            return self

        def order_by(self, *args):
            return self

        def values_list(self, *fields):
            assert fields == ("brand_id", "account__handle")
            return [("inclusionai", "AntLingAGI"),
                    ("inclusionai", "ParentCompanyNews")]

    monkeypatch.setattr(candidates.BrandAccount, "objects", Accounts())
    class Products:
        def filter(self, **kwargs):
            assert kwargs["hf_type"] == "model"
            return self

        def order_by(self, *args):
            return self

        def values_list(self, *fields):
            assert fields == ("brand_id", "display_name", "repo_id")
            return [("inclusionai", "Ming-Image-0.1-Design",
                     "inclusionAI/Ming-Image-0.1-Design"),
                    ("inclusionai", "Ming-Video-1.0", "inclusionAI/Ming-Video-1.0")]

    monkeypatch.setattr(candidates.Product, "objects", Products())
    aliases = candidates._snapshot_brand_aliases([{
        "candidate_key": {"brand_key": "inclusionai"},
        "display_name_en": "InclusionAI", "display_name_zh_cn": "InclusionAI",
    }], evidence_rows=[{"text": "Ant Group released Ming-Image-0.1-Design."}])
    assert "Ring" not in aliases["inclusionai"]
    assert {"inclusionai", "InclusionAI", "Ming-Image", "Ling"} <= set(aliases["inclusionai"])
    assert "@AntLingAGI" in aliases["inclusionai"]
    assert "@ParentCompanyNews" not in aliases["inclusionai"]
    assert "Ming-Image-0.1-Design" in aliases["inclusionai"]
    assert "Ming-Video-1.0" not in aliases["inclusionai"]
    source = {"evidence_id": "e_model", "excerpt":
              "Ant Group released Ming-Image-0.1-Design, ranked No. 1 among open UI/UX models.",
              "first_party_role": "public_opaque"}
    source["brand_relevance"] = candidates._source_brand_relevance(
        source, "inclusionai", aliases,
    )
    assert source["brand_relevance"]["status"] == "explicit_mention"
    from monitor.trend_narrative_generation import _lead_evidence_id
    assert _lead_evidence_id({
        "brand_key": "inclusionai", "display_name_en": "InclusionAI",
        "display_name_zh_cn": "InclusionAI", "evidence": [source],
    }) == "e_model"
    relevance = candidates._source_brand_relevance(
        {"excerpt": "@AntLingAGI Ling-3.0-flash-VL released a visual agent.",
         "first_party_role": "public_opaque"}, "inclusionai", aliases,
    )
    assert "@AntLingAGI" in relevance["matched_aliases"]


def test_secondary_product_word_does_not_turn_solar_wafers_into_upstage(monkeypatch):
    class Keywords:
        def filter(self, **kwargs):
            return self

        def order_by(self, *args):
            return self

        def values_list(self, *fields):
            return [("upstage", "Solar", False),
                    ("upstage", "Solar Pro 3", False)]

    class Accounts:
        def filter(self, **kwargs):
            return self

        def order_by(self, *args):
            return self

        def values_list(self, *fields):
            return [("upstage", "upstageai")]

    class Products:
        def filter(self, **kwargs):
            return self

        def order_by(self, *args):
            return self

        def values_list(self, *fields):
            return []

    monkeypatch.setattr(candidates.BrandKeyword, "objects", Keywords())
    monkeypatch.setattr(candidates.BrandAccount, "objects", Accounts())
    monkeypatch.setattr(candidates.Product, "objects", Products())
    unrelated = {"evidence_id": "e_reliance", "excerpt":
                 "Reliance invested in sodium-ion batteries and ultra thin solar wafers.",
                 "first_party_role": "public_opaque"}
    aliases = candidates._snapshot_brand_aliases([{
        "candidate_key": {"brand_key": "upstage"},
        "display_name_en": "Upstage Solar", "display_name_zh_cn": "업스테이지",
    }], evidence_rows=[{"text": unrelated["excerpt"]}])
    assert "Solar" not in aliases["upstage"]
    assert "Solar Pro 3" in aliases["upstage"]
    unrelated["brand_relevance"] = candidates._source_brand_relevance(
        unrelated, "upstage", aliases)
    assert unrelated["brand_relevance"]["status"] == "uncertain"
    from monitor.trend_narrative_generation import _lead_evidence_id
    dossier = {"brand_key": "upstage", "display_name_en": "Upstage Solar",
               "display_name_zh_cn": "업스테이지", "evidence": [unrelated]}
    assert _lead_evidence_id(dossier) is None
    actual = {"evidence_id": "e_product", "excerpt":
              "Upstage released Solar Pro 3 for enterprise use.",
              "first_party_role": "public_opaque"}
    actual["brand_relevance"] = candidates._source_brand_relevance(actual, "upstage", aliases)
    dossier["evidence"] = [actual]
    assert _lead_evidence_id(dossier) == "e_product"


def test_versioned_secondary_product_mentions_anchor_only_versioned_sources(monkeypatch):
    from monitor.trend_narrative_generation import _lead_evidence_id

    class Rows:
        def __init__(self, values):
            self.values = values

        def filter(self, **kwargs):
            return self

        def order_by(self, *args):
            return self

        def values_list(self, *fields):
            return self.values

    monkeypatch.setattr(candidates.BrandKeyword, "objects", Rows([
        ("nemo_megatron", "nemotron", False),
    ]))
    monkeypatch.setattr(candidates.BrandAccount, "objects", Rows([]))
    monkeypatch.setattr(candidates.Product, "objects", Rows([]))
    product_post = {"evidence_id": "e_product", "excerpt":
                    "Nemotron 3 Diarization app in Rust, version 0.1 beta.",
                    "first_party_role": "public_opaque"}
    list_post = {"evidence_id": "e_list", "excerpt":
                 "The list also mentions Nemotron among many other products.",
                 "first_party_role": "public_opaque"}
    aliases = candidates._snapshot_brand_aliases([{
        "candidate_key": {"brand_key": "nemo_megatron"},
        "display_name_en": "NVIDIA NeMo", "display_name_zh_cn": "NVIDIA NeMo",
    }], evidence_rows=[{"text": product_post["excerpt"]}, {"text": list_post["excerpt"]}])
    assert "nemotron 3" in aliases["nemo_megatron"]
    assert "nemotron" not in aliases["nemo_megatron"]
    for source in (product_post, list_post):
        source["brand_relevance"] = candidates._source_brand_relevance(
            source, "nemo_megatron", aliases)
    assert product_post["brand_relevance"]["status"] == "explicit_mention"
    assert list_post["brand_relevance"]["status"] == "uncertain"
    assert _lead_evidence_id({"brand_key": "nemo_megatron",
                              "display_name_en": "NVIDIA NeMo",
                              "display_name_zh_cn": "NVIDIA NeMo",
                              "evidence": [list_post, product_post]}) == "e_product"


def test_long_secondary_model_name_with_size_is_a_contextual_product_alias(monkeypatch):
    class Rows:
        def __init__(self, values):
            self.values = values

        def filter(self, **kwargs):
            return self

        def order_by(self, *args):
            return self

        def values_list(self, *fields):
            return self.values

    monkeypatch.setattr(candidates.BrandKeyword, "objects", Rows([
        ("nemo_megatron", "nemotron", False),
    ]))
    monkeypatch.setattr(candidates.BrandAccount, "objects", Rows([]))
    monkeypatch.setattr(candidates.Product, "objects", Rows([]))
    source = {"evidence_id": "e_agent", "excerpt":
              "My agent uses OpenRouter's free 120B Nemotron as its second model.",
              "first_party_role": "public_opaque"}
    aliases = candidates._snapshot_brand_aliases([{
        "candidate_key": {"brand_key": "nemo_megatron"},
        "display_name_en": "NVIDIA NeMo", "display_name_zh_cn": "NVIDIA NeMo",
    }], evidence_rows=[{"text": source["excerpt"]}])
    assert "nemotron" in aliases["nemo_megatron"]
    assert candidates._source_brand_relevance(source, "nemo_megatron", aliases)["status"] == "explicit_mention"


def test_source_sample_is_not_presented_as_a_whole_window_census():
    from monitor.trend_narrative_packet import project_dossier

    dossier = {"brand_key":"alpha", "facts":[
        {"fact_id":"f:count", "family":"volume", "metric":"post_count", "source_value":"100", "unit":"posts"}],
        "evidence":[{"evidence_id":str(i),"excerpt":"example"} for i in range(6)]}
    full = project_dossier(dossier)
    preview = project_dossier(dossier, rank=True)
    assert full["evidence_scope"] == {"selected_source_count":6,"collected_post_count":"100",
                                      "selection":"bounded_nonrandom_examples","population_inference_allowed":False}
    assert preview["evidence_scope"]["selected_source_count"] == 2
    assert preview["evidence_scope"]["collected_post_count"] == "100"


def test_support_spans_preserve_long_multilingual_text_and_source_identity():
    from monitor.trend_narrative_packet import evidence_support_spans

    text = ("Explicit source text. 原文を保持する。保留原文。\n" * 40) + "final words"
    source = {"evidence_id": "e1", "excerpt": text, "text_en": text,
              "text_zh_cn": "不同的中文原文。" * 150}
    spans = evidence_support_spans(source)
    assert "".join(s["text"] for s in spans if s["source_field"] == "excerpt") == text
    assert "".join(s["text"] for s in spans if s["source_field"] == "text_zh_cn") == source["text_zh_cn"]
    assert all(len(s["text"]) <= 400 for s in spans)
    assert not any(s["source_field"] == "text_en" for s in spans)
    assert spans == evidence_support_spans(source)
    other = evidence_support_spans({**source, "evidence_id": "e2"})
    assert not {s["span_id"] for s in spans} & {s["span_id"] for s in other}
