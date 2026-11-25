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
    import monitor.backfill_enrichment as enrichment

    monkeypatch.setattr(enrichment, "_saved_replay_cooldowns", {})
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
        job=job,
        ingestion_key="a" * 64,
        lease_token=uuid4(),
        lease_expires_at=timezone.now() + timedelta(minutes=5),
    )
    for identifier in ["native-1", "native-2"]:
        post = Post.objects.create(
            tweet_id=identifier, text="I tried Qwen today.", lang="en"
        )
        PostBrand.objects.create(post=post, brand_id="qwen")
        PostEnrichmentState.objects.create(post=post, translation_requested=True)
    with transaction.atomic():
        record_post_membership(run, None, ["native-1", "native-2"])

    def forbidden(*args, **kwargs):
        raise AssertionError("native enrichment used direct inference or X")

    monkeypatch.setattr("x_monitor.x_client.XClient.from_env", forbidden)
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


@pytest.mark.parametrize("catalog_mode", ["baseline", "compact_baseline"])
def test_native_submit_restart_import_and_publish_without_duplicate_model_calls(
    native, monkeypatch, catalog_mode,
):
    from monitor import cycle

    _, cfg, _, _ = native
    if catalog_mode != "baseline":
        cfg.llm.backfill_catalog_mode = catalog_mode
    monkeypatch.setattr(cycle, "_classification_tracked_brand_catalog", lambda: [
        {"brand_id": "qwen", "products": ["unused product"]},
    ])
    first = advance(native, initial=True)
    assert first["model_requests_sent"] == 6 and first["active_batches"] == 2
    catalogs = []
    for submitted in NativeProvider.files.values():
        for request in submitted:
            body = request["body"]
            if body["model"] != DEEPSEEK_0731_MODEL:
                continue
            packet = json.loads(next(m["content"] for m in body["messages"] if m["role"] == "user"))
            catalogs.append({brand["brand_id"]: brand for brand in packet["tracked_brands"]["brands"]})
    expected_products = [] if catalog_mode == "compact_baseline" else ["unused product"]
    assert [catalog["qwen"]["products"] for catalog in catalogs] == [expected_products] * 2
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


def test_request_recovers_paid_historical_reply_without_sending_again(native):
    from monitor.backfill_enrichment import replay_requested_saved_translation
    from monitor.cycle import CycleRunner
    from monitor.enrichment_queue import request_post_translation
    from monitor.post_artifacts import literal_translation_artifact_complete

    _job, cfg, delegates, _ = native
    advance(native, initial=True)
    # This models deployment after requests were sent and before their import.
    PostEnrichmentState.objects.update(translation_requested=False)
    advance(native)
    state = PostEnrichmentState.objects.get(pk="native-1")
    assert state.classification_status == "succeeded"
    assert OriginalContentCall.objects.filter(stage="translation", import_state="pending").exists()
    before = len(NativeProvider.submissions)
    request_post_translation("native-1")
    assert not replay_requested_saved_translation(cfg, delegates=delegates, post_ids={"native-2"})
    runner = CycleRunner(cfg=cfg, cycle_kind="enrichment", _post_fetch_clients=delegates)
    runner._run_post_fetch([], run_id="saved-replay-test", scope="continuous", fair_queue=True)
    assert literal_translation_artifact_complete(Post.objects.get(pk="native-1"))
    assert len(NativeProvider.submissions) == before


@pytest.mark.parametrize(("source", "detected", "conflicting", "physical"), [
    ("我今天试用了通义千问。", "zh-Hans", False, 1),
    ("我今天試用了通義千問。", "zh-Hant", False, 4),
    ("我今天试用了通义千问。", "zh-Hans", True, 0),
])
def test_saved_chinese_translation_uses_real_script_and_reuses_only_exact_paid_targets(
    native, monkeypatch, source, detected, conflicting, physical,
):
    from monitor.backfill_enrichment import replay_requested_saved_translation
    from monitor.cycle import CycleRunner
    from monitor.enrichment_queue import (
        HISTORICAL_SCRIPT_DEMAND,
        request_post_translation,
    )
    from monitor.post_artifacts import literal_translation_artifact_complete
    from tests.test_deepinfra import _response
    from x_monitor import literal_translation
    from x_monitor.translator import normalize_lang_detected

    _, cfg, delegates, _ = native
    Post.objects.filter(pk="native-1").update(text=source, lang="zh")
    with monkeypatch.context() as old_contract:
        old_contract.setattr(literal_translation, "_declared_source_language",
                             lambda tweet: normalize_lang_detected(tweet["source_language"]))
        advance(native, initial=True)
    PostEnrichmentState.objects.update(translation_requested=False)
    advance(native)
    receipts = list(OriginalContentCall.objects.filter(
        member_post_ids__contains=["native-1"], stage="translation", import_state="pending", state="completed",
    ))
    assert {c.provenance["context"]["target_language"] for c in receipts} == {"en", "ja"}
    assert all(c.provenance["context"]["source_language"] == "zh-Hans" for c in receipts)
    if conflicting:
        call = receipts[0]
        call.provenance["context"]["source_language"] = "zh-Hant"
        call.save(update_fields=["provenance"])
    originals = {c.pk: (c.request_packet, c.response_payload, c.provenance) for c in receipts}
    request_post_translation("native-1")
    assert replay_requested_saved_translation(cfg, delegates=delegates, post_ids={"native-1"})
    state = PostEnrichmentState.objects.get(pk="native-1")
    assert state.translation_error_code == ("incomplete_saved_translation" if conflicting else HISTORICAL_SCRIPT_DEMAND)
    assert not state.post.lang_detected and not literal_translation_artifact_complete(state.post)
    sent = []
    def send(body, timeout):
        prompt = body["messages"][-1]["content"]
        if body["max_tokens"] == 16:
            text = detected
        elif "Japanese (ja)" in prompt:
            text = "今日は通義千問を使いました。"
        elif "English (en)" in prompt:
            text = "I tried Qwen today."
        else:
            text = "我今天试用了通义千问。"
        sent.append(body)
        return _response(GEMMA_4_31B_MODEL, text)
    from dataclasses import replace
    delegates = {**delegates, "translation": replace(delegates["translation"], transport=send)}
    runner = CycleRunner(cfg=cfg, cycle_kind="enrichment", _post_fetch_clients=delegates)
    runner._run_post_fetch([], run_id="historical-script-demand", scope="continuous",
                           fair_queue=True, post_ids={"native-1"})
    post = Post.objects.get(pk="native-1")
    assert len(sent) == physical
    assert literal_translation_artifact_complete(post) is (not conflicting)
    if not conflicting:
        assert post.lang_detected == detected
        assert post.text_zh_cn == "我今天试用了通义千问。"
    assert post.lang == "zh"
    assert set(OriginalContentCall.objects.filter(pk__in=originals).values_list("import_state", flat=True)) == (
        {"applied"} if physical == 1 else {"pending"}
    )
    assert {c.pk: (c.request_packet, c.response_payload, c.provenance)
            for c in OriginalContentCall.objects.filter(pk__in=originals)} == originals


@pytest.mark.parametrize("classification_status", ["pending", "failed"])
def test_reader_replays_saved_translation_without_touching_classification(native, classification_status):
    from monitor.backfill_enrichment import replay_requested_saved_translation
    from monitor.enrichment_queue import request_post_translation
    from monitor.post_artifacts import literal_translation_artifact_complete

    job, cfg, delegates, _ = native
    advance(native, initial=True)
    PostEnrichmentState.objects.update(translation_requested=False)
    advance(native)
    request_post_translation("native-1")
    PostEnrichmentState.objects.filter(pk="native-1").update(
        classification_status=classification_status,
        classification_attempts=2,
        classification_error_code="owned_by_historical_job",
    )
    before = PostEnrichmentState.objects.values(
        "classification_status", "classification_attempts", "classification_error_code",
        "classification_first_attempt_at", "classification_last_attempt_at",
        "classification_next_attempt_at", "source_collection_job_id",
    ).get(pk="native-1")
    submissions = len(NativeProvider.submissions)
    PostEnrichmentState.objects.filter(pk="native-1").update(
        claim_owner="classification-worker", claim_run_id="classification-worker",
        claim_expires_at=timezone.now() + timedelta(minutes=5),
    )
    assert not replay_requested_saved_translation(cfg, delegates=delegates, post_ids={"native-1"})
    PostEnrichmentState.objects.filter(pk="native-1").update(
        claim_owner="", claim_run_id="", claim_expires_at=None,
    )
    assert replay_requested_saved_translation(cfg, delegates=delegates, post_ids={"native-1"})
    assert literal_translation_artifact_complete(Post.objects.get(pk="native-1"))
    assert PostEnrichmentState.objects.values(*before).get(pk="native-1") == before
    assert before["source_collection_job_id"] == job.pk
    assert len(NativeProvider.submissions) == submissions


@pytest.mark.parametrize("outstanding", [False, True])
def test_partial_paid_packet_is_honest_and_does_not_starve_replay(native, outstanding):
    from django.test import Client

    from monitor.backfill_enrichment import replay_requested_saved_translation
    from monitor.enrichment_queue import request_post_translation

    _job, cfg, delegates, _ = native
    advance(native, initial=True)
    PostEnrichmentState.objects.update(translation_requested=False)
    advance(native)
    call = OriginalContentCall.objects.filter(
        stage="translation", import_state="pending", member_post_ids__contains=["native-1"],
    ).first()
    assert call is not None
    if outstanding:
        call.state = "sent"
        call.completed_at = None
        OriginalContentCall.objects.filter(
            stage="translation", import_state="pending", member_post_ids__contains=["native-1"],
        ).exclude(pk=call.pk).update(import_state="applied")
    else:
        call.import_state = "error"
    call.save(update_fields=["state", "completed_at", "import_state", "updated_at"])
    request_post_translation("native-1")
    PostEnrichmentState.objects.filter(pk="native-1").update(
        claim_expires_at=timezone.now() - timedelta(minutes=1),
    )
    before = len(NativeProvider.submissions)
    assert replay_requested_saved_translation(cfg, delegates=delegates)
    state = PostEnrichmentState.objects.get(pk="native-1")
    assert state.translation_status == "pending"
    assert state.classification_status == "succeeded"
    assert state.translation_next_attempt_at is None
    if outstanding:
        assert state.translation_error_code == "historical_translation_unresolved"
    else:
        assert state.translation_error_code == "incomplete_saved_translation"
    response = Client().post(
        "/api/v2/post-translation-demands/",
        data=json.dumps({"post_ids": ["native-1"], "poll_only": True, "locale": "zh-cn"}),
        content_type="application/json", secure=True,
    )
    assert response.json()["results"][0]["status"] == ("deferred" if outstanding else "unavailable")
    # Repeated reader demands must not reset this owned request or reserve a
    # second daily slot. The historical owner can still resume pending work.
    from django.utils.crypto import salted_hmac

    from core.models import PostSynthesisRateLimitBucket
    capacity = PostSynthesisRateLimitBucket.objects.filter(
        scope_hash=salted_hmac("post-translation-capacity", "all", algorithm="sha256").hexdigest(),
    )
    buckets_before = list(capacity.values_list("pk", "count"))
    retry = Client().post(
        "/api/v2/post-translation-demands/",
        data=json.dumps({"post_ids": ["native-1"], "poll_only": False, "locale": "zh-cn"}),
        content_type="application/json", secure=True,
    )
    assert retry.json()["results"][0]["status"] == ("deferred" if outstanding else "unavailable")
    assert list(capacity.values_list("pk", "count")) == buckets_before
    state.refresh_from_db()
    assert state.translation_status == "pending" and state.source_collection_job_id == _job.pk
    assert len(NativeProvider.submissions) == before


def test_real_management_command_uses_only_native_provider_and_read_only_status(
    native, monkeypatch
):
    import monitor.backfill_enrichment as enrichment
    from monitor.management.commands import backfill

    job, cfg, delegates, _ = native
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    monkeypatch.setenv("DEEPINFRA_ON_DEMAND", "test-only")
    monkeypatch.setattr(backfill, "load_config", lambda path: cfg)
    def on_demand_provider(**kwargs):
        assert kwargs["api_key"] == "test-only"
        return NativeProvider(**kwargs)

    monkeypatch.setattr(enrichment, "DeepInfraBatchClient", on_demand_provider)
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
        enrich_native=True,
        enrichment_max_usd="5",
        enrichment_deadline=(timezone.now() + timedelta(hours=72)).isoformat(),
        stdout=output,
    )
    first = json.loads(output.getvalue())
    assert first["model_requests_sent"] == 6 and first["twitterapi_requests"] == 0
    before = first["control_requests"]
    monkeypatch.delenv("DEEPINFRA_ON_DEMAND")
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
    PostEnrichmentState.objects.create(post=post, translation_requested=True)
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


def _complete_membership_fixture(job, *, count=2):
    from core.collection_capture import archive_legacy

    run = job.runs.get()
    run.status, run.completed_at = "success", timezone.now()
    run.save(update_fields=["status", "completed_at"])
    marker = CollectionScopeRun.objects.create(
        run=run, scope_kind="x_backfill_result", scope_key="result",
        phase="backfill_result_v1",
        legacy_archive=archive_legacy({
            "post_membership": {"version": 1, "distinct_posts": count},
            "collection_drained": True,
        }),
    )
    job.state, job.last_success = "completed", run
    job.next_due_at, job.next_retry_at = None, None
    job.save()
    return run, marker


def test_completed_typed_membership_is_adopted_without_rewriting_outcome(native):
    from core.collection_capture import read_document

    job, _, _, _ = native
    run, marker = _complete_membership_fixture(job)
    original = marker.legacy_archive_id
    assert advance(native, initial=True)["model_requests_sent"] == 6
    job.refresh_from_db()
    run.refresh_from_db()
    marker.refresh_from_db()
    assert job.state == "completed" and run.status == "success"
    assert marker.legacy_archive_id == original
    assert read_document(marker.legacy_archive)["collection_drained"] is True
    assert CollectionObservation.objects.filter(run=run, source_subject_kind="post").count() == 2


def test_typed_membership_resume_does_not_load_oversized_legacy_receipt(native):
    from core.collection_capture import archive_legacy
    from tests.test_hf_catalog_retirement import denied_retirement_columns

    job, _, _, _ = native
    run, _ = _complete_membership_fixture(job)
    run.legacy_archive = archive_legacy({
        "report": {"recovered_post_ids": ["unused-legacy-array"] * 100001},
    })
    run.save(update_fields=["legacy_archive"])

    def forbid_old_archive_read(execute, sql, params, many, context):
        if '"collection_evidence_archives"' in sql and 'SELECT' in sql.upper():
            assert run.legacy_archive_id not in (params or ()), "typed resume loaded old receipt"
        return execute(sql, params, many, context)

    with denied_retirement_columns(), connection.execute_wrapper(forbid_old_archive_read):
        adopt_completed_membership(job)
    assert CollectionObservation.objects.filter(run=run, post__isnull=False).count() == 2
    assert not OriginalContentCall.objects.exists()


def test_typed_membership_count_drift_is_refused_before_provider_work(native):
    from core.provider_batches import BatchAdmissionError

    job, _, _, _ = native
    _complete_membership_fixture(job, count=3)
    with pytest.raises(BatchAdmissionError, match="typed_membership_count_changed"):
        adopt_completed_membership(job)
    assert not OriginalContentCall.objects.exists()


def test_unadopted_legacy_membership_is_refused_after_retirement(native):
    from core.provider_batches import BatchAdmissionError

    job, _, _, _ = native
    _, marker = _complete_membership_fixture(job)
    marker.delete()
    with pytest.raises(BatchAdmissionError, match="requires_pre_retirement_adoption"):
        adopt_completed_membership(job)
    assert not OriginalContentCall.objects.exists()


def test_database_pin_prevents_writes_and_provider_calls(native):
    from copy import deepcopy

    from core.collection_jobs import register_job, set_job_state
    from core.provider_batches import BatchAdmissionError

    job, _, _, _ = native
    definition = deepcopy(job.definition)
    definition["scope"]["database"] = {"name": "wrong", "user": "wrong"}
    # A copied job may be pinned to another database. Register its instructions
    # honestly instead of mutating an existing immutable job to make a fixture.
    wrong_database_job = register_job(
        job_key=job.job_key + ":wrong-database",
        source=job.source,
        purpose=job.purpose,
        operation=job.operation,
        mode=job.mode,
        contract=job.contract,
        definition=definition,
    )
    wrong_database_job = set_job_state(wrong_database_job.pk, "ready")
    with pytest.raises(BatchAdmissionError, match="database_identity_mismatch"):
        advance((wrong_database_job, *native[1:]), initial=True)
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


def _rejected_quantity_reply(native, *, language="en", reply="2000万トークン"):
    from core.provider_batches import digest
    from monitor.backfill_enrichment import _register_requests, prepare_page

    job, cfg, delegates, policy = native
    Post.objects.filter(pk="native-1").update(
        text="20 mil tokens", lang=language, lang_detected=language,
    )
    requests, _, _ = prepare_page(job, ["native-1"], cfg, delegates=delegates)
    request = next(r for r in requests if r["context"].get("target_language") == "ja")
    _register_requests(job, [request], policy, cfg, transport="direct")
    call = OriginalContentCall.objects.get(request_hash=request["hash"])
    payload = {"model": call.model, "choices": [
        {"finish_reason": "stop", "message": {"content": reply}},
    ], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
    now = timezone.now()
    OriginalContentCall.objects.filter(pk=call.pk).update(
        state="completed", sent_at=now, completed_at=now, response_hash=digest(payload),
        response_payload=payload, import_state="error",
        error_code="cached_response_validation_failed", actual_usd="0.00001",
        import_evidence={"validation": "failed", "reason": "canonical_cached_reply_rejected", "cost_kind": "provider_reported"},
    )
    return OriginalContentCall.objects.get(pk=call.pk)


def test_reader_replay_preserves_invalid_saved_reply_for_owning_job(native):
    from monitor.backfill_enrichment import replay_requested_saved_translation

    _job, cfg, delegates, _ = native
    call = _rejected_quantity_reply(native, reply="2万トークン")
    OriginalContentCall.objects.filter(pk=call.pk).update(import_state="pending", error_code="")
    PostEnrichmentState.objects.filter(pk="native-1").update(classification_status="succeeded")
    assert replay_requested_saved_translation(cfg, delegates=delegates, post_ids={"native-1"})
    call.refresh_from_db()
    assert call.import_state == "pending"
    assert call.response_payload is not None


@pytest.mark.parametrize("language,reply,accepted", [
    ("en", "2000万トークン", True), ("en", "2万トークン", False),
    ("es", "2万トークン", True), ("es", "2000万トークン", False),
])
def test_explicit_revalidation_uses_actual_cached_caller_and_retains_paid_history(native, language, reply, accepted):
    from monitor.backfill_enrichment import revalidate_cached_translations

    job, _, delegates, _ = native
    call = _rejected_quantity_reply(native, language=language, reply=reply)
    before = OriginalContentCall.objects.filter(pk=call.pk).values().get()
    result = revalidate_cached_translations(
        job.pk, call_ids=[call.pk], delegate=delegates["translation"],
        actor="test", reason="shared validator correction",
    )
    call.refresh_from_db()
    assert result["reopened"] == ([call.pk] if accepted else [])
    assert call.import_state == ("pending" if accepted else "error")
    after = OriginalContentCall.objects.filter(pk=call.pk).values().get()
    for key in set(before) - {"import_state", "import_evidence", "error_code", "updated_at"}:
        assert after[key] == before[key], key
    assert OriginalContentCall.objects.count() == 1 and NativeProvider.submissions == []
    if accepted:
        audit = call.import_evidence["revalidation_history"][0]
        assert audit["previous_import_evidence"] == before["import_evidence"]
        assert audit["previous_error_code"] == before["error_code"]
        assert audit["actor"] == "test"
        assert revalidate_cached_translations(
            job.pk, call_ids=[call.pk], delegate=delegates["translation"],
            actor="test", reason="repeat",
        )["reopened"] == []
        call.refresh_from_db()
        assert len(call.import_evidence["revalidation_history"]) == 1


@pytest.mark.parametrize("blocker", ["sent", "batch_claim", "post_claim", "source_change", "unknown"])
def test_saved_reply_revalidation_rejects_active_changed_and_unknown_work(native, blocker):
    from core.provider_batches import BatchAdmissionError
    from monitor.backfill_enrichment import revalidate_cached_translations

    job, _, delegates, _ = native
    call = _rejected_quantity_reply(native)
    if blocker in {"sent", "unknown"}:
        OriginalContentCall.objects.filter(pk=call.pk).update(
            state="sent" if blocker == "sent" else "ambiguous", completed_at=None,
        )
    elif blocker == "batch_claim":
        ProviderBatch.objects.filter(pk=call.provider_batch_id).update(
            claim_expires_at=timezone.now() + timedelta(minutes=5),
        )
    elif blocker == "post_claim":
        PostEnrichmentState.objects.filter(pk="native-1").update(
            claim_owner="other", claim_expires_at=timezone.now() + timedelta(minutes=5),
        )
    else:
        Post.objects.filter(pk="native-1").update(text="Changed source.")
    with pytest.raises(BatchAdmissionError):
        revalidate_cached_translations(
            job.pk, call_ids=[call.pk], delegate=delegates["translation"],
            actor="test", reason="must reject",
        )
    call.refresh_from_db()
    assert call.import_state == "error" and "revalidation_history" not in call.import_evidence


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
    # This cohort exercises historical classification ownership without a
    # reader-requested translation competing for the live worker.
    PostEnrichmentState.objects.filter(pk__in=["native-1", "native-2"]).update(
        translation_requested=False
    )
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


def test_untranslated_non_english_post_prepares_classifier_without_translation(native):
    from monitor.backfill_enrichment import prepare_page

    job, cfg, delegates, _policy = native
    PostEnrichmentState.objects.filter(pk="native-1").update(translation_requested=False)
    Post.objects.filter(pk="native-1").update(text="千亿参数模型发布", lang="zh", lang_detected=None, text_en=None)
    requests, _, _ = prepare_page(job, ["native-1"], cfg, delegates=delegates)
    stages = [request["context"]["stage"] for request in requests]
    assert stages.count("classification") == 2
    assert "translation" not in stages


def test_completed_untranslated_live_post_remains_available_for_live_reclassification(native):
    from core.provider_batches import own_historical_posts
    from monitor.enrichment_queue import claim_enrichment_states

    job, cfg, _delegates, _policy = native
    post = Post.objects.create(tweet_id="live-untranslated-membership", text="source")
    PostBrand.objects.create(post=post, brand_id="qwen")
    state = PostEnrichmentState.objects.create(
        post=post, translation_requested=False, translation_status="pending",
        classification_status="succeeded",
    )
    with transaction.atomic():
        record_post_membership(job.runs.get(), None, [post.pk])
    state.refresh_from_db()
    assert state.source_collection_job_id is None
    assert own_historical_posts(job, [post.pk]) == {}
    state.refresh_from_db()
    assert state.source_collection_job_id is None
    PostEnrichmentState.objects.filter(pk=post.pk).update(classification_status="pending")
    claimed = claim_enrichment_states(cfg=cfg.harvest.enrichment, run_id="live-reclass", post_ids={post.pk})
    assert [s.pk for s in claimed.states] == [post.pk]


def test_historical_membership_retains_requested_translation_work(native):
    job, _cfg, _delegates, _policy = native
    post = Post.objects.create(tweet_id="live-requested-membership", text="source")
    state = PostEnrichmentState.objects.create(
        post=post, translation_requested=True, translation_status="pending",
        classification_status="succeeded",
    )
    with transaction.atomic():
        record_post_membership(job.runs.get(), None, [post.pk])
    state.refresh_from_db()
    assert state.source_collection_job_id == job.pk




def test_outstanding_historical_translations_do_not_starve_live_classification(native):
    from monitor.cycle import _claim_enrichment_states

    _job, cfg, _, _ = native
    advance(native, initial=True)
    PostEnrichmentState.objects.update(
        created_at=timezone.now() - timedelta(days=90),
        claim_expires_at=timezone.now() - timedelta(seconds=1),
    )
    live = Post.objects.create(tweet_id='new-live-during-batch', text='live source')
    PostBrand.objects.create(post=live, brand_id='qwen')
    PostEnrichmentState.objects.create(post=live)
    claims = _claim_enrichment_states(cfg=cfg.harvest.enrichment, run_id='live-priority')
    assert [str(s.pk) for s in claims.states] == [live.pk]


def test_historical_reservation_refuses_an_active_live_claim(native):
    from core.provider_batches import BatchAdmissionError
    from monitor.backfill_enrichment import _register_requests, prepare_page

    job, cfg, delegates, policy = native
    requests, _, _ = prepare_page(job, ['native-1'], cfg, delegates=delegates)
    PostEnrichmentState.objects.filter(pk='native-1').update(
        claim_owner='enrichment:live', claim_run_id='live',
        claim_expires_at=timezone.now() + timedelta(minutes=5),
    )
    with pytest.raises(BatchAdmissionError, match='historical_state_missing_or_claimed'):
        _register_requests(job, requests, policy, cfg)
    assert not OriginalContentCall.objects.exists()


def test_saved_translation_replay_does_not_require_classifier_client(native):
    from monitor.backfill_enrichment import replay_requested_saved_translation
    from monitor.enrichment_queue import request_post_translation
    from monitor.post_artifacts import literal_translation_artifact_complete

    _job, cfg, delegates, _ = native
    advance(native, initial=True)
    PostEnrichmentState.objects.update(translation_requested=False)
    advance(native)
    request_post_translation('native-1')
    submissions = len(NativeProvider.submissions)
    assert replay_requested_saved_translation(cfg, delegates={'translation': delegates['translation'], 'classification': None}, post_ids={'native-1'})
    assert literal_translation_artifact_complete(Post.objects.get(pk='native-1'))
    assert len(NativeProvider.submissions) == submissions


def test_historical_run_defers_active_reader_claim_and_advances_other_members(native):
    job, cfg, delegates, policy = native
    # Establish the historical ownership before a reader acquires the lease.
    from core.provider_batches import own_historical_posts
    from monitor.backfill_enrichment import execute_enrichment
    own_historical_posts(job, ['native-1', 'native-2'])
    PostEnrichmentState.objects.filter(pk='native-1').update(
        claim_owner='reader', claim_run_id='reader', claim_expires_at=timezone.now() + timedelta(minutes=5),
    )
    execute_enrichment(job.pk, cfg=cfg, api_key='test', policy=policy,
                       delegates=delegates, client_factory=NativeProvider)
    state = PostEnrichmentState.objects.get(pk='native-1')
    assert state.claim_owner == 'reader'
    assert not OriginalContentCall.objects.filter(member_post_ids__contains=['native-1']).exists()
    assert OriginalContentCall.objects.filter(member_post_ids__contains=['native-2']).exists()


def test_reader_claim_after_historical_preparation_defers_reservation(native):
    from monitor.backfill_enrichment import _register_requests, prepare_page

    job, cfg, delegates, policy = native
    requests, _, _ = prepare_page(job, ['native-1', 'native-2'], cfg, delegates=delegates)
    assert requests
    PostEnrichmentState.objects.filter(pk='native-1').update(
        claim_owner='reader', claim_run_id='reader', claim_expires_at=timezone.now() + timedelta(minutes=5),
    )
    deferred = {}
    _register_requests(job, requests, policy, cfg, deferred=deferred, defer_claim_conflicts=True)
    assert deferred['native-1'] == 'historical_state_missing_or_claimed'
    assert not OriginalContentCall.objects.filter(member_post_ids__contains=['native-1']).exists()
    assert OriginalContentCall.objects.filter(member_post_ids__contains=['native-2']).exists()
    assert PostEnrichmentState.objects.get(pk='native-1').claim_owner == 'reader'
