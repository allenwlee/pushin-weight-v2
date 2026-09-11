from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import (
    Post,
    PostEnrichmentState,
    PostSynthesisArtifact,
    PostSynthesisDailyBudget,
    PostSynthesisDemand,
    PostTranslationArtifact,
)
from monitor.post_artifacts import (
    publish_literal_translation,
    publish_post_synthesis,
    read_post_content_many,
    record_literal_translation_failure,
    source_content_fingerprint,
)
from monitor.post_synthesis import (
    claim_synthesis_demands,
    process_synthesis_batch,
    publish_claimed_synthesis,
    request_post_synthesis,
)
from x_monitor.config import SynthesisConfig
from x_monitor.provider_telemetry import ProviderResponse
from x_monitor.synthesis import SynthesisResponse

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _config(**overrides) -> SynthesisConfig:
    values = {
        "activation_state": "owner_override",
        "provider_calls_enabled": True,
        "control_revision": "test-v1",
    }
    values.update(overrides)
    return SynthesisConfig(**values)


def _literal_row(post: Post) -> dict[str, object]:
    return {
        "tweet_id": post.pk,
        "lang_detected": "ja",
        "text_en": "The model is now available.",
        "text_zh_cn": "该模型现已发布。",
        "text_ja": post.text,
    }


def _synthesis_values(suffix: str = "") -> dict[str, str]:
    return {
        "en": f"The author announces availability and signals a product milestone{suffix}.",
        "zh-cn": f"作者宣布产品可用，表明项目达到新的里程碑{suffix}。",
        "ja": f"著者は提供開始を発表し、製品の節目を示しています{suffix}。",
    }


def test_japanese_literal_and_synthesis_publish_as_independent_artifacts():
    post = Post.objects.create(tweet_id="ja-1", text="モデルを公開しました。")
    state = PostEnrichmentState.objects.create(
        post=post,
        classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )
    literal = publish_literal_translation(
        post=post,
        row=_literal_row(post),
        expected_source_fingerprint=source_content_fingerprint(post),
        prompt_version="literal-v1",
        model="deepseek-v4-flash",
        input_tokens=30,
        output_tokens=20,
    )

    assert literal is not None
    assert literal.state == PostTranslationArtifact.State.SUCCEEDED
    assert {row.locale: row.text for row in literal.texts.all()} == {
        "en": "The model is now available.",
        "zh-cn": "该模型现已发布。",
        "ja": "モデルを公開しました。",
    }
    state.refresh_from_db()
    assert state.classification_status == PostEnrichmentState.Status.SUCCEEDED

    synthesis = publish_post_synthesis(
        post=post,
        values=_synthesis_values(),
        context_fingerprint="a" * 64,
        prompt_version="synthesis-v1",
        model="deepseek-v4-flash",
        output_schema_version=1,
    )
    projection = read_post_content_many([post])[post.pk]

    assert synthesis is not None
    assert set(projection.literal) == {"en", "zh-cn", "ja"}
    assert set(projection.synthesis) == {"en", "zh-cn", "ja"}
    assert projection.synthesis_status == "ready"
    assert projection.literal_source == "normalized"
    assert projection.synthesis_source == "normalized"
    assert PostTranslationArtifact.objects.count() == 1


def test_literal_publication_rejects_output_for_obsolete_source():
    post = Post.objects.create(tweet_id="stale-literal", text="old source")
    expected = source_content_fingerprint(post)
    Post.objects.filter(pk=post.pk).update(text="new source")

    artifact = publish_literal_translation(
        post=post,
        row={
            "tweet_id": post.pk,
            "lang_detected": "en",
            "text_en": "old source",
            "text_zh_cn": "旧来源",
            "text_ja": "古い情報源",
        },
        expected_source_fingerprint=expected,
        prompt_version="literal-v1",
        model="deepseek-v4-flash",
    )

    assert artifact is None
    assert not PostTranslationArtifact.objects.exists()


def test_literal_identity_includes_the_detected_source_language():
    post = Post.objects.create(tweet_id="language-identity", text="AI model")
    fingerprint = source_content_fingerprint(post)
    common = {
        "post": post,
        "expected_source_fingerprint": fingerprint,
        "prompt_version": "literal-v1",
        "model": "deepseek-v4-flash",
    }

    first = publish_literal_translation(
        row={
            "tweet_id": post.pk,
            "lang_detected": "en",
            "text_en": post.text,
            "text_zh_cn": "人工智能模型",
            "text_ja": "AIモデル",
        },
        **common,
    )
    second = publish_literal_translation(
        row={
            "tweet_id": post.pk,
            "lang_detected": "ja",
            "text_en": "AI model",
            "text_zh_cn": "人工智能模型",
            "text_ja": post.text,
        },
        **common,
    )

    assert first is not None and second is not None
    assert first.pk != second.pk
    assert PostTranslationArtifact.objects.count() == 2
    assert PostTranslationArtifact.objects.get(is_current=True).source_language == "ja"


def test_literal_failure_is_auditable_without_replacing_last_good():
    post = Post.objects.create(tweet_id="literal-failure", text="Source")
    fingerprint = source_content_fingerprint(post)
    succeeded = publish_literal_translation(
        post=post,
        row={
            "tweet_id": post.pk,
            "lang_detected": "en",
            "text_en": "Source",
            "text_zh_cn": "来源",
            "text_ja": "原文",
        },
        expected_source_fingerprint=fingerprint,
        prompt_version="literal-v1",
        model="deepseek-v4-flash",
    )
    failed = record_literal_translation_failure(
        post=post,
        expected_source_fingerprint=fingerprint,
        source_language="ja",
        prompt_version="literal-v1",
        model="deepseek-v4-flash",
        error_code="translation_incomplete",
    )

    assert succeeded is not None and failed is not None
    assert failed.state == PostTranslationArtifact.State.FAILED
    assert failed.error_code == "translation_incomplete"
    assert PostTranslationArtifact.objects.get(is_current=True).pk == succeeded.pk


def test_synthesis_rejects_commentary_that_copies_normalized_japanese_literal():
    post = Post.objects.create(tweet_id="copy-ja", text="English source")
    publish_literal_translation(
        post=post,
        row={
            "tweet_id": post.pk,
            "lang_detected": "en",
            "text_en": "English source",
            "text_zh_cn": "英语来源",
            "text_ja": "英語の原文",
        },
        expected_source_fingerprint=source_content_fingerprint(post),
        prompt_version="literal-v1",
        model="deepseek-v4-flash",
    )
    values = _synthesis_values()
    values["ja"] = "英語の原文"

    assert publish_post_synthesis(
        post=post,
        values=values,
        context_fingerprint="b" * 64,
        prompt_version="synthesis-v1",
        model="deepseek-v4-flash",
        output_schema_version=1,
    ) is None
    assert not PostSynthesisArtifact.objects.exists()


def test_repeated_demand_coalesces_and_upgrades_priority():
    post = Post.objects.create(tweet_id="demand-1", text="A post")
    config = _config()

    first = request_post_synthesis(
        post_ids=[post.pk], reason="lookahead", config=config
    )[0]
    second = request_post_synthesis(
        post_ids=[post.pk], reason="expanded", config=config
    )[0]

    assert first.pk == second.pk
    assert PostSynthesisDemand.objects.count() == 1
    second.refresh_from_db()
    assert second.reason == PostSynthesisDemand.Reason.EXPANDED
    assert second.priority == 80
    assert second.request_count == 2


def test_claim_reserves_daily_budget_and_hard_stops_at_request_cap():
    posts = [
        Post.objects.create(tweet_id=f"budget-{index}", text=f"post {index}")
        for index in range(2)
    ]
    config = _config(daily_request_cap=1)
    request_post_synthesis(
        post_ids=[post.pk for post in posts], reason="visible", config=config
    )

    claimed = claim_synthesis_demands(config=config, owner="worker-1")
    second_claim = claim_synthesis_demands(config=config, owner="worker-2")
    budget = PostSynthesisDailyBudget.objects.get()

    assert len(claimed) == 1
    assert second_claim == []
    assert budget.reserved_requests == 1
    assert budget.reserved_input_tokens == config.max_input_tokens_per_post
    assert budget.reserved_output_tokens == config.max_output_tokens_per_post


def test_two_workers_claim_disjoint_rows():
    posts = [
        Post.objects.create(tweet_id=f"worker-claim-{index}", text=f"post {index}")
        for index in range(2)
    ]
    config = _config(batch_size=1)
    request_post_synthesis(
        post_ids=[post.pk for post in posts], reason="visible", config=config
    )

    first = claim_synthesis_demands(config=config, owner="worker-1")
    second = claim_synthesis_demands(config=config, owner="worker-2")

    assert len(first) == len(second) == 1
    assert first[0].pk != second[0].pk
    assert first[0].lease_owner == "worker-1"
    assert second[0].lease_owner == "worker-2"


def test_abandoned_lease_is_reclaimed_and_old_fence_cannot_publish():
    post = Post.objects.create(tweet_id="lease-recovery", text="post")
    now = timezone.now()
    config = _config(batch_size=1, lease_seconds=30)
    request_post_synthesis(
        post_ids=[post.pk], reason="operator", config=config, now=now
    )
    first = claim_synthesis_demands(config=config, owner="worker-1", now=now)[0]
    reclaimed = claim_synthesis_demands(
        config=config,
        owner="worker-2",
        now=now + timedelta(seconds=config.lease_seconds + 1),
    )[0]
    response = SynthesisResponse(
        texts=_synthesis_values(), input_tokens=1, output_tokens=1, latency_ms=1
    )

    stale = publish_claimed_synthesis(
        demand_id=first.pk,
        owner="worker-1",
        fence=first.lease_fence,
        response=response,
        config=config,
        now=now + timedelta(seconds=config.lease_seconds + 2),
    )

    assert reclaimed.pk == first.pk
    assert reclaimed.lease_owner == "worker-2"
    assert reclaimed.lease_fence == first.lease_fence + 1
    assert stale is None
    assert not PostSynthesisArtifact.objects.filter(state="succeeded").exists()


class _SynthesisClient:
    _base_url = "https://api.deepseek.com/anthropic"

    def __init__(self):
        self.calls: list[dict] = []

    def messages_create(self, **kwargs):
        self.calls.append(kwargs)
        return ProviderResponse(
            {
                "post_id": "worker-1",
                "commentary_en": _synthesis_values()["en"],
                "commentary_zh_cn": _synthesis_values()["zh-cn"],
                "commentary_ja": _synthesis_values()["ja"],
            },
            usage={"input_tokens": 42, "output_tokens": 24},
        )


class _FailingSynthesisClient:
    _base_url = "https://api.deepseek.com/anthropic"

    def messages_create(self, **_kwargs):
        raise TimeoutError("provider unavailable")


def test_worker_publishes_locale_complete_artifact_and_observed_usage():
    post = Post.objects.create(tweet_id="worker-1", text="A release is available")
    config = _config()
    request_post_synthesis(post_ids=[post.pk], reason="visible", config=config)
    client = _SynthesisClient()

    result = process_synthesis_batch(config=config, client=client, owner="worker")
    demand = PostSynthesisDemand.objects.get()
    budget = PostSynthesisDailyBudget.objects.get()

    assert result == {
        "status": "processed",
        "claimed": 1,
        "succeeded": 1,
        "failed": 0,
        "cancelled": 0,
    }
    assert demand.state == PostSynthesisDemand.State.SUCCEEDED
    assert demand.artifact_id is not None
    assert budget.observed_input_tokens == 42
    assert budget.observed_output_tokens == 24
    assert client.calls[0]["model"] == "deepseek-v4-flash"
    assert client.calls[0]["thinking"] == {"type": "disabled"}


def test_worker_failure_persists_artifact_state_and_keeps_demand_retryable():
    post = Post.objects.create(tweet_id="worker-failure", text="A release")
    config = _config()
    request_post_synthesis(post_ids=[post.pk], reason="visible", config=config)

    result = process_synthesis_batch(
        config=config, client=_FailingSynthesisClient(), owner="worker"
    )
    demand = PostSynthesisDemand.objects.get()
    artifact = PostSynthesisArtifact.objects.get()

    assert result["failed"] == 1
    assert demand.state == PostSynthesisDemand.State.PENDING
    assert artifact.state == PostSynthesisArtifact.State.FAILED
    assert artifact.attempts == 1
    assert artifact.error_code == "TimeoutError"
    assert artifact.is_current is False


def test_expired_visible_demand_is_cancelled_without_provider_call():
    post = Post.objects.create(tweet_id="expired-1", text="A post")
    config = _config()
    now = timezone.now()
    demand = request_post_synthesis(
        post_ids=[post.pk], reason="visible", config=config, now=now
    )[0]
    PostSynthesisDemand.objects.filter(pk=demand.pk).update(
        expires_at=now - timedelta(seconds=1)
    )
    client = _SynthesisClient()

    result = process_synthesis_batch(
        config=config, client=client, owner="worker", now=now
    )
    demand.refresh_from_db()

    assert result["claimed"] == 0
    assert demand.state == PostSynthesisDemand.State.CANCELLED
    assert client.calls == []
