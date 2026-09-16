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
    assert artifact.prompt_version == "literal-translation-plaintext-v2"
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
