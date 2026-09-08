"""Stage 0 provider telemetry call-chain regression net.

These tests use the production translator entry point and deepest fake
transport. They intentionally inspect log records rather than a database
ledger: one record belongs to one application transport invocation.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

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


def test_parallel_real_transport_callers_keep_run_and_batch_correlation(caplog):
    """Three workers and >20 calls must not share mutable client context."""
    from x_monitor.translator import _call_with_retry

    class FakeClient:
        def messages_create(self, **kwargs):
            return _translation_response([{"tweet_id": "synthetic", "text": "x"}])

    caplog.set_level("INFO")
    client = FakeClient()
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(
            pool.map(
                lambda index: _call_with_retry(
                    client,
                    "synthetic prompt",
                    n_tweets=21,
                    telemetry_context={
                        "run_id": "synthetic-run",
                        "stage": "post_fetch",
                        "batch_size": 21,
                        "prompt_identity": f"synthetic-{index}",
                    },
                ),
                range(24),
            )
        )

    events = _events(caplog)
    assert len(events) == 24
    assert {event["run_id"] for event in events} == {"synthetic-run"}
    assert {event["batch_size"] for event in events} == {21}
    assert {event["prompt_identity"] for event in events} == {
        f"synthetic-{index}" for index in range(24)
    }
    assert all(event["role"] == "post_translation_synthesis" for event in events)
