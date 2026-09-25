"""Exercise the production post-fetch caller and its durable literal writer."""
from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import (
    Post,
    PostEnrichmentState,
    PostTranslationArtifact,
    PostTranslationChunk,
)
from monitor.cycle import CycleRunner
from x_monitor import literal_translation, reattribute
from x_monitor.config import Config, LlmConfig
from x_monitor.provider_telemetry import ProviderTextResponse

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_post_fetch_passes_the_pinned_direct_gemma_route_to_translator_factory(
    monkeypatch,
):
    """M18 pin: the real post-fetch caller passes its loaded role config."""
    post = Post.objects.create(tweet_id="deepinfra-translator-wiring", text="hello")
    PostEnrichmentState.objects.create(
        post=post,
        classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )
    received = []
    monkeypatch.setattr(
        reattribute,
        "build_translator_client_from_env",
        lambda cfg: received.append(cfg.llm) or None,
    )
    cfg = Config(
        enabled_models=["deepseek"],
        daily_ceiling=100,
        llm=LlmConfig(
            translator_provider="deepinfra",
            translator_model="google/gemma-4-31B-it-turbo",
            translator_base_url="https://api.deepinfra.com/v1/openai",
            translator_deepinfra_request_profile="gemma4_translation_v1",
        ),
    )

    counters = CycleRunner(cfg=cfg)._run_post_fetch([], run_id="deepinfra-wiring")

    assert received == [cfg.llm]
    assert counters["n_translator_unavailable"] == 1


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
    counters = CycleRunner(cfg=cfg)._run_post_fetch([], run_id="plaintext-wiring")
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
        state = PostEnrichmentState.objects.get(post=post)
        assert state.translation_attempts == 1
        assert state.translation_diagnostics == {"ja": "provider_error"}
    else:
        assert artifact.state == PostTranslationArtifact.State.SUCCEEDED
        assert {value.locale: value.text for value in artifact.texts.all()} == {
            "en": source, "zh-cn": '  第一\n\n第二。\n', "ja": '  最初\n\n次。\n',
        }
        assert artifact.input_tokens == 14
        assert artifact.output_tokens == 18
        post.refresh_from_db()
        assert post.text_en == source
        assert post.commentary_en is None
        assert post.commentary_zh_cn is None
        assert counters["enrichment_state_facts"] == [
            {
                "post_id": post.pk,
                "lane": "carryover",
                "translation_status": PostEnrichmentState.Status.SUCCEEDED,
                "classification_status": PostEnrichmentState.Status.SUCCEEDED,
                "output_complete": True,
            }
        ]


def test_expired_literal_deadline_does_not_spend_attempt_or_create_artifact(monkeypatch):
    from x_monitor.config import EnrichmentAttemptDeadline, EnrichmentConfig

    post = Post.objects.create(tweet_id="literal-not-sent", text="A short update", lang="en")
    state = PostEnrichmentState.objects.create(
        post=post, classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )

    class NoCallClient:
        def messages_create_text(self, **_kwargs):
            raise AssertionError("provider must not be called")

    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda cfg: NoCallClient())
    monkeypatch.setattr(
        EnrichmentConfig, "start_attempt_deadline",
        lambda self, *, monotonic, budget_seconds=None: EnrichmentAttemptDeadline(
            deadline_at=monotonic(), request_timeout_seconds=self.request_timeout_seconds,
            monotonic=monotonic,
        ),
    )
    cfg = Config(enabled_models=["deepseek"], daily_ceiling=100, llm=LlmConfig(
        literal_translation_v2_enabled=True,
        translator_model="deepseek-v4-flash",
        translator_base_url="https://api.deepseek.com/anthropic",
    ))

    CycleRunner(cfg=cfg)._run_post_fetch([], run_id="literal-not-sent-run")

    state.refresh_from_db()
    assert state.translation_status == PostEnrichmentState.Status.PENDING
    assert state.translation_attempts == 0
    assert state.translation_first_attempt_at is None
    assert state.translation_error_code == "not_sent_deadline"
    assert state.translation_diagnostics == {
        "zh-Hans": "not_sent_deadline", "ja": "not_sent_deadline",
    }
    assert not PostTranslationArtifact.objects.filter(post=post).exists()


def test_exhausted_llm_call_budget_is_not_counted_as_provider_attempt(monkeypatch):
    post = Post.objects.create(tweet_id="literal-budget-not-sent", text="An update", lang="en")
    state = PostEnrichmentState.objects.create(
        post=post, classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )

    class NoCallClient:
        def messages_create_text(self, **_kwargs):
            raise AssertionError("provider must not be called")

    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda cfg: NoCallClient())
    cfg = Config(enabled_models=["deepseek"], daily_ceiling=100, llm=LlmConfig(
        literal_translation_v2_enabled=True,
        translator_model="deepseek-v4-flash",
        translator_base_url="https://api.deepseek.com/anthropic",
    ))

    CycleRunner(cfg=cfg, _max_llm_calls=0)._run_post_fetch([], run_id="literal-budget-run")

    state.refresh_from_db()
    assert state.translation_status == PostEnrichmentState.Status.PENDING
    assert state.translation_attempts == 0
    assert state.translation_error_code == "not_sent_call_budget"
    assert state.translation_diagnostics == {
        "zh-Hans": "not_sent_call_budget", "ja": "not_sent_call_budget",
    }
    assert not PostTranslationArtifact.objects.filter(post=post).exists()


def test_cycle_short_post_finishes_before_long_retry_and_reuses_saved_chunks(monkeypatch):
    from x_monitor.literal_translation import _split_translation_chunks

    long_source = ("alpha " * 800 + "\n\n") * 3
    long_post = Post.objects.create(tweet_id="long-cycle", text=long_source, lang="en")
    short_post = Post.objects.create(tweet_id="short-cycle", text="Small update", lang="en")
    for post in (long_post, short_post):
        PostEnrichmentState.objects.create(
            post=post, classification_status=PostEnrichmentState.Status.SUCCEEDED,
        )

    class RawClient:
        def __init__(self, fail_long_call=None):
            self.calls = []
            self.long_calls = 0
            self.fail_long_call = fail_long_call

        def messages_create_text(self, **kwargs):
            prompt = kwargs["messages"][0]["content"]
            self.calls.append(prompt)
            if "CHUNK:\n" in prompt:
                self.long_calls += 1
                if self.long_calls == self.fail_long_call:
                    raise TimeoutError("provider stalled")
                content = prompt.split("CHUNK:\n", 1)[1]
            else:
                content = prompt.split("SOURCE:\n", 1)[1]
            prefix = "日" if "Japanese (ja)" in prompt else "中"
            return ProviderTextResponse(prefix + content, {"input_tokens": 5, "output_tokens": 5})

    client = RawClient(fail_long_call=3)
    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda cfg: client)
    cfg = Config(enabled_models=["deepseek"], daily_ceiling=100, llm=LlmConfig(
        literal_translation_v2_enabled=True,
        translator_model="deepseek-v4-flash",
        translator_base_url="https://api.deepseek.com/anthropic",
    ))

    CycleRunner(cfg=cfg)._run_post_fetch([], run_id="long-first")

    short_state = PostEnrichmentState.objects.get(post=short_post)
    long_state = PostEnrichmentState.objects.get(post=long_post)
    assert short_state.translation_status == PostEnrichmentState.Status.SUCCEEDED
    assert long_state.translation_status == PostEnrichmentState.Status.PENDING
    assert long_state.translation_attempts == 0  # Valid chunks made progress.
    assert long_state.translation_error_code == "chunk_2:transport_timeout"
    assert long_state.translation_diagnostics["zh-Hans"] == "chunk_2:transport_timeout"
    assert "SOURCE:\nSmall update" in client.calls[0]
    assert "SOURCE:\nSmall update" in client.calls[1]
    saved_count = PostTranslationChunk.objects.filter(post=long_post).count()
    assert saved_count > 0

    resumed_client = RawClient()
    monkeypatch.setattr(reattribute, "build_translator_client_from_env", lambda cfg: resumed_client)
    CycleRunner(cfg=cfg)._run_post_fetch([], run_id="long-resume")

    long_state.refresh_from_db()
    assert long_state.translation_status == PostEnrichmentState.Status.SUCCEEDED
    assert PostTranslationChunk.objects.filter(post=long_post).count() == 2 * len(
        _split_translation_chunks(long_source)
    )
    assert len(resumed_client.calls) == 2 * len(_split_translation_chunks(long_source)) - saved_count
    artifact = PostTranslationArtifact.objects.get(post=long_post, is_current=True)
    assert artifact.state == PostTranslationArtifact.State.SUCCEEDED


def test_chunk_cache_rejects_changed_source_model_and_stale_claim():
    from monitor.post_artifacts import (
        load_literal_translation_chunks,
        persist_literal_translation_chunk,
    )
    from x_monitor.literal_translation import CHUNK_TRANSLATION_PROMPT_VERSION

    source = "a" * 5_100
    post = Post.objects.create(tweet_id="chunk-fence", text=source, lang="en")
    state = PostEnrichmentState.objects.create(
        post=post,
        claim_run_id="owner-1",
        claim_expires_at=timezone.now() + timedelta(minutes=5),
        classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )
    tweet = {"tweet_id": post.pk, "text": source}
    kwargs = {
        "tweet": tweet,
        "source_language": "en",
        "target_language": "zh-Hans",
        "chunk_index": 0,
        "source_chunk": "a" * 5_000,
        "translated_text": "译" * 5_000,
        "model": "model-a",
        "prompt_version": CHUNK_TRANSLATION_PROMPT_VERSION,
        "usage": {"input_tokens": 10, "output_tokens": 10},
        "expected_claim_run_id": "owner-1",
    }
    assert persist_literal_translation_chunk(**kwargs)
    assert load_literal_translation_chunks(
        [tweet], model="model-a", prompt_version=CHUNK_TRANSLATION_PROMPT_VERSION
    )[post.pk]["en"]["zh-Hans"][0] == "译" * 5_000
    assert load_literal_translation_chunks(
        [tweet], model="model-b", prompt_version=CHUNK_TRANSLATION_PROMPT_VERSION
    ) == {}

    Post.objects.filter(pk=post.pk).update(text="b" * 5_100)
    assert load_literal_translation_chunks(
        [{"tweet_id": post.pk, "text": "b" * 5_100}],
        model="model-a", prompt_version=CHUNK_TRANSLATION_PROMPT_VERSION,
    ) == {}
    assert not persist_literal_translation_chunk(**kwargs)

    state.claim_run_id = "owner-2"
    state.save(update_fields=["claim_run_id"])
    assert not persist_literal_translation_chunk(**kwargs)


def test_post_fetch_does_not_publish_literal_response_after_claim_is_reassigned(monkeypatch):
    """A response from an expired worker must not overwrite a new owner's output."""
    post = Post.objects.create(
        tweet_id="literal-claim-fence",
        text="source",
        lang="en",
        text_en="newer English",
        text_zh_cn="较新的中文",
    )
    state = PostEnrichmentState.objects.create(
        post=post,
        classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )

    def translate_then_reassign(tweets, client, **kwargs):
        PostEnrichmentState.objects.filter(pk=state.pk).update(
            claim_owner="harvester:new-run",
            claim_run_id="new-run",
            claim_expires_at=timezone.now() + timedelta(minutes=5),
        )
        return [
            {
                "tweet_id": tweet["tweet_id"],
                "lang_detected": "en",
                "text_en": "source",
                "text_zh_cn": "过时的中文",
                "text_ja": "古い日本語",
            }
            for tweet in tweets
        ]

    monkeypatch.setattr(
        reattribute, "build_translator_client_from_env", lambda cfg: object()
    )
    monkeypatch.setattr(
        literal_translation,
        "translate_batch_literal_plaintext",
        translate_then_reassign,
    )
    cfg = Config(
        enabled_models=["deepseek"],
        daily_ceiling=100,
        llm=LlmConfig(
            literal_translation_v2_enabled=True,
            translator_model="deepseek-v4-flash",
            translator_base_url="https://api.deepseek.com/anthropic",
        ),
    )

    CycleRunner(cfg=cfg)._run_post_fetch([], run_id="old-run")

    state.refresh_from_db()
    post.refresh_from_db()
    assert state.claim_run_id == "new-run"
    assert state.translation_status == PostEnrichmentState.Status.PENDING
    assert post.text_en == "newer English"
    assert post.text_zh_cn == "较新的中文"
    assert not PostTranslationArtifact.objects.filter(post=post).exists()


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
