"""Exercise the production post-fetch caller and its durable literal writer."""
import pytest

from core.models import Post, PostEnrichmentState, PostTranslationArtifact
from monitor.cycle import CycleRunner
from x_monitor import reattribute
from x_monitor.config import Config, LlmConfig
from x_monitor.provider_telemetry import ProviderTextResponse

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("fail_ja", [False, True])
def test_post_fetch_plaintext_publishes_exact_text_or_records_failure(monkeypatch, fail_ja):
    source = '  "First paragraph"\n\nSecond paragraph.\n'
    post = Post.objects.create(tweet_id="plaintext-cycle", text=source, lang="en")
    PostEnrichmentState.objects.create(
        post=post, classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )
    calls = []

    class RawClient:
        _base_url = "https://api.deepseek.com/anthropic"

        def messages_create_text(self, **kwargs):
            calls.append(kwargs)
            if "Japanese (ja)" in kwargs["messages"][0]["content"]:
                if fail_ja:
                    error = ValueError("isolated locale failure")
                    error.provider_usage = {"input_tokens": 10, "output_tokens": 12}
                    raise error
                text = '  最初\n\n次。\n'
            else:
                text = '  第一\n\n第二。\n'
            return ProviderTextResponse(text, {"input_tokens": 7, "output_tokens": 9})

    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda cfg: RawClient())
    cfg = Config(enabled_models=["deepseek"], daily_ceiling=100, llm=LlmConfig(
        literal_translation_v2_enabled=True,
        translator_model="deepseek-v4-flash",
        translator_base_url="https://api.deepseek.com/anthropic",
    ))
    CycleRunner(cfg=cfg)._run_post_fetch([], run_id="plaintext-wiring")
    assert len(calls) == 2
    assert all(call["model"] == cfg.llm.translator_model for call in calls)
    assert all(call["timeout"] > 0 for call in calls)
    artifact = PostTranslationArtifact.objects.get(post=post)
    assert artifact.prompt_version == "literal-translation-plaintext-v12"
    if fail_ja:
        assert artifact.state == PostTranslationArtifact.State.FAILED
        assert not artifact.texts.exists()
        assert artifact.input_tokens == 17
        assert artifact.output_tokens == 21
    else:
        assert artifact.state == PostTranslationArtifact.State.SUCCEEDED
        assert {value.locale: value.text for value in artifact.texts.all()} == {
            "en": source, "zh-cn": '  第一\n\n第二。\n', "ja": '  最初\n\n次。\n',
        }
        assert artifact.input_tokens == 14
        assert artifact.output_tokens == 18
        post.refresh_from_db()
        assert post.text_en == source


@pytest.mark.parametrize("failure", ["quantity", "language", "pronunciation"])
def test_semantic_rejection_cannot_publish_from_real_post_fetch(monkeypatch, failure):
    source = (
        "The model was trained on 10.9 trillion tokens."
        if failure == "quantity" else
        "日本語の発音について説明します。こちらの例を読んでください。発音と意味の違いを確認しましょう。"
    )
    if failure == "pronunciation":
        source = "Pronunciation guide\nWidget → ウィジェット"
    post = Post.objects.create(tweet_id="invariant-" + failure, text=source, lang="ja" if failure == "language" else "en")
    PostEnrichmentState.objects.create(post=post, classification_status=PostEnrichmentState.Status.SUCCEEDED)
    calls = []

    class RawClient:
        _base_url = "https://api.deepseek.com/anthropic"

        def messages_create_text(self, **kwargs):
            calls.append(kwargs)
            prompt = kwargs["messages"][0]["content"]
            if failure == "quantity":
                text = "109万亿个token" if "Simplified Chinese" in prompt else "10.9兆トークン"
            elif failure == "pronunciation":
                assert "[[PQ0:001]]" in prompt
                text = "Widget → Widget"
            else:
                text = source if "English (en)" in prompt else "请阅读日语发音说明。"
            return ProviderTextResponse(text, {"input_tokens": 7, "output_tokens": 9})

    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda cfg: RawClient())
    cfg = Config(enabled_models=["deepseek"], daily_ceiling=100, llm=LlmConfig(
        literal_translation_v2_enabled=True, translator_model="deepseek-v4-flash",
        translator_base_url="https://api.deepseek.com/anthropic",
    ))
    CycleRunner(cfg=cfg)._run_post_fetch([], run_id="invariant-wiring")
    artifact = PostTranslationArtifact.objects.get(post=post)
    assert artifact.state == PostTranslationArtifact.State.FAILED
    assert not artifact.texts.exists()
    assert artifact.input_tokens == 14 and artifact.output_tokens == 18
    assert len(calls) == 2
