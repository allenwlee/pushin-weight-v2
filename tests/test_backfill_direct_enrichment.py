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


@pytest.mark.parametrize("path", ["live", "backfill"])
@pytest.mark.parametrize("extra_brace", [False, True])
def test_live_and_backfill_classifier_wire_budget_covers_multibrand_packets(native, path, extra_brace):
    """The real callers must not inherit the old, truncating 4,096-token default."""
    from django.db import transaction

    from core.models import CollectionRun, Post, PostBrand, PostEnrichmentState
    from core.provider_batches import record_post_membership
    from monitor.cycle import CycleRunner
    from x_monitor.deepinfra import DEEPSEEK_0731_MODEL

    class CapturingProvider(DirectProvider):
        def __init__(self):
            super().__init__()
            self.classifier_requests = []

        def transport(self, body, timeout):
            if body["model"] == DEEPSEEK_0731_MODEL:
                with self.lock:
                    self.classifier_requests.append(body)
            reply = super().transport(body, timeout)
            if extra_brace and body["model"] == DEEPSEEK_0731_MODEL:
                reply["choices"][0]["message"]["content"] += "}"
            return reply

    job, cfg, delegates, _ = native
    identifiers = [f"budget-{i:02}" for i in range(20 if path == "live" else 18)]
    for identifier in identifiers:
        post = Post.objects.create(
            tweet_id=identifier, text="I tried Qwen and DeepSeek today.", lang="en"
        )
        PostBrand.objects.create(post=post, brand_id="qwen")
        PostEnrichmentState.objects.create(post=post)
    if path == "backfill":
        with transaction.atomic():
            record_post_membership(CollectionRun.objects.get(job=job), None, identifiers)
        identifiers += ["native-1", "native-2"]
    # Match the retained truncation's shape: 20 Posts and 37 brand decisions.
    for identifier in identifiers[:17]:
        PostBrand.objects.create(post_id=identifier, brand_id="deepseek")

    provider = CapturingProvider()
    if path == "live":
        clients = {
            stage: provider.factory(
                api_key="test", model=client.model, request_profile=client.request_profile
            )
            for stage, client in delegates.items()
        }
        result = CycleRunner(
            cfg=cfg, _post_fetch_clients=clients, _max_llm_calls=100
        )._run_post_fetch([], run_id="classifier-budget-pin", post_ids=set(identifiers))
        assert result["n_enrichment_succeeded"] == 20, result
    else:
        for turn in range(15):
            result = run_direct(native, provider, initial=turn == 0)
            if result["status"] == "completed":
                break
        assert result["status"] == "completed", result
        assert result["twitterapi_requests"] == 0
    assert PostEnrichmentState.objects.filter(
        pk__in=identifiers,
        translation_status="succeeded",
        classification_status="succeeded",
    ).count() == 20
    assert len(provider.classifier_requests) == 2
    assert {
        "content" if "CONTENT ROLE:" in body["messages"][0]["content"] else "brand"
        for body in provider.classifier_requests
    } == {"content", "brand"}
    for body in provider.classifier_requests:
        payload = json.loads(next(m["content"] for m in body["messages"] if m["role"] == "user"))
        assert len(payload["cases"]) == 20
        assert sum(len(case["brand_decision_slots"]) for case in payload["cases"].values()) == 37
        assert body["max_tokens"] == 65_536, (
            f"{path} must send the selected 65,536-token budget for both classifier roles"
        )


@pytest.mark.parametrize("status", [401, 402, 403])
def test_provider_admission_failure_drains_sent_wave_then_stops(native, status):
    from core.provider_batches import BatchAdmissionError
    from x_monitor.deepinfra import DeepInfraPermanentError

    class RejectedProvider(DirectProvider):
        def transport(self, body, timeout):
            with self.lock:
                self.sent += 1
            raise DeepInfraPermanentError(f"deepinfra_http_status_{status}")

    provider = RejectedProvider()
    with pytest.raises(BatchAdmissionError, match=f"enrichment_provider_admission_http_{status}"):
        run_direct(native, provider, initial=True, concurrency=2)
    calls = OriginalContentCall.objects.filter(provider_batch__source_collection_job=native[0])
    sent = calls.filter(sent_at__isnull=False)
    assert provider.sent == sent.count() == 2
    assert sent.filter(state="failed").count() == 2
    assert not sent.filter(state__in=["sent", "ambiguous"]).exists()
    assert all(c.error_code for c in sent)


def test_completed_classifier_packets_survive_changed_pending_page(native, monkeypatch):
    """A changed page must consume saved packets before regrouping their cases."""
    from django.db import transaction

    from core.models import CollectionRun, Post, PostBrand, PostEnrichmentState
    from core.provider_batches import record_post_membership
    from monitor import backfill_enrichment as enrichment

    job, _, _, _ = native
    run = CollectionRun.objects.get(job=job)

    def add_members(ids):
        for identifier in ids:
            post = Post.objects.create(
                tweet_id=identifier, text="I tried Qwen today.", lang="en"
            )
            PostBrand.objects.create(post=post, brand_id="qwen")
            PostEnrichmentState.objects.create(post=post)
        with transaction.atomic():
            record_post_membership(run, None, ids)

    add_members([f"native-{i:02}" for i in range(3, 23)])
    provider = DirectProvider()
    run_direct(native, provider, initial=True, concurrency=32)
    # The final two-case packet can already publish; preserve those complete
    # Posts while the earlier twenty-case packet remains ready for replay.
    complete = list(Post.objects.order_by("pk").values_list("pk", flat=True))[20:]
    _, _, missing = enrichment.prepare_page(
        job, complete, native[1], delegates=native[2]
    )
    assert not missing
    before = list(Post.objects.filter(pk__in=complete).order_by("pk").values())
    saved = list(
        OriginalContentCall.objects.filter(
            stage="classification",
            state="completed",
            import_state="pending",
        ).values_list("pk", "response_hash")
    )
    assert saved
    unused = OriginalContentCall.objects.filter(
        stage="classification",
        member_post_ids=complete,
        import_state="applied",
    ).first()
    assert unused is not None
    # A retained reply for already-complete members must not block fresh work,
    # and must not be cleared just to make admission succeed.
    unused.import_state = "pending"
    unused.save(update_fields=["import_state"])
    sent = provider.sent

    # BEFORE: this earlier ID shifts the classifier's twenty-case packets and
    # admission refuses buying the already completed overlapping member work.
    add_members(["native-0"])
    original_register = enrichment._register_requests

    def register(job, requests, *args, **kwargs):
        assert (
            PostEnrichmentState.objects.exclude(pk="native-0")
            .filter(
                translation_status="succeeded",
                classification_status="succeeded",
            )
            .count()
            == 22
        )
        assert all(r["context"]["post_ids"] == ["native-0"] for r in requests)
        return original_register(job, requests, *args, **kwargs)

    monkeypatch.setattr(enrichment, "_register_requests", register)
    for _ in range(5):
        result = run_direct(native, provider, concurrency=32)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed", json.dumps(result)
    assert result["cohort_count"] == 23
    assert result["persisted_output_invalid_count"] == 0
    assert provider.sent == sent + 4  # Only the newly added Post needs inference.
    assert list(Post.objects.filter(pk__in=complete).order_by("pk").values()) == before
    unused.refresh_from_db()
    assert unused.import_state == "pending"
    for identifier, response_hash in saved:
        call = OriginalContentCall.objects.get(pk=identifier)
        assert call.import_state == "applied"
        assert call.response_hash == response_hash


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

    monkeypatch.setenv("DEEPINFRA_API_KEY", "scheduled-must-not-be-used")
    monkeypatch.setenv("DEEPINFRA_ON_DEMAND", "on-demand-fixture")
    monkeypatch.setattr(backfill, "load_config", lambda path: cfg)
    def on_demand_factory(**kwargs):
        assert kwargs["api_key"] == "on-demand-fixture"
        return provider.factory(**kwargs)

    monkeypatch.setattr(direct, "DeepInfraChatCompletionsClient", on_demand_factory)
    monkeypatch.setattr(direct, "ThreadPoolExecutor", executor)
    monkeypatch.setattr(
        enrichment,
        "build_translator_client_from_env",
        lambda cfg, *, deepinfra_key_env: delegates["translation"],
    )
    monkeypatch.setattr(
        enrichment,
        "build_classifier_client_from_env",
        lambda cfg, *, deepinfra_key_env: delegates["classification"],
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
    monkeypatch.delenv("DEEPINFRA_ON_DEMAND")
    monkeypatch.delenv("DEEPINFRA_API_KEY")
    call_command(
        "backfill",
        collection_job=str(job.pk),
        enrich_direct=True,
        status=True,
        stdout=StringIO(),
    )
    assert provider.sent == sent


def test_command_requires_on_demand_key_before_paid_admission(native, monkeypatch):
    from django.core.management.base import CommandError

    import monitor.backfill_enrichment as enrichment
    from monitor.management.commands import backfill

    monkeypatch.setenv("DEEPINFRA_API_KEY", "scheduled-must-not-be-used")
    monkeypatch.delenv("DEEPINFRA_ON_DEMAND", raising=False)
    monkeypatch.setattr(backfill, "load_config", lambda path: native[1])

    def forbidden(*args, **kwargs):
        raise AssertionError("Missing backfill key must be rejected before admission")

    monkeypatch.setattr(enrichment, "execute_enrichment", forbidden)
    with pytest.raises(CommandError, match="DEEPINFRA_ON_DEMAND"):
        call_command("backfill", collection_job=str(native[0].pk), enrich_direct=True)
    assert not OriginalContentCall.objects.exists()
    assert not ProviderBatch.objects.exists()


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
    first_wave = [0]
    from x_monitor.deepinfra import GEMMA_4_31B_MODEL

    def simultaneous(body, timeout):
        assert connection.connection is None
        if body["model"] == GEMMA_4_31B_MODEL:
            with provider.lock:
                wait = first_wave[0] < 32
                first_wave[0] += 1
            if wait:
                barrier.wait(timeout=10)
        return original(body, timeout)

    provider.transport = simultaneous
    result = run_direct(native, provider, initial=True, concurrency=32)
    assert provider.peak == 32
    assert result["direct_model_requests_sent"] == provider.sent


def test_direct_drains_ready_waves_before_repeating_database_preparation(native):
    provider = DirectProvider()
    result = run_direct(native, provider, initial=True, concurrency=1)
    assert result["model_requests_sent"] == result["model_requests_reserved"] == 6
    assert result["active_batches"] == 0
    assert provider.peak == 1
    assert run_direct(native, provider)["status"] == "completed"


def test_direct_advancement_still_bounds_total_waves_and_persists_unstarted_calls(
    native,
):
    from django.db import transaction

    from core.models import Post, PostBrand, PostEnrichmentState
    from core.provider_batches import record_post_membership
    from x_monitor.deepinfra import GEMMA_4_31B_MODEL

    job = native[0]
    ids = [f"drain-{index}" for index in range(8)]
    Post.objects.bulk_create(
        [
            Post(tweet_id=identifier, text="I tried Qwen today.", lang="en")
            for identifier in ids
        ]
    )
    PostBrand.objects.bulk_create(
        [PostBrand(post_id=identifier, brand_id="qwen") for identifier in ids]
    )
    PostEnrichmentState.objects.bulk_create(
        [PostEnrichmentState(post_id=identifier) for identifier in ids]
    )
    with transaction.atomic():
        record_post_membership(job.runs.get(), None, ids)
    provider = DirectProvider()
    run_direct(native, provider, initial=True, concurrency=1)
    group = ProviderBatch.objects.get(model=GEMMA_4_31B_MODEL)
    assert group.calls.filter(state="completed").count() == 8
    assert group.calls.filter(state="reserved").count() == 12
    assert group.state == "registered"
    assert provider.peak == 1


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


def test_invalid_cached_reply_is_retained_and_only_that_request_is_retried(native):
    from x_monitor.deepinfra import GEMMA_4_31B_MODEL

    provider = DirectProvider()
    original = provider.transport
    invalid = []

    def once(body, timeout):
        reply = original(body, timeout)
        with provider.lock:
            if body["model"] == GEMMA_4_31B_MODEL and not invalid:
                invalid.append(True)
                reply["model"] = "wrong-model"
        return reply

    provider.transport = once
    for turn in range(15):
        result = run_direct(native, provider, initial=turn == 0)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed"
    rejected = OriginalContentCall.objects.get(
        error_code="cached_response_validation_failed"
    )
    assert (
        rejected.state == "completed"
        and rejected.response_payload["model"] == "wrong-model"
    )
    attempts = OriginalContentCall.objects.filter(request_hash=rejected.request_hash)
    assert attempts.count() == 2
    assert attempts.exclude(pk=rejected.pk).get().import_state == "applied"
    assert all(call.reserved_usd > 0 for call in attempts)


def test_exhausted_translation_defers_its_packet_but_healthy_posts_finish(native):
    """Real shared callers: one poison reply must not block the next paid packet."""
    from django.db import transaction

    from core.models import Post, PostBrand, PostEnrichmentState
    from core.provider_batches import BatchAdmissionError, record_post_membership
    from monitor.backfill_enrichment import deferred_enrichment_work

    job, cfg, delegates, policy = native
    Post.objects.filter(pk="native-1").update(
        text="I tried Qwen today. Poison identifier."
    )
    ids = [f"native-{index:02}" for index in range(3, 23)]
    for identifier in ids:
        post = Post.objects.create(
            tweet_id=identifier, text="I tried Qwen today.", lang="en"
        )
        PostBrand.objects.create(post=post, brand_id="qwen")
        PostEnrichmentState.objects.create(post=post)
    with transaction.atomic():
        record_post_membership(job.runs.get(), None, ids)
    provider = DirectProvider()
    original = provider.transport

    def poison(body, timeout):
        reply = original(body, timeout)
        raw = json.dumps(body)
        if "Poison identifier" in raw and "Japanese (ja)" in raw:
            reply["model"] = "wrong-model"
        return reply

    provider.transport = poison
    for turn in range(20):
        try:
            result = execute_enrichment(
                job.pk,
                cfg=cfg,
                api_key="test",
                delegates=delegates,
                policy=policy if turn == 0 else None,
                transport="direct",
                direct_concurrency=32,
                direct_client_factory=provider.factory,
                defer_failures=True,
            )
        except BatchAdmissionError as exc:
            assert str(exc) == "model_attempt_allowance_exhausted"
            continue
        if result["actionable_pending_count"] == 0:
            break
    assert result["status"] == "partial", result
    assert result["cohort_count"] == 22 and result["pending_count"] == 1
    assert result["actionable_pending_count"] == 0
    deferred = deferred_enrichment_work(job, max_attempts=3)
    assert deferred["native-1"] == "model_attempt_allowance_exhausted"
    assert len(deferred) == 1
    assert PostEnrichmentState.objects.exclude(pk__in=deferred).filter(
        translation_status="succeeded",
        classification_status="succeeded",
    ).count() == 22 - len(deferred)
    rejected = OriginalContentCall.objects.filter(
        error_code="cached_response_validation_failed",
    )
    assert rejected.count() == 3
    assert rejected.values("request_hash").distinct().count() == 1
    saved = list(
        OriginalContentCall.objects.filter(state="completed").values_list(
            "pk", "response_hash"
        )
    )
    sent = provider.sent
    again = execute_enrichment(
        job.pk,
        cfg=cfg,
        api_key="test",
        delegates=delegates,
        transport="direct",
        direct_concurrency=32,
        direct_client_factory=provider.factory,
        defer_failures=True,
    )
    assert again["pending_count"] == result["pending_count"] and provider.sent == sent
    assert (
        list(
            OriginalContentCall.objects.filter(state="completed").values_list(
                "pk", "response_hash"
            )
        )
        == saved
    )


def test_aggregate_deferral_never_resends_an_unknown_paid_request(native):
    from monitor.backfill_enrichment import deferred_enrichment_work

    provider = DirectProvider()

    def timeout(body, seconds):
        provider.sent += 1
        raise TimeoutError("lost reply")

    provider.transport = timeout
    run_direct(native, provider, initial=True)
    # Drain only reservations that had never been sent; unknown calls stay intact.
    for _ in range(4):
        execute_enrichment(
            native[0].pk,
            cfg=native[1],
            api_key="test",
            delegates=native[2],
            transport="direct",
            direct_concurrency=32,
            direct_client_factory=provider.factory,
            defer_failures=True,
        )
    sent = provider.sent
    execute_enrichment(
        native[0].pk,
        cfg=native[1],
        api_key="test",
        delegates=native[2],
        transport="direct",
        direct_concurrency=32,
        direct_client_factory=provider.factory,
        defer_failures=True,
    )
    assert provider.sent == sent
    assert set(deferred_enrichment_work(native[0], max_attempts=3)) == {
        "native-1",
        "native-2",
    }
    assert OriginalContentCall.objects.filter(
        state="ambiguous", actual_usd=None
    ).exists()


def test_final_assessment_records_incomplete_without_changing_source_receipt(native):
    from core.collection_capture import (
        archive_legacy,
        read_document,
        run_report_document,
    )
    from scripts.backfill_campaign import assess_campaign

    job, cfg, _, _ = native
    run = job.runs.get()
    source = {"report": {"preserve": "source receipt"}}
    run.legacy_archive = archive_legacy(source)
    run.save(update_fields=["legacy_archive"])
    original = (run.legacy_archive_id, bytes(run.legacy_archive.body))
    job.last_attempt = run
    job.save(update_fields=["last_attempt"])
    window = {"index": 1}
    frozen = {"campaign": job.job_key.rsplit("/", 1)[0], "windows": [window]}
    result = assess_campaign(
        frozen, cfg, [{"status": "deferred", "error_code": "test_failure", "source_collection_job": str(job.pk)}]
    )
    assert result["status"] == "incomplete"
    assert result["windows_attempted"] == 1 and result["windows_verified"] == 0
    run.refresh_from_db()
    assert (run.legacy_archive_id, bytes(run.legacy_archive.body)) == original
    assert read_document(run.legacy_archive) == source
    report = run_report_document(run)
    assert report["preserve"] == "source receipt"
    assert report["backfill_campaign"]["latest"]["status"] == "failed"


def test_saved_packet_replays_exact_submitted_catalog_after_catalog_changes(native):
    from core.models import Brand, BrandSearchTerm
    from monitor.cycle import _classification_tracked_brand_catalog

    provider = DirectProvider()
    run_direct(native, provider, initial=True)
    saved = list(
        OriginalContentCall.objects.filter(
            stage="classification", state="completed", import_state="pending"
        )
    )
    assert len(saved) == 2
    original_revision = json.loads(
        next(
            m["content"]
            for m in saved[0].request_packet["messages"]
            if m["role"] == "user"
        )
    )["tracked_brands"]["revision"]
    BrandSearchTerm.objects.create(brand_id="qwen", term="fresh-catalog-alias")
    Brand.objects.create(nickname="catalog-added", display_name="A later brand")
    from x_monitor.attribution import _tracked_brand_catalog

    assert (
        _tracked_brand_catalog(
            [], [{"tracked_brand_catalog": _classification_tracked_brand_catalog()}]
        )["revision"]
        != original_revision
    )
    sent = provider.sent
    result = run_direct(native, provider)
    assert result["status"] == "completed", result
    assert provider.sent == sent
    for call in saved:
        retained = OriginalContentCall.objects.get(pk=call.pk)
        assert (
            retained.import_state == "applied"
            and retained.response_hash == call.response_hash
        )


def test_saved_packet_rejects_changed_source_before_publication_or_payment(native):
    from core.models import Post
    from core.provider_batches import BatchAdmissionError

    provider = DirectProvider()
    run_direct(native, provider, initial=True)
    sent = provider.sent
    Post.objects.filter(pk="native-1").update(text="A changed source must be reviewed.")
    with pytest.raises(
        BatchAdmissionError, match="saved_classifier_packet_source_changed"
    ):
        run_direct(native, provider)
    assert provider.sent == sent


def test_partial_saved_packet_repairs_only_incomplete_members_without_payment(native):
    from django.db import transaction

    from core.models import (
        Post,
        PostBrand,
        PostBrandClassificationState,
        PostEnrichmentState,
    )
    from core.provider_batches import record_post_membership

    ids = [f"partial-{i:02}" for i in range(20)]
    for identifier in ids:
        post = Post.objects.create(
            tweet_id=identifier, text="I tried Qwen today.", lang="en"
        )
        PostBrand.objects.create(post=post, brand_id="qwen")
        PostEnrichmentState.objects.create(post=post)
    with transaction.atomic():
        record_post_membership(native[0].runs.get(), None, ids)
    provider = DirectProvider()
    for turn in range(8):
        result = run_direct(native, provider, initial=turn == 0, concurrency=32)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed"
    packet = (
        OriginalContentCall.objects.filter(
            stage="classification", member_post_ids__len=20
        )
        .first()
        .member_post_ids
    )
    repaired = packet[:2]
    # A member can need translation while its classification is already valid.
    # Replaying the packet must preserve that classification too.
    PostEnrichmentState.objects.filter(pk=packet[2]).update(
        translation_status="pending"
    )
    PostEnrichmentState.objects.filter(pk__in=repaired).update(
        classification_status="pending"
    )
    PostBrandClassificationState.objects.filter(post_id__in=repaired).update(
        selected_final_judgment=None
    )
    OriginalContentCall.objects.filter(
        stage="classification", member_post_ids=packet
    ).update(import_state="pending")
    unchanged_posts = list(
        Post.objects.exclude(pk__in=repaired).order_by("pk").values()
    )
    unchanged_states = list(
        PostBrandClassificationState.objects.exclude(post_id__in=repaired)
        .order_by("pk")
        .values()
    )
    saved = list(
        OriginalContentCall.objects.filter(
            stage="classification", member_post_ids=packet
        ).values_list("pk", "response_hash")
    )
    sent = provider.sent
    result = run_direct(native, provider, concurrency=32)
    assert result["status"] == "completed", result
    assert provider.sent == sent
    assert (
        list(Post.objects.exclude(pk__in=repaired).order_by("pk").values())
        == unchanged_posts
    )
    assert (
        list(
            PostBrandClassificationState.objects.exclude(post_id__in=repaired)
            .order_by("pk")
            .values()
        )
        == unchanged_states
    )
    for pk, response_hash in saved:
        call = OriginalContentCall.objects.get(pk=pk)
        assert call.import_state == "applied" and call.response_hash == response_hash


def test_older_saved_attempt_remains_replayable_after_newer_attempt_fails(native):
    import copy
    from datetime import timedelta

    from core.provider_batches import digest

    provider = DirectProvider()
    run_direct(native, provider, initial=True)
    saved = list(OriginalContentCall.objects.filter(stage="classification"))
    assert len(saved) == 2
    newer = []
    for original in saved:
        call = copy.deepcopy(original)
        call.pk = None
        call.request_identity = (
            "newer-attempt-" + original.provenance["context"]["role"]
        )
        call.batch_key = original.batch_key + ":newer"
        call.reserved_at += timedelta(microseconds=1)
        call.provenance["attempt"] = 2
        if call.provenance["context"]["role"] == "content":
            body = call.response_payload
            value = json.loads(body["choices"][0]["message"]["content"])
            value["decisions"]["D01"]["post_types"] = ["invalid-post-type"]
            body["choices"][0]["message"]["content"] = json.dumps(value)
            call.response_hash = digest(body)
        call.save(force_insert=True)
        newer.append(call.pk)
    sent = provider.sent
    # A newer invalid reply must not abort before an older paid reply can repair
    # the remaining member in the same original positional packet.
    for _ in range(3):
        result = run_direct(native, provider)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed", result
    assert provider.sent == sent
    assert (
        OriginalContentCall.objects.filter(pk__in=newer, import_state="error").count()
        == 2
    )
    for original in saved:
        call = OriginalContentCall.objects.get(pk=original.pk)
        assert (
            call.import_state == "applied"
            and call.response_hash == original.response_hash
        )


def test_unknown_group_does_not_block_new_independent_members(native):
    from django.db import transaction

    from core.models import Post, PostBrand, PostEnrichmentState
    from core.provider_batches import record_post_membership

    provider = DirectProvider()
    normal = provider.transport

    def timeout(body, seconds):
        provider.sent += 1
        raise TimeoutError("lost original reply")

    provider.transport = timeout
    run_direct(native, provider, initial=True, concurrency=32)
    unknown = list(
        OriginalContentCall.objects.filter(state="ambiguous").values_list(
            "pk", "reserved_usd"
        )
    )
    assert unknown
    post = Post.objects.create(
        tweet_id="independent", text="I tried Qwen today.", lang="en"
    )
    PostBrand.objects.create(post=post, brand_id="qwen")
    PostEnrichmentState.objects.create(post=post)
    with transaction.atomic():
        record_post_membership(native[0].runs.get(), None, [post.pk])
    provider.transport = normal
    for _ in range(8):
        result = execute_enrichment(
            native[0].pk,
            cfg=native[1],
            api_key="test",
            delegates=native[2],
            transport="direct",
            direct_concurrency=32,
            direct_client_factory=provider.factory,
            defer_failures=True,
        )
        if result["actionable_pending_count"] == 0:
            break
    state = PostEnrichmentState.objects.get(pk=post.pk)
    assert state.translation_status == state.classification_status == "succeeded"
    assert result["pending_count"] == 2 and result["status"] == "partial"
    assert (
        list(
            OriginalContentCall.objects.filter(state="ambiguous").values_list(
                "pk", "reserved_usd"
            )
        )
        == unknown
    )
    assert OriginalContentCall.objects.filter(
        state="ambiguous", actual_usd=None
    ).count() == len(unknown)
