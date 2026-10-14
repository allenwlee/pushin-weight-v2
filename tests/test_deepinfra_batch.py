"""Provider batching keeps request semantics and bounds response memory."""

import json

import pytest


def test_batch_file_preserves_independent_wire_requests_and_ids():
    from x_monitor.deepinfra_batch import encode_requests

    body = {
        "model": "model-a",
        "messages": [{"role": "user", "content": "中文"}],
        "max_tokens": 100,
    }
    encoded = encode_requests(
        [("first", body), ("second", body)], max_requests=2, max_bytes=4096
    )
    rows = [json.loads(line) for line in encoded.splitlines()]
    assert [row["custom_id"] for row in rows] == ["first", "second"]
    assert all(
        row["body"] == body and row["url"] == "/v1/chat/completions" for row in rows
    )


@pytest.mark.parametrize(
    "rows,kwargs",
    [
        ([("a", {"model": "m"}), ("a", {"model": "m"})], {}),
        ([("a", {"model": "m"}), ("b", {"model": "other"})], {}),
        ([("a", {"model": "m"})], {"max_bytes": 1}),
        ([("a", {"model": "m"}), ("b", {"model": "m"})], {"max_requests": 1}),
        ([], {}),
    ],
)
def test_invalid_batch_rejected_before_transport(rows, kwargs):
    from x_monitor.deepinfra_batch import BatchProtocolError, encode_requests

    with pytest.raises(BatchProtocolError):
        encode_requests(rows, **kwargs)


def test_provider_error_classification_preserves_retry_after():
    from x_monitor.deepinfra_batch import BatchHTTPError

    limited = BatchHTTPError(429, "120")
    assert limited.retryable and limited.retry_after_seconds == 120
    assert BatchHTTPError(503).retryable
    assert not BatchHTTPError(401).retryable
    assert BatchHTTPError(429, "untrusted").retry_after_seconds == 60


def test_json_lines_decoder_handles_chunks_and_bounds_one_line():
    from x_monitor.deepinfra_batch import BatchProtocolError, decode_outputs

    raw = b'{"custom_id":"a"}\n{"custom_id":"b"}\n'
    assert list(decode_outputs([raw[:9], raw[9:24], raw[24:]], max_line_bytes=128)) == [
        {"custom_id": "a"},
        {"custom_id": "b"},
    ]
    with pytest.raises(BatchProtocolError):
        list(decode_outputs([b"x" * 129], max_line_bytes=128))


def test_batch_text_response_uses_same_strict_parser_as_direct():
    from x_monitor.deepinfra import GEMMA_4_31B_MODEL, DeepInfraChatCompletionsClient

    client = DeepInfraChatCompletionsClient(
        api_key="test-only", model=GEMMA_4_31B_MODEL
    )
    decoded = {
        "model": GEMMA_4_31B_MODEL,
        "choices": [{"finish_reason": "stop", "message": {"content": "译文"}}],
    }
    assert client.parse_text_response(decoded).text == "译文"
    decoded["choices"][0]["finish_reason"] = "length"
    with pytest.raises(Exception, match="deepinfra_response_incomplete"):
        client.parse_text_response(decoded)


def test_unterminated_final_result_cannot_bypass_count_limit(monkeypatch):
    import x_monitor.deepinfra_batch as batch

    monkeypatch.setattr(batch, "SERVER_MAX_REQUESTS", 2)
    with pytest.raises(batch.BatchProtocolError, match="batch_result_count_limit"):
        list(batch.decode_outputs([b"{}\n{}\n{}"]))


def test_http_admission_runs_before_paid_submission_and_never_retries():
    from x_monitor.deepinfra_batch import BatchHTTPError, DeepInfraBatchClient

    events = []

    class Reply:
        status_code = 429

        def __init__(self):
            self.headers = {"Retry-After": "95"}

        def close(self):
            events.append("close")

    class Session:
        def request(self, method, url, **kwargs):
            events.append("http")
            assert method == "POST" and url.endswith("/batches")
            assert kwargs["json"]["metadata"] == {"request_identity": "stable-id"}
            return Reply()

    client = DeepInfraBatchClient(
        api_key="test-only",
        before_request=lambda method, path: events.append("admit"),
        session=Session(),
    )
    with pytest.raises(BatchHTTPError) as error:
        client.submit("file-a", identity="stable-id")
    assert error.value.retry_after_seconds == 95
    assert events == ["admit", "http", "close"]


def test_exhausted_budget_prevents_http_start():
    from x_monitor.deepinfra_batch import DeepInfraBatchClient

    def deny(method, path):
        raise RuntimeError("budget exhausted")

    class Session:
        def request(self, *args, **kwargs):
            pytest.fail("provider called without admission")

    client = DeepInfraBatchClient(
        api_key="test-only", before_request=deny, session=Session()
    )
    with pytest.raises(RuntimeError, match="budget exhausted"):
        client.retrieve("batch-a")


def test_real_translator_prepares_then_replays_identical_wire_requests_without_http():
    from x_monitor.config import Config, LlmConfig
    from x_monitor.deepinfra import GEMMA_4_31B_MODEL, DeepInfraChatCompletionsClient
    from x_monitor.deferred_inference import DeferredInferenceClient
    from x_monitor.literal_translation import translate_batch_literal_plaintext

    def forbidden(*args, **kwargs):
        pytest.fail("request preparation/replay made a synchronous provider call")

    delegate = DeepInfraChatCompletionsClient(
        api_key="test-only",
        model=GEMMA_4_31B_MODEL,
        request_profile="gemma4_translation_v1",
        transport=forbidden,
    )
    captured = {}
    responses = {}

    def resolve(identity, body, kind, context):
        captured[identity] = (body, kind, context)
        return responses.get(identity)

    deferred = DeferredInferenceClient(delegate, resolve=resolve)
    cfg = Config(
        enabled_models=["qwen"],
        daily_ceiling=100,
        llm=LlmConfig(translator_model=GEMMA_4_31B_MODEL),
    )
    tweet = {"tweet_id": "one", "text": "A simple source", "lang_detected": "en"}
    pending = translate_batch_literal_plaintext([tweet], deferred, cfg=cfg)[0]
    assert pending["translation_failed"] and pending["provider_calls"] == 0
    assert len(captured) == 2
    for index, (identity, (body, kind, context)) in enumerate(captured.items()):
        assert kind == "text" and body["model"] == GEMMA_4_31B_MODEL
        assert context["post_ids"] == ["one"] and context["stage"] == "translation"
        assert "service_tier" not in body and "thinking" not in body
        responses[identity] = {
            "model": GEMMA_4_31B_MODEL,
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": ["中文", "日本語"][index]},
                }
            ],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 2,
                "estimated_cost": 0.001,
            },
        }
    completed = translate_batch_literal_plaintext([tweet], deferred, cfg=cfg)[0]
    assert not completed["translation_failed"]
    assert completed["text_en"] == tweet["text"] and completed["text_zh_cn"] == "中文"
    assert len(captured) == 2 and completed["input_tokens"] == 40


def test_real_classifier_batches_two_roles_and_replays_through_existing_parser():
    from tests.test_u18_runtime_0731 import FixedSlotTransport, _tweets
    from x_monitor.attribution import BrandRow, classify_batch_pragmatics_full
    from x_monitor.deepinfra import DEEPSEEK_0731_MODEL, DeepInfraChatCompletionsClient
    from x_monitor.deferred_inference import DeferredInferenceClient

    def forbidden(*args, **kwargs):
        pytest.fail("batch preparation/replay called synchronous inference")

    delegate = DeepInfraChatCompletionsClient(
        api_key="test-only",
        model=DEEPSEEK_0731_MODEL,
        request_profile="deepseek_0731",
        transport=forbidden,
    )
    captured, replies = {}, {}

    def resolve(identity, body, kind, context):
        captured[identity] = (body, kind, context)
        return replies.get(identity)

    client = DeferredInferenceClient(delegate, resolve=resolve)
    registry = [
        BrandRow(
            brand_id=name, display_name=name, accent_color="#000", is_sentinel=False
        )
        for name in ("deepseek", "minimax")
    ]
    tweets = _tweets(21)
    for tweet in tweets:
        tweet["english_translation"] = tweet["text"]
    waiting = classify_batch_pragmatics_full(
        tweets, registry, client, model=DEEPSEEK_0731_MODEL
    )
    assert not any(row["valid"] for row in waiting)
    assert len(captured) == 4  # two roles for twenty posts, then two for one
    simulator = FixedSlotTransport()
    assert sorted(len(context["post_ids"]) for _, _, context in captured.values()) == [
        1,
        1,
        20,
        20,
    ]
    for identity, (body, kind, context) in captured.items():
        assert kind == "json" and body["seed"] == 42 and body["top_p"] == 1
        assert context["stage"] == "classification"
        response = simulator.messages_create(
            system=body["messages"][0]["content"], messages=body["messages"][1:]
        )
        replies[identity] = {
            "model": DEEPSEEK_0731_MODEL,
            "choices": [
                {"finish_reason": "stop", "message": {"content": json.dumps(response)}}
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
    ready = classify_batch_pragmatics_full(
        tweets, registry, client, model=DEEPSEEK_0731_MODEL
    )
    assert all(row["valid"] for row in ready)
    assert len(captured) == 4


def test_preparation_and_replay_do_not_count_as_new_model_starts_or_sleep():
    from monitor.cycle import _BoundedClassifierClient
    from x_monitor.deepinfra import GEMMA_4_31B_MODEL, DeepInfraChatCompletionsClient
    from x_monitor.deferred_inference import (
        DeferredInferenceClient,
        DeferredRequestPending,
    )

    def forbidden(*args, **kwargs):
        pytest.fail("deferred inference used live admission, cost callback or sleep")

    delegate = DeepInfraChatCompletionsClient(
        api_key="test-only", model=GEMMA_4_31B_MODEL
    )
    deferred = DeferredInferenceClient(delegate, resolve=lambda *args: None)
    bounded = _BoundedClassifierClient(
        deferred,
        maximum_calls=10,
        pause_seconds=10,
        before_call=forbidden,
        after_call=forbidden,
        sleep=forbidden,
    )
    kwargs = {
        "model": GEMMA_4_31B_MODEL,
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "source"}],
        "_batch_context": {"post_ids": ["one"]},
    }
    for _ in range(2):
        with pytest.raises(DeferredRequestPending):
            bounded.messages_create_text(**kwargs)
    assert bounded.calls == 0 and bounded.remaining_calls == 8


def test_classifier_splits_multi_brand_posts_before_99_decision_slot_limit():
    from tests.test_u18_runtime_0731 import FixedSlotTransport, _tweets
    from x_monitor.attribution import BrandRow, classify_batch_pragmatics_full
    from x_monitor.deepinfra import DEEPSEEK_0731_MODEL

    names = ["deepseek", "minimax", "qwen", "glm", "openai", "gemini"]
    registry = [
        BrandRow(
            brand_id=name, display_name=name, accent_color="#000", is_sentinel=False
        )
        for name in names
    ]
    tweets = _tweets(21)
    for tweet in tweets:
        tweet["brand_ids"] = list(names)
        tweet["english_translation"] = tweet["text"]
    provider = FixedSlotTransport()
    results = classify_batch_pragmatics_full(
        tweets, registry, provider, model=DEEPSEEK_0731_MODEL
    )
    assert all(row["valid"] for row in results)
    assert len(provider.calls) == 4
    assert sorted(len(call["payload"]["cases"]) for call in provider.calls) == [
        5,
        5,
        16,
        16,
    ]
