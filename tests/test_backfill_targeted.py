"""Real extraction callers and domain publishers with captured HTTP."""

import json

import pytest

from core.models import (
    Event,
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


def test_read_only_checker_rejects_skipped_extraction(accepted):
    from scripts.backfill_verify import verify_posts

    ids, cfg = accepted
    cfg.targeted_extraction.enabled = True
    PostBrandSignal.objects.create(
        post_id=ids[0], brand_id="qwen", post_type_id="events", sentiment_id="neutral"
    )
    result = verify_posts(ids, cfg=cfg)
    assert "targeted_extraction_incomplete" in result["errors"][ids[0]]


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
