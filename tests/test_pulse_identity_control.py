"""Identity stop covers saved findings and saved acquisition recovery together."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest
from django.db import connection, connections, transaction

from core import models
from core import product_release_acquisition as acquisition
from core.product_release_detection_queue import enqueue_posts
from core.product_release_dossiers import record_release_report
from monitor import pulse_control, pulse_processing

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def control(monkeypatch, tmp_path, settings):
    monkeypatch.setenv("X_MONITOR_CLASSIFIER_PIPELINE", "compressed8_pulse_v1")
    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = False
    # These tests exercise collection/integration, never a broker or live provider.
    monkeypatch.setattr(acquisition, "_dispatch_if_enabled", lambda job: None)
    pulse_control.initialize(directory=tmp_path, state="stopped", actor="fixture", reason="test")
    return tmp_path


def request_state(state):
    row = pulse_control.read_status()
    return pulse_control.request_state(
        state, expected_revision=row["desired_revision"], actor="fixture", reason="test",
    )


def captured_job(*, name="Model4"):
    """Real collection/capture through an offline HTTP transport."""
    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"},
    )
    url = f"https://huggingface.co/lab/{name}"
    post = models.Post.objects.create(tweet_id=f"capture-{name}", text=f"Announcing {name} {url}")
    dossier, _, _ = record_release_report(
        post=post, record={"model_name": name, "source_url": url},
        release_identity=f"control-{name}", observed_name=name, source_url=url,
        maturity_code="unknown", release_value=None, release_precision="unknown", extraction_version="test",
    )
    claim = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=dossier, claim_kind_reference__code="release_report",
    )
    job = acquisition.queue_hf_name_search(claim.pk)
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"id": f"lab/{name}"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = acquisition.execute_hf_name_search(job.pk, client=client)
    job.refresh_from_db()
    scope = job.last_success.scopes.get(scope_kind="release_integration")
    assert len(requests) == result["physical_requests"] == 1
    assert job.last_success.observations.count() == 1
    assert models.CollectionRequest.objects.filter(attempt__run=job.last_success).count() == 1
    return job, scope, result


def recover(job):
    def forbidden(request):
        pytest.fail(f"Saved integration attempted a provider request: {request.url}")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        return acquisition.drain_due_hf_acquisitions(
            client=client, execute=True, job_ids=[str(job.pk)],
        )


def saved_posts(monkeypatch, count=1):
    from core import classified_product_releases, product_identity

    posts = []
    for number in range(count):
        post = models.Post.objects.create(tweet_id=f"identity-{number}", text="Saved release evidence")
        models.PostEnrichmentState.objects.create(post=post)
        enqueue_posts([post.pk])
        posts.append(post)
    # Inject only the saved evidence read; exercise the actual drain, transactions,
    # queue completion, global lock and operator acknowledgements.
    monkeypatch.setattr(classified_product_releases, "read_publication_findings", lambda post_id: (
        {"anchor_claim_id": post_id},
    ))

    def associate(**kwargs):
        # Synthetic IDs are not domain evidence. Keep the actual queue/lock
        # path and ensure association follows the committed identity write.
        assert not connection.in_atomic_block
        assert pulse_control.read_status()["status"] in {"stop_requested", "running"}
        return {"status": "complete", "merged_ids": [], "more_remaining": False}

    monkeypatch.setattr(product_identity, "reconcile_product_release_events", associate)
    return posts


def test_stopped_recovery_keeps_capture_pending_until_resume(control, monkeypatch, settings):
    from core import product_release_source_queue, source_metric_projection
    from monitor.tasks import recover_due_product_releases

    job, scope, result = captured_job()
    assert result["integration"]["status"] == "stopped"
    assert not models.Product.objects.exists()
    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = True
    # Keep this recovery regression on its real saved-finding/acquisition paths.
    monkeypatch.setattr(product_release_source_queue, "drain_mapping_reconciliations", lambda **kw: {})
    monkeypatch.setattr(product_release_source_queue, "drain_observations", lambda **kw: {})
    monkeypatch.setattr(source_metric_projection, "recover_release_projection_followups", lambda **kw: {})
    monkeypatch.setattr(acquisition, "recover_release_registrations", lambda **kw: {})
    recovered = recover_due_product_releases()
    assert recovered["detection"]["status"] == "stopped"
    assert recovered["jobs"][0]["integration"]["status"] == "stopped"
    assert recovered["provider_calls"] == 0
    scope.refresh_from_db()
    assert scope.outcome == "pending" and scope.raw_count == 0 and scope.retry_at is None
    assert not models.Product.objects.exists()
    assert job.last_success.observations.get().product_id is None
    request_state("running")
    resumed = recover(job)
    assert resumed["provider_calls"] == 0
    assert resumed["jobs"][0]["integration"]["status"] == "complete"
    assert models.Product.objects.get().repo_id == "lab/Model4"
    assert job.last_success.observations.get().product_id is not None
    scope.refresh_from_db()
    assert scope.outcome == "complete" and scope.raw_count == 0


def test_unavailable_control_defers_without_spending_failure_retries(control, settings):
    settings.PULSE_CONTROL_DIRECTORY = ""
    job, scope, result = captured_job()
    assert result["integration"]["status"] == "unavailable"
    for _ in range(4):
        assert recover(job)["jobs"][0]["integration"]["status"] == "unavailable"
    scope.refresh_from_db()
    assert scope.outcome == "pending" and scope.raw_count == 0 and scope.retry_at is None
    assert not models.Product.objects.exists()
    settings.PULSE_CONTROL_DIRECTORY = str(control)
    request_state("running")
    assert recover(job)["jobs"][0]["integration"]["status"] == "complete"


def test_legacy_route_integration_preserves_behavior(control, monkeypatch):
    monkeypatch.setenv("X_MONITOR_CLASSIFIER_PIPELINE", "two_role")
    _job, scope, result = captured_job()
    assert result["integration"]["status"] == "complete"
    assert scope.outcome == "complete"
    assert models.Product.objects.get().repo_id == "lab/Model4"
    assert pulse_control.read_status()["status"] == "stop_requested"


def test_stop_between_posts_acknowledges_only_after_first_commit(control, monkeypatch):
    from core import product_release_dossiers

    posts = saved_posts(monkeypatch, count=2)
    request_state("running")
    calls, committed_states = [], []

    def resolve(*, claim_id):
        assert connection.in_atomic_block
        calls.append(claim_id)
        models.Product.objects.create(repo_id=f"fixture/{claim_id}", display_name=claim_id)
        if len(calls) == 1:
            request_state("stopped")
            assert pulse_control.read_status()["status"] == "stop_requested"
            transaction.on_commit(lambda: committed_states.append(pulse_control.read_status()["status"]))
        return {"status": "resolved"}

    monkeypatch.setattr(product_release_dossiers, "resolve_saved_release_finding", resolve)
    result = pulse_processing.process_saved_findings()
    assert calls == [posts[0].pk]
    assert committed_states == ["stop_requested"]
    assert result["status"] == pulse_control.read_status()["status"] == "stopped"
    assert result["processed"] == 1 and result["failed"] == 0
    second = models.ProductReleaseDetectionState.objects.get(post=posts[1])
    assert second.completed_at is None and second.attempts == 0
    request_state("running")
    assert pulse_processing.process_saved_findings()["processed"] == 1
    assert calls == [post.pk for post in posts]


@pytest.mark.parametrize("owner", ["processor", "acquisition"])
def test_global_lock_excludes_both_identity_writers(control, monkeypatch, owner):
    from core import product_release_dossiers

    _job, scope, _ = captured_job()
    saved_posts(monkeypatch)
    request_state("running")
    entered, finish = Event(), Event()
    original = acquisition._integrate_acquisition_run

    def held_operation(*args, **kwargs):
        assert connection.in_atomic_block
        entered.set()
        assert finish.wait(10), "test did not release the identity transaction"
        if owner == "acquisition":
            return original(*args, **kwargs)
        return {"status": "resolved"}

    if owner == "processor":
        monkeypatch.setattr(product_release_dossiers, "resolve_saved_release_finding", held_operation)
    else:
        monkeypatch.setattr(acquisition, "_integrate_acquisition_run", held_operation)

    def worker():
        try:
            if owner == "processor":
                return pulse_processing.process_saved_findings()
            return acquisition.integrate_acquisition_run(scope.run_id)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(worker)
        try:
            assert entered.wait(10), "identity worker never entered its transaction"
            request_state("stopped")
            assert pulse_processing.process_saved_findings()["status"] == "busy"
            assert acquisition.integrate_acquisition_run(scope.run_id)["status"] == "busy"
            assert pulse_control.read_status()["status"] == "stop_requested"
            assert not models.Product.objects.exists()
        finally:
            finish.set()
        result = future.result(timeout=10)
        if owner == "processor":
            assert result["processed"] == 1 and result["failed"] == 0
        else:
            assert result["status"] == "complete"
    assert pulse_control.read_status()["status"] == "stopped"
    scope.refresh_from_db()
    assert scope.raw_count == 0
    if owner == "processor":
        assert scope.outcome == "pending"
        assert not models.Product.objects.exists()
    else:
        assert scope.outcome == "complete"
        assert models.Product.objects.get().repo_id == "lab/Model4"


def test_nested_integration_cannot_acknowledge_before_outer_commit(control):
    job, scope, _ = captured_job()
    request_state("running")
    with pulse_processing.identity_application():
        with transaction.atomic():
            request_state("stopped")
            result = acquisition.integrate_acquisition_run(scope.run_id)
            assert result["status"] == "complete"
            assert models.Product.objects.exists()
            assert pulse_control.read_status()["status"] == "stop_requested"
        assert pulse_control.read_status()["status"] == "stop_requested"
    assert pulse_control.read_status()["status"] == "stopped"
    assert job.last_success.observations.get().product_id is not None


def test_unrelated_transaction_defers_lock_until_commit(control):
    _job, scope, _ = captured_job()
    request_state("running")
    with transaction.atomic():
        models.CollectionScopeRun.objects.select_for_update().get(pk=scope.pk)
        assert acquisition.integrate_acquisition_run(scope.run_id)["status"] == "transaction_pending"
        assert not models.Product.objects.exists()
    assert models.Product.objects.get().repo_id == "lab/Model4"
    assert pulse_control.read_status()["status"] == "running"
