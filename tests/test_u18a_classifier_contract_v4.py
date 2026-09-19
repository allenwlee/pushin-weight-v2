"""Regression net for the selected two-call, fixed-slot U18A contract."""

from __future__ import annotations

import json

from core.classification_contract import (
    CANONICAL_POST_TYPE_KEYS,
    CANONICAL_PRODUCT_LABEL_KEYS,
    CANONICAL_TAXONOMY_VERSION,
    parse_stage1_v4_classifications,
)


def _row(**changes):
    row = {
        "brand_id": "minimax",
        "outcome": "classified",
        "post_types": ["results_analysis", "opinions_reactions"],
        "audience_topics": ["cost_performance"],
        "product_labels": ["testimonial"],
        "sentiment": "positive",
        "geopolitical_modes": ["none"],
        "china_national_stance": "none",
        "us_national_stance": "none",
    }
    row.update(changes)
    return row


def test_v4_manifest_and_parser_normalize_transport_sentinels_without_repair():
    assert CANONICAL_TAXONOMY_VERSION == "stage1-taxonomy-v4"
    assert len(CANONICAL_POST_TYPE_KEYS) == 14
    assert "results_analysis" in CANONICAL_POST_TYPE_KEYS
    assert "news_reporting" in CANONICAL_POST_TYPE_KEYS
    assert CANONICAL_PRODUCT_LABEL_KEYS[-1] == "investigate_claim"

    parsed = parse_stage1_v4_classifications([_row()], ["minimax"])

    assert parsed == {
        "minimax": {
            "outcome": "classified",
            "post_types": ["results_analysis", "opinions_reactions"],
            "audience_topics": ["cost_performance"],
            "audience_topics_state": "selected",
            "product_labels": ["testimonial"],
            "sentiment": "positive",
            "geopolitical_modes": [],
            "geopolitical_modes_state": "none",
            "china_national_stance": "none",
            "us_national_stance": "none",
        }
    }


def test_v4_parser_rejects_brand_cross_axis_and_nationalism_shape_drift():
    bad_topics = _row(audience_topics=["none", "cost_performance"])
    bad_stances = _row(
        geopolitical_modes=["framework"], china_national_stance="pro"
    )
    context_missing = _row(
        outcome="context_missing", post_types=[], audience_topics=["unavailable"],
        product_labels=["none"], sentiment="unknown",
        geopolitical_modes=["unavailable"], china_national_stance="unknown",
        us_national_stance="unknown",
    )

    assert parse_stage1_v4_classifications([bad_topics], ["minimax"]) is None
    assert parse_stage1_v4_classifications([bad_stances], ["minimax"]) is None
    parsed = parse_stage1_v4_classifications([context_missing], ["minimax"])
    assert parsed and parsed["minimax"]["sentiment"] is None


def test_selected_fingerprint_includes_all_model_evidence_fields():
    from x_monitor.attribution import _two_role_fingerprint

    tweet = {
        "tweet_id": "p1",
        "text": "visible source",
        "context": [{"text": "stored context"}],
        "created_at": "2026-09-18T10:00:00Z",
        "english_translation": "visible translation",
        "brand_ids": ["minimax"],
        "source_language": "ja",
        "affiliations": [],
    }
    baseline = _two_role_fingerprint(tweet)

    changed_date = dict(tweet, created_at="2026-09-18T10:01:00Z")
    changed_translation = dict(tweet, english_translation="changed translation")

    assert _two_role_fingerprint(changed_date) != baseline
    assert _two_role_fingerprint(changed_translation) != baseline


def test_selected_parser_rejects_invented_promotion_evidence_per_post():
    from x_monitor.attribution import (
        BrandRow,
        _two_role_fixed_slot_payload,
        _two_role_parse_fixed_slots,
    )

    tweets = [
        {
            "tweet_id": "p1",
            "text": "Try Example Harness today.",
            "context": [],
            "brand_ids": ["minimax"],
            "source_language": "en",
        },
        {
            "tweet_id": "p2",
            "text": "Try Example Harness tomorrow.",
            "context": [{"text": "stored context"}],
            "english_translation": "Try Example Harness tomorrow.",
            "brand_ids": ["minimax"],
            "source_language": "en",
        },
    ]
    catalog = {
        "revision": "catalog-v1",
        "brands": [{
            "brand_id": "minimax",
            "aliases": ["MiniMax"],
            "handles": [],
            "domains": [],
            "products": [],
        }],
    }
    contract = _two_role_fixed_slot_payload(
        tweets,
        "content",
        request_profile="deepseek_0731",
        tracked_catalog=catalog,
    )
    assert contract is not None
    _, decision_slots, post_slots, _ = contract
    response = {
        "decisions": {
            slot: {
                "outcome": "classified",
                "post_types": ["other"],
                "audience_topics": ["none"],
            }
            for slot in decision_slots
        },
        "post_promotions": {
            "P01": ["general"],
            "P02": ["none"],
        },
        "promoted_subjects": {
            "P01": [{
                "name": "Example Harness",
                "handle": "@example_harness",
                "domain": None,
                "account_handle": None,
                "evidence": "invented evidence not in the post",
            }],
            "P02": [],
        },
    }

    parsed = _two_role_parse_fixed_slots(response, contract, "content")

    assert set(parsed) == {"p2"}
    assert parsed["p2"]["untracked_brand_promotions"] == []


def test_selected_parser_accepts_promotion_evidence_from_translation_and_context():
    from x_monitor.attribution import (
        _two_role_fixed_slot_payload,
        _two_role_parse_fixed_slots,
    )

    tweets = [{
        "tweet_id": "p1",
        "text": "Source text.",
        "english_translation": "Try Example Harness.",
        "context": [{"text": "Context promotion."}],
        "brand_ids": ["minimax"],
        "source_language": "ja",
    }]
    catalog = {"revision": "catalog-v1", "brands": []}
    contract = _two_role_fixed_slot_payload(
        tweets,
        "content",
        request_profile="deepseek_0731",
        tracked_catalog=catalog,
    )
    assert contract is not None
    _, decision_slots, _, _ = contract
    response = {
        "decisions": {
            slot: {
                "outcome": "classified",
                "post_types": ["other"],
                "audience_topics": ["none"],
            }
            for slot in decision_slots
        },
        "post_promotions": {"P01": ["general"]},
        "promoted_subjects": {"P01": [{
            "name": "Example Harness",
            "handle": None,
            "domain": None,
            "account_handle": None,
            "evidence": "try example harness",
        }]},
    }

    parsed = _two_role_parse_fixed_slots(response, contract, "content")

    assert set(parsed) == {"p1"}


def test_selected_prompt_disambiguates_outcome_and_unattributed_discovery():
    from x_monitor.classifier_0731_prompts import selected_system_prompt

    content = selected_system_prompt(
        "content", decision_slots=["D01"], post_slots=["P01"]
    )
    brand = selected_system_prompt(
        "brand_interpretation", decision_slots=["D01"], post_slots=["P01"]
    )

    assert "other is a POST TYPE, never an outcome" in content
    assert "exact verbatim substring" in content
    assert "_unattributed is a discovery sentinel" in content
    assert "without requiring a tracked-brand connection" in content
    assert 'sentiment="neutral"' in brand


def test_selected_runtime_classifies_unattributed_discovery_content():
    from x_monitor.attribution import BrandRow, classify_batch_pragmatics_full

    class UnattributedDiscoveryTransport(_SelectedTransport):
        def messages_create(self, **kwargs):
            payload = json.loads(kwargs["messages"][0]["content"])
            is_content = "CONTENT ROLE:" in kwargs["system"]
            decisions = {}
            for case in payload["cases"].values():
                for slot in case["brand_decision_slots"]:
                    decisions[slot] = (
                        {
                            "outcome": "classified",
                            "post_types": ["job_listings"],
                            "audience_topics": ["none"],
                        }
                        if is_content
                        else {
                            "product_labels": ["none"],
                            "sentiment": "neutral",
                            "geopolitical_modes": ["none"],
                            "china_national_stance": "none",
                            "us_national_stance": "none",
                        }
                    )
            if not is_content:
                return {"decisions": decisions}
            return {
                "decisions": decisions,
                "post_promotions": {"P01": ["general"]},
                "promoted_subjects": {"P01": [{
                    "name": "Example Hiring",
                    "handle": None,
                    "domain": "example.test",
                    "account_handle": None,
                    "evidence": "Apply for the AI role",
                }]},
            }

    rows = classify_batch_pragmatics_full(
        [{
            "tweet_id": "job-1",
            "text": "Apply for the AI role today.",
            "brand_ids": ["_unattributed"],
            "context": [],
            "source_language": "en",
        }],
        [BrandRow("_unattributed", "Unattributed", "#6b7280", True)],
        UnattributedDiscoveryTransport(),
    )

    assert rows[0]["valid"] is True
    assert rows[0]["by_brand"]["_unattributed"]["post_types"] == [
        "job_listings"
    ]
    assert rows[0]["untracked_brand_promotions"] == ["general"]


def test_selected_parser_normalizes_only_observed_0731_wire_variants():
    from x_monitor.attribution import (
        _two_role_fixed_slot_payload,
        _two_role_parse_fixed_slots,
    )

    tweets = [{
        "tweet_id": "p1",
        "text": "Run MiniMax locally.",
        "brand_ids": ["minimax"],
        "context": [],
        "source_language": "en",
    }]
    contract = _two_role_fixed_slot_payload(
        tweets,
        "content",
        request_profile="deepseek_0731",
        tracked_catalog={"revision": "catalog-v1", "brands": []},
    )
    assert contract is not None
    response = {
        "decisions": [{
            "outcome": "hands_on_usage",
            "post_types": ["hands_on_usage"],
            "audience_topics": ["local_inference"],
        }],
        "post_promotions": {"P01": "none"},
        "promoted_subjects": {"P01": []},
    }

    parsed = _two_role_parse_fixed_slots(response, contract, "content")

    assert parsed["p1"]["by_brand"]["minimax"]["outcome"] == "classified"
    assert parsed["p1"]["untracked_brand_promotions"] == []


def test_selected_parser_does_not_infer_missing_or_misaligned_0731_data():
    from x_monitor.attribution import (
        _two_role_fixed_slot_payload,
        _two_role_parse_fixed_slots,
    )

    tweets = [{
        "tweet_id": "p1", "text": "Post", "brand_ids": ["minimax"],
        "context": [], "source_language": "en",
    }]
    contract = _two_role_fixed_slot_payload(
        tweets,
        "content",
        request_profile="deepseek_0731",
        tracked_catalog={"revision": "catalog-v1", "brands": []},
    )
    assert contract is not None
    response = {
        "decisions": [{
            "outcome": "results_analysis",
            "post_types": ["opinions_reactions"],
            "audience_topics": ["none"],
        }],
        "post_promotions": {"P01": "none"},
        "promoted_subjects": {"P01": []},
    }

    assert _two_role_parse_fixed_slots(response, contract, "content") == {}


class _SelectedTransport:
    request_profile = "deepseek_0731"

    def __init__(self):
        self.calls: list[dict] = []

    def messages_create(self, **kwargs):
        payload = json.loads(kwargs["messages"][0]["content"])
        is_content = "CONTENT ROLE:" in kwargs["system"]
        self.calls.append({"payload": payload, "system": kwargs["system"], "content": is_content})
        decisions = {}
        for case in payload["cases"].values():
            for slot in case["brand_decision_slots"]:
                decisions[slot] = (
                    {
                        "outcome": "classified",
                        "post_types": ["results_analysis", "opinions_reactions"],
                        "audience_topics": ["evals_benchmarks"],
                    }
                    if is_content
                    else {
                        "product_labels": ["none"],
                        "sentiment": "neutral",
                        "geopolitical_modes": ["none"],
                        "china_national_stance": "none",
                        "us_national_stance": "none",
                    }
                )
        if not is_content:
            return {"decisions": decisions}
        post_slots = list(payload["cases"])
        return {
            "decisions": decisions,
            "post_promotions": {slot: ["none"] for slot in post_slots},
            "promoted_subjects": {slot: [] for slot in post_slots},
        }


def test_selected_runtime_reports_semantically_invalid_provider_output():
    from x_monitor.attribution import BrandRow, classify_batch_pragmatics_full

    class InvalidTransport(_SelectedTransport):
        def messages_create(self, **kwargs):
            self.calls.append(kwargs)
            return {"decisions": {}}

    errors = []
    transport = InvalidTransport()
    rows = classify_batch_pragmatics_full(
        [{
            "tweet_id": "p1", "text": "A model result.",
            "brand_ids": ["minimax"], "context": [],
            "source_language": "en",
        }],
        [BrandRow("minimax", "MiniMax", "#000", False)],
        transport,
        on_batch_error=lambda _batch, exc: errors.append(str(exc)),
    )

    assert len(transport.calls) == 2
    assert rows[0]["valid"] is False
    assert sorted(errors) == [
        "classification_brand_interpretation_response_invalid",
        "classification_content_response_invalid",
    ]


def test_selected_runtime_uses_two_calls_catalog_fixed_slots_and_v4_merge():
    from x_monitor.attribution import BrandRow, classify_batch_pragmatics_full

    transport = _SelectedTransport()
    rows = classify_batch_pragmatics_full(
        [{
            "tweet_id": "p1", "text": "A benchmark compares both models.",
            "brand_ids": ["minimax", "deepseek"], "context": [],
            "source_language": "en",
        }],
        [
            BrandRow("minimax", "MiniMax", "#000", False),
            BrandRow("deepseek", "DeepSeek", "#000", False),
        ],
        transport,
    )

    assert len(transport.calls) == 2
    assert {call["content"] for call in transport.calls} == {True, False}
    assert all(set(call["payload"]) == {"tracked_brands", "cases"} for call in transport.calls)
    assert all(
        [brand["brand_id"] for brand in call["payload"]["tracked_brands"]["brands"]]
        == ["deepseek", "minimax"]
        for call in transport.calls
    )
    assert all("D01, D02" in call["system"] for call in transport.calls)
    assert rows[0]["valid"] is True
    assert rows[0]["untracked_brand_promotions"] == []
    assert rows[0]["promoted_subjects"] == []
    assert rows[0]["by_brand"]["minimax"]["post_types"] == [
        "results_analysis", "opinions_reactions"
    ]
    assert rows[0]["by_brand"]["minimax"]["audience_topics"] == ["evals_benchmarks"]


def test_selected_runtime_makes_all_axes_unavailable_when_content_lacks_context():
    from x_monitor.attribution import BrandRow, classify_batch_pragmatics_full

    class ContextMissingTransport(_SelectedTransport):
        def messages_create(self, **kwargs):
            payload = json.loads(kwargs["messages"][0]["content"])
            is_content = "CONTENT ROLE:" in kwargs["system"]
            decisions = {}
            for case in payload["cases"].values():
                for slot in case["brand_decision_slots"]:
                    decisions[slot] = (
                        {
                            "outcome": "context_missing",
                            "post_types": [],
                            "audience_topics": ["unavailable"],
                        }
                        if is_content
                        else {
                            "product_labels": ["testimonial"],
                            "sentiment": "positive",
                            "geopolitical_modes": ["none"],
                            "china_national_stance": "none",
                            "us_national_stance": "none",
                        }
                    )
            if not is_content:
                return {"decisions": decisions}
            return {
                "decisions": decisions,
                "post_promotions": {"P01": ["none"]},
                "promoted_subjects": {"P01": []},
            }

    rows = classify_batch_pragmatics_full(
        [{
            "tweet_id": "p1", "text": "This", "brand_ids": ["minimax"],
            "context": [], "source_language": "en",
        }],
        [BrandRow("minimax", "MiniMax", "#000", False)],
        ContextMissingTransport(),
    )

    assert rows[0]["valid"] is True
    assert rows[0]["by_brand"]["minimax"] == {
        "outcome": "context_missing",
        "post_types": [],
        "audience_topics": [],
        "audience_topics_state": "unavailable",
        "product_labels": [],
        "sentiment": None,
        "geopolitical_modes": [],
        "geopolitical_modes_state": "unavailable",
        "china_national_stance": None,
        "us_national_stance": None,
    }
    assert rows[0]["untracked_brand_promotions"] == []
    assert rows[0]["promoted_subjects"] == []
