"""Regression pins for the owner-selected direct DeepInfra enrichment routes.

These tests do not contact DeepInfra.  They exercise the same factory boundary
that ``CycleRunner._run_post_fetch`` calls and capture the adapter constructor
arguments, including in the presence of stale credentials and role overrides.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.yaml"


@pytest.fixture
def deepinfra_adapter(monkeypatch):
    """Install a fake adapter without importing or contacting a provider."""
    calls: list[dict[str, object]] = []
    client = object()

    class FakeDeepInfraChatCompletionsClient:
        @classmethod
        def from_config(cls, **kwargs):
            calls.append(kwargs)
            return client

    module = ModuleType("x_monitor.deepinfra")
    module.DeepInfraChatCompletionsClient = FakeDeepInfraChatCompletionsClient
    monkeypatch.setitem(sys.modules, "x_monitor.deepinfra", module)
    return client, calls


def test_committed_config_pins_owner_selected_direct_deepinfra_routes(monkeypatch):
    """YAML wins over stale role env values for all selected enrichment lanes."""
    from x_monitor.config import load_config

    monkeypatch.setenv("X_MONITOR_CLASSIFIER_MODEL", "stale-classifier")
    monkeypatch.setenv("X_MONITOR_CLASSIFIER_BASE_URL", "https://stale.example/v1")
    monkeypatch.setenv("X_MONITOR_TRANSLATOR_MODEL", "stale-translator")
    monkeypatch.setenv("X_MONITOR_TRANSLATOR_BASE_URL", "https://stale.example/v1")

    cfg = load_config(CONFIG_PATH)

    assert cfg.llm.classifier_provider == "deepinfra"
    assert cfg.llm.classifier_model == "deepseek-ai/DeepSeek-V4-Flash-0731"
    assert cfg.llm.classifier_base_url == "https://api.deepinfra.com/v1/openai"
    assert cfg.llm.classifier_deepinfra_request_profile == "deepseek_0731"
    assert cfg.llm.translator_provider == "deepinfra"
    assert cfg.llm.translator_model == "google/gemma-4-31B-it-turbo"
    assert cfg.llm.translator_base_url == "https://api.deepinfra.com/v1/openai"
    assert cfg.llm.translator_deepinfra_request_profile == "gemma4_translation_v1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"classifier_model": "different-model"},
        {"classifier_base_url": "https://api.deepinfra.com/v1"},
        {"classifier_deepinfra_request_profile": None},
        {"translator_model": "different-model"},
        {"translator_base_url": "https://api.deepinfra.com/v1"},
        {"translator_deepinfra_request_profile": None},
    ],
)
def test_direct_deepinfra_route_rejects_partial_or_drifted_selection(overrides):
    """Changing any part of a direct selected route is an explicit config error."""
    from pydantic import ValidationError

    from x_monitor.config import LlmConfig

    selected = {
        "classifier_provider": "deepinfra",
        "classifier_model": "deepseek-ai/DeepSeek-V4-Flash-0731",
        "classifier_base_url": "https://api.deepinfra.com/v1/openai",
        "classifier_deepinfra_request_profile": "deepseek_0731",
        "translator_provider": "deepinfra",
        "translator_model": "google/gemma-4-31B-it-turbo",
        "translator_base_url": "https://api.deepinfra.com/v1/openai",
        "translator_deepinfra_request_profile": "gemma4_translation_v1",
    }
    selected.update(overrides)

    with pytest.raises(ValidationError):
        LlmConfig(**selected)


def test_selected_factories_pass_exact_direct_routes_to_the_adapter(
    monkeypatch, deepinfra_adapter
):
    """Production factories preserve each role's pinned model/profile."""
    from x_monitor.config import load_config
    from x_monitor.reattribute import (
        build_classifier_client_from_env,
        build_translator_client_from_env,
    )

    # These must not affect a direct DeepInfra route.
    monkeypatch.setenv("OPENROUTER_API_KEY", "wrong-provider")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "wrong-provider")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "wrong-provider")
    cfg = load_config(CONFIG_PATH)
    client, calls = deepinfra_adapter

    assert build_classifier_client_from_env(cfg) is client
    assert build_translator_client_from_env(cfg) is client
    assert calls == [
        {
            "model": "deepseek-ai/DeepSeek-V4-Flash-0731",
            "base_url": "https://api.deepinfra.com/v1/openai",
            "request_profile": "deepseek_0731",
        },
        {
            "model": "google/gemma-4-31B-it-turbo",
            "base_url": "https://api.deepinfra.com/v1/openai",
            "request_profile": "gemma4_translation_v1",
        },
    ]


def test_direct_provider_factory_does_not_fall_back_when_dedicated_key_is_absent(
    monkeypatch,
):
    """A direct route stays unavailable instead of borrowing another key."""
    from x_monitor.config import LlmConfig
    from x_monitor.reattribute import build_classifier_client_from_env

    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-be-used")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "must-not-be-used")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-be-used")
    cfg = type(
        "Config",
        (),
        {
            "llm": LlmConfig(
                classifier_provider="deepinfra",
                classifier_model="deepseek-ai/DeepSeek-V4-Flash-0731",
                classifier_base_url="https://api.deepinfra.com/v1/openai",
                classifier_deepinfra_request_profile="deepseek_0731",
            )
        },
    )()

    assert build_classifier_client_from_env(cfg) is None


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_cycle_classifier_reaches_direct_deepinfra_request_shape(monkeypatch):
    """M18: persisted work crosses the real factory and direct adapter."""
    import json
    from django.core.management import call_command

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
    from x_monitor.config import load_config
    from x_monitor.deepinfra import DeepInfraChatCompletionsClient

    # Migration-contract tests intentionally flush seed catalogs. Rebuild the
    # production prerequisite so this call-chain test is order-independent.
    call_command("seed_i18n_labels", verbosity=0)

    brand = Brand.objects.create(
        nickname="direct-route-brand", display_name="Direct Route"
    )
    post = Post.objects.create(
        tweet_id="direct-route-post", text="I used it and it worked.", lang="en"
    )
    PostBrand.objects.create(post=post, brand=brand)
    PostEnrichmentState.objects.create(
        post=post,
        translation_status=PostEnrichmentState.Status.SUCCEEDED,
    )
    PostTypeKey.objects.get_or_create(key="hands_on_usage")
    SentimentKey.objects.get_or_create(key="neutral")
    NationalismKey.objects.get_or_create(key="none")

    requests = []

    def fake_send(self, request, *, timeout):
        requests.append((request, timeout))
        system = request["messages"][0]["content"]
        payload = json.loads(request["messages"][-1]["content"])
        role = (
            "content"
            if "CONTENT ROLE:" in system
            else "brand_interpretation"
        )
        decisions = {}
        for case in payload["cases"].values():
            for slot in case["brand_decision_slots"]:
                decisions[slot] = (
                    {
                        "outcome": "classified",
                        "post_types": ["hands_on_usage"],
                        "audience_topics": ["none"],
                    }
                    if role == "content"
                    else {
                        "product_labels": ["none"],
                        "sentiment": "neutral",
                        "geopolitical_modes": ["none"],
                        "china_national_stance": "none",
                        "us_national_stance": "none",
                    }
                )
        response = {"decisions": decisions}
        if role == "content":
            response["post_promotions"] = {
                post_slot: ["none"] for post_slot in payload["cases"]
            }
            response["promoted_subjects"] = {
                post_slot: [] for post_slot in payload["cases"]
            }
        return {
            "id": f"direct-{role}",
            "model": "deepseek-ai/DeepSeek-V4-Flash-0731",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": json.dumps(response)},
                }
            ],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
                "estimated_cost": 0.00001,
            },
        }

    monkeypatch.setenv("DEEPINFRA_API_KEY", "direct-fixture")
    monkeypatch.setattr(DeepInfraChatCompletionsClient, "_send_request", fake_send)
    monkeypatch.setattr(
        "monitor.cycle._requeue_recent_incomplete_translations", lambda **_kwargs: 0
    )
    cfg = load_config(CONFIG_PATH)

    counters = CycleRunner(cfg=cfg)._run_post_fetch([], run_id="direct-route")

    assert counters["n_classifier_unavailable"] == 0
    assert len(requests) == 2
    for request, timeout in requests:
        assert request["model"] == "deepseek-ai/DeepSeek-V4-Flash-0731"
        assert request["temperature"] == 1.0
        assert request["top_p"] == 1.0
        assert request["seed"] == 42
        assert request["reasoning_effort"] == "none"
        assert "provider" not in request
        assert "response_format" not in request
        assert timeout > 0
    state = PostEnrichmentState.objects.get(post=post)
    assert state.classification_status == PostEnrichmentState.Status.SUCCEEDED
