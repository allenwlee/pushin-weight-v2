"""Real shared callers and PostgreSQL publishers with a fake native provider."""

import json
from datetime import timedelta
from io import StringIO
from pathlib import Path
from typing import ClassVar
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.db import connection, transaction
from django.db.models import Sum
from django.utils import timezone

from core.models import (
    CollectionObservation,
    CollectionRun,
    CollectionScopeRun,
    OriginalContentCall,
    Post,
    PostBrand,
    PostEnrichmentState,
    ProviderBatch,
)
from core.provider_batches import record_post_membership
from monitor.backfill_enrichment import (
    adopt_completed_membership,
    execute_enrichment,
    policy_snapshot,
)
from tests.test_backfill_collection import ready_job
from tests.test_u18_runtime_0731 import FixedSlotTransport
from x_monitor.config import load_config
from x_monitor.deepinfra import (
    DEEPSEEK_0731_MODEL,
    GEMMA_4_31B_MODEL,
    DeepInfraChatCompletionsClient,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


class NativeProvider:
    files: ClassVar[dict] = {}
    batches: ClassVar[dict] = {}
    submissions: ClassVar[list] = []

    def __init__(self, *, api_key, before_request):
        self.before = before_request

    def request(self, method, path):
        assert not connection.in_atomic_block
        self.before(method, path)
        assert not connection.in_atomic_block

    def upload(self, content):
        self.request("POST", "/files")
        identifier = "file-" + uuid4().hex
        self.files[identifier] = [json.loads(line) for line in content.splitlines()]
        return {"id": identifier}

    def submit(self, file_id, *, identity):
        self.request("POST", "/batches")
        assert OriginalContentCall.objects.filter(state="sent").exists()
        self.submissions.append(file_id)
        identifier = "batch-" + uuid4().hex
        self.batches[identifier] = {
            "id": identifier,
            "input_file_id": file_id,
            "status": "completed",
            "output_file_id": file_id,
            "metadata": {"request_identity": identity},
        }
        return self.batches[identifier]

    def retrieve(self, batch_id):
        self.request("GET", "/batches/" + batch_id)
        return self.batches[batch_id]

    def list_batches(self, *, after=None):
        self.request("GET", "/batches")
        return {"data": list(self.batches.values()), "has_more": False}

    def outputs(self, file_id):
        self.request("GET", "/files/" + file_id + "/content")
        for row in reversed(self.files[file_id]):
            body = row["body"]
            if body["model"] == GEMMA_4_31B_MODEL:
                prompt = next(
                    m["content"] for m in body["messages"] if m["role"] == "user"
                )
                content = (
                    "テスト翻訳です。"
                    if "Japanese (ja)" in json.dumps(body)
                    else "这是测试译文。"
                )
                if body["max_tokens"] == 16:
                    content = "en"
                elif "CHUNK:\n" in prompt:
                    content = prompt.split("CHUNK:\n", 1)[1].replace("alpha", "译文")
            else:
                system = next(
                    m["content"] for m in body["messages"] if m["role"] == "system"
                )
                messages = [m for m in body["messages"] if m["role"] == "user"]
                content = json.dumps(
                    FixedSlotTransport().messages_create(
                        system=system, messages=messages
                    )
                )
            yield {
                "custom_id": row["custom_id"],
                "response": {
                    "status_code": 200,
                    "body": {
                        "model": body["model"],
                        "choices": [
                            {"finish_reason": "stop", "message": {"content": content}}
                        ],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    },
                },
                "error": None,
            }


@pytest.fixture
def native(monkeypatch, seeded_policy_keywords):
    call_command("seed_i18n_labels", stdout=StringIO())
    job = ready_job()
    cfg = load_config(Path("config.yaml"))
    cfg.llm.literal_translation_v2_enabled = True
    NativeProvider.files, NativeProvider.batches, NativeProvider.submissions = (
        {},
        {},
        [],
    )
    run = CollectionRun.objects.create(
        source=job.source,
        job=job,
        purpose="content",
        ingestion_key="a" * 64,
        lease_token=uuid4(),
        lease_expires_at=timezone.now() + timedelta(minutes=5),
    )
    for identifier in ["native-1", "native-2"]:
        post = Post.objects.create(
            tweet_id=identifier, text="I tried Qwen today.", lang="en"
        )
        PostBrand.objects.create(post=post, brand_id="qwen")
        PostEnrichmentState.objects.create(post=post)
    with transaction.atomic():
        record_post_membership(run, None, ["native-1", "native-2"])

    def forbidden(*args, **kwargs):
        raise AssertionError("native enrichment used direct inference or X")

    monkeypatch.setattr("x_monitor.apify.TwitterApiClient.from_env", forbidden)
    delegates = {
        "translation": DeepInfraChatCompletionsClient(
            api_key="test",
            model=GEMMA_4_31B_MODEL,
            request_profile="gemma4_translation_v1",
            transport=forbidden,
        ),
        "classification": DeepInfraChatCompletionsClient(
            api_key="test",
            model=DEEPSEEK_0731_MODEL,
            request_profile="deepseek_0731",
            transport=forbidden,
        ),
    }
    policy = policy_snapshot(max_usd="5", deadline=timezone.now() + timedelta(hours=72))
    return job, cfg, delegates, policy


def advance(native, *, initial=False):
    job, cfg, delegates, policy = native
    ProviderBatch.objects.filter(source_collection_job=job).update(
        next_poll_at=timezone.now()
    )
    return execute_enrichment(
        job.pk,
        cfg=cfg,
        delegates=delegates,
        policy=policy if initial else None,
        api_key="test",
        client_factory=NativeProvider,
    )


def test_native_submit_restart_import_and_publish_without_duplicate_model_calls(native):
    first = advance(native, initial=True)
    assert first["model_requests_sent"] == 6 and first["active_batches"] == 2
    assert not Post.objects.exclude(text_en=None).exists()
    assert not PostEnrichmentState.objects.exclude(claim_owner="").exists()
    second = advance(native)
    assert second["pending_count"] == 0 and second["status"] == "completed"
    assert second["model_requests_sent"] == 6 and second["control_requests"] == 8
    assert second["cost_unknown_requests"] == 6
    from monitor.post_artifacts import literal_translation_artifact_complete

    assert all(literal_translation_artifact_complete(p) for p in Post.objects.all())
    assert not OriginalContentCall.objects.exclude(import_state="applied").exists()
    third = advance(native)
    assert third["model_requests_sent"] == 6 and len(NativeProvider.submissions) == 2


def test_real_management_command_uses_only_native_provider_and_read_only_status(
    native, monkeypatch
):
    import monitor.backfill_enrichment as enrichment
    from monitor.management.commands import backfill

    job, cfg, delegates, _ = native
    monkeypatch.setenv("DEEPINFRA_API_KEY", "test-only")
    monkeypatch.setattr(backfill, "load_config", lambda path: cfg)
    monkeypatch.setattr(enrichment, "DeepInfraBatchClient", NativeProvider)
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
        enrich_native=True,
        enrichment_max_usd="5",
        enrichment_deadline=(timezone.now() + timedelta(hours=72)).isoformat(),
        stdout=output,
    )
    first = json.loads(output.getvalue())
    assert first["model_requests_sent"] == 6 and first["twitterapi_requests"] == 0
    before = first["control_requests"]
    output = StringIO()
    call_command(
        "backfill",
        collection_job=str(job.pk),
        enrich_native=True,
        status=True,
        stdout=output,
    )
    assert json.loads(output.getvalue())["control_requests"] == before


def test_verified_pilot_expands_cohort_without_reprocessing_controls_or_resetting_cost(
    native,
):
    from monitor.backfill_enrichment import finish_pilot

    job, cfg, _, policy = native
    policy["selection"] = ["native-1", "native-2"]
    advance(native, initial=True)
    assert advance(native)["status"] == "completed"
    before = OriginalContentCall.objects.aggregate(n=Sum("reserved_usd"))["n"]
    post = Post.objects.create(
        tweet_id="native-3", text="I tried Qwen today.", lang="en"
    )
    PostBrand.objects.create(post=post, brand_id="qwen")
    PostEnrichmentState.objects.create(post=post)
    with transaction.atomic():
        record_post_membership(job.runs.get(), None, [post.pk])
    finish_pilot(job.pk, cfg=cfg)
    assert OriginalContentCall.objects.aggregate(n=Sum("reserved_usd"))["n"] == before
    assert advance(native)["model_requests_sent"] == 10
    assert advance(native)["status"] == "completed"
    assert (
        OriginalContentCall.objects.filter(
            member_post_ids__overlap=["native-1", "native-2"]
        ).count()
        == 6
    )


def test_completed_flags_cannot_mask_missing_persisted_outputs(native):
    PostEnrichmentState.objects.update(
        translation_status="succeeded", classification_status="succeeded"
    )
    result = advance(native, initial=True)
    assert result["status"] == "partial" and result["pending_count"] == 2
    assert result["model_requests_sent"] == 6
    assert advance(native)["status"] == "completed"


def test_new_brand_reopens_classification_and_preserves_valid_translation(native):
    from monitor.backfill_enrichment import reopen_incomplete_successes

    job, _, _, _ = native
    advance(native, initial=True)
    assert advance(native)["status"] == "completed"
    PostBrand.objects.create(post_id="native-1", brand_id="glm")
    reopen_incomplete_successes(
        job, CollectionObservation.objects.filter(post_id="native-1")
    )
    state = PostEnrichmentState.objects.get(pk="native-1")
    assert (
        state.translation_status == "succeeded"
        and state.classification_status == "pending"
    )
    assert advance(native)["model_requests_sent"] == 8
    assert advance(native)["status"] == "completed"
    assert OriginalContentCall.objects.filter(stage="translation").count() == 4


def test_real_native_http_transport_admission_submit_and_import_reach_publishers(
    native,
):
    from urllib.parse import urlsplit

    from x_monitor.deepinfra_batch import DeepInfraBatchClient

    server = NativeProvider(api_key="test", before_request=lambda *args: None)

    class Response:
        status_code = 200
        headers: ClassVar[dict] = {}

        def __init__(self, body):
            self.body = body

        def iter_content(self, chunk_size):
            yield self.body

        def close(self):
            pass

    class Session:
        def request(self, method, url, **kwargs):
            path = urlsplit(url).path.removeprefix("/v1/openai")
            assert not connection.in_atomic_block
            assert ProviderBatch.objects.filter(control_requests__gt=0).exists()
            if path == "/files":
                result = server.upload(kwargs["files"]["file"][1])
            elif path == "/batches":
                body = kwargs["json"]
                result = server.submit(
                    body["input_file_id"], identity=body["metadata"]["request_identity"]
                )
            elif path.startswith("/batches/"):
                result = server.retrieve(path.rsplit("/", 1)[1])
            else:
                rows = server.outputs(path.split("/")[2])
                return Response(
                    b"".join(json.dumps(row).encode() + b"\n" for row in rows)
                )
            return Response(json.dumps(result).encode())

    def factory(**kwargs):
        return DeepInfraBatchClient(**kwargs, session=Session())

    job, cfg, delegates, policy = native
    first = execute_enrichment(
        job.pk,
        cfg=cfg,
        delegates=delegates,
        policy=policy,
        api_key="test",
        client_factory=factory,
    )
    assert first["model_requests_sent"] == 6
    ProviderBatch.objects.update(next_poll_at=timezone.now())
    second = execute_enrichment(
        job.pk, cfg=cfg, delegates=delegates, api_key="test", client_factory=factory
    )
    assert second["status"] == "completed" and second["control_requests"] == 8


def test_legacy_completed_collection_membership_is_adopted_without_rewriting_outcome(
    native,
):
    job, _, _, _ = native
    run = job.runs.get()
    CollectionObservation.objects.filter(run=run).delete()
    PostEnrichmentState.objects.update(source_collection_job=None)
    CollectionScopeRun.objects.create(
        run=run,
        scope_key="legacy",
        scope_kind="x_query",
        ownership={},
        envelopes=[
            {
                "post_ids": ["native-1", "native-2"],
                "observed_at": timezone.now().isoformat(),
            }
        ],
    )
    run.status, run.completed_at = "success", timezone.now()
    run.report = {
        "collection_drained": True,
        "recovered_post_ids": ["native-1", "native-2"],
    }
    run.save()
    job.state, job.last_success = "completed", run
    job.next_due_at, job.next_retry_at = None, None
    job.save()
    assert advance(native, initial=True)["model_requests_sent"] == 6
    job.refresh_from_db()
    run.refresh_from_db()
    assert (
        job.state == "completed"
        and run.status == "success"
        and run.report["collection_drained"]
    )
    assert (
        CollectionObservation.objects.filter(
            run=run, source_subject_kind="post"
        ).count()
        == 2
    )


def test_typed_membership_resume_does_not_load_oversized_legacy_receipt(native):
    job, _, _, _ = native
    run = job.runs.get()
    run.status, run.completed_at = "success", timezone.now()
    run.report = {
        "post_membership": {"version": 1, "distinct_posts": 2},
        "recovered_post_ids": ["unused-legacy-array"] * 100001,
    }
    run.save()
    job.state, job.last_success = "completed", run
    job.next_due_at, job.next_retry_at = None, None
    job.save()
    job.refresh_from_db()

    def forbid_full_report(execute, sql, params, many, context):
        if '"collection_runs"."report"' in sql:
            assert "->" in sql, "typed resume materialized the complete receipt"
        return execute(sql, params, many, context)

    with connection.execute_wrapper(forbid_full_report):
        adopt_completed_membership(job)
    assert CollectionObservation.objects.filter(run=run, post__isnull=False).count() == 2
    assert not OriginalContentCall.objects.exists()


def test_typed_membership_count_drift_is_refused_before_provider_work(native):
    from core.provider_batches import BatchAdmissionError

    job, _, _, _ = native
    run = job.runs.get()
    run.status, run.completed_at = "success", timezone.now()
    run.report = {"post_membership": {"version": 1, "distinct_posts": 3}}
    run.save()
    job.state, job.last_success = "completed", run
    job.next_due_at, job.next_retry_at = None, None
    job.save()
    with pytest.raises(BatchAdmissionError, match="typed_membership_count_changed"):
        adopt_completed_membership(job)
    assert not OriginalContentCall.objects.exists()


def test_database_pin_prevents_writes_and_provider_calls(native):
    from core.provider_batches import BatchAdmissionError

    job, _, _, _ = native
    job.definition["scope"]["database"] = {"name": "wrong", "user": "wrong"}
    job.save(update_fields=["definition"])
    with pytest.raises(BatchAdmissionError, match="database_identity_mismatch"):
        advance(native, initial=True)
    assert not ProviderBatch.objects.exists() and NativeProvider.submissions == []


def test_source_change_between_preparation_and_reservation_stops_before_http(native):
    from core.provider_batches import BatchAdmissionError
    from monitor.backfill_enrichment import _register_requests, prepare_page

    job, cfg, delegates, policy = native
    requests, _, _ = prepare_page(
        job, ["native-1", "native-2"], cfg, delegates=delegates
    )
    Post.objects.filter(pk="native-1").update(text="Changed after preparation.")
    with pytest.raises(BatchAdmissionError, match="source_changed_before_reservation"):
        _register_requests(job, requests, policy, cfg)
    assert (
        not ProviderBatch.objects.exists() and not OriginalContentCall.objects.exists()
    )
    assert NativeProvider.submissions == []


def test_failed_result_duplicates_and_interrupted_import_resume_without_duplicate_charge(
    native, monkeypatch
):
    from x_monitor.deepinfra_batch import BatchTransportError

    original = NativeProvider.outputs
    failed = set()

    def stream(self, file_id):
        for output in original(self, file_id):
            if not failed:
                failed.add(output["custom_id"])
                output = output | {
                    "response": {"status_code": 500},
                    "error": {"code": "fixture"},
                }
                yield output
                yield output
                raise BatchTransportError("interrupted_after_error_receipt")
            if output["custom_id"] in failed:
                output = output | {
                    "response": {"status_code": 500},
                    "error": {"code": "fixture"},
                }
            yield output

    monkeypatch.setattr(NativeProvider, "outputs", stream)
    advance(native, initial=True)
    second = advance(native)
    assert second["model_requests_sent"] == 6
    third = advance(native)
    assert third["model_requests_sent"] == 7
    assert advance(native)["status"] == "completed"


def test_ambiguous_submission_reconciles_without_second_paid_send(native, monkeypatch):
    from x_monitor.deepinfra_batch import BatchTransportError

    original = NativeProvider.submit

    def accepted_but_interrupted(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise BatchTransportError("accepted_before_connection_failed")

    monkeypatch.setattr(NativeProvider, "submit", accepted_but_interrupted)
    first = advance(native, initial=True)
    assert first["model_requests_sent"] == 6
    assert ProviderBatch.objects.filter(state="ambiguous").count() == 2
    monkeypatch.setattr(NativeProvider, "submit", original)
    second = advance(native)
    assert second["active_batches"] == 2 and len(NativeProvider.submissions) == 2
    third = advance(native)
    assert third["status"] == "completed" and third["model_requests_sent"] == 6


def test_expired_post_lease_and_historical_age_do_not_admit_live_duplicate(native):
    from monitor.cycle import _claim_enrichment_states

    _job, cfg, _, _ = native
    advance(native, initial=True)
    PostEnrichmentState.objects.update(
        created_at=timezone.now() - timedelta(days=90),
        claim_expires_at=timezone.now() - timedelta(seconds=1),
    )
    live = _claim_enrichment_states(cfg=cfg.harvest.enrichment, run_id="live")
    assert not live.states and live.quarantined == 0
    assert PostEnrichmentState.objects.filter(translation_status="pending").count() == 2
    assert advance(native)["status"] == "completed"


def test_changed_source_cannot_publish_old_waiting_outputs(native):
    advance(native, initial=True)
    Post.objects.filter(pk="native-1").update(text="Qwen changed after submission.")
    result = advance(native)
    assert result["status"] == "partial"
    assert OriginalContentCall.objects.filter(
        member_post_ids__contains=["native-1"], import_state="stale"
    ).exists()
    assert not Post.objects.exclude(text_en=None).exists()


def test_partial_output_preserves_returned_requests_and_retries_only_missing(
    native, monkeypatch
):
    original = NativeProvider.outputs
    omitted = set()

    def partial(self, file_id):
        for output in original(self, file_id):
            if not omitted and output["response"]["body"]["model"] == GEMMA_4_31B_MODEL:
                omitted.add(output["custom_id"])
                continue
            yield output

    monkeypatch.setattr(NativeProvider, "outputs", partial)
    advance(native, initial=True)
    second = advance(native)
    assert second["model_requests_sent"] == 7 and second["status"] == "partial"
    monkeypatch.setattr(NativeProvider, "outputs", original)
    third = advance(native)
    assert third["status"] == "completed" and third["model_requests_sent"] == 7
    assert OriginalContentCall.objects.filter(state="failed").count() == 1


def test_duplicate_shuffled_results_are_idempotent(native, monkeypatch):
    original = NativeProvider.outputs

    def duplicates(self, file_id):
        for output in original(self, file_id):
            yield output
            yield output

    monkeypatch.setattr(NativeProvider, "outputs", duplicates)
    advance(native, initial=True)
    assert advance(native)["status"] == "completed"
    assert ProviderBatch.objects.aggregate(n=Sum("imported_count"))["n"] == 6


def test_long_posts_and_unknown_language_make_progress_in_dependent_waves(native):
    from core.models import PostTranslationChunk

    Post.objects.filter(pk="native-1").update(text="alpha " * 2100, lang="en")
    Post.objects.filter(pk="native-2").update(lang=None)
    first = advance(native, initial=True)
    assert first["model_requests_sent"] > 10
    for _ in range(5):
        result = advance(native)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed"
    assert PostTranslationChunk.objects.filter(post_id="native-1").count() > 10
    assert not PostEnrichmentState.objects.exclude(claim_owner="").exists()


@pytest.mark.parametrize("days", [30, 90])
def test_month_scale_cohort_reads_are_bounded_and_untouched_debt_survives(
    native, monkeypatch, days
):
    from django.test.utils import CaptureQueriesContext

    import monitor.backfill_enrichment as enrichment
    from monitor.cycle import _claim_enrichment_states

    job, cfg, _, _ = native
    run = job.runs.get()
    posts = [
        Post(
            tweet_id=f"month-{i:05}",
            text="Qwen update",
            lang="en",
            created_at=timezone.now() - timedelta(days=(i % days)),
        )
        for i in range(days * 100)
    ]
    Post.objects.bulk_create(posts, batch_size=100)
    PostEnrichmentState.objects.bulk_create(
        [PostEnrichmentState(post=p) for p in posts], batch_size=100
    )
    for offset in range(0, len(posts), 100):
        with transaction.atomic():
            record_post_membership(
                run, None, [p.pk for p in posts[offset : offset + 100]]
            )
    PostEnrichmentState.objects.update(created_at=timezone.now() - timedelta(days=days))
    page_sizes = []

    def capture_page(job, ids, cfg, **kwargs):
        page_sizes.append(len(ids))
        return [], {}, True

    monkeypatch.setattr(enrichment, "prepare_page", capture_page)
    with CaptureQueriesContext(connection) as queries:
        result = advance(native, initial=True)
    assert len(page_sizes) == 20 and max(page_sizes) <= 100
    assert len(queries) < 120
    assert (
        result["cohort_count"] == days * 100 + 2 and result["model_requests_sent"] == 0
    )
    assert not _claim_enrichment_states(
        cfg=cfg.harvest.enrichment, run_id="live"
    ).states
    assert (
        PostEnrichmentState.objects.filter(translation_status="pending").count()
        == days * 100 + 2
    )
    assert not PostEnrichmentState.objects.exclude(translation_attempts=0).exists()
