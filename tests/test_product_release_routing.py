"""Release evidence follows saved classification, independent of search source."""

import pytest

from core.models import (
    CollectionJob,
    CollectionRequest,
    DataSource,
    EventDossier,
    EventDossierClaim,
    PostBrandSignal,
    PostTypeKey,
    RareTypeSearchHit,
    SentimentKey,
    TargetedExtractionState,
)
from core.product_release_detection_queue import drain_posts
from monitor.cycle import CycleRunner
from scripts.backfill_targeted import requirements
from tests.test_post_enrichment_queue import _cfg, _classification_results, _state
from tests.test_rare_type_commands import _hits, _mark_kept_and_link
from x_monitor import attribution, reattribute, translator

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]

QUOTE = "Nanbeige released Nanbeige4.3-33B. Qwen is a comparator; the 33B model teaches an upcoming 3B model."


@pytest.fixture
def enabled_release_background(settings, monkeypatch):
    from monitor.tasks import acquire_product_release, recover_due_product_releases

    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = True
    monkeypatch.setattr(acquire_product_release, "apply_async", lambda **_kwargs: None)
    monkeypatch.setattr(recover_due_product_releases, "apply_async", lambda **_kwargs: None)


@pytest.mark.parametrize("origin", ["ordinary", "special-events"])
@pytest.mark.parametrize("path", ["new-classification", "saved-replay"])
def test_real_enrichment_and_replay_accept_the_same_release(monkeypatch, origin, path):
    DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    state = _state("release-routing")
    state.post.text = "DeepSeek comparison and a quoted release announcement"
    state.post.quoted_text = QUOTE
    state.post.save(update_fields=["text", "quoted_text"])
    if origin == "special-events":
        _mark_kept_and_link(_hits(state.pk)[0], state.post)
    else:
        assert not RareTypeSearchHit.objects.exists()
    cfg = _cfg()
    cfg.targeted_extraction.enabled = True
    cfg.targeted_extraction.max_calls_per_cycle = 1
    seen = []

    def extract(system, user, model, max_tokens):
        assert QUOTE in user
        seen.append(user)
        return {
            "records": [
                {
                    "organization_name": "Nanbeige",
                    "model_name": "Nanbeige4.3-33B",
                    "version": "4.3-33B",
                    "release_channel": "stable",
                    "release_precision": "unknown",
                }
            ]
        }

    runner = CycleRunner(
        cfg=cfg, _targeted_extraction_calls={"model_release_extraction": extract}
    )
    if path == "saved-replay":
        state.classification_status = "succeeded"
        state.save(update_fields=["classification_status"])
        PostBrandSignal.objects.create(
            post=state.post,
            brand_id="deepseek",
            post_type=PostTypeKey.objects.get(key="releases_updates"),
            sentiment=SentimentKey.objects.get(key="neutral"),
        )
        assert set(requirements(state.post, cfg)) == {"model_release_extraction"}
        result = runner._replay_targeted_extractions(post_ids={state.pk})
        assert result["calls"] == 1
    else:
        monkeypatch.setattr(
            reattribute, "build_translator_client_from_env", lambda *a, **k: object()
        )
        monkeypatch.setattr(
            reattribute, "build_classifier_client_from_env", lambda *a, **k: object()
        )
        monkeypatch.setattr(
            translator,
            "translate_batch_pragmatics",
            lambda tweets, *a, **k: [
                {
                    "tweet_id": t["tweet_id"],
                    "text_en": t["text"],
                    "text_zh_cn": "引述南北阁模型发布，并对比其他模型。",
                    "en_equivalent": "The announcement introduces a model for comparison.",
                    "cn_equivalent": "这次发布提供了新的模型比较对象。",
                    "lang_detected": "en",
                }
                for t in tweets
            ],
        )
        monkeypatch.setattr(
            attribution,
            "classify_batch_pragmatics_full",
            lambda tweets, *a, **k: _classification_results(tweets),
        )
        result = runner._run_post_fetch(
            [], run_id="release-routing", post_ids={state.pk}
        )
        assert result["n_targeted_extraction_calls"] == 1
        state.refresh_from_db()
        assert state.classification_status == "succeeded"
    dossier = EventDossier.objects.get(event_kind_reference__code="product_release")
    claim = EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=dossier, claim_kind_reference__code="release_report"
    )
    assert claim.reported_brand_id is None
    assert claim.reported_brand_discovery_candidate.observed_name == "Nanbeige"
    assert dossier.current_review_id is None
    assert claim.collection_job_links.count() == 1
    assert CollectionJob.objects.filter(operation="release_acquisition").count() == 1
    assert not CollectionRequest.objects.exists()
    assert len(seen) == 1
    assert TargetedExtractionState.objects.get(post=state.post).status == "succeeded"
    replay = runner._replay_targeted_extractions(post_ids={state.pk})
    assert replay["calls"] == 0
    assert len(seen) == 1
    assert EventDossierClaim.objects.filter(claim_kind_reference__code="release_report").count() == 1
    assert CollectionJob.objects.filter(operation="release_acquisition").count() == 1


def test_collected_unclassified_announcement_gets_pending_dossier_without_model_calls(enabled_release_background):
    state = _state("release-raw-worker")
    state.post.text = "Today we announce a new model from an unfamiliar lab"
    state.post.save(update_fields=["text"])
    cfg = _cfg()
    cfg.harvest.enrichment.mode = "worker"
    runner = CycleRunner(cfg=cfg, cycle_kind="scheduled")
    kept = [{"_persisted_post_id": state.pk, "_db_inserted": True}]
    first = runner._run_post_fetch(kept, run_id="raw-release")
    assert first["enrichment_processed_externally"] is True
    assert first["product_release_intake"]["queued"] == 1
    assert not EventDossier.objects.exists()
    assert drain_posts()["candidates"] == 1
    dossier = EventDossier.objects.get(event_kind_reference__code="product_release")
    assert dossier.current_review_id is None
    assert EventDossierClaim.objects.filter(
        event_dossier_source__event_dossier=dossier, claim_kind_reference__code="release_signal"
    ).exists()
    before = EventDossierClaim.objects.count()
    second = runner._run_post_fetch(kept, run_id="raw-release-again")
    assert second["product_release_intake"]["queued"] == 1
    assert drain_posts()["candidates"] == 1
    assert EventDossier.objects.count() == 1 and EventDossierClaim.objects.count() == before
    assert not CollectionRequest.objects.exists()


def test_intake_failure_does_not_interrupt_collection_and_saved_post_can_be_replayed(monkeypatch, enabled_release_background):
    from core import product_release_detection_queue

    state = _state("release-intake-failure")
    state.post.text = "Announcing a new model"
    state.post.save(update_fields=["text"])
    cfg = _cfg()
    cfg.harvest.enrichment.mode = "worker"
    runner = CycleRunner(cfg=cfg, cycle_kind="scheduled")
    kept = [{"_persisted_post_id": state.pk, "_db_inserted": True}]
    actual = product_release_detection_queue.enqueue_posts
    def fail(_ids):
        raise RuntimeError("simulated intake failure")
    monkeypatch.setattr(product_release_detection_queue, "enqueue_posts", fail)
    result = runner._run_post_fetch(kept, run_id="failed-release-intake")
    assert result["enrichment_processed_externally"] is True
    assert result["product_release_intake"]["failed"] == 1
    assert not EventDossier.objects.filter(event_kind_reference__code="product_release").exists()
    monkeypatch.setattr(product_release_detection_queue, "enqueue_posts", actual)
    result = runner._run_post_fetch(kept, run_id="replayed-release-intake")
    assert result["product_release_intake"]["queued"] == 1
    assert drain_posts()["candidates"] == 1
    assert EventDossier.objects.filter(event_kind_reference__code="product_release").count() == 1


def test_raw_release_queues_linked_repositories_as_unresolved_leads(enabled_release_background):
    import httpx

    from core.collection_capture import observation_object_documents
    from core.product_release_acquisition import drain_due_hf_acquisitions

    DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    state = _state("raw-linked-release")
    state.post.text = (
        "We released a student trained on a teacher. "
        "https://huggingface.co/lab/student https://huggingface.co/teacher/base"
    )
    state.post.save(update_fields=["text"])
    cfg = _cfg()
    cfg.harvest.enrichment.mode = "worker"
    runner = CycleRunner(cfg=cfg, cycle_kind="scheduled")
    kept = [{"_persisted_post_id": state.pk, "_db_inserted": True}]
    result = runner._run_post_fetch(kept, run_id="raw-linked")
    assert result["product_release_intake"]["queued"] == 1
    assert drain_posts()["candidates"] == 1
    jobs = CollectionJob.objects.filter(operation="release_acquisition", targets__target_role="exact_model")
    assert jobs.count() == 2 and not CollectionRequest.objects.exists()
    assert set(jobs.values_list("targets__native_identifier", flat=True)) == {"lab/student", "teacher/base"}
    calls = []
    def respond(request):
        repo = request.url.path.removeprefix("/api/models/")
        calls.append(repo)
        return httpx.Response(200, json={"id": repo, "likes": 2})
    client = httpx.Client(transport=httpx.MockTransport(respond))
    drained = drain_due_hf_acquisitions(client=client, execute=True, limit=2)
    assert drained["provider_calls"] == 2 and set(calls) == {"lab/student", "teacher/base"}
    for job in jobs:
        observation = job.last_success.observations.get()
        assert observation.processing_outcome == "unresolved"
        assert observation_object_documents(observation)[0]["id"] in calls
    runner._run_post_fetch(kept, run_id="raw-linked-again")
    drain_posts()
    assert CollectionJob.objects.filter(operation="release_acquisition", targets__target_role="exact_model").count() == 2
    assert drain_due_hf_acquisitions(client=client, execute=True,
                                    job_ids=[str(job.pk) for job in jobs])["provider_calls"] == 0
    from core.models import Product, ProductReleaseDetail
    assert Product.objects.count() == 2 and not ProductReleaseDetail.objects.exists()


def test_raw_versioned_announcement_queues_name_search_without_extraction(enabled_release_background):
    import httpx

    from core.collection_capture import observation_object_documents
    from core.models import Product
    from core.product_release_acquisition import drain_due_hf_acquisitions

    DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    state = _state("raw-versioned-release")
    state.post.text = "Excited to announce Nanbeige4.3-33B!"
    state.post.save(update_fields=["text"])
    cfg = _cfg()
    cfg.harvest.enrichment.mode = "worker"
    runner = CycleRunner(cfg=cfg, cycle_kind="scheduled")
    kept = [{"_persisted_post_id": state.pk, "_db_inserted": True}]
    assert runner._run_post_fetch(kept)["product_release_intake"]["queued"] == 1
    assert drain_posts()["candidates"] == 1
    job = CollectionJob.objects.get(operation="release_acquisition")
    target = job.targets.get()
    assert target.target_role == "name_search" and target.native_identifier == "Nanbeige4.3-33B"
    lead = EventDossierClaim.objects.get(scope_key__startswith="hf_name_lead:")
    assert lead.assertion_text == "Nanbeige4.3-33B" and lead.source_excerpt == state.post.text
    assert not CollectionRequest.objects.exists()
    def respond(request):
        assert request.url.params["search"] == "Nanbeige4.3-33B"
        return httpx.Response(200, json=[{"id": "nanbeige/Nanbeige4.3-33B"}])
    client = httpx.Client(transport=httpx.MockTransport(respond))
    assert drain_due_hf_acquisitions(client=client, execute=True)["provider_calls"] == 1
    job.refresh_from_db()
    observation = job.last_success.observations.get()
    assert observation.processing_outcome == "unresolved"
    assert observation_object_documents(observation)[0]["id"] == "nanbeige/Nanbeige4.3-33B"
    assert not Product.objects.exists()
    followup = CollectionJob.objects.get(targets__target_role="exact_model")
    assert followup.targets.get().native_identifier == "nanbeige/Nanbeige4.3-33B"
    assert followup.dossier_claim_links.get().claim.event_dossier_source.collection_observation_id == observation.pk
    runner._run_post_fetch(kept)
    drain_posts()
    assert CollectionJob.objects.filter(operation="release_acquisition").count() == 2


def test_opt_in_dispatch_runs_one_committed_job_without_duplicate_fetch(settings, monkeypatch):
    import httpx

    from monitor.tasks import acquire_product_release, recover_due_product_releases

    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = True
    DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    state = _state("background-release")
    state.post.text = "We announce Nanbeige4.3-33B today"
    state.post.save(update_fields=["text"])
    messages = []
    monkeypatch.setattr(acquire_product_release, "apply_async", lambda **kwargs: messages.append(kwargs))
    monkeypatch.setattr(recover_due_product_releases, "apply_async", lambda **kwargs: None)
    cfg = _cfg()
    cfg.harvest.enrichment.mode = "worker"
    runner = CycleRunner(cfg=cfg, cycle_kind="scheduled")
    kept = [{"_persisted_post_id": state.pk, "_db_inserted": True}]
    runner._run_post_fetch(kept)
    drain_posts()
    job = CollectionJob.objects.get(operation="release_acquisition")
    assert messages == [{"kwargs": {"job_id": str(job.pk)}, "queue": "trend-narratives", "retry": False}]
    assert not CollectionRequest.objects.exists()
    calls = []
    original_client = httpx.Client
    def client_factory(**_kwargs):
        def respond(request):
            calls.append(request)
            return httpx.Response(200, json=[{"id": "nanbeige/Nanbeige4.3-33B"}])
        return original_client(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(httpx, "Client", client_factory)
    result = acquire_product_release.run(job_id=str(job.pk))
    assert result["provider_calls"] == 1 and len(calls) == 1
    assert acquire_product_release.run(job_id=str(job.pk))["provider_calls"] == 0
    assert len(calls) == 1
    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = False
    assert acquire_product_release.run(job_id=str(job.pk))["status"] == "disabled"


def test_background_dispatch_failure_keeps_the_saved_job(settings, monkeypatch):
    from monitor.tasks import acquire_product_release, recover_due_product_releases

    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = True
    DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    state = _state("background-broker-failure")
    state.post.text = "We announce Nanbeige4.3-33B today"
    state.post.save(update_fields=["text"])
    def unavailable(**_kwargs):
        raise RuntimeError("broker unavailable")
    monkeypatch.setattr(acquire_product_release, "apply_async", unavailable)
    monkeypatch.setattr(recover_due_product_releases, "apply_async", unavailable)
    cfg = _cfg()
    cfg.harvest.enrichment.mode = "worker"
    runner = CycleRunner(cfg=cfg, cycle_kind="scheduled")
    result = runner._run_post_fetch([{"_persisted_post_id": state.pk, "_db_inserted": True}])
    assert result["product_release_intake"]["failed"] == 0
    assert drain_posts()["candidates"] == 1
    assert CollectionJob.objects.filter(operation="release_acquisition", state="ready").count() == 1
    assert not CollectionRequest.objects.exists()


def test_existing_harvest_wakeup_recovers_broker_failure_and_delayed_release(settings, monkeypatch):
    from datetime import timedelta

    import httpx
    from django.utils import timezone

    from monitor.tasks import acquire_product_release, recover_due_product_releases

    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = True
    DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    state = _state("retry-harvest-wakeup")
    state.post.text = "We announce Nanbeige4.3-33B today"
    state.post.save(update_fields=["text"])
    def unavailable(**_kwargs):
        raise RuntimeError("broker unavailable for initial dispatch")
    monkeypatch.setattr(acquire_product_release, "apply_async", unavailable)
    sweeps = []
    monkeypatch.setattr(recover_due_product_releases, "apply_async", lambda **kwargs: sweeps.append(kwargs))
    cfg = _cfg()
    cfg.harvest.enrichment.mode = "worker"
    runner = CycleRunner(cfg=cfg, cycle_kind="scheduled")
    first = runner._run_post_fetch([{"_persisted_post_id": state.pk, "_db_inserted": True}])
    assert first["product_release_recovery"]["status"] == "scheduled" and len(sweeps) == 1
    responses = iter([httpx.Response(200, json=[]), httpx.Response(
        200, json=[{"id": "nanbeige/Nanbeige4.3-33B"}]
    )])
    calls = []
    original_client = httpx.Client
    def client_factory(**_kwargs):
        def respond(request):
            calls.append(request)
            return next(responses)
        return original_client(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(httpx, "Client", client_factory)
    initial = recover_due_product_releases.run()
    job = CollectionJob.objects.get(operation="release_acquisition", targets__target_role="name_search")
    assert initial["provider_calls"] == 1 and initial["jobs"][0]["outcome"] == "empty"
    # Even when all provider jobs are cooling down, wake the saved-claim sweep.
    assert runner._run_post_fetch([])["product_release_recovery"]["status"] == "scheduled"
    assert len(sweeps) == 2 and len(calls) == 1
    CollectionJob.objects.filter(pk=job.pk).update(next_retry_at=timezone.now() - timedelta(seconds=1))
    assert runner._run_post_fetch([])["product_release_recovery"]["status"] == "scheduled"
    assert len(sweeps) == 3
    retried = recover_due_product_releases.run()
    assert retried["provider_calls"] == 1 and retried["jobs"][0]["outcome"] == "found"
    assert len(calls) == 2
    job.refresh_from_db()
    assert job.last_success_id is not None
    assert CollectionJob.objects.filter(targets__target_role="exact_model", state="ready").exists()


@pytest.mark.parametrize("stop", ["disabled", "budget", "deadline", "unclassified"])
def test_release_replay_respects_existing_dispatch_guards(stop):
    from unittest.mock import Mock

    state = _state("release-routing-guard")
    state.classification_status = "pending" if stop == "unclassified" else "succeeded"
    state.save(update_fields=["classification_status"])
    PostBrandSignal.objects.create(
        post=state.post,
        brand_id="deepseek",
        post_type=PostTypeKey.objects.get(key="releases_updates"),
        sentiment=SentimentKey.objects.get(key="neutral"),
    )
    cfg = _cfg()
    cfg.targeted_extraction.enabled = stop != "disabled"
    cfg.targeted_extraction.max_calls_per_cycle = 0 if stop == "budget" else 1
    extract = Mock(side_effect=AssertionError("guard must stop provider dispatch"))
    runner = CycleRunner(
        cfg=cfg, _targeted_extraction_calls={"model_release_extraction": extract}
    )
    deadline = Mock(can_start=Mock(return_value=False)) if stop == "deadline" else None
    result = runner._replay_targeted_extractions(post_ids={state.pk}, deadline=deadline)
    assert result["calls"] == 0
    extract.assert_not_called()
    assert not EventDossier.objects.filter(
        event_kind_reference__code="product_release"
    ).exists()
