"""Lossless history import without network, invented posts or duplicate charges."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.models import (
    EditorialAssessment,
    EditorialBudget,
    EditorialCall,
    OriginalContent,
    OriginalContentCall,
    OriginalContentRun,
    OriginalContentText,
    Post,
)
from monitor.original_content_backfill import backfill_original_content
from tests.test_editorial_views import edition

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_read_only_then_replayed_import_preserve_ids_text_sources_and_uncertainty():
    post = Post.objects.create(tweet_id="1", text="current changed source")
    saved = edition()
    EditorialCall.objects.create(
        assessment=saved.assessment,
        stage="media:picture-1",
        kind="media",
        state="ambiguous",
        reserved_usd="0.100000",
        budget_day=timezone.now().date(),
    )
    EditorialBudget.objects.create(
        day=timezone.now().date(), reserved_usd="0.100000", calls=1, media_calls=1
    )
    report = backfill_original_content(apply=False)
    assert report["ready"] and not OriginalContent.objects.exists()
    assert not OriginalContentRun.objects.exists()
    report = backfill_original_content(apply=True)
    assert report["ready"]
    text = OriginalContentText.objects.get(public_id=saved.pk)
    assert text.headline == saved.headline and text.body == saved.article
    assert text.narrative.story_id == saved.story_id
    assert text.sources.get().post_id == post.pk
    assert text.sources.get().source_hash is not None
    assert text.producing_call_id is None  # Unknown legacy producer is honest.
    call = OriginalContentCall.objects.get()
    assert call.state == "ambiguous" and call.legacy_import
    assert call.completed_at is None and call.request_hash is None
    assert backfill_original_content(apply=True)["ready"]
    assert (
        OriginalContentText.objects.count() == OriginalContentCall.objects.count() == 1
    )


def test_external_receipt_is_zero_send_and_reconciles_once():
    now = timezone.now()
    EditorialAssessment.objects.create(
        interval=now - timedelta(minutes=15),
        cutoff=now,
        source_cycle_id="operator-budget-carry-forward",
        scope="external-spend-20261007",
        state="complete",
        lease_until=now,
        outcome={
            "external_reserved_usd": 2.093153,
            "external_calls": 10,
            "sources": ["earlier live runs"],
            "provider_send": False,
        },
    )
    EditorialBudget.objects.create(day=now.date(), reserved_usd="2.093153", calls=10)
    assert backfill_original_content(apply=True)["ready"]
    assert backfill_original_content(apply=True)["ready"]
    receipt = OriginalContentRun.objects.get(workflow_key="reservation-carryforward")
    assert Decimal(receipt.outcome["external_reserved_usd"]) == Decimal("2.093153")
    assert receipt.outcome["external_calls"] == 10
    assert (
        not OriginalContentCall.objects.exists()
        and not OriginalContentText.objects.exists()
    )


def test_missing_source_and_unexplained_budget_block_ready_without_dummy_rows():
    saved = edition()
    EditorialBudget.objects.create(
        day=timezone.now().date(), reserved_usd="0.123456", calls=1
    )
    report = backfill_original_content(apply=True)
    assert not report["ready"]
    assert {e["kind"] for e in report["exceptions"]} >= {"edition", "budget"}
    assert not Post.objects.exists()
    assert not OriginalContentText.objects.filter(public_id=saved.pk).exists()


def test_headline_opaque_alias_recovers_actual_post_key_from_saved_identity():
    from hashlib import sha256

    from core.models import Brand
    from monitor.original_content import digest

    now = timezone.now()
    Post.objects.create(
        tweet_id="historic-headline", text="edited today", created_at=now
    )
    Post.objects.filter(pk="historic-headline").update(fetched_at=now)
    candidate = "minimax:full-window"
    passage = "The saved source text"
    alias = (
        "e_"
        + sha256(
            f"{candidate}\x1fhistoric-headline\x1foriginal_post\x1f{passage}".encode()
        ).hexdigest()[:24]
    )
    source = {"evidence_id": alias, "excerpt": passage, "created_at": now.isoformat()}
    Brand.objects.create(nickname="minimax", display_name="MiniMax")
    run = OriginalContentRun.objects.create(
        source_cycle_id="headline-history",
        window_days=7,
        facts_as_of=now,
        packet_schema_version=3,
        snapshot={
            "dossiers": [
                {
                    "brand_key": "minimax",
                    "source_row_provenance": {"candidate_id": candidate},
                    "evidence": [source],
                }
            ]
        },
    )
    parent = OriginalContent.objects.create(
        run=run,
        brand_key_snapshot="minimax",
        status="approved",
        brand_name_en_snapshot="MiniMax",
        brand_name_zh_cn_snapshot="MiniMax",
        headline_en="Saved title",
        secondary_en="Saved explanation",
        headline_zh_cn="保存标题",
        secondary_zh_cn="保存说明",
        attempted_at=now,
        verified_at=now,
        selected_evidence_packet=[source],
        cited_evidence_ids=[alias],
    )
    assert backfill_original_content(apply=False)["ready"]
    assert backfill_original_content(apply=True)["ready"]
    assert parent.localized_texts.count() == 2
    for text in parent.localized_texts.all():
        citation = text.sources.get()
        assert citation.post_id == "historic-headline"
        assert citation.source_hash == digest(source)
        assert citation.hash_basis == "legacy_packet"
