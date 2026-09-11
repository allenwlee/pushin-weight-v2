"""Stage 0 provider telemetry call-chain regression net.

These tests use the production translator entry point and deepest fake
transport. They intentionally inspect log records rather than a database
ledger: one record belongs to one application transport invocation.
"""

from __future__ import annotations

import json
import logging
import time
from io import StringIO
from types import SimpleNamespace

import pytest

USAGE_KEYS = {
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "reasoning_tokens",
    "total_tokens",
}
EVENT_KEYS = {
    "event_id",
    "timestamp",
    "role",
    "stage",
    "run_id",
    "model",
    "provider_host_class",
    "prompt_identity",
    "batch_size",
    "attempt",
    "attempt_kind",
    "outcome",
    "error_type",
    "elapsed_ms",
    "usage",
    "usage_source",
}


def _translation_response(tweets):
    from x_monitor.provider_telemetry import ProviderResponse

    return ProviderResponse(
        {
            "results": [
                {
                    "tweet_id": tweet["tweet_id"],
                    "text_en": "Synthetic English translation",
                    "literal_zh": "合成翻译",
                    "text_zh_cn": "合成翻译",
                    "lang_detected": "fr",
                    "en_equivalent": "A concise equivalent.",
                    "cn_equivalent": "简洁等价表达。",
                    "annotation": "",
                    "noop_en": False,
                    "noop_zh": False,
                }
                for tweet in tweets
            ]
        },
        usage={
            "input_tokens": 31,
            "output_tokens": 17,
            "cache_read_input_tokens": 4,
            "cache_creation_input_tokens": 2,
            "reasoning_tokens": 3,
            "total_tokens": 48,
        },
    )


def _events(caplog):
    return [
        record.provider_transport_event
        for record in caplog.records
        if hasattr(record, "provider_transport_event")
    ]


def test_usage_normalizer_preserves_reported_total_and_missing_fields():
    from x_monitor.provider_telemetry import normalize_usage

    usage = normalize_usage({"input_tokens": 10, "output_tokens": 3, "total_tokens": 13})
    assert set(usage) == USAGE_KEYS
    assert usage["total_tokens"] == 13
    assert usage["cache_read_input_tokens"] is None
    assert usage["reasoning_tokens"] is None
    assert normalize_usage({"max_tokens": 999})["total_tokens"] is None


def test_usage_normalizer_rejects_non_count_values_and_event_context_is_safe(caplog):
    from x_monitor.provider_telemetry import emit_attempt, normalize_usage

    assert normalize_usage({"input_tokens": True, "output_tokens": -1, "total_tokens": 1.5}) == {
        "input_tokens": None, "output_tokens": None, "cache_read_input_tokens": None,
        "cache_creation_input_tokens": None, "reasoning_tokens": None, "total_tokens": None,
    }
    caplog.set_level("INFO")
    emit_attempt(
        logging.getLogger("telemetry-test"), role="safe-role", model="safe-model",
        attempt=1, outcome="success", started=time.monotonic(), prompt="safe prompt",
        role_override="ignored", event_id="forged", prompt_identity="forged",
        raw_body="secret", full_url="https://secret.invalid", stage="safe-stage",
    )
    event = _events(caplog)[0]
    assert event["role"] == "safe-role"
    assert event["stage"] == "safe-stage"
    assert event["event_id"] != "forged"
    assert event["prompt_identity"] != "forged"
    assert "raw_body" not in event and "full_url" not in event


def test_provider_host_class_is_allowlisted_and_hides_custom_hosts(caplog):
    from x_monitor.provider_telemetry import emit_attempt, provider_host_class

    assert provider_host_class("https://api.deepseek.com/anthropic") == "deepseek"
    assert provider_host_class("https://api.minimax.io/anthropic") == "minimax"
    assert provider_host_class("https://api.anthropic.com") == "anthropic"
    custom_url = "https://private-gateway.example/anthropic"
    assert provider_host_class(custom_url) == "unknown"
    assert provider_host_class("https://evil.deepseek.com/anthropic") == "unknown"
    assert provider_host_class("https://api.deepseek.com.evil.invalid") == "unknown"
    assert provider_host_class("https://[broken") == "unknown"

    class BrokenClient:
        @property
        def _base_url(self):
            raise RuntimeError("private provider failure")

    assert provider_host_class(BrokenClient()) == "unknown"
    caplog.set_level("INFO")
    emit_attempt(
        logging.getLogger("telemetry-host-class"),
        role="safe-role",
        model="safe-model",
        attempt=1,
        outcome="success",
        started=time.monotonic(),
        provider_host_class=provider_host_class(custom_url),
    )
    rendered = json.dumps(_events(caplog)[0])
    assert '"provider_host_class": "unknown"' in rendered
    assert "private-gateway.example" not in rendered


def test_default_stream_handler_renders_safe_serialized_provider_event():
    from x_monitor.provider_telemetry import emit_attempt

    stream = StringIO()
    logger = logging.getLogger("telemetry-rendered-stream")
    logger.handlers = [logging.StreamHandler(stream)]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        emit_attempt(
            logger,
            role="safe-role",
            model="safe-model",
            attempt=1,
            outcome="success",
            started=time.monotonic(),
            prompt="private provider prompt",
            run_id="safe-run",
            raw_body="private response",
            full_url="https://private.invalid",
        )
    finally:
        logger.handlers.clear()

    rendered = json.loads(stream.getvalue())
    assert rendered["role"] == "safe-role"
    assert rendered["run_id"] == "safe-run"
    assert rendered["usage"]["total_tokens"] is None
    assert "private provider prompt" not in stream.getvalue()
    assert "private response" not in stream.getvalue()
    assert "private.invalid" not in stream.getvalue()


def test_headline_parse_failure_emits_one_usage_preserving_terminal_event(caplog):
    from monitor.trend_narrative_generation import (
        HeadlineGenerationError,
        execute_per_brand_provider_request,
    )
    from x_monitor.config import HeadlineNarrativeConfig

    request = {"model": "test-model", "max_tokens": 8, "thinking": {"type": "disabled"}, "system": "test", "messages": [{"role": "user", "content": "test"}]}
    message = SimpleNamespace(content=[], usage=SimpleNamespace(input_tokens=13, output_tokens=2))
    caplog.set_level("INFO")
    with pytest.raises(HeadlineGenerationError, match="headline_output_text_missing"):
        execute_per_brand_provider_request(
            request, HeadlineNarrativeConfig(), api_key="test-key",
            client_factory=lambda **_kwargs: SimpleNamespace(messages=SimpleNamespace(create=lambda **_kwargs: message)),
        )
    events = _events(caplog)
    assert len(events) == 1
    assert events[0]["outcome"] == "error"
    assert events[0]["usage"]["input_tokens"] == 13


def test_headline_missing_usage_keeps_event_usage_nullable(caplog):
    from monitor.trend_narrative_generation import execute_per_brand_provider_request
    from x_monitor.config import HeadlineNarrativeConfig

    request = {"model": "test-model", "max_tokens": 8, "thinking": {"type": "disabled"}, "system": "test", "messages": [{"role": "user", "content": "test"}]}
    message = SimpleNamespace(content=[SimpleNamespace(text="{}")], usage=None)
    caplog.set_level("INFO")
    execute_per_brand_provider_request(
        request,
        HeadlineNarrativeConfig(),
        api_key="test-key",
        client_factory=lambda **_kwargs: SimpleNamespace(messages=SimpleNamespace(create=lambda **_kwargs: message)),
    )
    event = _events(caplog)[0]
    assert event["usage_source"] == "missing"
    assert all(value is None for value in event["usage"].values())


def test_translator_production_entry_emits_redacted_single_boundary_event(caplog):
    from x_monitor.translator import translate_batch_pragmatics

    tweets = [{"tweet_id": "synthetic-1", "text": "A synthetic provider case"}]

    class FakeClient:
        def messages_create(self, **kwargs):
            return _translation_response(tweets)

    caplog.set_level("INFO")
    result = translate_batch_pragmatics(tweets, ["en", "zh_cn"], client=FakeClient())
    assert result[0]["tweet_id"] == "synthetic-1"

    events = _events(caplog)
    assert len(events) == 1
    event = events[0]
    assert EVENT_KEYS <= set(event)
    assert event["role"] == "post_translation_synthesis"
    assert event["outcome"] == "success"
    assert set(event["usage"]) == USAGE_KEYS
    assert event["usage"]["total_tokens"] == 48
    serialized = json.dumps(event, ensure_ascii=False)
    for secret in ("A synthetic provider case", "api_key", "messages", "https://"):
        assert secret not in serialized


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_cycle_post_fetch_uses_real_factories_and_bounded_workers(caplog, monkeypatch):
    """M18: persisted work reaches both real factories and HTTP extraction."""
    from core.models import (
        Brand,
        NationalismKey,
        Post,
        PostBrand,
        PostEnrichmentState,
        PostTypeKey,
        SentimentKey,
    )
    from monitor.cycle import CycleRunner

    brand = Brand.objects.create(nickname="telemetry-brand", display_name="Telemetry")
    posts = [
        Post.objects.create(tweet_id=f"telemetry-{index:02d}", text=f"post {index}")
        for index in range(21)
    ]
    PostBrand.objects.bulk_create([PostBrand(post=post, brand=brand) for post in posts])
    PostEnrichmentState.objects.bulk_create([PostEnrichmentState(post=post) for post in posts])
    SentimentKey.objects.get_or_create(key="neutral")
    NationalismKey.objects.get_or_create(key="none")
    PostTypeKey.objects.get_or_create(key="hands_on_usage")

    requests: list[dict] = []

    class FakeHttpResponse:
        status = 200

        def __init__(self, body):
            self._body = body

        def read(self):
            return json.dumps(self._body).encode()

    class FakeHttpsConnection:
        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout
            self.body = None
            self.headers = None

        def request(self, method, path, body, headers):
            assert method == "POST"
            assert path == "/anthropic/v1/messages"
            self.body = json.loads(body)
            self.headers = headers
            requests.append({"host": self.host, "body": self.body, "headers": headers})

        def getresponse(self):
            prompt = self.body["messages"][0]["content"]
            ids = [post.tweet_id for post in posts if post.tweet_id in prompt]
            if "unsanctioned_flags" in self.body.get("system", ""):
                payload = {
                    "results": [
                            {"tweet_id": ident, "classifications": [{
                                "brand_id": "telemetry-brand", "outcome": "classified",
                                "post_types": ["hands_on_usage"], "product_labels": [],
                                "sentiment": "neutral", "china_nationalism": "none",
                                "us_nationalism": "none",
                            }], "unsanctioned_flags": []}
                        for ident in ids
                    ]
                }
                usage = {"input_tokens": 7, "output_tokens": 5, "total_tokens": 12}
            else:
                payload = _translation_response([{"tweet_id": ident, "text": ""} for ident in ids])
                usage = {"input_tokens": 31, "output_tokens": 17, "total_tokens": 48}
            return FakeHttpResponse({"content": [{"type": "text", "text": json.dumps(payload)}], "usage": usage})

        def close(self):
            pass

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    monkeypatch.setenv("X_MONITOR_CLASSIFIER_BASE_URL", "https://api.deepseek.com/anthropic")
    monkeypatch.setattr("http.client.HTTPSConnection", FakeHttpsConnection)
    caplog.set_level("INFO")
    counters = CycleRunner()._run_post_fetch([], run_id="telemetry-cycle")

    states = list(PostEnrichmentState.objects.order_by("post_id"))
    assert counters["n_enrichment_claimed"] == 21
    # Two translation calls plus the classifier's two base, three secondary,
    # and three review calls for a 21-post production-shaped batch.
    assert len(requests) == 10
    assert {request["host"] for request in requests} == {"api.deepseek.com"}
    assert all(request["headers"]["x-api-key"] == "test-key" for request in requests)
    assert all(state.translation_status == "succeeded" for state in states)
    assert all(state.classification_status == "succeeded" for state in states)
    events = _events(caplog)
    assert len(events) == 10
    assert {event["run_id"] for event in events} == {"telemetry-cycle"}
    assert {event["stage"] for event in events} == {"post_fetch"}
    assert {event["batch_size"] for event in events} == {1, 10, 20}
    assert {event["role"] for event in events} == {"post_translation_synthesis", "classification"}
    assert {event["provider_host_class"] for event in events} == {"deepseek"}
    assert all(event["model"] for event in events)
    classifier_requests = [
        request["body"]
        for request in requests
        if "unsanctioned_flags" in request["body"].get("system", "")
    ]
    assert len(classifier_requests) == 8
    assert all(
        len(request["messages"]) == 1
        and request["messages"][0]["role"] == "user"
        and isinstance(json.loads(request["messages"][0]["content"]), list)
        for request in classifier_requests
    )


def test_direct_http_wrapper_retains_usage_when_assistant_json_is_malformed(monkeypatch):
    """The real response extractor keeps usage when assistant text cannot parse."""
    from x_monitor.reattribute import build_anthropic_client_from_env

    class FakeHttpResponse:
        status = 200

        def read(self):
            return json.dumps(
                {
                    "content": [{"type": "text", "text": "{malformed"}],
                    "usage": {"input_tokens": 6, "output_tokens": 2, "total_tokens": 8},
                }
            ).encode()

    class FakeHttpsConnection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, *_args, **_kwargs):
            pass

        def getresponse(self):
            return FakeHttpResponse()

        def close(self):
            pass

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("X_MONITOR_CLASSIFIER_BASE_URL", "https://api.deepseek.com/anthropic")
    monkeypatch.setattr("http.client.HTTPSConnection", FakeHttpsConnection)
    client = build_anthropic_client_from_env()
    assert client is not None
    response = client.messages_create(model="test-model", max_tokens=8, messages=[])
    assert response == {"verdict": "uncertain", "reason": "llm_non_json_response"}
    assert response.provider_usage == {"input_tokens": 6, "output_tokens": 2, "total_tokens": 8}


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_narrative_stage_event_reconciles_to_the_sent_ledger_call(caplog, monkeypatch):
    """The actual task transport retains the durable call/run/stage identity."""
    from django.utils import timezone

    from core.models import TrendNarrativeRun
    from monitor.trend_narrative_lifecycle import reserve_trend_narrative_provider_call
    from monitor.trend_narrative_tasks import execute_per_brand_stage
    from x_monitor.config import HeadlineNarrativeConfig

    config = HeadlineNarrativeConfig(activation_state="owner_override", provider_calls_enabled=True)
    run = TrendNarrativeRun.objects.create(
        source_cycle_id="telemetry-headline", window_days=1, facts_as_of=timezone.now(),
        packet_schema_version=3, snapshot={}, brand_manifest=[],
    )
    request = {"model": config.model, "max_tokens": 8, "thinking": {"type": "disabled"}, "system": "test", "messages": [{"role": "user", "content": "test"}]}
    call = reserve_trend_narrative_provider_call(
        run=run, stage="rank", batch_key="1d:001", request_identity="telemetry-headline-rank",
        request_hash="a" * 64, request_packet={"provider_request": request}, now=timezone.now(),
    )
    assert call is not None

    class FakeMessages:
        def create(self, **kwargs):
            assert kwargs == request
            return SimpleNamespace(content=[SimpleNamespace(text="{}")], usage=SimpleNamespace(input_tokens=9, output_tokens=4))

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr("monitor.trend_narrative_tasks._load_config", lambda: config)
    monkeypatch.setattr("monitor.trend_narrative_generation._anthropic_client", lambda **_kwargs: SimpleNamespace(messages=FakeMessages()))
    monkeypatch.setattr("monitor.trend_narrative_tasks._reconcile_run", lambda *_args, **_kwargs: None)
    caplog.set_level("INFO")
    assert execute_per_brand_stage(call.pk)["status"] == "completed"

    call.refresh_from_db()
    event = _events(caplog)[0]
    assert call.state == "completed"
    assert (event["call_id"], event["run_id"], event["stage"], event["batch_key"]) == (call.pk, str(run.pk), "rank", "1d:001")
    assert event["request_identity"] == call.request_identity
    assert event["usage"]["input_tokens"] == call.input_tokens == 9
