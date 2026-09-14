"""U18's two independent roles are the only active classifier topology."""

from __future__ import annotations

import json
import threading
import time

import pytest


def _tweets(count: int) -> list[dict]:
    return [
        {
            "tweet_id": str(index),
            "text": f"post {index}",
            "brand_ids": ["deepseek"],
            "context": [],
            "source_language": "en",
        }
        for index in range(count)
    ]


class TwoRoleTransport:
    def __init__(self):
        self.calls: list[dict] = []
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def messages_create(self, **kwargs):
        payload = json.loads(kwargs["messages"][0]["content"])
        role = "content" if "Content owns only" in kwargs["system"] else "brand_interpretation"
        with self.lock:
            self.calls.append({"role": role, "payload": payload})
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.03)
        with self.lock:
            self.active -= 1
        results = []
        for tweet in payload:
            if role == "content":
                classifications = [{
                    "brand_id": brand_id,
                    "outcome": "classified",
                    "post_types": ["hands_on_usage"],
                } for brand_id in tweet["brand_ids"]]
            else:
                classifications = [{
                    "brand_id": brand_id,
                    "product_labels": [],
                    "sentiment": "neutral",
                    "china_nationalism": None,
                    "us_nationalism": None,
                } for brand_id in tweet["brand_ids"]]
            result = {
                "tweet_id": tweet["tweet_id"],
                "input_context_fingerprint": tweet["input_context_fingerprint"],
                "role_revision": tweet["role_revision"],
                "classifications": classifications,
            }
            if role == "content":
                result["unsanctioned_flags"] = []
            results.append(result)
        return {"results": results}


def test_two_concurrent_roles_have_exact_batch_cardinality_and_no_repair_calls():
    from x_monitor.attribution import classify_batch_pragmatics_full

    transport = TwoRoleTransport()
    assert classify_batch_pragmatics_full([], [], transport, max_workers=3) == []

    twenty = classify_batch_pragmatics_full(_tweets(20), [], transport, max_workers=3)
    assert len(twenty) == 20
    assert all(row["valid"] for row in twenty)
    assert len(transport.calls) == 2
    assert {call["role"] for call in transport.calls} == {
        "content", "brand_interpretation"
    }

    transport = TwoRoleTransport()
    twenty_one = classify_batch_pragmatics_full(
        _tweets(21), [], transport, max_workers=3
    )
    assert len(twenty_one) == 21
    assert len(transport.calls) == 4
    assert transport.max_active == 3
    assert all(call["role"] in {"content", "brand_interpretation"} for call in transport.calls)


def test_mismatched_sibling_identity_leaves_the_post_invalid_without_a_fallback():
    from x_monitor.attribution import classify_batch_pragmatics_full

    class BadSibling(TwoRoleTransport):
        def messages_create(self, **kwargs):
            response = super().messages_create(**kwargs)
            if "Brand interpretation owns only" in kwargs["system"]:
                response["results"][0]["role_revision"] = "wrong-revision"
            return response

    transport = BadSibling()
    result = classify_batch_pragmatics_full(_tweets(1), [], transport)
    assert result[0]["valid"] is False
    assert result[0]["by_brand"] == {}
    assert len(transport.calls) == 2


@pytest.mark.parametrize("remaining,expected_calls,expected_valid", [
    (0, 0, 0), (1, 0, 0), (2, 2, 20), (3, 2, 20), (4, 4, 21),
])
def test_reserved_pair_budget_never_starts_an_orphan_role(remaining, expected_calls, expected_valid):
    from x_monitor.attribution import classify_batch_pragmatics_full

    class LimitedTransport(TwoRoleTransport):
        @property
        def remaining_calls(self):
            return remaining

    transport = LimitedTransport()
    rows = classify_batch_pragmatics_full(_tweets(21), [], transport)
    assert len(transport.calls) == expected_calls
    assert sum(row["valid"] for row in rows) == expected_valid


def test_role_prompts_are_real_contracts_and_unknown_content_flag_fails_closed():
    from x_monitor.attribution import (
        _TWO_ROLE_BRAND_SYSTEM_PROMPT,
        _TWO_ROLE_CONTENT_SYSTEM_PROMPT,
        classify_batch_pragmatics_full,
    )

    assert len((_TWO_ROLE_CONTENT_SYSTEM_PROMPT + _TWO_ROLE_BRAND_SYSTEM_PROMPT).encode("utf-8")) <= 9_000

    class BadFlag(TwoRoleTransport):
        def messages_create(self, **kwargs):
            response = super().messages_create(**kwargs)
            if "Content owns only" in kwargs["system"]:
                assert "visible evidence" in kwargs["system"]
                assert "product_labels" in kwargs["system"]
                response["results"][0]["unsanctioned_flags"] = ["not-a-real-flag"]
            else:
                assert "product_labels" in kwargs["system"]
            return response

    assert classify_batch_pragmatics_full(_tweets(1), [], BadFlag())[0]["valid"] is False


def test_reviewed_role_change_changes_the_shared_input_fingerprint():
    from x_monitor.attribution import _two_role_fingerprint

    tweet = _tweets(1)[0]
    tweet["affiliations"] = [{"brand_id": "deepseek", "role": "official", "reviewed": True}]
    official = _two_role_fingerprint(tweet)
    tweet["affiliations"] = [{"brand_id": "deepseek", "role": "staff", "reviewed": True}]
    assert _two_role_fingerprint(tweet) != official


def test_two_role_parser_rejects_any_malformed_sibling_or_envelope_row():
    from x_monitor.attribution import _two_role_parse, _two_role_payload

    payload = _two_role_payload(_tweets(1), "content")
    valid = {
        "results": [{
            "tweet_id": "0",
            "input_context_fingerprint": payload[0]["input_context_fingerprint"],
            "role_revision": payload[0]["role_revision"],
            "classifications": [{"brand_id": "deepseek", "outcome": "classified", "post_types": ["hands_on_usage"]}],
            "unsanctioned_flags": [],
        }]
    }
    assert _two_role_parse(valid, payload, "content")["0"]["by_brand"]
    for mutation in (
        lambda value: value.update({"extra": True}),
        lambda value: value["results"].append(dict(value["results"][0])),
        lambda value: value["results"][0].update({"unknown": True}),
        lambda value: value["results"][0]["classifications"][0].update({"post_types": ["other", "hands_on_usage"]}),
        lambda value: value["results"][0]["classifications"][0].update({"post_types": ["not-a-type"]}),
    ):
        candidate = json.loads(json.dumps(valid))
        mutation(candidate)
        assert _two_role_parse(candidate, payload, "content") == {}


@pytest.mark.parametrize("cap,expected_calls", [(0, 0), (1, 0), (5, 0), (6, 2), (7, 2), (12, 2)])
def test_bounded_pair_reserves_all_retry_attempts_before_dispatch(cap, expected_calls):
    from monitor.cycle import _BoundedClassifierClient
    from x_monitor.attribution import classify_batch_pragmatics_full

    delegate = TwoRoleTransport()
    bounded = _BoundedClassifierClient(delegate, maximum_calls=cap, pause_seconds=0)
    rows = classify_batch_pragmatics_full(_tweets(1), [], bounded)
    assert len(delegate.calls) == expected_calls
    assert bounded.calls == expected_calls <= cap
    assert rows[0]["valid"] is (cap >= 6)
    assert bounded.remaining_calls == cap - expected_calls


def test_openrouter_request_uses_the_configured_data_policy_and_pinned_route(monkeypatch):
    from x_monitor.openrouter import OpenRouterChatCompletionsClient

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    client = OpenRouterChatCompletionsClient.from_config(
        model="google/gemma-4-31b-it:free",
        provider="google-ai-studio",
        data_collection="allow",
        max_input_price=0,
        max_output_price=0,
    )
    request = client.build_request(
        model="google/gemma-4-31b-it:free",
        max_tokens=100,
        messages=[{"role": "user", "content": "[]"}],
        system='{"role":"content"}',
    )
    assert request["provider"] == {
        "only": ["google-ai-studio"],
        "allow_fallbacks": False,
        "require_parameters": True,
        "data_collection": "allow",
        "zdr": False,
        "max_price": {"prompt": 0, "completion": 0},
    }
    assert "max_price" not in request
    assert request["response_format"] == {"type": "json_object"}


def test_openrouter_candidate_identity_includes_explicit_zdr_setting():
    from x_monitor.openrouter import OpenRouterChatCompletionsClient

    client = OpenRouterChatCompletionsClient(
        api_key="test-key", model="qwen/qwen3.5-9b", provider="deepinfra", zdr=True, reasoning_enabled=False
    )
    request = client.build_request(model="qwen/qwen3.5-9b", max_tokens=1, messages=[])
    assert request["provider"]["zdr"] is True
    assert request["reasoning"] == {"enabled": False}
    assert client.request_identity.startswith("openrouter:")

    no_reasoning = OpenRouterChatCompletionsClient(
        api_key="test-key", model="qwen/qwen3-235b", provider="gmicloud"
    ).build_request(model="qwen/qwen3-235b", max_tokens=1, messages=[])
    assert "reasoning" not in no_reasoning


def test_openrouter_missing_key_does_not_fall_back_to_a_stale_deepseek_route(monkeypatch):
    from types import SimpleNamespace

    from x_monitor.reattribute import build_classifier_client_from_env

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "must-not-be-used")
    cfg = SimpleNamespace(llm=SimpleNamespace(
        classifier_provider="openrouter",
        classifier_openrouter_provider="google-ai-studio",
        classifier_openrouter_data_collection="deny",
        classifier_openrouter_max_input_price=None,
        classifier_openrouter_max_output_price=None,
        classifier_model="google/gemma-4-31b-it:free",
    ))
    assert build_classifier_client_from_env(cfg) is None


def test_openrouter_rejects_mismatched_route_and_never_echoes_source_or_secret(monkeypatch):
    import x_monitor.openrouter as openrouter
    from x_monitor.provider_telemetry import provider_host_class

    client = openrouter.OpenRouterChatCompletionsClient(
        api_key="secret-token", model="vendor/model", provider="gmicloud"
    )

    class Response:
        status = 400
        def read(self):
            return b'{"error":"secret-token visible source text"}'

    class Connection:
        def __init__(self, *args, **kwargs):
            pass
        def request(self, *args, **kwargs):
            pass
        def getresponse(self):
            return Response()
        def close(self):
            pass

    monkeypatch.setattr(openrouter.http.client, "HTTPSConnection", Connection)
    with pytest.raises(openrouter.OpenRouterPermanentError) as exc:
        client.messages_create(model="vendor/model", max_tokens=1, messages=[])
    assert str(exc.value) == "openrouter_http_status_400"
    assert "secret-token" not in str(exc.value)
    assert provider_host_class("https://api.openrouter.ai/api/v1") == "openrouter"


def test_openrouter_permanent_response_failure_is_not_transport_retried(monkeypatch):
    from x_monitor.attribution import _call_signal_with_retry
    from x_monitor.openrouter import OpenRouterPermanentError

    class PermanentFailure:
        calls = 0
        def messages_create(self, **kwargs):
            self.calls += 1
            raise OpenRouterPermanentError("openrouter_response_provider_mismatch")

    client = PermanentFailure()
    monkeypatch.setattr("x_monitor.attribution._BACKOFF_BASE_SECONDS", 0)
    with pytest.raises(OpenRouterPermanentError):
        _call_signal_with_retry(client, "{}", system="contract")
    assert client.calls == 1


def test_openrouter_response_requires_pinned_identity_and_exposes_safe_usage(monkeypatch):
    import x_monitor.openrouter as openrouter
    from x_monitor.provider_telemetry import normalize_usage

    client = openrouter.OpenRouterChatCompletionsClient(
        api_key="test-key", model="vendor/model", provider="provider-a",
        response_model="vendor/model-alias", response_provider="provider-a-alias",
        quantizations=["fp8"],
    )

    class Response:
        status = 200
        def read(self):
            return json.dumps({
                "id": "req_safe-1", "model": "vendor/model-alias",
                "openrouter_metadata": {
                    "endpoints": {"available": [{
                        "model": "vendor/model-alias",
                        "provider": "provider-a-alias",
                        "selected": True,
                    }]}
                },
                "choices": [{"message": {"content": "{}"}}],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 4,
                    "total_tokens": 16,
                    "prompt_tokens_details": {"cached_tokens": 2},
                    "completion_tokens_details": {"reasoning_tokens": 3},
                    "cost": 0.001,
                },
            }).encode()

    class Connection:
        def __init__(self, *args, **kwargs): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self): return Response()
        def close(self): pass

    monkeypatch.setattr(openrouter.http.client, "HTTPSConnection", Connection)
    response = client.messages_create(model="vendor/model", max_tokens=1, messages=[])
    assert response.provider_usage["request_identity"] == client.request_identity
    assert normalize_usage(response.provider_usage) == {
        "input_tokens": 12, "output_tokens": 4, "cache_read_input_tokens": 2,
        "cache_creation_input_tokens": None, "reasoning_tokens": 3, "total_tokens": 16,
        "cost_usd": 0.001, "provider_request_id": "req_safe-1",
    }
    assert client.build_request(model="vendor/model", max_tokens=1, messages=[])["provider"]["quantizations"] == ["fp8"]


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_two_role_publisher_keeps_exact_lineage_idempotence_and_last_good_on_rejection():
    """Exercise the real two-role result through the production publisher."""
    from copy import deepcopy

    from core.models import (
        Brand,
        Post,
        PostBrand,
        PostBrandClassificationJudgment,
        PostBrandClassificationState,
        PostEnrichmentState,
        PostTypeKey,
        ProductLabelKey,
        SentimentKey,
    )
    from monitor.cycle import _publish_stage1_classification
    from x_monitor.attribution import classify_batch_pragmatics_full

    for key in ("hands_on_usage", "other"):
        PostTypeKey.objects.get_or_create(key=key)
    ProductLabelKey.objects.get_or_create(key="testimonial")
    SentimentKey.objects.get_or_create(key="neutral")
    post = Post.objects.create(tweet_id="u18-two-role-post", text="visible source", lang_detected="en")
    brands = [
        Brand.objects.create(nickname="u18-content", display_name="Content"),
        Brand.objects.create(nickname="u18-brand", display_name="Brand"),
    ]
    for brand in brands:
        PostBrand.objects.create(post=post, brand=brand)
    PostEnrichmentState.objects.create(post=post, claim_run_id="u18-run")

    tweet = {**_tweets(1)[0], "tweet_id": post.pk, "text": post.text, "brand_ids": [brand.pk for brand in brands]}
    result = classify_batch_pragmatics_full(
        [tweet], [], TwoRoleTransport(), model="u18-model"
    )[0]
    assert result["valid"] is True
    assert _publish_stage1_classification(
        post_id=post.pk, result=result, tweet=tweet, model="u18-model", run_id="u18-run"
    ).outcome == "cleared"
    assert _publish_stage1_classification(
        post_id=post.pk, result=deepcopy(result), tweet=tweet, model="u18-model", run_id="u18-run"
    ).outcome == "cleared"

    finals = list(PostBrandClassificationJudgment.objects.filter(post=post, stage="final").order_by("brand_id"))
    assert len(finals) == 2
    assert all(row.content_judgment.stage == "content" for row in finals)
    assert all(row.brand_interpretation_judgment.stage == "brand_interpretation" for row in finals)
    assert all(row.content_judgment.post_id == row.post_id == row.brand_interpretation_judgment.post_id for row in finals)
    assert all(row.content_judgment.brand_id == row.brand_id == row.brand_interpretation_judgment.brand_id for row in finals)
    assert PostBrandClassificationJudgment.objects.filter(post=post).count() == 6

    rejected = deepcopy(result)
    rejected["classification_trace"]["brand_interpretation"]["by_brand"].pop(brands[0].pk)
    with pytest.raises(ValueError, match="brands_mismatch"):
        _publish_stage1_classification(
            post_id=post.pk, result=rejected, tweet=tweet, model="u18-model", run_id="u18-run"
        )
    assert PostBrandClassificationState.objects.filter(post=post).count() == 2
    assert PostBrandClassificationJudgment.objects.filter(post=post).count() == 6


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_real_cycle_classifier_path_sends_reviewed_affiliations_to_both_roles(monkeypatch):
    """Production-shaped queue claim → public classifier → publisher path."""
    from core.models import Account, Brand, BrandAccount, Post, PostBrand, PostBrandClassificationState, PostEnrichmentState, PostTypeKey, ProductLabelKey, Role, SentimentKey
    from monitor.cycle import CycleRunner
    from x_monitor import reattribute
    from x_monitor.config import Config

    for key in ("hands_on_usage", "other"):
        PostTypeKey.objects.get_or_create(key=key)
    ProductLabelKey.objects.get_or_create(key="testimonial")
    SentimentKey.objects.get_or_create(key="neutral")
    role, _ = Role.objects.get_or_create(key="official")
    author = Account.objects.create(author_id="u18-author", handle="u18_author")
    post = Post.objects.create(tweet_id="u18-cycle-post", text="visible source", author=author, lang_detected="en")
    brands = [
        Brand.objects.create(nickname="u18_cycle_a", display_name="A"),
        Brand.objects.create(nickname="u18_cycle_b", display_name="B"),
    ]
    for brand in brands:
        PostBrand.objects.create(post=post, brand=brand)
        BrandAccount.objects.create(brand=brand, account=author, role=role)
    state = PostEnrichmentState.objects.create(post=post)
    state.translation_status = PostEnrichmentState.Status.SUCCEEDED
    state.save(update_fields=["translation_status", "updated_at"])
    transport = TwoRoleTransport()
    monkeypatch.setattr(reattribute, "build_classifier_client_from_env", lambda cfg: transport)
    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda cfg: None)

    CycleRunner(cfg=Config(enabled_models=[brand.pk for brand in brands], daily_ceiling=100))._run_post_fetch(
        [], run_id="u18-cycle-run"
    )
    assert len(transport.calls) == 2
    assert all(call["payload"][0]["affiliations"] == [
        {"brand_id": brand.pk, "role": "official", "reviewed": True}
        for brand in brands
    ] for call in transport.calls)
    state.refresh_from_db()
    assert state.classification_status == PostEnrichmentState.Status.SUCCEEDED
    assert PostBrandClassificationState.objects.filter(post=post).count() == 2
