"""Real extraction callers and domain publishers with captured HTTP."""

import json

import pytest

from core.models import (
    Event,
    Opportunity,
    OriginalContentCall,
    Post,
    PostBrandSignal,
    TargetedExtractionState,
)
from scripts.backfill_targeted import advance_targeted, incomplete_roles
from tests.test_backfill_direct_enrichment import DirectProvider
from tests.test_backfill_native_enrichment import native as native_fixture
from tests.test_backfill_verify import accepted as accepted_fixture

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
native = native_fixture
accepted = accepted_fixture


@pytest.mark.parametrize("zone", ["Asia/Tokyo", "Pacific Time"])
@pytest.mark.parametrize("role", ["event_extraction", "opportunity_extraction"])
def test_saved_timezone_reply_replays_after_legacy_columns_are_removed(
    accepted, native, role, zone,
):
    from django.db import connection

    from core.models import TimeZone

    ids, cfg = accepted
    cfg.targeted_extraction.enabled = True
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() "
            "AND table_name IN ('events','opportunities','metrics') "
            "AND column_name='source_timezone'"
        )
        assert cursor.fetchall() == [], "test must exercise the actual post-cutover schema"
    TimeZone.objects.get_or_create(code="Asia/Tokyo")
    kind = "events" if role == "event_extraction" else "opportunities"
    PostBrandSignal.objects.create(
        post_id=ids[0], brand_id="qwen", post_type_id=kind, sentiment_id="neutral",
    )
    record = {
        "brand_id": "qwen", "organization_name": "Qwen",
        "source_timezone": zone,
    }
    if role == "event_extraction":
        record |= {
            "title": "Live workshop", "attendance_mode": "online_live",
            "start_value": "2026-08-10T10:00:00+09:00", "start_precision": "datetime",
            "end_value": None, "end_precision": "unknown", "source_status": "scheduled",
        }
        model = Event
    else:
        record |= {
            "opportunity_type": "contest", "action_type": "submit a project",
            "benefit_type": "prize", "open_value": None, "open_precision": "unknown",
            "close_value": None, "close_precision": "unknown", "source_status": "open",
        }
        model = Opportunity

    class SavedReplyProvider(DirectProvider):
        def transport(self, body, timeout):
            self.sent += 1
            return {
                "model": body["model"],
                "choices": [{"finish_reason": "stop", "message": {
                    "content": json.dumps({"records": [record]}),
                }}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 30},
            }

    provider = SavedReplyProvider()
    kwargs = {
        "cfg": cfg, "api_key": "test", "delegate": native[2]["classification"],
        "post_ids": [ids[0]],
    }
    advance_targeted(native[0].pk, **kwargs, client_factory=provider.factory)
    call = OriginalContentCall.objects.get(provenance__context__operation="post_targeted_extraction")
    assert provider.sent == 1 and call.state == "completed" and call.import_state == "pending"
    assert not model.objects.exists()
    paid_before = OriginalContentCall.objects.values().get(pk=call.pk)

    def no_additional_http(**kwargs):
        raise AssertionError("saved reply was repurchased during post-cutover replay")

    for _ in range(3):
        result = advance_targeted(native[0].pk, **kwargs, client_factory=no_additional_http)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed", result
    row = model.objects.get()
    assert row.source_timezone_reference_id == (zone if zone == "Asia/Tokyo" else None)
    assert row.raw_payload["source_timezone"] == zone
    assert not incomplete_roles(Post.objects.get(pk=ids[0]), cfg)
    call.refresh_from_db()
    assert call.import_state == "applied"
    paid_after = OriginalContentCall.objects.values().get(pk=call.pk)
    for field in ("import_state", "import_evidence"):
        paid_before.pop(field)
        paid_after.pop(field)
    assert paid_after == paid_before
    assert provider.sent == 1 and model.objects.count() == 1


class ExtractionProvider(DirectProvider):
    def transport(self, body, timeout):
        self.sent += 1
        return {
            "model": body["model"],
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            {
                                "records": [
                                    {
                                        "brand_id": "qwen",
                                        "organization_name": "Qwen",
                                        "title": "Live workshop",
                                        "attendance_mode": "online_live",
                                        "start_value": "2026-08-10T10:00:00+09:00",
                                        "start_precision": "datetime",
                                        "end_value": None,
                                        "end_precision": "unknown",
                                        "source_status": "scheduled",
                                    }
                                ]
                            }
                        )
                    },
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 30},
        }


def test_structured_extraction_uses_paid_ledger_and_shared_publisher(accepted, native):
    ids, cfg = accepted
    cfg.targeted_extraction.enabled = True
    for identifier in ids:
        PostBrandSignal.objects.create(
            post_id=identifier,
            brand_id="qwen",
            post_type_id="events",
            sentiment_id="neutral",
        )
    provider = ExtractionProvider()
    assert incomplete_roles(Post.objects.get(pk=ids[0]), cfg) == ["event_extraction"]
    for _ in range(5):
        result = advance_targeted(
            native[0].pk,
            cfg=cfg,
            api_key="test",
            delegate=native[2]["classification"],
            client_factory=provider.factory,
        )
        if result["status"] == "completed":
            break
    assert result["status"] == "completed", result
    assert Event.objects.count() == 1
    assert TargetedExtractionState.objects.filter(status="succeeded").count() == 2
    assert not incomplete_roles(Post.objects.get(pk=ids[0]), cfg)
    calls = OriginalContentCall.objects.filter(
        provenance__context__operation="post_targeted_extraction"
    )
    assert calls.count() == provider.sent == 2
    assert not calls.exclude(state="completed", import_state="applied").exists()
    assert all(c.reserved_usd > 0 for c in calls)
    advance_targeted(
        native[0].pk,
        cfg=cfg,
        api_key="test",
        delegate=native[2]["classification"],
        client_factory=provider.factory,
    )
    assert provider.sent == 2


@pytest.mark.parametrize("saved_targeted_reply", [False, True])
def test_inherited_base_completion_can_extract_without_reassigning_base_ownership(
    accepted, native, saved_targeted_reply,
):
    from core.models import PostEnrichmentState
    from tests.test_backfill_independent_progress import _aggregate, _new_campaign

    ids, cfg = accepted
    original_owner = PostEnrichmentState.objects.get(pk=ids[0]).source_collection_job_id
    campaign = _new_campaign(native)
    base_provider = DirectProvider()
    for turn in range(8):
        base = _aggregate(campaign, base_provider, initial=turn == 0)
        if base["status"] == "completed":
            break
    assert base["status"] == "completed"
    assert PostEnrichmentState.objects.get(pk=ids[0]).source_collection_job_id == original_owner
    # Add the targeted requirement after the base contract has been checked;
    # its fixture signal is intentionally outside the base classifier reply.
    cfg.targeted_extraction.enabled = True
    PostBrandSignal.objects.create(
        post_id=ids[0], brand_id="qwen", post_type_id="events", sentiment_id="neutral",
    )
    if saved_targeted_reply:
        old_provider = ExtractionProvider()
        for _ in range(4):
            old = advance_targeted(
                native[0].pk, cfg=cfg, api_key="test", delegate=native[2]["classification"],
                client_factory=old_provider.factory,
            )
            if old["status"] == "completed":
                break
        assert old["status"] == "completed" and old_provider.sent == 1
        TargetedExtractionState.objects.filter(post_id=ids[0]).delete()
    original_calls = list(OriginalContentCall.objects.order_by("pk").values())
    provider = ExtractionProvider()
    for _ in range(4):
        result = advance_targeted(
            campaign[0].pk, cfg=cfg, api_key="test", delegate=native[2]["classification"],
            client_factory=provider.factory, defer_failures=True,
        )
        if result["status"] == "completed":
            break
    assert result["status"] == "completed" and Event.objects.count() == 1
    assert provider.sent == (0 if saved_targeted_reply else 1)
    assert PostEnrichmentState.objects.get(pk=ids[0]).source_collection_job_id == original_owner
    assert list(OriginalContentCall.objects.filter(pk__in=[c["id"] for c in original_calls])
                .order_by("pk").values()) == original_calls


def test_read_only_checker_rejects_skipped_extraction(accepted):
    from scripts.backfill_verify import verify_posts

    ids, cfg = accepted
    cfg.targeted_extraction.enabled = True
    PostBrandSignal.objects.create(
        post_id=ids[0], brand_id="qwen", post_type_id="events", sentiment_id="neutral"
    )
    result = verify_posts(ids, cfg=cfg)
    assert "targeted_extraction_incomplete" in result["errors"][ids[0]]


def test_selected_extraction_preserves_unselected_failed_post(accepted, native):
    ids, cfg = accepted
    cfg.targeted_extraction.enabled = True
    for identifier in ids:
        PostBrandSignal.objects.create(
            post_id=identifier, brand_id="qwen", post_type_id="events",
            sentiment_id="neutral",
        )
    excluded = TargetedExtractionState.objects.create(
        post_id=ids[1], role="event_extraction", status="failed",
        model=cfg.targeted_extraction.roles["event_extraction"].model,
        prompt_version="previous-failed-input", content_identity="0" * 64,
    )
    before = TargetedExtractionState.objects.filter(pk=excluded.pk).values().get()
    provider = ExtractionProvider()
    for _ in range(5):
        result = advance_targeted(
            native[0].pk, cfg=cfg, api_key="test",
            delegate=native[2]["classification"], client_factory=provider.factory,
            post_ids=[ids[0], ids[0]],
        )
        if result["status"] == "completed":
            break
    assert result["status"] == "completed"
    calls = OriginalContentCall.objects.filter(
        provenance__context__operation="post_targeted_extraction",
    )
    assert calls.count() == provider.sent == 1
    assert calls.get().member_post_ids == [ids[0]]
    assert calls.get().import_state == "applied"
    assert not incomplete_roles(Post.objects.get(pk=ids[0]), cfg)
    assert incomplete_roles(Post.objects.get(pk=ids[1]), cfg) == ["event_extraction"]
    assert TargetedExtractionState.objects.filter(pk=excluded.pk).values().get() == before


@pytest.mark.parametrize("selection", [[], ["outside-job-membership"]])
def test_targeted_selection_rejects_invalid_members_before_payment(
    accepted, native, selection, monkeypatch,
):
    from core.provider_batches import BatchAdmissionError

    _ids, cfg = accepted
    cfg.targeted_extraction.enabled = True
    provider = ExtractionProvider()
    batch = native[0].provider_batches.order_by("created_at").first()
    batch.state = "registered"
    batch.save(update_fields=["state"])

    def must_not_advance(*args, **kwargs):
        raise AssertionError("invalid selection advanced an existing paid group")

    monkeypatch.setattr("scripts.backfill_targeted.advance_direct", must_not_advance)
    before = list(OriginalContentCall.objects.order_by("pk").values())
    with pytest.raises(BatchAdmissionError, match="targeted_selection"):
        advance_targeted(
            native[0].pk, cfg=cfg, api_key="test",
            delegate=native[2]["classification"], client_factory=provider.factory,
            post_ids=selection,
        )
    assert provider.sent == 0
    assert list(OriginalContentCall.objects.order_by("pk").values()) == before


def test_historical_base_failures_do_not_block_required_targeted_work(accepted, native):
    import copy
    from datetime import timedelta

    from django.utils import timezone

    from monitor.backfill_enrichment import deferred_enrichment_work

    ids, cfg = accepted
    cfg.targeted_extraction.enabled = True
    original = OriginalContentCall.objects.filter(
        stage="classification",
        provenance__context__role="content",
    ).first()
    for index in range(3):
        old = copy.deepcopy(original)
        old.pk = None
        old.request_identity = f"old-failed-input-{index}"
        old.batch_key = f"old-failed-input-{index}"
        old.reserved_at = timezone.now() - timedelta(days=1)
        old.import_state = "error"
        old.import_evidence = {
            "validation": "canonical_validation_failed",
            "invalid_member_ids": ids,
        }
        old.provenance["context"]["input_fingerprints"] = {p: "0" * 64 for p in ids}
        old.save(force_insert=True)
    assert deferred_enrichment_work(native[0], max_attempts=3)
    for post_id in ids:
        PostBrandSignal.objects.create(
            post_id=post_id,
            brand_id="qwen",
            post_type_id="events",
            sentiment_id="neutral",
        )
    provider = ExtractionProvider()
    for _ in range(5):
        result = advance_targeted(
            native[0].pk,
            cfg=cfg,
            api_key="test",
            delegate=native[2]["classification"],
            client_factory=provider.factory,
            defer_failures=True,
        )
        if result["status"] == "completed":
            break
    assert result["status"] == "completed"
    assert TargetedExtractionState.objects.filter(status="succeeded").count() == 2
    assert provider.sent == 2
