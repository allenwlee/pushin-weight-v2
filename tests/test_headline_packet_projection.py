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
