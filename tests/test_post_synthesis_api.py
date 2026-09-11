from __future__ import annotations

import json
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, RequestFactory

from core.models import Post, PostSynthesisDemand, PostSynthesisRateLimitBucket
from monitor.views import _accept_synthesis_rate

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _user():
    return get_user_model().objects.create_user(
        username="synthesis-owner", email="owner@example.com", password="test"
    )


def test_synthesis_demand_api_requires_authentication_and_csrf():
    post = Post.objects.create(tweet_id="api-auth", text="Post")
    anonymous = Client().post(
        "/api/v2/post-synthesis-demands/",
        data=json.dumps({"post_ids": [post.pk], "reason": "visible"}),
        content_type="application/json",
        secure=True,
    )
    assert anonymous.status_code == 302

    client = Client(enforce_csrf_checks=True)
    client.force_login(_user())
    rejected = client.post(
        "/api/v2/post-synthesis-demands/",
        data=json.dumps({"post_ids": [post.pk], "reason": "visible"}),
        content_type="application/json",
        secure=True,
    )
    assert rejected.status_code == 403


def test_synthesis_demand_api_creates_once_and_poll_only_does_not_mutate():
    user = _user()
    post = Post.objects.create(tweet_id="api-demand", text="Post")
    client = Client()
    client.force_login(user)

    created = client.post(
        "/api/v2/post-synthesis-demands/",
        data=json.dumps({"post_ids": [post.pk], "reason": "visible"}),
        content_type="application/json",
        secure=True,
    )
    polled = client.post(
        "/api/v2/post-synthesis-demands/",
        data=json.dumps(
            {"post_ids": [post.pk], "reason": "visible", "poll_only": True}
        ),
        content_type="application/json",
        secure=True,
    )

    assert created.status_code == 200
    assert created.json()["results"][0]["status"] == "pending"
    assert polled.status_code == 200
    assert PostSynthesisDemand.objects.get().request_count == 1


def test_synthesis_demand_api_rejects_unknown_post_and_oversized_batch():
    client = Client()
    client.force_login(_user())

    unknown = client.post(
        "/api/v2/post-synthesis-demands/",
        data=json.dumps({"post_ids": ["missing"], "reason": "visible"}),
        content_type="application/json",
        secure=True,
    )
    oversized = client.post(
        "/api/v2/post-synthesis-demands/",
        data=json.dumps(
            {"post_ids": [f"post-{index}" for index in range(21)], "reason": "visible"}
        ),
        content_type="application/json",
        secure=True,
    )

    assert unknown.status_code == 404
    assert oversized.status_code == 400
    assert not PostSynthesisDemand.objects.exists()


def test_database_rate_limit_is_atomic_per_identity_bucket():
    user = _user()
    request = RequestFactory().post("/api/v2/post-synthesis-demands/")
    request.user = user
    request.META["REMOTE_ADDR"] = "127.0.0.1"

    assert _accept_synthesis_rate(request, cost=119)
    assert _accept_synthesis_rate(request, cost=1)
    assert not _accept_synthesis_rate(request, cost=1)
    assert sorted(PostSynthesisRateLimitBucket.objects.values_list("count", flat=True)) == [
        120,
        120,
    ]


def test_management_command_uses_the_shared_demand_and_poll_shape():
    post = Post.objects.create(tweet_id="command-demand", text="Post")
    created_out = StringIO()
    call_command(
        "request_post_synthesis", post.pk, "--json", stdout=created_out
    )
    polled_out = StringIO()
    call_command(
        "request_post_synthesis",
        post.pk,
        "--poll-only",
        "--json",
        stdout=polled_out,
    )

    created = json.loads(created_out.getvalue())
    polled = json.loads(polled_out.getvalue())
    demand = PostSynthesisDemand.objects.get()

    assert created == polled
    assert created["results"][0]["post_id"] == post.pk
    assert created["results"][0]["status"] == "pending"
    assert demand.reason == PostSynthesisDemand.Reason.OPERATOR
    assert demand.request_count == 1


def test_management_command_rejects_unknown_post_without_demand():
    with pytest.raises(CommandError, match="unknown post IDs"):
        call_command("request_post_synthesis", "missing")
    assert not PostSynthesisDemand.objects.exists()
