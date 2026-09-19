from __future__ import annotations

import json
from pathlib import Path

from scripts import model_classifier_experiment as experiment


def _packet(path: Path) -> None:
    rows = [{"trial_id": f"P{i}", "source_language": "en", "target_brand_ids": ["qwen"], "source_packet": {"text": f"Qwen release {i}", "context": [], "affiliations": []}} for i in range(1, 6)]
    path.write_text(json.dumps({"rows": rows, "suites": {"smoke_8_source_post_ids": [row["trial_id"] for row in rows], "diagnostic_24_source_post_ids": [row["trial_id"] for row in rows], "regression_90_source_post_ids": [row["trial_id"] for row in rows]}}), encoding="utf-8")


def test_prepare_uses_current_proposal_prompts_and_exact_two_fixed_slot_calls(tmp_path: Path):
    source, directory = tmp_path / "input.json", tmp_path / "trial"
    _packet(source)
    contract = experiment.prepare(source, directory)
    roles = contract["batches"][0]["roles"]
    assert [item["role"] for item in roles] == ["content", "brand_interpretation"]
    assert contract["profile"]["provider"] == "Alibaba"
    assert contract["profile"]["profile"] == "qwen_classifier_v1"
    assert contract["limits"]["attempts"] == 6
    assert "news_reporting" in roles[0]["request"]["messages"][0]["content"]
    assert roles[0]["request"]["messages"][0]["role"] == "system"
    assert "system" not in roles[0]["request"]
    assert "P1" not in roles[0]["request"]["messages"][1]["content"]
    assert "temperature" not in roles[0]["request"]
    assert "{{DECISION_SLOT_KEYS}}" not in roles[0]["request"]["messages"][0]["content"]
    assert "ambassador roles" in roles[0]["request"]["messages"][0]["content"]
    assert "A broad claim that one country's" not in roles[0]["request"]["messages"][0]["content"]
    assert roles[0]["request"]["provider"]["only"] == ["alibaba"]
    assert all(len(experiment._json(item["request"])) <= experiment.QWEN_MAX_INPUT_REQUEST_BYTES for item in roles)


def test_qwen_v2_uses_raw_json_and_explicit_axis_state_table(tmp_path: Path):
    source, directory = tmp_path / "input.json", tmp_path / "trial"
    _packet(source)
    contract = experiment.prepare(source, directory, profile_key="qwen_classifier_v2")
    request = contract["batches"][0]["roles"][1]["request"]
    assert contract["profile"]["base_profile"] == "qwen_commentary_v1"
    assert "response_format" not in request
    assert "STATE CONSISTENCY CHECK" in request["messages"][0]["content"]
    assert "If geopolitical_modes does not include \"nationalism\"" in request["messages"][0]["content"]


def test_qwen_v3_uses_bounded_reasoning_from_saved_route_profile(tmp_path: Path):
    source, directory = tmp_path / "input.json", tmp_path / "trial"
    _packet(source)
    contract = experiment.prepare(source, directory, profile_key="qwen_classifier_v3")
    request = contract["batches"][0]["roles"][0]["request"]
    assert contract["profile"]["base_profile"] == "qwen_translation_v2"
    assert request["reasoning"] == {"enabled": True, "max_tokens": 2048, "exclude": True}
    assert "response_format" not in request


def test_gemini_classifier_keeps_flex_tier_and_gets_slot_specific_strict_schema(tmp_path: Path):
    source, directory = tmp_path / "input.json", tmp_path / "trial"
    _packet(source)
    contract = experiment.prepare(source, directory, profile_key="gemini_flex_classifier_v1")
    request = contract["batches"][0]["roles"][0]["request"]
    schema = request["response_format"]["json_schema"]
    assert request["provider"]["only"] == ["google-ai-studio/flex"]
    assert request["service_tier"] == "flex"
    assert contract["limits"]["attempts"] == 3
    assert schema["name"] == "classifier_slots" and schema["strict"] is True
    assert set(schema["schema"]["properties"]["decisions"]["properties"]) == {"D01", "D02", "D03", "D04", "D05"}


def test_qwen_v3_dense_flags_are_unfolded_but_invalid_stance_is_not_repaired(tmp_path: Path):
    source, directory = tmp_path / "input.json", tmp_path / "trial"
    _packet(source)
    contract = experiment.prepare(source, directory, profile_key="qwen_classifier_v3")
    prompt = contract["batches"][0]["roles"][1]["request"]["messages"][0]["content"]
    assert "FIXED DENSE OUTPUT MAP" in prompt and "geopolitical_mode_flags" in prompt
    decisions = {"D01": ("P1", "qwen")}; posts = {"P01": "P1"}
    false_products = {key: False for key in experiment.taxonomy.PRODUCT_LABELS}
    false_modes = {key: False for key in experiment.taxonomy.GEO}
    false_products["none"] = True; false_modes["none"] = True
    response = {"decisions": {"D01": {"product_label_flags": false_products, "sentiment": "neutral", "geopolitical_mode_flags": false_modes, "china_national_stance": "none", "us_national_stance": "none"}}}
    assert experiment._parse(response, decisions, posts, "brand_interpretation", profile_key="qwen_classifier_v3")["P1"]
    response["decisions"]["D01"]["china_national_stance"] = "pro"
    assert experiment._parse(response, decisions, posts, "brand_interpretation", profile_key="qwen_classifier_v3") == {}


def test_qwen_v4_compact_bits_require_exact_slots_and_all_axis_positions(tmp_path: Path):
    source, directory = tmp_path / "input.json", tmp_path / "trial"
    _packet(source)
    contract = experiment.prepare(source, directory, profile_key="qwen_classifier_v4")
    prompt = contract["batches"][0]["roles"][0]["request"]["messages"][0]["content"]
    assert "FIXED BIT-VECTOR OUTPUT MAP" in prompt and "post_type_bits" in prompt
    decisions = {"D01": ("P1", "qwen")}; posts = {"P01": "P1"}
    bits = lambda keys, selected: "".join("1" if key in selected else "0" for key in keys)
    topics = tuple(key for key in experiment.taxonomy.TOPICS if key != "none")
    promotions = tuple(key for key in experiment.taxonomy.PROMOTIONS if key != "none")
    response = {"decisions": {"D01": {"outcome": "classified", "post_type_bits": bits(experiment.taxonomy.POST_TYPES, {"opinions_reactions"}), "audience_topic_bits": bits(topics, set())}}, "post_promotion_bits": {"P01": bits(promotions, set())}, "promoted_subjects": {"P01": []}}
    assert experiment._parse(response, decisions, posts, "content", profile_key="qwen_classifier_v4")["P1"]
    response["decisions"] = {"P01_D01_qwen": response["decisions"]["D01"]}
    assert experiment._parse(response, decisions, posts, "content", profile_key="qwen_classifier_v4") == {}


def test_qwen_v5_corrected_bits_keep_axis_checks_before_the_replacement_contract(tmp_path: Path):
    source, directory = tmp_path / "input.json", tmp_path / "trial"
    _packet(source)
    contract = experiment.prepare(source, directory, profile_key="qwen_classifier_v5")
    content_prompt = contract["batches"][0]["roles"][0]["request"]["messages"][0]["content"]
    brand_prompt = contract["batches"][0]["roles"][1]["request"]["messages"][0]["content"]
    assert contract["profile"]["profile"] == "qwen_classifier_v5"
    assert contract["limits"]["attempts"] == 6
    assert "INDEPENDENT-AXIS CHECK" in content_prompt
    assert "STATE CONSISTENCY CHECK" in brand_prompt
    assert "FIXED BIT-VECTOR OUTPUT MAP" in content_prompt


def test_qwen_v6_uses_one_source_and_readable_named_arrays(tmp_path: Path):
    source, directory = tmp_path / "input.json", tmp_path / "trial"
    _packet(source)
    contract = experiment.prepare(source, directory, profile_key="qwen_classifier_v6")
    assert contract["profile"]["profile"] == "qwen_classifier_v6"
    assert contract["limits"]["batch_size"] == 1
    assert len(contract["batches"]) == 5
    assert all(len(batch["source_post_ids"]) == 1 for batch in contract["batches"])
    content_prompt = contract["batches"][0]["roles"][0]["request"]["messages"][0]["content"]
    brand_prompt = contract["batches"][0]["roles"][1]["request"]["messages"][0]["content"]
    assert "FIXED NAMED OUTPUT MAP" in content_prompt and "post_type_bits" not in content_prompt
    assert "STATE CONSISTENCY CHECK" in brand_prompt and "geopolitical_mode_bits" not in brand_prompt


def test_v6_replay_only_wraps_an_exact_bare_brand_slot_mapping():
    decisions = {"D01": ("P1", "qwen")}
    posts = {"P01": "P1"}
    bare = {"D01": {"product_labels": ["none"], "sentiment": "neutral", "geopolitical_modes": ["none"], "china_national_stance": "none", "us_national_stance": "none"}}
    assert experiment._parse(bare, decisions, posts, "brand_interpretation", profile_key="qwen_classifier_v6") == {}
    assert experiment._parse(bare, decisions, posts, "brand_interpretation", profile_key="qwen_classifier_v6_normalized")["P1"]
    assert experiment._parse({"qwen": bare["D01"]}, decisions, posts, "brand_interpretation", profile_key="qwen_classifier_v6_normalized") == {}


def test_v6_replay_maps_only_a_singleton_complete_canonical_brand_key_bijection():
    decisions = {"D01": ("P1", "qwen")}
    posts = {"P01": "P1"}
    content = {"decisions": {"qwen": {"outcome": "classified", "post_types": ["opinions_reactions"], "audience_topics": ["none"]}}, "post_promotions": {"P01": ["none"]}, "promoted_subjects": {"P01": []}}
    assert experiment._parse(content, decisions, posts, "content", profile_key="qwen_classifier_v6") == {}
    assert experiment._parse(content, decisions, posts, "content", profile_key="qwen_classifier_v6_normalized_brand_keys")["P1"]
    alias = json.loads(json.dumps(content)); alias["decisions"] = {"Qwen": alias["decisions"]["qwen"]}
    assert experiment._parse(alias, decisions, posts, "content", profile_key="qwen_classifier_v6_normalized_brand_keys") == {}
    unknown = json.loads(json.dumps(content)); unknown["decisions"] = {"deepseek": unknown["decisions"]["qwen"]}
    assert experiment._parse(unknown, decisions, posts, "content", profile_key="qwen_classifier_v6_normalized_brand_keys") == {}
    two_decisions = {"D01": ("P1", "qwen"), "D02": ("P1", "qwen")}
    assert experiment._parse(content, two_decisions, posts, "content", profile_key="qwen_classifier_v6_normalized_brand_keys") == {}
    two_posts = {"P01": "P1", "P02": "P2"}
    assert experiment._parse(content, decisions, two_posts, "content", profile_key="qwen_classifier_v6_normalized_brand_keys") == {}


def test_current_0731_control_pins_proven_deepinfra_fp8_route_and_disabled_reasoning(tmp_path: Path):
    source, directory = tmp_path / "input.json", tmp_path / "trial"
    _packet(source)
    contract = experiment.prepare(source, directory, profile_key="deepseek_0731_classifier_current_v1")
    request = contract["batches"][0]["roles"][0]["request"]
    assert contract["profile"]["model"] == "deepseek/deepseek-v4-flash-0731"
    assert contract["profile"]["endpoint_tag"] == "deepinfra/fp8"
    assert request["provider"]["only"] == ["deepinfra/fp8"]
    assert request["reasoning"] == {"enabled": False, "exclude": True}
    assert request["max_tokens"] == 6000
    assert (request["temperature"], request["top_p"], request["seed"]) == (1.0, 1.0, 42)
    assert "response_format" not in request


def test_local_parser_rejects_missing_slot_and_accepts_complete_current_taxonomy_shape():
    decisions = {"D01": ("P1", "qwen")}; posts = {"P01": "P1"}
    content = {"decisions": {"D01": {"outcome": "classified", "post_types": ["news_reporting"], "audience_topics": ["none"]}}, "post_promotions": {"P01": ["none"]}, "promoted_subjects": {"P01": []}}
    assert experiment._parse(content, decisions, posts, "content")["P1"]
    content["post_promotions"] = {}
    assert experiment._parse(content, decisions, posts, "content") == {}


def test_duplicate_response_keys_are_rejected_before_local_parse():
    try:
        json.loads('{"decisions":{},"decisions":{}}', object_pairs_hook=experiment._no_duplicate_keys)
    except ValueError as error:
        assert str(error) == "duplicate JSON key"
    else:
        raise AssertionError("duplicate JSON key was accepted")


def test_missing_context_country_values_are_unknown_but_assessed_non_nationalism_is_none():
    decisions = {"D01": ("P1", "qwen")}
    posts = {"P01": "P1"}
    value = {"product_labels": ["none"], "sentiment": "unknown", "geopolitical_modes": ["unavailable"], "china_national_stance": "unknown", "us_national_stance": "unknown"}
    response = {"decisions": {"D01": value}}
    assert experiment._parse(response, decisions, posts, "brand_interpretation")
    value["geopolitical_modes"] = ["framework"]
    assert not experiment._parse(response, decisions, posts, "brand_interpretation")
    value.update(china_national_stance="none", us_national_stance="none")
    assert experiment._parse(response, decisions, posts, "brand_interpretation")


def test_promotions_require_subject_identity_and_exclusive_general():
    decisions = {"D01": ("P1", "qwen")}
    posts = {"P01": "P1"}
    response = {"decisions": {"D01": {"outcome": "classified", "post_types": ["opinions_reactions"], "audience_topics": ["none"]}}, "post_promotions": {"P01": ["general"]}, "promoted_subjects": {"P01": []}}
    assert not experiment._parse(response, decisions, posts, "content")
    response["promoted_subjects"]["P01"] = [{"name": "Harness", "handle": None, "domain": "harness.ai", "account_handle": None, "evidence": "Try Harness"}]
    assert experiment._parse(response, decisions, posts, "content")
    response["post_promotions"]["P01"].append("spam")
    assert not experiment._parse(response, decisions, posts, "content")


def test_live_classifier_sends_two_roles_and_retains_candidate_output(tmp_path, monkeypatch):
    source, directory = tmp_path / "input.json", tmp_path / "trial"
    _packet(source)
    experiment.prepare(source, directory)
    monkeypatch.setattr(experiment, "credential", lambda _: "fake")
    sent = []
    def fake_send(client, request, *, timeout):
        sent.append(request)
        assert (directory / "attempt-1.consumed.json").exists()
        assert request["messages"][0]["role"] == "system"
        cases = json.loads(request["messages"][1]["content"])["cases"]
        slots = [key for case in cases.values() for key in case["brand_decision_slots"]]
        if len(sent) == 1:
            result = {"decisions": {key: {"outcome": "classified", "post_types": ["news_reporting"], "audience_topics": ["none"]} for key in slots}, "post_promotions": {key: ["none"] for key in cases}, "promoted_subjects": {key: [] for key in cases}}
        else:
            result = {"decisions": {key: {"product_labels": ["none"], "sentiment": "neutral", "geopolitical_modes": ["none"], "china_national_stance": "none", "us_national_stance": "none"} for key in slots}}
        return {"model": experiment.MODEL, "openrouter_metadata": {"endpoints": {"available": [{"selected": True, "provider": "Alibaba", "model": experiment.MODEL}]}}, "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}], "usage": {"prompt_tokens": 100, "completion_tokens": 100}}
    monkeypatch.setattr(experiment.OpenRouterChatCompletionsClient, "_send_request", fake_send)
    report = experiment.run(directory)
    assert len(sent) == 2
    assert report["source_post_errors"]["count"] == 0
    assert report["calls"][0]["structured_output"]["promoted_subjects"]


def test_direct_v41_incumbent_uses_singleton_readable_anthropic_requests_and_no_proxy_price(tmp_path: Path):
    source, directory = tmp_path / "input.json", tmp_path / "trial"
    _packet(source)
    contract = experiment.prepare(source, directory, profile_key="deepseek_v41_incumbent_classifier_v1")
    assert contract["profile"]["provider"] == "DeepSeek (direct)"
    assert contract["profile"]["price_usd_per_million"] == {"input": None, "output": None}
    assert contract["pricing"]["status"] == "direct_route_price_unavailable"
    assert contract["reservation_kind"] == "task_budget_allocation_without_direct_price_estimate"
    assert contract["reserved_cost_usd"] == experiment.MAX_TASK_USD
    assert contract["limits"]["batch_size"] == 1
    assert len(contract["batches"]) == 5
    request = contract["batches"][0]["roles"][0]["request"]
    assert request["model"] == "deepseek-v4-flash"
    assert request["thinking"] == {"type": "disabled"}
    assert "provider" not in request and "response_format" not in request
    assert request["messages"][0]["role"] == "user"
    assert "FIXED NAMED OUTPUT MAP" in request["system"]
    assert "post_type_bits" not in request["system"]


def test_direct_v41_run_requires_provider_and_observed_response_alias(tmp_path: Path, monkeypatch):
    source, directory = tmp_path / "input.json", tmp_path / "trial"
    _packet(source)
    experiment.prepare(source, directory, profile_key="deepseek_v41_incumbent_classifier_v1")
    monkeypatch.setattr(experiment, "credential", lambda _: "fake")
    calls = []

    def fake_text(client, *, timeout, **request):
        calls.append(request)
        cases = json.loads(request["messages"][0]["content"])["cases"]
        slots = [slot for case in cases.values() for slot in case["brand_decision_slots"]]
        if len(calls) % 2:
            value = {"decisions": {slot: {"outcome": "classified", "post_types": ["news_reporting"], "audience_topics": ["none"]} for slot in slots}, "post_promotions": {slot: ["none"] for slot in cases}, "promoted_subjects": {slot: [] for slot in cases}}
        else:
            value = {"decisions": {slot: {"product_labels": ["none"], "sentiment": "neutral", "geopolitical_modes": ["none"], "china_national_stance": "none", "us_national_stance": "none"} for slot in slots}}
        return type("Response", (), {"text": json.dumps(value), "provider_usage": {"provider": "deepseek", "model": "deepseek-flash", "provider_request_id": "request-1"}})()

    monkeypatch.setattr(experiment.AnthropicClaudeClient, "messages_create_text", fake_text)
    report = experiment.run(directory)
    assert len(calls) == 10
    assert report["source_post_errors"]["count"] == 0
    assert report["calls"][0]["raw_response"]["content"].startswith("{")


def test_direct_v41_run_rejects_an_unattested_response_alias(tmp_path: Path, monkeypatch):
    source, directory = tmp_path / "input.json", tmp_path / "trial"
    _packet(source)
    experiment.prepare(source, directory, profile_key="deepseek_v41_incumbent_classifier_v1")
    monkeypatch.setattr(experiment, "credential", lambda _: "fake")
    monkeypatch.setattr(experiment.AnthropicClaudeClient, "messages_create_text", lambda *_args, **_kwargs: type("Response", (), {"text": "{}", "provider_usage": {"provider": "deepseek", "model": "other", "provider_request_id": "request-1"}})())
    report = experiment.run(directory)
    assert report["source_post_errors"]["count"] == 5
    assert all(row["error"] == "direct DeepSeek provider/model attestation failed" for row in report["calls"])


def test_new_classifier_contract_uses_incumbent_parity_rather_than_a_fixed_error_rate(tmp_path: Path):
    source, directory = tmp_path / "input.json", tmp_path / "trial"
    _packet(source)
    contract = experiment.prepare(source, directory, profile_key="gemini_flex_classifier_v1")
    quality = contract["quality"]
    assert "equal or beat direct DeepSeek V4.1" in quality["acceptance"]
    assert quality["full_source_review_required"] is True
    assert "source_post_error_ceiling" not in quality


def test_gemini_v2_isolates_sources_and_restores_evidence_availability_checks(tmp_path: Path):
    source, directory = tmp_path / "input.json", tmp_path / "trial"
    _packet(source)
    contract = experiment.prepare(source, directory, profile_key="gemini_flex_classifier_v2")
    assert contract["profile"]["profile"] == "gemini_flex_classifier_v2"
    assert contract["limits"]["batch_size"] == 1
    assert len(contract["batches"]) == 5
    content = contract["batches"][0]["roles"][0]["request"]["messages"][0]["content"]
    brand = contract["batches"][0]["roles"][1]["request"]["messages"][0]["content"]
    assert "BRAND-BOUND CHECK" in content
    assert "DIRECT EVIDENCE AVAILABILITY CHECK" in brand
    assert contract["batches"][0]["roles"][0]["request"]["response_format"]["json_schema"]["strict"] is True
