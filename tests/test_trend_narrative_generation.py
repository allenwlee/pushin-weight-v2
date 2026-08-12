"""Closed-input, single-attempt contracts for headline prose generation."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from monitor.trend_narrative_generation import (
    HeadlineGenerationError,
    generate_trend_narrative,
    generation_fingerprint,
)
from x_monitor.config import HeadlineNarrativeConfig, load_config


def _facts(*, narrative_type: str = "handoff") -> dict:
    return {
        "schema_version": 1,
        "window_days": 1,
        "as_of": "2026-08-12T12:00:00Z",
        "window_start": "2026-08-11T12:00:00Z",
        "midpoint": "2026-08-12T00:00:00Z",
        "coverage": {
            "state": "sufficient",
            "ratio": "1.000000",
            "earliest_at": "2025-01-15T00:00:00Z",
        },
        "thresholds": {
            "min_posts": 20,
            "min_authors": 10,
            "contested_ratio": "0.80",
            "minimum_coverage": "0.75",
            "momentum": {
                "surging": "1.50",
                "rising": "1.15",
                "steady": "0.85",
            },
        },
        "narrative_type": narrative_type,
        "primary_brand": {
            "key": "minimax",
            "display_name_en": "MiniMax",
            "display_name_zh_hans": "MiniMax",
            "recent_posts": 30,
            "recent_authors": 15,
            "earlier_posts": 10,
            "earlier_authors": 8,
        },
        "secondary_brand": None,
        "earlier_leader": {
            "key": "deepseek",
            "display_name_en": "DeepSeek",
            "display_name_zh_hans": "DeepSeek",
            "recent_posts": 12,
            "recent_authors": 8,
            "earlier_posts": 25,
            "earlier_authors": 12,
        },
        "momentum": "surging",
    }


def _valid_payload() -> dict:
    return {
        "body_en": (
            "MiniMax now leads the conversation as attention moves away from DeepSeek."
        ),
        "body_zh_hans": "讨论热度已从 DeepSeek 转向 MiniMax，后者目前更受关注。",
        "narrative_type": "handoff",
        "mentioned_brand_keys": ["minimax", "deepseek"],
    }


class _FakeMessages:
    def __init__(self, payload: object):
        self.payload = payload
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        raw = (
            self.payload
            if isinstance(self.payload, str)
            else json.dumps(self.payload, ensure_ascii=False)
        )
        return SimpleNamespace(
            content=[SimpleNamespace(text=raw)],
            usage=SimpleNamespace(input_tokens=120, output_tokens=52),
        )


class _FakeClient:
    def __init__(self, payload: object):
        self.messages = _FakeMessages(payload)


def test_headline_config_defaults_are_pinned_and_fail_closed():
    config = HeadlineNarrativeConfig()

    assert config.provider == "anthropic"
    assert config.base_url == "https://api.anthropic.com"
    assert config.model == "claude-haiku-4-5-20251001"
    assert config.cadence_minutes == {1: 30, 7: 60, 30: 360, 365: 1440}
    assert config.stale_minutes == {1: 60, 7: 120, 30: 720, 365: 2880}
    assert config.call_cap == 4
    assert not config.serving_enabled
    assert not config.enqueue_enabled
    assert not config.provider_calls_enabled


def test_headline_config_yaml_non_null_wins_and_null_permits_env(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("X_MONITOR_HEADLINE_MODEL", "env-model")
    monkeypatch.setenv("X_MONITOR_HEADLINE_TIMEOUT_SECONDS", "33")
    path = tmp_path / "config.yaml"
    path.write_text(
        """
enabled_models: [minimax]
daily_ceiling: 100
headline_narrative:
  model: claude-haiku-4-5-20251001
  timeout_seconds: null
""",
        encoding="utf-8",
    )

    config = load_config(path).headline_narrative

    assert config.model == "claude-haiku-4-5-20251001"
    assert config.timeout_seconds == 33


def test_real_boundary_explicitly_pins_route_model_timeout_and_zero_retries(
    monkeypatch,
):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://wrong.example")
    monkeypatch.setenv("X_MONITOR_CLASSIFIER_MODEL", "wrong-classifier")
    monkeypatch.setenv("X_MONITOR_TRANSLATOR_MODEL", "wrong-translator")
    constructors: list[dict] = []
    client = _FakeClient(_valid_payload())

    def factory(**kwargs):
        constructors.append(kwargs)
        return client

    result = generate_trend_narrative(
        _facts(),
        HeadlineNarrativeConfig(timeout_seconds=41),
        api_key="headline-secret",
        client_factory=factory,
        monotonic=lambda: 10.0 if not client.messages.calls else 10.25,
    )

    assert constructors == [
        {
            "api_key": "headline-secret",
            "base_url": "https://api.anthropic.com",
            "timeout": 41.0,
            "max_retries": 0,
        }
    ]
    assert len(client.messages.calls) == 1
    call = client.messages.calls[0]
    assert call["model"] == "claude-haiku-4-5-20251001"
    assert call["temperature"] == 0
    assert call["max_tokens"] == 320
    assert "raw_text" not in json.dumps(call)
    assert result.body_zh_hans.startswith("讨论热度")
    assert result.provider_host == "api.anthropic.com"
    assert result.input_tokens == 120
    assert result.output_tokens == 52
    assert result.latency_ms == 250


def test_aggregate_only_guard_rejects_nested_raw_text_before_client_creation():
    facts = _facts()
    facts["primary_brand"]["RAW_TEXT"] = "private post body"
    factory_calls: list[dict] = []

    def factory(**kwargs):
        factory_calls.append(kwargs)
        return _FakeClient(_valid_payload())

    with pytest.raises(
        HeadlineGenerationError,
        match="headline_fact_payload_not_aggregate_only",
    ):
        generate_trend_narrative(
            facts,
            HeadlineNarrativeConfig(),
            api_key="headline-secret",
            client_factory=factory,
        )

    assert factory_calls == []


def test_digit_bearing_brand_name_is_allowed_but_numeric_claims_are_not():
    facts = _facts(narrative_type="leader")
    facts["primary_brand"].update(
        key="yi",
        display_name_en="01.AI Yi",
        display_name_zh_hans="01.AI Yi",
    )
    facts["earlier_leader"] = None
    valid = {
        "body_en": "01.AI Yi leads attention across the current market.",
        "body_zh_hans": "当前市场讨论中，01.AI Yi 更受关注。",
        "narrative_type": "leader",
        "mentioned_brand_keys": ["yi"],
    }

    result = generate_trend_narrative(
        facts,
        HeadlineNarrativeConfig(),
        api_key="headline-secret",
        client_factory=lambda **_kwargs: _FakeClient(valid),
    )
    assert result.body_en.startswith("01.AI Yi")

    invalid = dict(valid, body_en="01.AI Yi leads with 30 posts today.")
    with pytest.raises(HeadlineGenerationError):
        generate_trend_narrative(
            facts,
            HeadlineNarrativeConfig(),
            api_key="headline-secret",
            client_factory=lambda **_kwargs: _FakeClient(invalid),
        )


def test_short_brand_key_requires_a_real_word_boundary():
    facts = _facts(narrative_type="leader")
    facts["primary_brand"].update(
        key="yi",
        display_name_en="Yi",
        display_name_zh_hans="Yi",
    )
    facts["earlier_leader"] = None
    payload = {
        "body_en": "Attention has steadily yielded across the current market.",
        "body_zh_hans": "当前市场讨论热度仍在持续变化中。",
        "narrative_type": "leader",
        "mentioned_brand_keys": ["yi"],
    }

    with pytest.raises(HeadlineGenerationError):
        generate_trend_narrative(
            facts,
            HeadlineNarrativeConfig(),
            api_key="headline-secret",
            client_factory=lambda **_kwargs: _FakeClient(payload),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("body_en", "MiniMax has 30 posts and leads DeepSeek."),
        ("body_en", "MiniMax leads; see https://example.com for DeepSeek."),
        ("body_en", "**MiniMax** leads attention away from DeepSeek."),
        ("body_en", "<b>MiniMax</b> leads attention away from DeepSeek."),
        ("body_en", "MiniMax leads\u202e attention away from DeepSeek."),
        ("body_zh_hans", "MiniMax now leads DeepSeek."),
        ("narrative_type", "leader"),
        ("mentioned_brand_keys", ["minimax"]),
        ("mentioned_brand_keys", ["minimax", "deepseek", "qwen"]),
    ],
)
def test_invalid_or_unsupported_output_fails_without_repair_call(field, value):
    payload = _valid_payload()
    payload[field] = value
    client = _FakeClient(payload)

    with pytest.raises(HeadlineGenerationError):
        generate_trend_narrative(
            _facts(),
            HeadlineNarrativeConfig(),
            api_key="headline-secret",
            client_factory=lambda **_kwargs: client,
        )

    assert len(client.messages.calls) == 1


@pytest.mark.parametrize("payload", ["not json", {"type": "refusal"}, ""])
def test_refusal_or_non_json_fails_after_one_request(payload):
    client = _FakeClient(payload)

    with pytest.raises(HeadlineGenerationError):
        generate_trend_narrative(
            _facts(),
            HeadlineNarrativeConfig(),
            api_key="headline-secret",
            client_factory=lambda **_kwargs: client,
        )

    assert len(client.messages.calls) == 1


def test_extra_output_fields_are_rejected_without_repair_call():
    payload = {**_valid_payload(), "explanation": "untrusted extra prose"}
    client = _FakeClient(payload)

    with pytest.raises(HeadlineGenerationError):
        generate_trend_narrative(
            _facts(),
            HeadlineNarrativeConfig(),
            api_key="headline-secret",
            client_factory=lambda **_kwargs: client,
        )

    assert len(client.messages.calls) == 1


def test_current_minimax_route_is_explicit_and_legacy_model_is_rejected():
    config = HeadlineNarrativeConfig(
        provider="minimax",
        base_url="https://api.minimax.io/anthropic",
        model="MiniMax-M3",
    )
    assert config.provider == "minimax"
    with pytest.raises(ValidationError):
        HeadlineNarrativeConfig(
            provider="minimax",
            base_url="https://api.minimax.io/anthropic",
            model="minimax/MiniMax-M3.0[1m]",
        )


def test_unapproved_provider_host_is_rejected():
    with pytest.raises(ValidationError):
        HeadlineNarrativeConfig(base_url="https://evil.example/anthropic")


def test_generation_fingerprint_includes_route_prompt_and_epoch():
    facts = _facts()
    baseline = HeadlineNarrativeConfig()
    same = generation_fingerprint(facts, baseline)

    assert same == generation_fingerprint(facts, baseline)
    assert same != generation_fingerprint(
        facts,
        baseline.model_copy(update={"publication_epoch": 2}),
    )
    minimax = HeadlineNarrativeConfig(
        provider="minimax",
        base_url="https://api.minimax.io/anthropic",
        model="MiniMax-M3",
    )
    assert same != generation_fingerprint(facts, minimax)


def test_generation_fingerprint_ignores_exact_count_and_timestamp_drift():
    facts = _facts()
    drifted = json.loads(json.dumps(facts))
    drifted["as_of"] = "2026-08-12T12:15:00Z"
    drifted["primary_brand"]["recent_posts"] = 37
    drifted["primary_brand"]["recent_authors"] = 19

    assert generation_fingerprint(
        facts, HeadlineNarrativeConfig()
    ) == generation_fingerprint(drifted, HeadlineNarrativeConfig())


def test_generation_fingerprint_changes_with_brand_copy():
    facts = _facts()
    renamed = json.loads(json.dumps(facts))
    renamed["primary_brand"]["display_name_en"] = "MiniMax AI"

    assert generation_fingerprint(
        facts, HeadlineNarrativeConfig()
    ) != generation_fingerprint(renamed, HeadlineNarrativeConfig())
