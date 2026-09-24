"""Real request/validator boundaries for source-scoped numerical claims."""

import json
from copy import deepcopy

import pytest

from monitor.trend_narrative_candidates import build_editor_batches
from monitor.trend_narrative_generation import (
    HeadlineGenerationError,
    build_per_brand_critic_request,
    build_per_brand_editor_request,
    validate_per_brand_critic_response,
    validate_per_brand_editor_response,
)
from monitor.trend_narrative_packet import evidence_support_spans
from x_monitor.config import HeadlineNarrativeConfig
from x_monitor.deepinfra import DEEPSEEK_0731_MODEL, DeepInfraChatCompletionsClient


def finance_case():
    config = HeadlineNarrativeConfig(
        provider="deepinfra", model=DEEPSEEK_0731_MODEL, base_url="https://api.deepinfra.com/v1/openai",
        editor_prompt_version="headline-editor-finance-v1-ja", critic_prompt_version="headline-critic-finance-v1-ja",
        editor_request_profile="headline_editor_v3", critic_request_profile="headline_critic_v3",
    )
    snapshot = {"packet_schema_version": 3, "window_days": 1, "as_of": "2026-09-24T00:00:00Z",
                "baseline_context": {}, "dossiers": [{
                    "brand_key": "alpha", "outcome": "narrative_eligible",
                    "comparison_status": {"allowed": False, "prior_post_count": 123456},
                    "source_row_provenance": {"start_at": "2026-09-23T00:00:00Z", "end_at": "2026-09-24T00:00:00Z"},
                    "facts": [{"fact_id": "f:alpha:count", "family": "volume", "metric": "post_count",
                               "source_value": "10", "baseline_value": "123456", "unit": "posts"}],
                    "evidence": [{"evidence_id": "e1", "excerpt": "Alpha has useful local inference tools.", "_private": "hidden"}],
                }]}
    packet = build_editor_batches(snapshot)[0]
    envelope, request = build_per_brand_editor_request(packet, config)
    narrative = {
        "brand_key": "alpha", "headline_en": "Alpha's local tools draw discussion.",
        "headline_zh_cn": "Alpha的本地工具引发讨论。", "headline_ja": "Alphaのローカルツールが話題に。",
        "secondary_en": "The window contains 10 posts.", "secondary_zh_cn": "窗口内有10条帖子。",
        "secondary_ja": "対象期間の投稿は10件です。", "narrative_kind": "content_shift", "confidence": "medium",
        "headline_proposition_ids": ["p1"], "secondary_proposition_ids": ["p2"], "events": [],
        "propositions": [
            {"proposition_id": "p1", "output_section": "headline", "claim_type": "content_summary",
             "claim_en": "Alpha's local tools draw discussion.", "claim_zh_cn": "Alpha的本地工具引发讨论。",
             "claim_ja": "Alphaのローカルツールが話題に。", "fact_ids": [], "evidence_ids": ["e1"], "measurements": []},
            {"proposition_id": "p2", "output_section": "secondary", "claim_type": "quantity",
             "claim_en": "The window contains 10 posts.", "claim_zh_cn": "窗口内有10条帖子。",
             "claim_ja": "対象期間の投稿は10件です。", "fact_ids": ["f:alpha:count"], "evidence_ids": [],
             "measurements": [{"fact_id": "f:alpha:count", "value": "10.0", "unit": "posts", "scope_ref": "s1"}]},
        ],
    }
    response = {"editor_response_schema_version": 3, "packet_hash": envelope["packet_hash"],
                "batch_key": packet["batch_key"], "brands": [narrative]}
    return config, envelope, request, response


def test_finance_schema_and_number_binding_accept_representation_equivalence():
    config, envelope, request, response = finance_case()
    assert validate_per_brand_editor_response(response, envelope) == response
    from monitor.trend_narrative_generation import execute_per_brand_provider_request

    captured = []

    def transport(wire, timeout):
        captured.append(wire)
        return {"model": config.model, "service_tier": "priority", "id": "fixture",
                "usage": {"prompt_tokens": 20, "completion_tokens": 20,
                          "completion_tokens_details": {"reasoning_tokens": 0},
                          "estimated_cost": 0.0000072},
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(response)}}]}

    result = execute_per_brand_provider_request(
        request, config, api_key="test", telemetry_context={"stage": "editor"},
        client_factory=lambda **kwargs: DeepInfraChatCompletionsClient(**kwargs, transport=transport),
    )
    assert json.loads(result.raw_text) == response
    assert len(captured) == 1
    wire = captured[0]
    schema = wire["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["editor_response_schema_version"]["enum"] == [3]
    assert "measurements" in schema["properties"]["brands"]["items"]["properties"]["propositions"]["items"]["required"]


@pytest.mark.parametrize("field,value", [("value", "11"), ("value", "NaN"), ("unit", "percent"),
                                         ("scope_ref", "prior_period"), ("fact_id", "f:beta:count")])
def test_incorrect_number_unit_interval_or_brand_binding_is_rejected(field, value):
    _, envelope, _, response = finance_case()
    response["brands"][0]["propositions"][1]["measurements"][0][field] = value
    with pytest.raises(HeadlineGenerationError, match="measurement"):
        validate_per_brand_editor_response(response, envelope)


def test_both_critic_paths_preserve_allowed_fact_boundary_and_hold_bad_bindings():
    config, envelope, _editor_request, response = finance_case()
    for valid in (True, False):
        parse = {"status": "valid" if valid else "invalid", "error_codes": [], "response": response}
        critic, request = build_per_brand_critic_request(envelope, json.dumps(response), parse, config)
        wire_text = request["messages"][0]["content"]
        assert "123456" not in wire_text and "_private" not in wire_text
        assert "scope_ref" in wire_text and "s1" in wire_text
        if valid:
            assert "review_bundles" in wire_text and "analysis_packet" not in wire_text
        else:
            assert "analysis_packet" in wire_text
        bad = deepcopy(response["brands"][0])
        bad["propositions"][1]["measurements"][0]["value"] = "11"
        result = validate_per_brand_critic_response({
            "critic_response_schema_version": 3, "packet_hash": critic["packet_hash"], "batch_key": critic["batch_key"],
            "decisions": [{"brand_key": "alpha", "decision": "approve", "narrative": bad, "hold_code": None}],
        }, critic)
        assert result["decisions"][0]["decision"] == "hold"


def test_measurements_and_ambiguous_brand_mentions_always_get_a_critic():
    from monitor.trend_narrative_tasks import _critic_risk_reasons

    config, envelope, _, response = finance_case()
    response["brands"][0]["propositions"][1]["claim_type"] = "mix"
    packet = deepcopy(envelope["analysis_packet"])
    packet["dossiers"][0]["evidence"][0]["brand_relevance"] = {"status": "multiple_brands"}
    reasons, _ = _critic_risk_reasons(batch=packet, parsed_editor=response,
                                    editor_envelope=envelope, config=config)
    assert "fact_alignment" in reasons and "brand_relevance" in reasons


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("profile_version", [3, 4, 5])
def test_real_snapshot_to_durable_stages_and_trilingual_serving(monkeypatch, profile_version):
    from datetime import UTC, datetime, timedelta

    from core.models import (
        Brand,
        Post,
        PostBrand,
        TrendNarrativeProviderCall,
        TrendNarrativeRun,
    )
    from monitor import trend_narrative_tasks as tasks
    from monitor.trend_narrative_generation import PerBrandProviderResponse
    from monitor.trend_narrative_projection import project_trend_narrative

    config, _, _, template = finance_case()
    config = HeadlineNarrativeConfig.model_validate({
        **config.model_dump(), "activation_state": "reviewed", "serving_enabled": True,
        "editor_request_profile": f"headline_editor_v{min(profile_version, 4)}",
        "critic_request_profile": f"headline_critic_v{profile_version}",
        "critic_prompt_version": ("headline-critic-finance-source-audit-v5-ja"
                                  if profile_version == 5 else config.critic_prompt_version),
        "materiality_policy_version": "reviewed-finance-v1",
        "enqueue_enabled": True, "provider_calls_enabled": True,
        "per_brand_batch_size": 2, "per_brand_call_cap": 41,
        "per_brand_input_token_cap": 1_600_000, "per_brand_output_token_cap": 350_000,
        "per_brand_cost_cap_usd": "0.30", "per_brand_input_usd_per_million": "0.09",
        "per_brand_output_usd_per_million": "0.27", "per_brand_worker_concurrency": 3,
    })
    now = datetime(2026, 9, 24, tzinfo=UTC)
    brand = Brand.objects.create(nickname="alpha", display_name_en="Alpha")
    post = Post.objects.create(tweet_id="finance-regnet", text="Alpha has useful local inference tools.",
                               created_at=now - timedelta(hours=2), lang="en")
    Post.objects.filter(pk=post.pk).update(fetched_at=now - timedelta(hours=1))
    PostBrand.objects.create(post=post, brand=brand)
    queued, captured = [], []
    monkeypatch.setattr(tasks, "_load_config", lambda: config)
    monkeypatch.setattr(tasks.timezone, "now", lambda: now)
    monkeypatch.setattr(tasks, "_enqueue_per_brand_stage", lambda kind, **kwargs: queued.append((kind, kwargs)))

    def execute(request, active_config, **kwargs):
        stage = kwargs["telemetry_context"]["stage"]
        content = request["messages"][0]["content"]
        envelope = json.loads(content.split("request_envelope=", 1)[1] if stage != "critic" else content.split("\n", 1)[1])
        captured.append((stage, envelope))
        common = {"packet_hash": envelope["packet_hash"], "batch_key": envelope["batch_key"]}
        if stage == "rank":
            result = {**common, "rank_response_schema_version": 1, "ordered_brands": [
                {"brand_key": row["brand_key"], "confidence": "low",
                 "reason_refs": [{"kind": "fact", "id": row["facts"][0]["fact_id"]}]}
                for row in envelope["analysis_packet"]["dossiers"]
            ]}
        elif stage == "editor":
            source = envelope["analysis_packet"]["dossiers"][0]
            fact = next(row for row in source["facts"] if row["metric"] == "post_count")
            narrative = deepcopy(template["brands"][0])
            narrative["propositions"][0]["evidence_ids"] = [source["evidence"][0]["evidence_id"]]
            proposition = narrative["propositions"][1]
            proposition["fact_ids"] = [fact["fact_id"]]
            proposition["measurements"] = [{key: fact[key] for key in ("fact_id", "value", "unit", "scope_ref")}]
            for locale in ("en", "zh_cn", "ja"):
                narrative[f"secondary_{locale}"] = narrative[f"secondary_{locale}"].replace("10", "1")
                proposition[f"claim_{locale}"] = proposition[f"claim_{locale}"].replace("10", "1")
            result = {**common, "editor_response_schema_version": 3, "brands": [narrative]}
        else:
            result = {**common, "critic_response_schema_version": 3, "decisions": [
                {"brand_key": row["brand_key"], "decision": "approve", "hold_code": None, "narrative": row["draft"]}
                for row in envelope["review_bundles"]
            ]}
            if profile_version == 5:
                result["critic_response_schema_version"] = 4
                for decision, bundle in zip(result["decisions"], envelope["review_bundles"], strict=True):
                    source = bundle["dossier"]["evidence"][0]
                    decision.update(draft_errors=[], source_check={
                        "subject": "Alpha local tools", "brand_relevance": "direct", "number_ownership": [], "conflicts": [],
                        "span_ids": [source["source_spans"][0]["span_id"]],
                    })
        return PerBrandProviderResponse(raw_text=json.dumps(result), input_tokens=100, output_tokens=100,
                                       latency_ms=1, provider_usage={"cost_usd": 0.000036})

    monkeypatch.setattr(tasks, "execute_per_brand_provider_request", execute)
    run = tasks.initialize_per_brand_snapshot(source_cycle_id="finance-regnet", window_days=1, facts_as_of=now,
                                              enqueue=lambda kind, **kwargs: queued.append((kind, kwargs)))
    assert run is not None
    while queued:
        kind, kwargs = queued.pop(0)
        if kind == "stage":
            tasks.execute_per_brand_stage(**kwargs, now=now)
        elif kind == "finalize":
            tasks.finalize_per_brand_run(kwargs["run_id"], now=now + timedelta(seconds=1))
        else:
            pytest.fail(f"unexpected queue task {kind}")
    run.refresh_from_db()
    assert run.status == TrendNarrativeRun.Status.ACTIVE
    assert [stage for stage, _ in captured] == ["rank", "editor", "critic"]
    assert TrendNarrativeProviderCall.objects.filter(run=run).count() == 3
    if profile_version == 5:
        critic_call = TrendNarrativeProviderCall.objects.get(run=run, stage="critic")
        assert "source_check" in json.dumps(critic_call.response_payload)
    for _, envelope in captured:
        text = json.dumps(envelope)
        assert "_ranks" not in text and "prior_post_count" not in text
        assert "finance_context" in text and "historical_status" in text
    for locale in ("en", "zh-cn", "ja"):
        projection = project_trend_narrative(1, locale=locale, selected_brand_keys=["alpha"], now=now, config=config)
        assert projection["items"][0]["state"] == "available"
        locale_key = locale.replace("-", "_")
        assert projection["items"][0]["headline"] == template["brands"][0][f"headline_{locale_key}"]
        assert projection["items"][0]["secondary"] == template["brands"][0][f"secondary_{locale_key}"].replace("10", "1")
        assert "source_check" not in json.dumps(projection)


def test_bound_schema_cannot_reuse_another_requests_citations():
    from copy import deepcopy

    config, _envelope, request, _response = finance_case()
    client = DeepInfraChatCompletionsClient(api_key="test", model=config.model,
                                           request_profile="headline_editor_v4")
    def wire(req):
        return client.build_request(model=req["model"], system=req["system"],
                                    messages=req["messages"], max_tokens=req["max_tokens"])
    first = wire(request)
    raw = json.loads(request["messages"][0]["content"].split("request_envelope=",1)[1])
    second = deepcopy(raw)
    second["analysis_packet"]["dossiers"][0]["evidence"][0]["evidence_id"] = "different-source"
    modified = deepcopy(request)
    modified["messages"][0]["content"] = "request_envelope=" + json.dumps(second)
    second_wire = wire(modified)
    schema = first["response_format"]["json_schema"]["schema"]
    branch = schema["properties"]["brands"]["items"]["anyOf"][0]
    assert branch["properties"]["brand_key"]["enum"] == ["alpha"]
    assert list(branch["properties"])[1] == "propositions"
    ordered = list(branch["properties"]["propositions"]["items"]["properties"])
    assert ordered.index("measurements") < ordered.index("claim_en")
    assert branch["properties"]["propositions"]["items"]["properties"]["evidence_ids"]["items"]["enum"] == ["e1"]
    assert "different-source" not in json.dumps(first)
    assert '"e1"' not in json.dumps(second_wire["response_format"])
    assert wire(request) == first


def audited_critic_case():
    config, editor, _request, draft = finance_case()
    config = HeadlineNarrativeConfig.model_validate({**config.model_dump(),
        "critic_request_profile": "headline_critic_v5",
        "critic_prompt_version": "headline-critic-finance-source-audit-v5-ja"})
    envelope, request = build_per_brand_critic_request(editor, json.dumps(draft),
        {"status": "valid", "error_codes": [], "response": draft}, config)
    decision = {"brand_key": "alpha", "decision": "approve", "hold_code": None,
                "narrative": draft["brands"][0], "draft_errors": [],
                "source_check": {"subject": "Alpha's local inference tools", "brand_relevance": "direct", "number_ownership": [], "conflicts": [],
                                 "span_ids": [evidence_support_spans(editor["analysis_packet"]["dossiers"][0]["evidence"][0])[0]["span_id"]]}}
    response = {"critic_response_schema_version": 4, "packet_hash": envelope["packet_hash"],
                "batch_key": envelope["batch_key"], "decisions": [decision]}
    return config, envelope, request, response


def test_source_audit_precedes_decision_and_retains_exact_support():
    config, envelope, request, response = audited_critic_case()
    wire = DeepInfraChatCompletionsClient(api_key="test", model=config.model,
        request_profile=config.critic_request_profile).build_request(model=request["model"],
        system=request["system"], messages=request["messages"], max_tokens=request["max_tokens"])
    branch = wire["response_format"]["json_schema"]["schema"]["properties"]["decisions"]["items"]["anyOf"][0]
    assert list(branch["properties"]).index("source_check") < list(branch["properties"]).index("decision")
    assert validate_per_brand_critic_response(response, envelope) == response


@pytest.mark.parametrize("corruption", ["fabricated_span", "other_brand", "absent_brand", "ignored_error", "no_support", "fabricated_conflict", "duplicate_conflict"])
def test_source_audit_cannot_approve_fabricated_or_contradictory_support(corruption):
    _, envelope, _, response = audited_critic_case()
    row = response["decisions"][0]
    if corruption == "fabricated_span":
        row["source_check"]["span_ids"] = ["s:invented"]
    elif corruption == "other_brand":
        row["source_check"]["span_ids"] = [evidence_support_spans({"evidence_id": "another-brand", "excerpt": "Alpha has useful local inference tools."})[0]["span_id"]]
    elif corruption == "absent_brand":
        row["source_check"]["brand_relevance"] = "absent"
    elif corruption == "ignored_error":
        row["draft_errors"] = ["Draft funding claim is unsupported."]
    elif corruption in {"fabricated_conflict", "duplicate_conflict"}:
        own = row["source_check"]["span_ids"][0]
        row["source_check"]["conflicts"] = [{"description": "Conflicting release descriptions.",
            "span_ids": [own, "s:invented" if corruption == "fabricated_conflict" else own]}]
    else:
        row["source_check"]["span_ids"] = []
    with pytest.raises(HeadlineGenerationError, match="source_audit"):
        validate_per_brand_critic_response(response, envelope)
