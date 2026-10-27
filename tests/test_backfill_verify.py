"""Same captured source through normal and historical shared publishers."""

import copy
from datetime import UTC

import pytest
from django.db import transaction

from core.models import (
    CollectionObservation,
    CollectionRun,
    Post,
    PostBrandMention,
    PostTranslationText,
)
from core.provider_batches import record_post_membership
from monitor.cycle import CycleRunner, _build_brand_index, _load_brand_search_terms
from scripts.backfill_verify import semantic_snapshot, verify_posts
from tests.test_backfill_direct_enrichment import DirectProvider, run_direct
from tests.test_backfill_native_enrichment import native as native_fixture
from x_monitor.deepinfra import DeepInfraChatCompletionsClient
from x_monitor.x_client import _normalize_tweet

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
native = native_fixture


def ingest(cfg, identifiers):
    items = [
        _normalize_tweet(
            {
                "id": identifier,
                "text": "I tried Qwen today.",
                "lang": "en",
                "createdAt": "Sun Aug 09 00:10:00 +0000 2026",
                "author": {
                    "id": "parity-author",
                    "userName": "parity_user",
                    "name": "Parity User",
                    "description": "Independent builder",
                },
                "likeCount": 3,
                "replyCount": 2,
                "retweetCount": 1,
                "conversationId": "parity-conversation",
                "isReply": True,
                "url": "https://x.com/parity_user/status/" + identifier,
            }
        )
        for identifier in identifiers
    ]
    runner = CycleRunner(cfg=cfg)
    runner._attribute_items(
        items, _build_brand_index(cfg.enabled_models), _load_brand_search_terms()
    )
    result = runner._persist_items(copy.deepcopy(items))
    assert result == (len(identifiers), 0, len(identifiers), 0)
    return items


@pytest.fixture
def accepted(native):
    job, cfg, _delegates, _ = native
    ids = ["native-1", "native-2"]
    CollectionObservation.objects.all().delete()
    Post.objects.all().delete()
    ingest(cfg, ids)
    with transaction.atomic():
        record_post_membership(CollectionRun.objects.get(job=job), None, ids)
    provider = DirectProvider()
    for turn in range(15):
        result = run_direct(native, provider, initial=turn == 0)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed", result
    return ids, cfg


@pytest.mark.parametrize("context_missing", [False, True])
def test_normal_and_backfill_persist_identical_consumer_data(
    native, monkeypatch, context_missing
):
    if context_missing:
        from tests.test_u18_runtime_0731 import FixedSlotTransport

        original = FixedSlotTransport.messages_create

        def missing_context(self, **kwargs):
            response = original(self, **kwargs)
            if "CONTENT ROLE:" in kwargs["system"]:
                response["decisions"] = {
                    slot: {
                        "outcome": "context_missing",
                        "post_types": [],
                        "audience_topics": ["unavailable"],
                    }
                    for slot in response["decisions"]
                }
            return response

        monkeypatch.setattr(FixedSlotTransport, "messages_create", missing_context)
    _, cfg, _, _ = native
    CollectionObservation.objects.all().delete()
    Post.objects.all().delete()
    ids = ["native-1", "native-2"]
    items = ingest(cfg, ids)
    provider = DirectProvider()
    clients = {
        role: DeepInfraChatCompletionsClient(
            api_key="test",
            model=model,
            request_profile=profile,
            transport=provider.transport,
        )
        for role, model, profile in [
            ("translation", cfg.llm.translator_model, "gemma4_translation_v1"),
            ("classification", cfg.llm.classifier_model, "deepseek_0731"),
        ]
    }
    runner = CycleRunner(cfg=cfg, _post_fetch_clients=clients)
    runner._run_post_fetch(items, run_id="normal-parity", post_ids=set(ids))
    assert verify_posts(ids, cfg=cfg)["errors"] == {}
    expected = {i: semantic_snapshot(i) for i in ids}
    Post.objects.all().delete()
    ingest(cfg, ids)
    job = native[0]
    with transaction.atomic():
        record_post_membership(CollectionRun.objects.get(job=job), None, ids)
    provider = DirectProvider()
    for turn in range(15):
        result = run_direct(native, provider, initial=turn == 0)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed", result
    assert verify_posts(ids, cfg=cfg)["errors"] == {}
    assert {i: semantic_snapshot(i) for i in ids} == expected


def test_verifier_accepts_all_valid_members(accepted):
    ids, cfg = accepted
    assert verify_posts(ids, cfg=cfg) == {"checked": 2, "valid": 2, "errors": {}}


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("missing_post", "post_missing"),
        ("missing_text", "source_text_missing"),
        ("missing_author", "x_author_missing"),
        ("missing_mention", "brand_mention_missing"),
        ("missing_locale", "canonical_translation_invalid"),
        ("false_success", "canonical_translation_invalid"),
        ("wrong_time", "outside_frozen_window"),
    ],
)
def test_verifier_rejects_broken_persisted_data(accepted, mutation, expected):
    from datetime import datetime

    ids, cfg = accepted
    target = ids[0]
    if mutation == "missing_post":
        CollectionObservation.objects.filter(post_id=target).delete()
        Post.objects.filter(pk=target).delete()
    elif mutation == "missing_text":
        Post.objects.filter(pk=target).update(text="")
    elif mutation == "missing_author":
        Post.objects.filter(pk=target).update(author=None)
    elif mutation == "missing_mention":
        PostBrandMention.objects.filter(post_id=target).delete()
    elif mutation == "missing_locale":
        PostTranslationText.objects.filter(
            artifact__post_id=target, locale="ja"
        ).delete()
    elif mutation == "false_success":
        Post.objects.get(pk=target).translation_artifacts.update(is_current=False)
    elif mutation == "wrong_time":
        Post.objects.filter(pk=target).update(
            created_at=datetime(2026, 9, 1, tzinfo=UTC)
        )
    result = verify_posts(ids, cfg=cfg, since_epoch=1786233600, until_epoch=1786234500)
    assert expected in result["errors"][target]


def test_collection_accepts_source_before_ordinary_enrichment(native):
    _job, cfg, _, _ = native
    CollectionObservation.objects.all().delete()
    Post.objects.all().delete()
    ids = ["collected-only"]
    ingest(cfg, ids)
    assert verify_posts(ids, cfg=cfg, collection_only=True)["errors"] == {}
    assert "durable_enrichment_incomplete" in verify_posts(ids, cfg=cfg)["errors"][ids[0]]


@pytest.mark.parametrize("broken", [None, "cursor", "membership", "rare"])
def test_collection_window_accepts_only_complete_durable_zero_results(native, broken):
    from django.utils import timezone

    from core.models import CollectionScopeRun
    from scripts.backfill_verify import verify_collection_window

    job, cfg, _, _ = native
    run = CollectionRun.objects.get(job=job)
    CollectionObservation.objects.all().delete()
    run.status = "success"
    run.completed_at = timezone.now()
    run.execution_state, run.coverage_state = "completed", "complete"
    run.save(update_fields=["status", "completed_at", "execution_state", "coverage_state"])
    job.state, job.last_success = "completed", run
    job.save(update_fields=["state", "last_success"])
    unit = job.scope["units"][0]
    envelope = {"collection_drained": True, "post_ids": [], "received_post_ids": [], "raw_count": 0}
    if broken == "membership":
        envelope["post_ids"] = ["missing-member"]
    if broken == "rare":
        envelope["rare_hit_ids"] = [999999999]
    scoped = CollectionScopeRun.objects.create(
        run=run, scope_kind=unit["scope_kind"], scope_key=unit["scope_key"],
        enumeration_complete=broken != "cursor",
        outcome="pending" if broken == "cursor" else "complete",
        execution_state="yielded" if broken == "cursor" else "completed",
        coverage_state="partial" if broken == "cursor" else "complete",
    )
    from core.collection_pages import project_page_receipts

    if broken in {"membership", "rare"}:
        # Typed receipt writers reject dangling references before publication.
        with pytest.raises(ValueError, match="page .*missing"), transaction.atomic():
            project_page_receipts(scoped, [envelope])
    else:
        project_page_receipts(scoped, [envelope])
    if broken:
        with pytest.raises(ValueError, match="collection_"):
            verify_collection_window(job.pk, cfg=cfg)
    else:
        result = verify_collection_window(job.pk, cfg=cfg)
        assert result["status"] == "verified"
        assert result["checked_posts"] == 0 and result["zero_results"]
