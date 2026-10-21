"""Retained paid work must not starve independent campaign members."""

import copy
from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import transaction
from django.utils import timezone

from core.collection_jobs import register_job, set_job_state
from core.models import (
    CollectionObservation,
    CollectionRun,
    OriginalContentCall,
    Post,
    PostBrand,
    PostBrandClassificationState,
    PostEnrichmentState,
    PostTranslationArtifact,
)
from core.provider_batches import record_post_membership
from monitor.backfill_enrichment import execute_enrichment
from scripts.backfill_campaign import prepare_current_contract
from tests.test_backfill_direct_enrichment import DirectProvider, run_direct
from tests.test_backfill_native_enrichment import native as native_fixture

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
native = native_fixture


def _complete(native):
    provider = DirectProvider()
    for turn in range(10):
        result = run_direct(native, provider, initial=turn == 0)
        if result["status"] == "completed":
            return
    pytest.fail(str(result))


def _new_campaign(native):
    old, cfg, delegates, policy = native
    job = register_job(
        job_key="independent-" + uuid4().hex, source=old.source, purpose="content",
        operation="x_backfill", mode="historical", definition=copy.deepcopy(old.definition),
    )
    job = set_job_state(job.pk, "ready")
    run = CollectionRun.objects.create(
        job=job, ingestion_key=uuid4().hex * 2, lease_token=uuid4(),
        lease_expires_at=timezone.now() + timedelta(minutes=5),
    )
    post = Post.objects.create(tweet_id="native-0", text="I tried Qwen today.", lang="en")
    PostBrand.objects.create(post=post, brand_id="qwen")
    PostEnrichmentState.objects.create(post=post)
    with transaction.atomic():
        record_post_membership(run, None, ["native-0", "native-1", "native-2"])
    return job, cfg, delegates, policy


def _aggregate(native, provider, *, initial=False):
    job, cfg, delegates, policy = native
    return execute_enrichment(
        job.pk, cfg=cfg, api_key="test", delegates=delegates,
        policy=policy if initial else None, transport="direct", direct_concurrency=8,
        direct_client_factory=provider.factory, defer_failures=True,
    )


def test_complete_foreign_members_and_saved_reply_do_not_block_new_campaign(native):
    _complete(native)
    old_job = native[0]
    retained = OriginalContentCall.objects.filter(stage="classification").first()
    retained.import_state = "pending"
    retained.save(update_fields=["import_state"])
    paid = list(OriginalContentCall.objects.order_by("pk").values())
    campaign = _new_campaign(native)
    prepare_current_contract(campaign[0], campaign[1])
    provider = DirectProvider()
    for turn in range(8):
        result = _aggregate(campaign, provider, initial=turn == 0)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed", result
    assert provider.sent == 4
    assert set(PostEnrichmentState.objects.filter(pk__in=["native-1", "native-2"])
               .values_list("source_collection_job_id", flat=True)) == {old_job.pk}
    assert list(OriginalContentCall.objects.filter(pk__in=[p["id"] for p in paid])
                .order_by("pk").values()) == paid


def test_foreign_unknown_is_durably_deferred_without_blocking_unrelated_members(native):
    _complete(native)
    old_job = native[0]
    call = OriginalContentCall.objects.get(
        stage="translation", member_post_ids=["native-1"],
        provenance__context__target_language="ja",
    )
    call.state, call.import_state = "ambiguous", "pending"
    call.response_payload, call.response_hash = {}, ""
    call.completed_at = None
    call.save()
    original = OriginalContentCall.objects.filter(pk=call.pk).values().get()
    PostTranslationArtifact.objects.filter(post_id="native-1").delete()
    PostEnrichmentState.objects.filter(pk="native-1").update(translation_status="pending")
    campaign = _new_campaign(native)
    prepare_current_contract(campaign[0], campaign[1])
    provider = DirectProvider()
    for turn in range(8):
        result = _aggregate(campaign, provider, initial=turn == 0)
        if result["actionable_pending_count"] == 0:
            break
    assert result["status"] == "partial" and result["pending_count"] == 1
    assert result["deferred_post_count"] == 1 and result["actionable_pending_count"] == 0
    assert result["deferred_reasons"] == {"historical_state_owned_elsewhere": 1}
    assert PostEnrichmentState.objects.get(pk="native-1").source_collection_job_id == old_job.pk
    assert provider.sent == 4
    assert OriginalContentCall.objects.filter(pk=call.pk).values().get() == original
    sent = provider.sent
    assert _aggregate(campaign, provider)["deferred_post_count"] == 1
    assert provider.sent == sent


def test_unrelated_saved_call_does_not_prevent_reclaiming_a_foreign_pending_member(native):
    _complete(native)
    old_job = native[0]
    campaign = _new_campaign(native)
    provider = DirectProvider()
    first = _aggregate(campaign, provider, initial=True)
    assert first["pending_count"] == 1 and provider.sent == 4
    assert OriginalContentCall.objects.filter(
        provider_batch__source_collection_job=campaign[0], import_state="pending",
    ).exists()

    PostTranslationArtifact.objects.filter(post_id="native-1").delete()
    PostEnrichmentState.objects.filter(pk="native-1").update(translation_status="pending")
    # The page contains a foreign incomplete member, a foreign complete one,
    # and saved paid work for a different member. Only a correlated foreign
    # outstanding call could prevent reclaiming the incomplete member.
    prepare_current_contract(campaign[0], campaign[1])
    assert PostEnrichmentState.objects.get(pk="native-1").source_collection_job_id == campaign[0].pk
    assert PostEnrichmentState.objects.get(pk="native-2").source_collection_job_id == old_job.pk
    for _ in range(8):
        result = _aggregate(campaign, provider)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed" and provider.sent == 4


def test_global_completed_cache_replays_original_packet_without_rebuying(native):
    _complete(native)
    # Its paid requests are final and reusable, while the canonical stored
    # translation was lost. The new campaign must consume the saved replies.
    PostTranslationArtifact.objects.filter(post_id="native-1").delete()
    before = list(OriginalContentCall.objects.order_by("pk").values())
    campaign = _new_campaign(native)
    prepare_current_contract(campaign[0], campaign[1])
    provider = DirectProvider()
    for turn in range(10):
        result = _aggregate(campaign, provider, initial=turn == 0)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed", result
    assert provider.sent == 4
    assert list(OriginalContentCall.objects.filter(pk__in=[p["id"] for p in before])
                .order_by("pk").values()) == before


def test_invalid_foreign_cache_is_unchanged_and_deferred_while_siblings_publish(native):
    from core.provider_batches import digest

    _complete(native)
    call = OriginalContentCall.objects.get(
        stage="translation", member_post_ids=["native-1"],
        provenance__context__target_language="ja",
    )
    call.response_payload = copy.deepcopy(call.response_payload)
    call.response_payload["choices"][0]["finish_reason"] = "length"
    call.response_hash = digest(call.response_payload)
    call.save()
    before = list(OriginalContentCall.objects.order_by("pk").values())
    PostTranslationArtifact.objects.filter(post_id="native-1").delete()
    campaign = _new_campaign(native)
    prepare_current_contract(campaign[0], campaign[1])
    provider = DirectProvider()
    for turn in range(8):
        result = _aggregate(campaign, provider, initial=turn == 0)
        if result["actionable_pending_count"] == 0:
            break
    assert result["status"] == "partial" and result["pending_count"] == 1
    assert result["deferred_post_count"] == 1 and provider.sent == 4
    assert PostEnrichmentState.objects.get(pk="native-0").translation_status == "succeeded"
    assert OriginalContentCall.objects.filter(request_hash=call.request_hash).count() == 1
    assert list(OriginalContentCall.objects.filter(pk__in=[p["id"] for p in before])
                .order_by("pk").values()) == before


def test_duplicate_racing_admission_does_not_roll_back_independent_requests(native, monkeypatch):
    from monitor import backfill_enrichment as enrichment
    from monitor.backfill_direct import advance_direct

    original = enrichment._register_requests
    provider = DirectProvider()
    races = []

    def register(job, requests, *args, **kwargs):
        if requests and not races:
            races.append(requests[0]["hash"])
            # A second admitted runner finishes this exact paid request after
            # preparation. The real reservation guard sees it at admission.
            for batch_id in original(job, requests[:1], *args, **kwargs):
                advance_direct(batch_id, api_key="test", concurrency=8,
                               client_factory=provider.factory)
        return original(job, requests, *args, **kwargs)

    monkeypatch.setattr(enrichment, "_register_requests", register)
    first = _aggregate(native, provider, initial=True)
    assert first["deferred_reasons"] == {"model_request_already_outstanding_or_complete": 1}
    assert OriginalContentCall.objects.count() == 6 and provider.sent == 6
    for _ in range(8):
        result = _aggregate(native, provider)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed" and provider.sent == 6
    assert OriginalContentCall.objects.filter(request_hash=races[0]).count() == 1


@pytest.mark.parametrize("changed_member", ["native-1", "native-2"])
def test_global_packet_with_changed_source_does_not_starve_fresh_work(native, changed_member):
    _complete(native)
    Post.objects.filter(pk=changed_member).update(text="I tried Qwen again.")
    PostTranslationArtifact.objects.filter(post_id="native-1").delete()
    PostBrandClassificationState.objects.filter(post_id="native-1").delete()
    before = list(OriginalContentCall.objects.order_by("pk").values())
    foreign_state = PostEnrichmentState.objects.filter(pk="native-2").values().get()
    campaign = _new_campaign(native)
    # The original paid classifier packet includes a member that this new
    # campaign does not own. Its changed source must not authorize or block
    # publication of the unchanged selected member.
    CollectionObservation.objects.filter(run__job=campaign[0], post_id="native-2").delete()
    prepare_current_contract(campaign[0], campaign[1])
    provider = DirectProvider()
    for turn in range(10):
        result = _aggregate(campaign, provider, initial=turn == 0)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed", result
    assert provider.sent == (6 if changed_member == "native-1" else 4)
    assert PostEnrichmentState.objects.filter(pk="native-2").values().get() == foreign_state
    assert list(OriginalContentCall.objects.filter(pk__in=[p["id"] for p in before])
                .order_by("pk").values()) == before


def test_overlapping_paid_member_defers_only_that_member_and_regroups_the_rest(native, monkeypatch):
    from monitor import backfill_enrichment as enrichment
    from monitor.backfill_direct import advance_direct

    original = enrichment._register_requests
    provider = DirectProvider()
    raced = []

    def register(job, requests, *args, **kwargs):
        if requests and not raced:
            raced.append(True)
            previous, _, _ = enrichment.prepare_page(
                job, ["native-1"], native[1], delegates=native[2],
            )
            previous = [r for r in previous if r["context"]["stage"] == "classification"]
            assert len(previous) == 2
            for batch_id in original(job, previous, *args, **kwargs):
                advance_direct(batch_id, api_key="test", concurrency=8,
                               client_factory=provider.factory)
        return original(job, requests, *args, **kwargs)

    monkeypatch.setattr(enrichment, "_register_requests", register)
    first = _aggregate(native, provider, initial=True)
    assert first["deferred_reasons"] == {"model_member_work_already_outstanding": 1}
    assert first["actionable_pending_count"] == 1
    assert provider.sent == 6
    for _ in range(8):
        result = _aggregate(native, provider)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed" and provider.sent == 8
    classifier = OriginalContentCall.objects.filter(stage="classification")
    assert classifier.filter(member_post_ids=["native-1"]).count() == 2
    assert classifier.filter(member_post_ids=["native-2"]).count() == 2


def test_all_skipped_first_groups_keep_policy_for_campaign_continuation(native, monkeypatch):
    from core.models import ProviderBatch
    from core.provider_batches import BatchAdmissionError
    from monitor import backfill_enrichment as enrichment

    prepare, reserve = enrichment.prepare_page, enrichment.reserve_requests
    provider = DirectProvider()

    def first_page(job, ids, *args, **kwargs):
        return prepare(job, ids[:1], *args, **kwargs)

    def raced_duplicate(claim, requests):
        # The real duplicate and overlap guards are exercised by the two
        # admission race tests above. Isolate the caller's zero-admission
        # policy handling here, with independent work still outside the page.
        raise BatchAdmissionError(
            "model_request_already_outstanding_or_complete",
            member_ids={p for r in requests for p in r["context"]["post_ids"]},
        )

    monkeypatch.setattr(enrichment, "prepare_page", first_page)
    monkeypatch.setattr(enrichment, "reserve_requests", raced_duplicate)
    first = _aggregate(native, provider, initial=True)
    assert first["model_requests_reserved"] == 0 and provider.sent == 0
    assert first["actionable_pending_count"] == 1
    anchors = ProviderBatch.objects.filter(source_collection_job=native[0])
    assert anchors.exists() and not anchors.exclude(state="completed").exists()
    assert not anchors.exclude(request_count=0).exists()

    monkeypatch.setattr(enrichment, "prepare_page", prepare)
    monkeypatch.setattr(enrichment, "reserve_requests", reserve)
    for _ in range(8):
        # The campaign drops its initial policy after the first advancement.
        result = _aggregate(native, provider)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed" and provider.sent == 6
