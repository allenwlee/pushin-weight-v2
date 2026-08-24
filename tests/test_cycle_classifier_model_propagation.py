"""Production call-chain pin for the classifier's configured model."""

from __future__ import annotations

from typing import Any

import pytest

from x_monitor.config import Config, LlmConfig

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_cycle_post_fetch_sends_configured_flash_with_thinking_disabled(monkeypatch):
    """CycleRunner must not fall back to the classifier module's ambient model."""
    from core.models import Brand, Post, PostBrand, PostEnrichmentState
    from monitor.cycle import CycleRunner
    from x_monitor import attribution, reattribute, translator

    brand = Brand.objects.create(
        nickname="deepseek",
        display_name="DeepSeek",
        accent_color="#4f46e5",
    )
    post = Post.objects.create(
        tweet_id="cycle-classifier-flash",
        text="DeepSeek released a model",
    )
    PostBrand.objects.create(post=post, brand=brand)
    PostEnrichmentState.objects.create(post=post)

    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    monkeypatch.setenv(
        "X_MONITOR_CLASSIFIER_BASE_URL",
        "https://api.deepseek.com/anthropic",
    )
    monkeypatch.setattr(attribution, "_SIGNAL_MODEL", "ambient-model")

    class ClassifierClient:
        def __init__(self):
            self.calls: list[dict[str, Any]] = []

        def messages_create(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "results": [{
                    "tweet_id": post.pk,
                    "classifications": [],
                    "unsanctioned_flags": [],
                }]
            }

    classifier_client = ClassifierClient()
    translator_client = object()
    monkeypatch.setattr(
        reattribute,
        "build_translator_client_from_env",
        lambda cfg: translator_client,
    )
    monkeypatch.setattr(
        reattribute,
        "build_anthropic_client_from_env",
        lambda cfg: classifier_client,
    )
    monkeypatch.setattr(
        translator,
        "translate_batch_pragmatics",
        lambda tweets, locales, client, **kwargs: [
            {
                "tweet_id": tweet["tweet_id"],
                "text_en": tweet["text"],
                "text_zh_cn": "深度求索发布了一个模型",
                "lang_detected": "en",
            }
            for tweet in tweets
        ],
    )

    cfg = Config(
        enabled_models=["deepseek"],
        daily_ceiling=100,
        llm=LlmConfig(classifier_model="deepseek-v4-flash"),
    )
    CycleRunner(cfg=cfg)._run_post_fetch([], run_id="classifier-model-pin")

    assert len(classifier_client.calls) == 1
    call = classifier_client.calls[0]
    assert call["model"] == "deepseek-v4-flash"
    assert call["thinking"] == {"type": "disabled"}
    assert call["max_tokens"] == 4096
