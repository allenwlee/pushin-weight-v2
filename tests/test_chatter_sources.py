"""Chatter keeps physical receipts and exact source projections without raw archives."""

from unittest.mock import Mock, patch

import pytest

from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
from x_monitor.x_client import XClient


def test_full_by_id_lookup_and_metrics_share_the_existing_endpoint_and_normalizer():
    client = XClient(api_key="fixture-only", max_retries=0)
    response = Mock(status_code=200)
    response.json.return_value = {
        "tweets": [
            {
                "id": "123",
                "text": "An attributed source.",
                "createdAt": "Wed Nov 04 00:00:00 +0000 2026",
                "likeCount": 12,
                "author": {"id": "42", "userName": "reporter"},
            }
        ]
    }
    response.content = b'{"tweets":[]}'
    with patch("x_monitor.x_client.requests.get", return_value=response) as get:
        posts = client.get_posts_by_ids(["123"])
        assert posts["123"]["text"] == "An attributed source."
        assert posts["123"]["author_handle"] == "reporter"
        assert client.get_tweets_by_ids(["123"]) == {"123": {"like_count": 12}}
        assert get.call_count == 2
        assert get.call_args.kwargs["params"] == {"tweet_ids": "123"}


@pytest.mark.django_db
@pytest.mark.requires_postgres
def test_source_session_records_one_request_and_no_raw_response_or_profile(monkeypatch):
    from django.utils import timezone

    from core.models import (
        CollectionEvidenceArchive,
        CollectionObservation,
        CollectionRequest,
        OriginalContentCall,
        Post,
    )
    from monitor.editorial.chatter_sources import SourceSession
    from tests.test_chatter_accounting import policy
    from tests.test_original_content_consideration import consideration

    run = consideration().run
    cfg = policy(20)
    cfg.chatter = cfg.chatter.model_copy(update={"source_request_limit": 4})
    # The model reservation identifies the shared validation ledger before source calls.
    OriginalContentCall.objects.create(
        run=run,
        workflow_key="chatter-discovery",
        stage="discovery",
        request_identity="source-test",
        request_hash="a" * 64,
        request_packet={"fixture": True},
        reserved_at=timezone.now(),
        budget_scope="chatter-test",
        reserved_usd=1,
    )
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "fixture-only")
    session = SourceSession(run, cfg, purpose=TwitterApiCredentialPurpose.ON_DEMAND)
    post = Post.objects.create(
        tweet_id="123", text="source", created_at=run.facts_as_of, like_count=100
    )
    token = session.start("/twitter/tweets", {"tweet_ids": "123"})
    session.finish(
        token,
        {
            "outcome": "received",
            "status_code": 200,
            "body": b'{"tweets":[{"id":"123","text":"source","author":{"description":"unused-large-profile"}}]}',
        },
    )
    request = CollectionRequest.objects.get(pk=token.pk)
    assert request.reserved_usd > 0 and request.estimated_usd > 0
    assert request.archive_id is None and request.response_sha256
    assert not CollectionEvidenceArchive.objects.exists()
    appearance = CollectionObservation.objects.get(request=request)
    assert appearance.source_identifier == "123" and appearance.receipt_ordinal == 0
    session.ingest(
        [
            {
                "id": "123",
                "text": "source",
                "created_at": run.facts_as_of.isoformat(),
                "like_count": 0,
            }
        ]
    )
    post.refresh_from_db()
    assert (
        post.like_count == 100
    )  # A missing wire counter must not overwrite a saved measurement.
    session.close(success=True)


@pytest.mark.django_db
@pytest.mark.requires_postgres
def test_abandoned_validation_source_run_keeps_its_original_content_owner(monkeypatch):
    from core.models import CollectionRun
    from monitor.editorial.chatter_sources import SourceSession
    from tests.test_chatter_accounting import policy
    from tests.test_original_content_consideration import consideration

    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "fixture-only")
    first, second = consideration().run, consideration().run
    cfg = policy(20)
    abandoned = SourceSession(first, cfg, purpose=TwitterApiCredentialPurpose.ON_DEMAND)
    next_cycle = SourceSession(
        second, cfg, purpose=TwitterApiCredentialPurpose.ON_DEMAND
    )
    assert abandoned.claim.run_id != next_cycle.claim.run_id
    assert (
        CollectionRun.objects.get(pk=abandoned.claim.run_id).content_run_id == first.pk
    )
    next_cycle.close(success=False)
    abandoned.close(success=False)
