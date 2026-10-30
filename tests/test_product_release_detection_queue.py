"""The harvest handoff is durable, bounded and independent of enrichment."""

from datetime import timedelta

import pytest
from django.utils import timezone

from core import models
from core.product_release_detection_queue import drain_posts, enqueue_posts

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_queue_retains_nonmatches_and_processes_candidates_without_provider_calls():
    posts = [models.Post.objects.create(tweet_id="scan-candidate", text="We announce a new model."),
             models.Post.objects.create(tweet_id="scan-nonmatch", text="A quiet day.")]
    result = enqueue_posts([posts[0].pk, posts[1].pk, posts[0].pk, "missing-post"])
    assert result == {"selected": 3, "queued": 2, "missing": 1, "failed": 1}
    assert not models.EventDossier.objects.exists()
    assert models.ProductReleaseDetectionState.objects.count() == 2
    run = drain_posts(limit=10)
    assert run["processed"] == 2 and run["candidates"] == 1 and not run["due_remaining"]
    assert models.EventDossier.objects.count() == 1
    assert models.ProductReleaseDetectionState.objects.filter(completed_at__isnull=False).count() == 2
    assert not models.CollectionRequest.objects.exists()
    assert drain_posts(limit=10)["processed"] == 0


def test_new_observation_during_detection_remains_pending(monkeypatch):
    from core import product_release_pipeline

    post = models.Post.objects.create(tweet_id="scan-new-generation", text="We announce a new model.")
    enqueue_posts([post.pk])
    original = product_release_pipeline.persist_source
    def changed(source):
        result = original(source)
        enqueue_posts([post.pk])
        return result
    monkeypatch.setattr(product_release_pipeline, "persist_source", changed)
    first = drain_posts(limit=1)
    assert first["processed"] == 1 and first["due_remaining"]
    monkeypatch.setattr(product_release_pipeline, "persist_source", original)
    second = drain_posts(limit=1)
    assert second["processed"] == 1 and not second["due_remaining"]
    assert models.EventDossier.objects.count() == 1


def test_enqueue_reports_committed_batches_when_a_later_batch_fails(monkeypatch):
    from core import product_release_detection_queue as queue

    ids = [models.Post.objects.create(tweet_id=f"batch-{n}", text="Post").pk for n in range(3)]
    original = models.ProductReleaseDetectionState.objects.bulk_create
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated later batch failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(queue, "ENQUEUE_BATCH_SIZE", 2)
    monkeypatch.setattr(models.ProductReleaseDetectionState.objects, "bulk_create", fail_second)
    assert enqueue_posts(ids) == {"selected": 3, "queued": 2, "missing": 0, "failed": 1, "status": "error"}
    assert models.ProductReleaseDetectionState.objects.count() == 2


def test_requeue_advances_generation_even_if_clock_does_not(monkeypatch):
    from core import product_release_detection_queue as queue

    post = models.Post.objects.create(tweet_id="scan-clock", text="A post.")
    enqueue_posts([post.pk])
    state = models.ProductReleaseDetectionState.objects.get(post=post)
    original = state.requested_at
    models.ProductReleaseDetectionState.objects.filter(pk=post.pk).update(completed_at=original)
    monkeypatch.setattr(queue.timezone, "now", lambda: original)
    enqueue_posts([post.pk])
    state.refresh_from_db()
    assert state.requested_at > original and state.completed_at == original


def test_concurrent_worker_does_not_block_or_duplicate_a_post():
    import hashlib
    import threading
    from django.db import connection, transaction

    post = models.Post.objects.create(tweet_id="scan-busy", text="We announce a new model.")
    enqueue_posts([post.pk])
    acquired, release = threading.Event(), threading.Event()
    key = int(hashlib.sha256(f"release-detection:{post.pk}".encode()).hexdigest()[:15], 16)
    def hold_lock():
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])
                acquired.set()
                assert release.wait(10)
    worker = threading.Thread(target=hold_lock)
    worker.start()
    try:
        assert acquired.wait(5)
        busy = drain_posts(limit=1)
        assert busy["busy"] == 1 and busy["processed"] == 0 and busy["due_remaining"]
    finally:
        release.set()
        worker.join(10)
    assert not worker.is_alive()
    assert drain_posts(limit=1)["processed"] == 1
    assert models.EventDossier.objects.count() == 1


def test_queue_lock_timeout_is_bounded_and_caller_timeouts_are_restored():
    import threading
    from time import monotonic
    from django.db import OperationalError, connection, transaction
    from core.product_release_detection_queue import enqueue_saved_post

    post = models.Post.objects.create(tweet_id="scan-row-lock", text="A post.")
    enqueue_posts([post.pk])
    acquired, release = threading.Event(), threading.Event()

    def hold_row():
        with transaction.atomic():
            models.ProductReleaseDetectionState.objects.select_for_update().get(post=post)
            acquired.set()
            assert release.wait(10)

    worker = threading.Thread(target=hold_row)
    worker.start()
    try:
        assert acquired.wait(5)
        started = monotonic()
        with pytest.raises(OperationalError), transaction.atomic():
            enqueue_saved_post(post.pk)
        assert monotonic() - started < 2
    finally:
        release.set()
        worker.join(10)
    assert not worker.is_alive()
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '100ms'")
        cursor.execute("SET LOCAL statement_timeout = '1s'")
        enqueue_saved_post(post.pk)
        cursor.execute("SELECT current_setting('lock_timeout'), current_setting('statement_timeout')")
        assert cursor.fetchone() == ("100ms", "1s")


def test_detection_failure_is_retried_then_retained_without_false_scam(monkeypatch):
    from core import product_release_pipeline

    post = models.Post.objects.create(tweet_id="scan-retry", text="We announce a new model.")
    enqueue_posts([post.pk])
    def fail(_source):
        raise RuntimeError("temporary failure")
    monkeypatch.setattr(product_release_pipeline, "persist_source", fail)
    for expected in (1, 2, 3):
        run = drain_posts(limit=1)
        state = models.ProductReleaseDetectionState.objects.get(post=post)
        assert run["failed"] == 1 and state.attempts == expected
        assert state.completed_at is None and state.error_code == "processing_error"
        if expected < 3:
            assert state.retry_at is not None and drain_posts(limit=1)["selected"] == 0
            models.ProductReleaseDetectionState.objects.filter(pk=post.pk).update(
                retry_at=timezone.now() - timedelta(seconds=1)
            )
        else:
            assert state.retry_at is None and not run["due_remaining"]
    assert not models.EventDossierIntakeDecision.objects.filter(outcome="scam").exists()
    enqueue_posts([post.pk])
    assert models.ProductReleaseDetectionState.objects.get(post=post).attempts == 3
    assert drain_posts(limit=1)["selected"] == 0


def test_real_post_save_and_detection_handoff_are_atomic(settings, monkeypatch):
    from core import product_release_detection_queue as queue
    from monitor.cycle import CycleRunner
    from tests.test_post_enrichment_queue import _cfg

    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = True
    runner = CycleRunner(cfg=_cfg(), cycle_kind="scheduled")
    item = {"id": "outbox-real-post", "author_id": "outbox-author", "author_handle": "outbox",
            "text": "We announce a new model.", "brand_ids": [], "mentions": [], "classifications": {}}
    original = queue.enqueue_saved_post
    def fail(_post_id):
        raise RuntimeError("outbox unavailable")
    monkeypatch.setattr(queue, "enqueue_saved_post", fail)
    assert runner._persist_items([item]) == (0, 0, 0, 1)
    assert not models.Post.objects.filter(pk=item["id"]).exists()
    assert "_persisted_post_id" not in item
    monkeypatch.setattr(queue, "enqueue_saved_post", original)
    assert runner._persist_items([item]) == (1, 0, 0, 0)
    assert models.ProductReleaseDetectionState.objects.filter(post_id=item["id"], completed_at__isnull=True).exists()
    assert not models.EventDossier.objects.exists()
    assert drain_posts()["candidates"] == 1


def test_lost_broker_wakeup_leaves_durable_post_for_later_recovery(settings, monkeypatch):
    from monitor.cycle import CycleRunner
    from monitor.tasks import recover_due_product_releases
    from tests.test_post_enrichment_queue import _cfg, _state

    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = True
    state = _state("scan-broker-recovery")
    state.post.text = "We announce a new model."
    state.post.save(update_fields=["text"])
    def fail(**_kwargs):
        raise RuntimeError("broker unavailable")
    monkeypatch.setattr(recover_due_product_releases, "apply_async", fail)
    cfg = _cfg()
    cfg.harvest.enrichment.mode = "worker"
    runner = CycleRunner(cfg=cfg, cycle_kind="scheduled")
    result = runner._run_post_fetch([{"_persisted_post_id": state.pk, "_db_inserted": True}])
    assert result["product_release_intake"]["queued"] == 1
    assert not models.EventDossier.objects.exists()
    assert models.ProductReleaseDetectionState.objects.get(post=state.post).completed_at is None
    recovered = recover_due_product_releases.run()
    assert recovered["detection"]["candidates"] == 1 and recovered["provider_calls"] == 0
    assert models.ProductReleaseDetectionState.objects.get(post=state.post).completed_at is not None
