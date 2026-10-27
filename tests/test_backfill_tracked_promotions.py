"""Shared semantic repairs through saved backfill requests and publication."""
import json
from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import (
    OriginalContentCall,
    Post,
    PostBrandClassificationState,
    PostEnrichmentState,
    UntrackedBrandPromotionEvidence,
)
from monitor import cycle
from tests.test_backfill_direct_enrichment import DirectProvider, run_direct
from tests.test_backfill_native_enrichment import native  # noqa: F401
from x_monitor.deepinfra import DEEPSEEK_0731_MODEL

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("subjects,expected", [
    (["Muse"], []),
    (["Independent Harness"], ["Independent Harness"]),
    (["Muse", "Independent Harness"], ["Independent Harness"]),
])
def test_backfill_preserves_labels_and_raw_replies_when_normalizing_tracked_subjects(native, monkeypatch, subjects, expected):  # noqa: F811
    job, _, _, _ = native
    ids = ["native-1", "native-2"]
    Post.objects.filter(pk__in=ids).update(text="Try Muse. Try Independent Harness. Qwen is faster.")
    monkeypatch.setattr(cycle, "_classification_tracked_brand_catalog", lambda: [{
        "brand_id": "qwen", "aliases": ["Qwen"], "products": ["Muse"],
        "handles": [], "domains": [], "keywords": [], "hashtags": [], "accounts": [],
    }])

    class Provider(DirectProvider):
        def transport(self, body, timeout):
            response = super().transport(body, timeout)
            if body["model"] == DEEPSEEK_0731_MODEL:
                value = json.loads(response["choices"][0]["message"]["content"])
                if "promoted_subjects" in value:
                    system = next(m["content"] for m in body["messages"] if m["role"] == "system")
                    assert "reviewed aliases and products" in system
                    for slot in value["promoted_subjects"]:
                        value["post_promotions"][slot] = ["general"]
                        value["promoted_subjects"][slot] = [{
                            "name": name, "handle": None, "domain": None,
                            "account_handle": None, "evidence": f"Try {name}.",
                        } for name in subjects]
                    response["choices"][0]["message"]["content"] = json.dumps(value)
            return response

    provider = Provider()
    for turn in range(15):
        report = run_direct(native, provider, initial=turn == 0)
        if report["status"] == "completed":
            break
    assert report["status"] == "completed", report
    assert report["persisted_output_invalid_count"] == 0 and report["twitterapi_requests"] == 0
    assert PostEnrichmentState.objects.filter(post_id__in=ids, classification_status="succeeded").count() == 2
    assert PostBrandClassificationState.objects.filter(post_id__in=ids).count() == 2
    for post_id in ids:
        assert sorted(UntrackedBrandPromotionEvidence.objects.filter(source_post_id=post_id)
                      .values_list("observed_name", flat=True)) == sorted(expected)
    # Saved provider replies retain exactly what the model said, including the
    # tracked subject removed from the current normalized publication.
    from core.models import ProviderBatch

    batch_ids = ProviderBatch.objects.filter(source_collection_job=job).values("pk")
    calls = OriginalContentCall.objects.filter(provider_batch_id__in=batch_ids)
    assert calls.exists()
    if "Muse" in subjects:
        assert any("Muse" in json.dumps(value) for value in calls.values_list("response_payload", flat=True))
    sent = provider.sent
    assert run_direct(native, provider)["status"] == "completed"
    assert provider.sent == sent


def test_expired_backfill_claim_cannot_publish(native, monkeypatch):  # noqa: F811
    state = PostEnrichmentState.objects.get(pk="native-1")
    state.claim_run_id = "expired-backfill-proof"
    state.claim_expires_at = timezone.now() - timedelta(seconds=1)
    state.save(update_fields=["claim_run_id", "claim_expires_at"])
    # An otherwise malformed payload must never reach parsing after its claim
    # expires; the fence applies before any classification writes.
    result = cycle._publish_stage1_classification(
        post_id=state.pk, result={"valid": True, "by_brand": {"qwen": {}}},
        tweet={}, model=DEEPSEEK_0731_MODEL, run_id=state.claim_run_id,
    )
    assert result is None
    assert not PostBrandClassificationState.objects.filter(post_id=state.pk).exists()
