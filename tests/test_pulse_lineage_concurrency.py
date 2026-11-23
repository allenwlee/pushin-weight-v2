"""End-to-end wakeup ordering across real publication and review transactions."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from django.db import connections
from django.utils import timezone

from core import models
from monitor import pulse_control, pulse_processing
from tests.test_classified_product_releases import setup_cycle
from tests.test_pulse_finding_persistence import finding

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_child_publication_uncommitted_during_parent_review_then_recovers(monkeypatch, tmp_path, settings):
    from core import product_release_detection_queue
    from core.event_dossiers import ClaimDecision, ProductReleaseInput, complete_review
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="test")
    state, runner, transport = setup_cycle(monkeypatch, official=True)
    author = state.post.author
    parent_post = models.Post.objects.create(tweet_id="parent-qwen3", author=author, text="We released Qwen3")
    parent_finding = finding(name="Qwen3", key="3" * 64)
    parent_finding["assertions"][0].update(assertion_text=parent_post.text, source_excerpt=parent_post.text)
    parent_finding["issuer_evidence"] = {"relation": "source_author", "source_locator": None,
                                        "source_excerpt": parent_post.text, "observed_name": None}
    saved = persist_classified_release_findings(source={"kind": "post", "id": parent_post.pk},
             revision_id="b" * 64, content_fingerprint="c" * 64, extraction_version="test", findings=[parent_finding])
    parent = resolve_saved_release_finding(claim_id=saved["findings"][0]["anchor_claim_id"])
    assert parent["status"] == "created"

    excerpt = "Qwen4 succeeds Qwen3."
    state.post.text += " " + excerpt
    state.post.save(update_fields=["text"])
    transport.document["release_findings"]["findings"][0]["lineage_evidence"] = [{
        "relationship_kind": "new_version", "parent_observed_name": "Qwen3",
        "source_locator": "post", "source_excerpt": excerpt,
    }]
    respond = transport.messages_create

    def supported(**kwargs):
        answer = respond(**kwargs)
        if not kwargs["model"].startswith("deepseek"):
            answer["answers"]["release:0:lineage:0:supported"]["noul"] = 0.9
        return answer

    monkeypatch.setattr(transport, "messages_create", supported)
    entered, release = Event(), Event()
    original_enqueue = product_release_detection_queue.enqueue_saved_post

    def pause_enqueue(post_id, **kwargs):
        entered.set()
        assert release.wait(20)
        return original_enqueue(post_id, **kwargs)

    monkeypatch.setattr(product_release_detection_queue, "enqueue_saved_post", pause_enqueue)

    def publish():
        try:
            runner._run_post_fetch([], run_id="concurrent-child")
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(publish)
        try:
            assert entered.wait(20)
            anchor = parent["anchor_claim_id"]
            complete_review(parent["dossier_id"], expected_current_review_id=None,
                display_title="Qwen3", review_state="confirmed", evidence_cutoff_at=timezone.now(),
                method_version="test", actor="test", reason="Source", claims=[ClaimDecision(anchor, "accepted", "Source")],
                product_release=ProductReleaseInput(observed_name="Qwen3", product_key=parent["product_key"]))
        finally:
            release.set()
        task.result(timeout=30)
    state.refresh_from_db()
    assert state.classification_status == "succeeded"
    assert models.ProductReleaseDetectionState.objects.filter(post_id=state.pk).exists()
    result = pulse_processing.process_saved_findings()
    assert result["failed"] == 0 and result["processed"] == 1
    edge = models.ProductRelationship.objects.get()
    assert str(edge.parent_product.product_key) == parent["product_key"]
    assert edge.child_product.display_name == "Qwen4"
    assert len(transport.calls) == 2


def test_parent_arrives_after_child_worker_wakeup_recovers_without_model_call(monkeypatch, tmp_path, settings):
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="test")
    state, runner, transport = setup_cycle(monkeypatch, official=True)
    excerpt = "Qwen4 succeeds Qwen3."
    state.post.text += " " + excerpt
    state.post.save(update_fields=["text"])
    transport.document["release_findings"]["findings"][0]["lineage_evidence"] = [{
        "relationship_kind": "new_version", "parent_observed_name": "Qwen3",
        "source_locator": "post", "source_excerpt": excerpt,
    }]
    respond = transport.messages_create

    def supported(**kwargs):
        answer = respond(**kwargs)
        if not kwargs["model"].startswith("deepseek"):
            answer["answers"]["release:0:lineage:0:supported"]["noul"] = 0.9
        return answer

    monkeypatch.setattr(transport, "messages_create", supported)
    runner._run_post_fetch([], run_id="child-first")
    assert pulse_processing.process_saved_findings()["failed"] == 0
    assert not models.ProductRelationship.objects.exists()
    child = models.Product.objects.get(display_name="Qwen4")
    parent_post = models.Post.objects.create(tweet_id="parent-qwen3", author=state.post.author, text="We released Qwen3")
    parent_finding = finding(name="Qwen3", key="3" * 64)
    parent_finding["assertions"][0].update(assertion_text=parent_post.text, source_excerpt=parent_post.text)
    parent_finding["issuer_evidence"] = {"relation": "source_author", "source_locator": None,
                                        "source_excerpt": parent_post.text, "observed_name": None}
    saved = persist_classified_release_findings(source={"kind": "post", "id": parent_post.pk},
             revision_id="b" * 64, content_fingerprint="c" * 64, extraction_version="test", findings=[parent_finding])
    parent = resolve_saved_release_finding(claim_id=saved["findings"][0]["anchor_claim_id"])
    assert parent["status"] == "created"
    job = models.CollectionJob.objects.get(operation="lineage_wakeup")
    control = pulse_control.read_status()
    pulse_control.request_state("stopped", expected_revision=control["desired_revision"], actor="fixture", reason="test")
    assert pulse_processing.process_saved_findings()["status"] == "stopped"
    job.refresh_from_db()
    assert job.last_attempt_id is None and not models.ProductRelationship.objects.exists()
    control = pulse_control.read_status()
    pulse_control.request_state("running", expected_revision=control["desired_revision"], actor="fixture", reason="test")
    result = pulse_processing.process_saved_findings()
    assert result["lineage_wakeup"]["status"] == "complete"
    assert result["failed"] == 0 and result["processed"] == 1
    job.refresh_from_db()
    assert job.last_success_id
    edge = models.ProductRelationship.objects.get()
    assert str(edge.parent_product.product_key) == parent["product_key"]
    assert edge.child_product_id == child.product_key
    assert len(transport.calls) == 2
    again = pulse_processing.process_saved_findings()
    assert again["lineage_wakeup"]["status"] == "idle"
    assert models.ProductRelationship.objects.count() == 1 and len(transport.calls) == 2


def test_budget_blocked_wakeup_is_reported_and_does_not_starve_another_job(tmp_path, settings):
    from django.db import transaction

    from core.product_release_lineage_recovery import register_lineage_wakeup
    from tests.test_product_release_lineage import _two_saved_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="test")
    parent, _ = _two_saved_findings()
    with transaction.atomic():
        blocked = register_lineage_wakeup(parent_claim_id=parent["anchor_claim_id"], cause_review_id=None,
                   budgets={"requests": 1, "bytes": 1, "seconds": 5, "items": 2})
        ready = register_lineage_wakeup(parent_claim_id=parent["anchor_claim_id"], cause_review_id=None,
                   budgets={"requests": 1, "bytes": 10000, "seconds": 5, "items": 2})
    first = pulse_processing.process_saved_findings()
    assert first["lineage_wakeup"]["status"] == "budget_blocked"
    assert any(row["code"] == "lineage_wakeup_budget_blocked" for row in pulse_control.read_status()["diagnostics"])
    assert models.CollectionJob.objects.get(pk=blocked["job_id"]).last_success_id is None
    second = pulse_processing.process_saved_findings()
    assert second["lineage_wakeup"]["status"] == "complete"
    assert models.CollectionJob.objects.get(pk=ready["job_id"]).last_success_id is not None
    third = pulse_processing.process_saved_findings()
    assert third["lineage_wakeup"]["status"] == "idle"


def test_child_processing_during_uncommitted_parent_qualification_retries(monkeypatch, tmp_path, settings):
    from core import product_release_lineage_recovery
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_detection_queue import enqueue_posts
    from core.product_release_dossiers import persist_classified_release_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="test")
    state, runner, transport = setup_cycle(monkeypatch, official=True)
    excerpt = "Qwen4 succeeds Qwen3."
    state.post.text += " " + excerpt
    state.post.save(update_fields=["text"])
    transport.document["release_findings"]["findings"][0]["lineage_evidence"] = [{
        "relationship_kind": "new_version", "parent_observed_name": "Qwen3",
        "source_locator": "post", "source_excerpt": excerpt,
    }]
    respond = transport.messages_create

    def supported(**kwargs):
        answer = respond(**kwargs)
        if not kwargs["model"].startswith("deepseek"):
            answer["answers"]["release:0:lineage:0:supported"]["noul"] = 0.9
        return answer

    monkeypatch.setattr(transport, "messages_create", supported)
    runner._run_post_fetch([], run_id="child-before-parent-commit")
    assert pulse_processing.process_saved_findings()["failed"] == 0
    parent_post = models.Post.objects.create(tweet_id="parent-qwen3", author=state.post.author, text="We released Qwen3")
    item = finding(name="Qwen3", key="3" * 64)
    item["assertions"][0].update(assertion_text=parent_post.text, source_excerpt=parent_post.text)
    item["issuer_evidence"] = {"relation": "source_author", "source_locator": None,
                               "source_excerpt": parent_post.text, "observed_name": None}
    saved = persist_classified_release_findings(source={"kind": "post", "id": parent_post.pk},
             revision_id="b" * 64, content_fingerprint="c" * 64, extraction_version="test", findings=[item])
    entered, release = Event(), Event()
    original = product_release_lineage_recovery.register_lineage_wakeup

    def pause_registration(**kwargs):
        value = original(**kwargs)
        if str(kwargs["parent_claim_id"]) == str(saved["findings"][0]["anchor_claim_id"]):
            entered.set()
            assert release.wait(20)
        return value

    monkeypatch.setattr(product_release_lineage_recovery, "register_lineage_wakeup", pause_registration)

    def qualify_parent():
        try:
            return resolve_saved_release_finding(claim_id=saved["findings"][0]["anchor_claim_id"])
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(qualify_parent)
        try:
            assert entered.wait(20)
            enqueue_posts([state.pk])
            pending = pulse_processing.process_saved_findings()
            assert pending["failed"] == 0 and pending["association_pending"] == 1
            assert not models.ProductRelationship.objects.exists()
        finally:
            release.set()
        parent = task.result(timeout=30)
    monkeypatch.setattr(product_release_lineage_recovery, "register_lineage_wakeup", original)
    assert parent["status"] == "created"
    recovered = pulse_processing.process_saved_findings()
    assert recovered["failed"] == 0 and recovered["processed"] == 1
    edge = models.ProductRelationship.objects.get()
    assert str(edge.parent_product.product_key) == parent["product_key"]
    assert len(transport.calls) == 2


def test_busy_wakeup_moves_behind_another_ready_job(tmp_path, settings):
    from django.db import transaction

    from core.collection_state import claim_job
    from core.product_release_lineage_recovery import register_lineage_wakeup
    from tests.test_product_release_lineage import _two_saved_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="test")
    parent, _ = _two_saved_findings()
    with transaction.atomic():
        busy = register_lineage_wakeup(parent_claim_id=parent["anchor_claim_id"], cause_review_id=None,
                   budgets={"requests": 1, "bytes": 9000, "seconds": 5, "items": 2})
        ready = register_lineage_wakeup(parent_claim_id=parent["anchor_claim_id"], cause_review_id=None,
                   budgets={"requests": 1, "bytes": 10000, "seconds": 5, "items": 2})
    claim_job(busy["job_id"], typed=True, manual_authorized=True)
    # Simulate an older interrupted/long-running job ahead of fresh work.
    from datetime import timedelta

    models.CollectionJob.objects.filter(pk=busy["job_id"]).update(updated_at=timezone.now() - timedelta(minutes=1))
    first = pulse_processing.process_saved_findings()
    assert first["lineage_wakeup"]["status"] == "busy"
    second = pulse_processing.process_saved_findings()
    assert second["lineage_wakeup"]["status"] == "complete"
    assert models.CollectionJob.objects.get(pk=ready["job_id"]).last_success_id is not None
