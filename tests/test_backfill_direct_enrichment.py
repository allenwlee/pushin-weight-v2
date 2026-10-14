"""Ordinary HTTP enrichment through the shared callers and PostgreSQL writers."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from core.models import OriginalContentCall, ProviderBatch
from monitor.backfill_enrichment import execute_enrichment
from tests.test_backfill_native_enrichment import (
    NativeProvider,
)
from tests.test_backfill_native_enrichment import (
    native as native_fixture,
)
from x_monitor.deepinfra import DeepInfraChatCompletionsClient

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
native = native_fixture


class DirectProvider:
    def __init__(self):
        self.lock = threading.Lock()
        self.active = self.peak = self.sent = 0

    def factory(self, *, api_key, model, request_profile):
        return DeepInfraChatCompletionsClient(
            api_key=api_key,
            model=model,
            request_profile=request_profile,
            transport=self.transport,
        )

    def transport(self, body, timeout):
        assert not connection.in_atomic_block
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.sent += 1
        try:
            time.sleep(0.02)
            # Reuse the native fixture's canonical replies, with no file HTTP.
            provider = NativeProvider(api_key="test", before_request=lambda *a: None)
            identifier = str(id(body))
            provider.files[identifier] = [{"custom_id": "direct", "body": body}]
            return next(provider.outputs(identifier))["response"]["body"]
        finally:
            with self.lock:
                self.active -= 1


def run_direct(native, provider, *, initial=False, concurrency=2):
    job, cfg, delegates, policy = native
    return execute_enrichment(
        job.pk,
        cfg=cfg,
        api_key="test",
        delegates=delegates,
        policy=policy if initial else None,
        transport="direct",
        direct_concurrency=concurrency,
        direct_client_factory=provider.factory,
    )


def test_direct_real_callers_publish_and_reuse_without_file_requests(native):
    provider = DirectProvider()
    for turn in range(15):
        result = run_direct(native, provider, initial=turn == 0)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed", json.dumps(result)
    assert result["persisted_output_invalid_count"] == 0
    assert result["twitterapi_requests"] == 0
    assert provider.peak == 2
    assert provider.sent == result["model_requests_sent"]
    assert not ProviderBatch.objects.exclude(transport="direct").exists()
    assert not ProviderBatch.objects.exclude(
        input_file_id="", provider_batch_id=""
    ).exists()
    assert OriginalContentCall.objects.filter(import_state="applied").exists()
    sent = provider.sent
    assert run_direct(native, provider)["status"] == "completed"
    assert provider.sent == sent


def test_direct_invalid_concurrency_refused_before_paid_work(native):
    from core.provider_batches import BatchAdmissionError

    provider = DirectProvider()
    with pytest.raises(BatchAdmissionError, match="direct_concurrency_invalid"):
        run_direct(native, provider, initial=True, concurrency=0)
    assert provider.sent == 0
    assert not OriginalContentCall.objects.exists()


def test_direct_command_admits_before_http_and_status_does_no_work(native, monkeypatch):
    import monitor.backfill_direct as direct
    import monitor.backfill_enrichment as enrichment
    from monitor.management.commands import backfill

    job, cfg, delegates, policy = native
    provider = DirectProvider()
    starts = []

    def executor(**kwargs):
        assert not connection.in_atomic_block
        calls = list(OriginalContentCall.objects.filter(state="sent"))
        assert calls and all(c.sent_at and c.reserved_usd > 0 for c in calls)
        starts.append(len(calls))
        return ThreadPoolExecutor(**kwargs)

    monkeypatch.setenv("DEEPINFRA_API_KEY", "test-only")
    monkeypatch.setattr(backfill, "load_config", lambda path: cfg)
    monkeypatch.setattr(direct, "DeepInfraChatCompletionsClient", provider.factory)
    monkeypatch.setattr(direct, "ThreadPoolExecutor", executor)
    monkeypatch.setattr(
        enrichment,
        "build_translator_client_from_env",
        lambda cfg: delegates["translation"],
    )
    monkeypatch.setattr(
        enrichment,
        "build_classifier_client_from_env",
        lambda cfg: delegates["classification"],
    )
    output = StringIO()
    call_command(
        "backfill",
        collection_job=str(job.pk),
        enrich_direct=True,
        enrichment_concurrency=2,
        enrichment_max_usd="5",
        enrichment_deadline=policy["deadline"],
        stdout=output,
    )
    assert starts and provider.sent > 0
    assert json.loads(output.getvalue())["twitterapi_requests"] == 0
    sent = provider.sent
    call_command(
        "backfill",
        collection_job=str(job.pk),
        enrich_direct=True,
        status=True,
        stdout=StringIO(),
    )
    assert provider.sent == sent


def test_direct_switch_reuses_completed_native_replies(native):
    from tests.test_backfill_native_enrichment import advance

    advance(native, initial=True)
    # Complete the provider replies without publishing, then switch transport.
    from monitor.backfill_enrichment import advance_batch

    for group in ProviderBatch.objects.all():
        ProviderBatch.objects.filter(pk=group.pk).update(next_poll_at=timezone.now())
        advance_batch(group.pk, api_key="test", client_factory=NativeProvider)
    received = OriginalContentCall.objects.filter(state="completed").count()
    assert received > 0
    provider = DirectProvider()
    assert run_direct(native, provider)["status"] == "completed"
    assert provider.sent == 0
    assert OriginalContentCall.objects.count() == received


def test_direct_timeout_retains_ambiguity_and_never_resends(native):
    provider = DirectProvider()

    def timeout(body, seconds):
        provider.sent += 1
        raise TimeoutError("test interrupted response")

    provider.transport = timeout
    run_direct(native, provider, initial=True)
    sent = provider.sent
    assert OriginalContentCall.objects.filter(
        state="ambiguous", import_state="pending"
    ).exists()
    unstarted = OriginalContentCall.objects.filter(state="reserved").count()
    assert run_direct(native, provider)["status"] == "partial"
    assert provider.sent == sent + unstarted
    sent = provider.sent
    assert run_direct(native, provider)["status"] == "partial"
    assert provider.sent == sent
    assert OriginalContentCall.objects.filter(
        state="ambiguous", actual_usd=None
    ).exists()


def test_direct_spend_guard_stops_before_http(native):
    from core.provider_batches import BatchAdmissionError

    native[3]["max_usd"] = "0.000001"
    provider = DirectProvider()
    with pytest.raises(BatchAdmissionError, match="model_campaign_allowance_exhausted"):
        run_direct(native, provider, initial=True)
    assert provider.sent == 0
    assert not OriginalContentCall.objects.exists()


def test_direct_32_requests_overlap_without_worker_database_connections(native):
    from core.models import Post, PostBrand, PostEnrichmentState
    from core.provider_batches import record_post_membership

    job = native[0]
    ids = []
    for index in range(16):
        post = Post.objects.create(
            tweet_id=f"direct-wide-{index}", text="I tried Qwen today.", lang="en"
        )
        PostBrand.objects.create(post=post, brand_id="qwen")
        PostEnrichmentState.objects.create(post=post)
        ids.append(post.pk)
    from django.db import transaction

    with transaction.atomic():
        record_post_membership(job.runs.get(), None, ids)
    provider = DirectProvider()
    original = provider.transport
    barrier = threading.Barrier(32)
    from x_monitor.deepinfra import GEMMA_4_31B_MODEL

    def simultaneous(body, timeout):
        assert connection.connection is None
        if body["model"] == GEMMA_4_31B_MODEL:
            barrier.wait(timeout=10)
        return original(body, timeout)

    provider.transport = simultaneous
    result = run_direct(native, provider, initial=True, concurrency=32)
    assert provider.peak == 32
    assert result["direct_model_requests_sent"] == provider.sent


def test_direct_429_defers_retry_and_keeps_prior_reservations(native):
    from x_monitor.deepinfra import DeepInfraRetryableError

    provider = DirectProvider()

    def throttled(body, timeout):
        provider.sent += 1
        raise DeepInfraRetryableError("deepinfra_http_status_429")

    provider.transport = throttled
    run_direct(native, provider, initial=True)
    sent = provider.sent
    run_direct(native, provider)
    assert provider.sent == sent
    assert ProviderBatch.objects.filter(next_poll_at__gt=timezone.now()).exists()
    assert OriginalContentCall.objects.filter(
        state="failed", reserved_usd__gt=0
    ).exists()
