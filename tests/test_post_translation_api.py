from __future__ import annotations

import json

import pytest
from django.test import Client, override_settings

from core.models import Post, PostEnrichmentState, PostSynthesisRateLimitBucket

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _request(client, post_id, *, poll_only=False):
    return client.post(
        "/api/v2/post-translation-demands/",
        data=json.dumps({"post_ids": [post_id], "poll_only": poll_only}),
        content_type="application/json",
        secure=True,
    )


def test_poll_does_not_request_and_explicit_request_is_coalesced():
    post = Post.objects.create(tweet_id="translate-api-1", text="Bonjour")
    client = Client()
    assert _request(client, post.pk, poll_only=True).json()["results"][0]["status"] == "not_requested"
    assert not PostEnrichmentState.objects.filter(post=post).exists()
    assert _request(client, post.pk).json()["results"][0]["status"] == "pending"
    assert _request(client, post.pk).json()["results"][0]["status"] == "pending"
    state = PostEnrichmentState.objects.get(post=post)
    assert state.translation_requested and state.translation_attempts == 0


def test_unknown_post_rejected_without_creating_work():
    assert _request(Client(), "unknown-post").status_code == 404
    assert not PostEnrichmentState.objects.exists()


def test_public_translation_request_requires_csrf():
    post = Post.objects.create(tweet_id="csrf-post", text="Bonjour")
    client = Client(enforce_csrf_checks=True)
    assert _request(client, post.pk).status_code == 403
    client.get("/?locale=en", secure=True)
    response = client.post(
        "/api/v2/post-translation-demands/",
        data=json.dumps({"post_ids": [post.pk]}), content_type="application/json", secure=True,
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        HTTP_REFERER="https://testserver/?locale=en",
    )
    assert response.status_code == 200
    assert PostEnrichmentState.objects.get(post=post).translation_requested


def test_cached_legacy_translation_does_not_use_capacity():
    post = Post.objects.create(tweet_id="cached-post", text="Bonjour", text_en="Hello")
    assert _request(Client(), post.pk).json()["results"][0]["status"] == "ready"
    assert not PostEnrichmentState.objects.filter(post=post).exists()


def test_completed_legacy_result_missing_requested_locale_is_not_ready():
    post = Post.objects.create(tweet_id="legacy-missing-ja", text="Bonjour", text_en="Hello")
    PostEnrichmentState.objects.create(post=post, translation_requested=True, translation_status="succeeded")
    response = Client().post(
        "/api/v2/post-translation-demands/",
        data=json.dumps({"post_ids": [post.pk], "poll_only": True, "locale": "ja"}),
        content_type="application/json", secure=True,
    )
    assert response.json()["results"][0]["status"] == "failed"


@override_settings(POST_TRANSLATION_DAILY_REQUEST_LIMIT=1)
def test_daily_quota_is_shared_but_duplicate_and_poll_do_not_consume_it():
    first = Post.objects.create(tweet_id="translation-quota-1", text="Bonjour")
    second = Post.objects.create(tweet_id="translation-quota-2", text="Salut")
    client = Client()
    assert _request(client, first.pk).status_code == 200
    assert _request(client, first.pk).status_code == 200
    assert _request(client, second.pk, poll_only=True).status_code == 200
    assert _request(client, second.pk).status_code == 429
    assert not PostEnrichmentState.objects.filter(post=second).exists()
    assert PostSynthesisRateLimitBucket.objects.filter(count=1).exists()


def test_completed_translation_race_returns_ready_without_spending_capacity(monkeypatch):
    from monitor import post_artifacts

    post = Post.objects.create(tweet_id="completion-race", text="元の文章")
    PostEnrichmentState.objects.create(post=post, translation_requested=True, classification_status="succeeded")
    original = post_artifacts.read_post_content_many
    first = True

    def publish_after_initial_read(posts):
        nonlocal first
        result = original(posts)
        if first:
            first = False
            post_artifacts.publish_literal_translation(
                post=post, row={"lang_detected": "ja", "text_en": "Original text", "text_zh_cn": "原文", "text_ja": post.text},
                expected_source_fingerprint=post_artifacts.source_content_fingerprint(post),
                prompt_version="race", model="race",
            )
            PostEnrichmentState.objects.filter(pk=post.pk).update(translation_status="succeeded")
        return result

    monkeypatch.setattr(post_artifacts, "read_post_content_many", publish_after_initial_read)
    response = _request(Client(), post.pk)
    assert response.json()["results"][0]["status"] == "ready"
    assert response.json()["results"][0]["literal"]["en"] == "Original text"
    assert not PostSynthesisRateLimitBucket.objects.filter(count__gt=1).exists()
