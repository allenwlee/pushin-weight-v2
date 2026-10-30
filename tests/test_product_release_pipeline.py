"""Release intake must preserve uncertainty and immutable evidence in PostgreSQL."""

import pytest
from django.db import IntegrityError, transaction

from core import models
from core.event_dossiers import add_claim, attach_source, create_dossier, identity_key

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def evidence(key):
    event = create_dossier(
        event_kind="product_release", identity_key=identity_key("test-intake", key)
    )
    post = models.Post.objects.create(tweet_id=key, text="Announcing something new")
    source = attach_source(event.pk, post_id=post.pk)
    claim = add_claim(
        source.pk,
        claim_kind="announcement",
        scope_key="unknown",
        assertion_text=post.text,
        source_excerpt=post.text,
        extraction_version="test-v1",
    )
    return event, claim


def test_intake_decision_cannot_use_another_dossiers_evidence_or_be_rewritten():
    event, claim = evidence("decision-one")
    _, other = evidence("decision-two")
    values = {
        "event_dossier": event,
        "supporting_claim": claim,
        "outcome": "pending",
        "actor": "test",
        "method_version": "test-v1",
        "reason": "Identity unresolved",
        "input_hash": "a" * 64,
    }
    saved = models.EventDossierIntakeDecision.objects.create(**values)
    with pytest.raises(IntegrityError), transaction.atomic():
        models.EventDossierIntakeDecision.objects.filter(pk=saved.pk).update(
            outcome="scam"
        )
    values.update(supporting_claim=other, input_hash="b" * 64)
    with pytest.raises(IntegrityError), transaction.atomic():
        models.EventDossierIntakeDecision.objects.create(**values)


def test_intake_decision_requires_a_reason_and_a_known_outcome():
    event, claim = evidence("invalid-decision")
    values = {
        "event_dossier": event,
        "supporting_claim": claim,
        "outcome": "confirmed",
        "actor": "test",
        "method_version": "test-v1",
        "reason": "",
        "input_hash": "a" * 64,
    }
    with pytest.raises(IntegrityError), transaction.atomic():
        models.EventDossierIntakeDecision.objects.create(**values)


def test_stored_post_replay_keeps_unknown_release_and_is_idempotent():
    from datetime import timedelta

    from django.utils import timezone

    from core.product_release_pipeline import persist_source
    from core.product_release_replay import ReplayWindow
    from core.product_release_sources import post_page

    now = timezone.now()
    models.Post.objects.create(
        tweet_id="unknown-release", text="Today we announce a new model", created_at=now
    )
    rows = post_page(
        ReplayWindow(now - timedelta(minutes=1), now + timedelta(minutes=1))
    )
    assert len(rows) == 1
    first = persist_source(rows[0])
    assert first["disposition"] == "pending"
    counts = (
        models.EventDossier.objects.count(),
        models.EventDossierClaim.objects.count(),
        models.EventDossierIntakeDecision.objects.count(),
    )
    assert persist_source(rows[0])["dossier_ids"] == first["dossier_ids"]
    assert counts == (
        models.EventDossier.objects.count(),
        models.EventDossierClaim.objects.count(),
        models.EventDossierIntakeDecision.objects.count(),
    )
    assert not models.ProductReleaseDetail.objects.exists()
    assert not models.Product.objects.exists()


def test_saved_release_report_provides_search_lead_without_repository_link():
    from core.product_release_dossiers import record_release_report
    from core.product_release_pipeline import persist_source
    from core.product_release_sources import stored_posts

    post = models.Post.objects.create(
        tweet_id="saved-name-no-repository", text="Announcing Nanbeige4.3-33B"
    )
    brand = models.Brand.objects.create(nickname="nanbeige-test")
    event, _, _ = record_release_report(
        post=post,
        record={"model_name": "Nanbeige4.3-33B"},
        release_identity="unresolved-nanbeige",
        observed_name="Nanbeige4.3-33B",
        source_url=None,
        brand=brand,
        maturity_code="unknown",
        release_value=None,
        release_precision="unknown",
        extraction_version="saved-classification-v1",
    )
    report = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=event,
        claim_kind_reference__code="release_report",
    )
    source = stored_posts(["saved-name-no-repository"])[0]
    result = persist_source(source)
    assert result["dossier_ids"] == [str(event.pk)]
    assert result["search_leads"] == [
        {
            "term": "Nanbeige4.3-33B",
            "locator": f"event_dossier_claims:{report.pk}",
            "eligible": True,
        }
    ]
    assert result["references"] == []
    assert not models.Product.objects.exists()
    assert persist_source(source) == result


@pytest.mark.parametrize("status,outcome", [(200, "found"), (404, "missing_or_private"),
                                           (429, "throttled_or_forbidden")])
def test_github_repository_reference_is_retained_as_unresolved_and_reused(status, outcome):
    import httpx

    from core.measurement_taxonomy import digest
    from core.product_release_acquisition import (
        drain_due_hf_acquisitions,
        execute_github_repository,
        queue_github_repository,
    )
    from core.product_release_pipeline import persist_source
    from core.product_release_sources import stored_posts

    assert not models.DataSource.objects.filter(pk="github").exists()
    models.Post.objects.create(tweet_id="github-release-lead", text=(
        "We release our agent at https://github.com/Example/Agent"
    ))
    source = stored_posts(["github-release-lead"])[0]
    first = persist_source(source)
    assert models.DataSource.objects.get(pk="github").enabled is False
    lead = models.EventDossierClaim.objects.get(scope_key__startswith="github_repo_lead:")
    assert lead.source_locator == "https://github.com/Example/Agent"
    assert "role is unresolved" in lead.assertion_text
    assert not models.Product.objects.exists()
    assert persist_source(source) == first
    assert models.EventDossierClaim.objects.filter(scope_key__startswith="github_repo_lead:").count() == 1
    job = queue_github_repository(lead.pk)
    assert job.targets.get().native_identifier == "Example/Agent"
    assert queue_github_repository(lead.pk).pk == job.pk
    assert job.dossier_claim_links.count() == 1
    assert not models.CollectionRequest.objects.exists()
    fabricated = add_claim(
        lead.event_dossier_source_id, claim_kind="release_context",
        scope_key="github_repo_lead:" + digest("other/unrelated"),
        assertion_text="Unrelated repository", source_excerpt="Unrelated repository",
        source_locator="https://github.com/other/unrelated", extraction_version="test-v1",
    )
    with pytest.raises(ValueError, match="differs from saved source"):
        queue_github_repository(fabricated.pk)
    assert models.CollectionJob.objects.count() == 1
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(
        status, json={"id": 42, "full_name": "Example/Agent", "private": False,
                   "stargazers_count": 7, "owner": {"login": "Example"}}
    )))
    batch = drain_due_hf_acquisitions(client=client, execute=True, job_ids=[str(job.pk)])
    assert batch["provider_calls"] == 1
    result = batch["jobs"][0]
    assert result["outcome"] == outcome and result["physical_requests"] == 1
    if status == 200:
        from core.collection_capture import observation_object_documents

        assert models.EventDossierClaim.objects.filter(scope_key__startswith="github_capture:").count() == 1
        observation = models.CollectionObservation.objects.get(projection_kind="github-release-exact-v1")
        payload, dimensions, _ = observation_object_documents(observation)
        assert payload["stargazers_count"] == 7 and dimensions["kind"] == "repository"
        assert execute_github_repository(job.pk, client=client)["physical_requests"] == 0
        models.Post.objects.create(tweet_id="github-second-release", text=(
            "We launch another product at https://github.com/Example/Agent"
        ))
        persist_source(stored_posts(["github-second-release"])[0])
        second = models.EventDossierClaim.objects.get(
            scope_key__startswith="github_repo_lead:",
            event_dossier_source__post_id="github-second-release",
        )
        assert queue_github_repository(second.pk).pk == job.pk
        assert models.EventDossierClaim.objects.filter(scope_key__startswith="github_capture:").count() == 2
        assert models.CollectionRequest.objects.count() == 1
    else:
        job.refresh_from_db()
        assert job.last_attempt.status == "partial" and job.next_retry_at is not None
        assert not models.EventDossierClaim.objects.filter(scope_key__startswith="github_capture:").exists()
    assert not models.Product.objects.exists()


def test_github_checkpoint_recovers_without_refetch(monkeypatch):
    from datetime import timedelta

    import httpx
    from django.utils import timezone

    import core.collection_state as state
    from core.product_release_acquisition import (
        drain_due_hf_acquisitions,
        execute_github_repository,
        queue_github_repository,
    )
    from core.product_release_pipeline import persist_source
    from core.product_release_sources import stored_posts

    models.DataSource.objects.get_or_create(
        pk="github", defaults={"name": "GitHub", "source_type": "model_adoption"}
    )
    models.Post.objects.create(tweet_id="github-crash", text=(
        "We release https://github.com/Example/Agent"
    ))
    persist_source(stored_posts(["github-crash"])[0])
    lead = models.EventDossierClaim.objects.get(scope_key__startswith="github_repo_lead:")
    job = queue_github_repository(lead.pk)
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"id": 42, "full_name": "Example/Agent", "private": False})
    client = httpx.Client(transport=httpx.MockTransport(respond))
    finish = state.finish_run
    monkeypatch.setattr(state, "finish_run", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("crash")))
    with pytest.raises(RuntimeError, match="crash"):
        execute_github_repository(job.pk, client=client)
    run = models.CollectionRun.objects.get(job=job)
    models.CollectionRun.objects.filter(pk=run.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
    monkeypatch.setattr(state, "finish_run", finish)
    batch = drain_due_hf_acquisitions(client=client, execute=True, job_ids=[str(job.pk)])
    assert batch["provider_calls"] == 0
    result = batch["jobs"][0]
    assert result["outcome"] == "found" and result["physical_requests"] == 0
    assert len(calls) == 1 and models.CollectionRequest.objects.filter(attempt__run=run).count() == 1


def test_registration_recovery_resumes_bounded_pages(monkeypatch):
    from core import product_release_acquisition as acquisition
    from core.product_release_pipeline import persist_source
    from core.product_release_sources import stored_posts

    for source in ("hf", "github"):
        models.DataSource.objects.get_or_create(
            pk=source, defaults={"name": source, "source_type": "model_adoption"}
        )
    original = acquisition.queue_github_repository
    monkeypatch.setattr(acquisition, "queue_github_repository",
                        lambda _claim_id: (_ for _ in ()).throw(RuntimeError("queue failure")))
    for index in range(2):
        post_id = f"registration-page-{index}"
        models.Post.objects.create(tweet_id=post_id, text=(
            f"We release https://github.com/Example/Agent{index}"
        ))
        persist_source(stored_posts([post_id])[0])
    attempts = []
    def temporarily_unavailable(claim_id):
        attempts.append(claim_id)
        if len(attempts) == 1:
            raise RuntimeError("one transient registration failure")
        return original(claim_id)
    monkeypatch.setattr(acquisition, "queue_github_repository", temporarily_unavailable)
    first = acquisition.recover_release_registrations(limit=1)
    second = acquisition.recover_release_registrations(limit=1)
    last = acquisition.recover_release_registrations(limit=1)
    assert first["claims"][0]["outcome"] == "registration_failed" and first["queued"] == 0
    assert second["queued"] == 1
    assert first["status"] == second["status"] == "pending"
    assert last["status"] == "complete" and last["scanned"] == 0
    retried = acquisition.recover_release_registrations(limit=1)
    assert retried["queued"] == 1
    assert models.CollectionJob.objects.filter(source_id="github").count() == 2
    assert not models.CollectionRequest.objects.exists()
    assert acquisition.recover_release_registrations(limit=1)["scanned"] == 0


def test_worker_recovers_failed_registration_and_fetches(monkeypatch, settings):
    import httpx

    from core import product_release_acquisition as acquisition
    from core.product_release_pipeline import persist_source
    from core.product_release_sources import stored_posts
    from monitor.tasks import recover_due_product_releases

    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = False
    for source in ("hf", "github"):
        models.DataSource.objects.get_or_create(
            pk=source, defaults={"name": source, "source_type": "model_adoption"}
        )
    original = acquisition.queue_github_repository
    monkeypatch.setattr(acquisition, "queue_github_repository",
                        lambda _claim_id: (_ for _ in ()).throw(RuntimeError("queue failure")))
    models.Post.objects.create(tweet_id="worker-queue-recovery", text=(
        "We release https://github.com/Example/Agent"
    ))
    persist_source(stored_posts(["worker-queue-recovery"])[0])
    monkeypatch.setattr(acquisition, "queue_github_repository", original)
    assert not models.CollectionJob.objects.exists()
    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = True
    factory = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **_kwargs: factory(transport=httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"id": 42, "full_name": "Example/Agent", "private": False})
    )))
    result = recover_due_product_releases.run()
    assert result["registration_recovery"]["queued"] == 1
    assert result["provider_calls"] == 1 and result["jobs"][0]["outcome"] == "found"
    assert models.EventDossierClaim.objects.filter(scope_key__startswith="github_capture:").count() == 1


def test_github_registration_failure_can_be_recovered(monkeypatch):
    from core import product_release_acquisition as acquisition
    from core.product_release_pipeline import persist_source
    from core.product_release_sources import stored_posts

    models.DataSource.objects.get_or_create(
        pk="github", defaults={"name": "GitHub", "source_type": "model_adoption"}
    )
    models.Post.objects.create(tweet_id="github-queue-recovery", text=(
        "We release https://github.com/Example/Agent"
    ))
    original = acquisition.queue_github_repository
    monkeypatch.setattr(acquisition, "queue_github_repository",
                        lambda _claim_id: (_ for _ in ()).throw(RuntimeError("queue failure")))
    persist_source(stored_posts(["github-queue-recovery"])[0])
    assert not models.CollectionJob.objects.exists()
    monkeypatch.setattr(acquisition, "queue_github_repository", original)
    assert acquisition.queue_saved_release_claims(persist=True)["queued"] == 1
    assert models.CollectionJob.objects.get().targets.get().native_identifier == "Example/Agent"


def test_raw_repo_lead_registration_failure_can_be_recovered(monkeypatch):
    from core import product_release_acquisition
    from core.product_release_pipeline import persist_source
    from core.product_release_sources import stored_posts

    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    models.Post.objects.create(tweet_id="raw-recovery", text=(
        "We release a model at https://huggingface.co/lab/raw-model"
    ))
    original = product_release_acquisition.queue_hf_name_search
    def fail(_claim_id):
        raise RuntimeError("temporary queue error")
    monkeypatch.setattr(product_release_acquisition, "queue_hf_name_search", fail)
    persist_source(stored_posts(["raw-recovery"])[0])
    assert models.EventDossierClaim.objects.filter(scope_key__startswith="hf_repo_lead:").count() == 1
    assert not models.CollectionJob.objects.exists()
    monkeypatch.setattr(product_release_acquisition, "queue_hf_name_search", original)
    result = product_release_acquisition.queue_saved_release_claims(persist=True)
    assert result["queued"] == 1
    assert models.CollectionJob.objects.get().targets.get().native_identifier == "lab/raw-model"
    assert not models.CollectionRequest.objects.exists()


def test_dossier_search_leads_do_not_leak_other_product_from_same_post():
    import httpx

    from core.hf_metadata_client import HFMetadataClient
    from core.product_release_acquisition import (
        dossier_name_leads,
        search_dossier_names,
    )
    from core.product_release_dossiers import record_release_report
    from core.product_release_pipeline import record_intake_decision

    post = models.Post.objects.create(
        tweet_id="family-two-products", text="Announcing Alto and Solo"
    )
    brand = models.Brand.objects.create(nickname="family-lab-test")
    events = []
    for name in ("Alto", "Solo"):
        event, _, _ = record_release_report(
            post=post,
            record={"model_name": name},
            release_identity="family-" + name,
            observed_name=name,
            source_url=None,
            brand=brand,
            maturity_code="unknown",
            release_value=None,
            release_precision="unknown",
            extraction_version="test",
        )
        events.append(event)
    assert [row["term"] for row in dossier_name_leads(events[0].pk)] == ["Alto"]
    assert [row["term"] for row in dossier_name_leads(events[1].pk)] == ["Solo"]
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=[{"id": "lab/Solo"}])

    hf = HFMetadataClient(
        httpx.Client(transport=httpx.MockTransport(respond)),
        max_requests=1,
        max_seconds=5,
    )
    results = search_dossier_names(events[1].pk, hf)
    assert len(results) == 1 and results[0]["term"] == "Solo"
    assert results[0]["repository_ids"] == ["lab/Solo"]
    assert requests[0].url.params["search"] == "Solo"
    assert not models.Product.objects.exists()
    report = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=events[1],
        claim_kind_reference__code="release_report",
    )
    record_intake_decision(
        events[1].pk, claim_id=report.pk, outcome="scam", actor="test",
        reason="Explicit evidence of impersonation",
    )
    excluded = search_dossier_names(events[1].pk, hf)
    assert excluded[0]["outcome"] == "excluded"
    assert len(requests) == 1


def test_one_lookup_job_can_be_linked_to_multiple_release_claims_without_duplicates():
    from core.collection_jobs import register_job
    from core.product_release_acquisition import link_claim_to_job
    from core.product_release_dossiers import record_release_report

    post = models.Post.objects.create(tweet_id="shared-lookup", text="Two announcements")
    brand = models.Brand.objects.create(nickname="shared-lookup-lab")
    claims = []
    for name in ("Alpha", "Beta"):
        event, _, _ = record_release_report(
            post=post, record={"model_name": name},
            release_identity="shared-lookup-" + name, observed_name=name,
            source_url=None, brand=brand, maturity_code="unknown",
            release_value=None, release_precision="unknown", extraction_version="test",
        )
        claims.append(models.EventDossierClaim.objects.get(
            event_dossier_source__event_dossier=event,
            claim_kind_reference__code="release_report",
        ))
    source, _ = models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    job = register_job(
        job_key="shared-lookup-test", source=source, purpose="catalog",
        operation="hf_catalog", mode="historical",
        definition={"version": 1, "scope": {},
                    "schedule": {"kind": "manual", "driver": "manual"},
                    "budgets": {"requests": 2, "bytes": 10000, "seconds": 10, "items": 10}},
    )
    first = link_claim_to_job(claims[0].pk, job.pk)
    assert link_claim_to_job(claims[0].pk, job.pk).pk == first.pk
    second = link_claim_to_job(claims[1].pk, job.pk)
    assert first.pk != second.pk
    assert job.dossier_claim_links.count() == 2
    assert models.CollectionJob.objects.filter(pk=job.pk).count() == 1
    with pytest.raises(IntegrityError), transaction.atomic():
        models.EventDossierClaimCollectionJob.objects.create(claim=claims[0], job=job)


def test_queue_saved_name_shares_one_bounded_job_without_provider_requests():
    import httpx

    from core.collection_capture import observation_object_documents
    from core.product_release_acquisition import (
        execute_hf_name_search,
        queue_hf_name_search,
    )
    from core.product_release_dossiers import record_release_report

    brand = models.Brand.objects.create(nickname="lookup-publisher")
    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    claims = []
    for index in range(2):
        post = models.Post.objects.create(
            tweet_id=f"search-source-{index}", text="We announce Nanbeige4.3-33B"
        )
        event, _, _ = record_release_report(
            post=post, record={"model_name": "Nanbeige4.3-33B"},
            release_identity=f"source-release-{index}", observed_name="Nanbeige4.3-33B",
            source_url=None, brand=brand, maturity_code="unknown", release_value=None,
            release_precision="unknown", extraction_version="test",
        )
        claims.append(models.EventDossierClaim.objects.get(
            event_dossier_source__event_dossier=event, claim_kind_reference__code="release_report"
        ))
    first = queue_hf_name_search(claims[0].pk)
    second = queue_hf_name_search(claims[1].pk)
    assert first.pk == second.pk == queue_hf_name_search(claims[0].pk).pk
    assert first.state == "ready" and first.mode == "manual"
    assert first.budgets == {"requests": 3, "bytes": 1048576, "seconds": 30, "items": 10}
    assert first.targets.get().native_identifier == "Nanbeige4.3-33B"
    assert first.dossier_claim_links.count() == 2
    assert not models.CollectionRun.objects.exists()
    assert not models.CollectionRequest.objects.exists()
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=[{"id": "lab/Nanbeige4.3-33B", "likes": 7}])

    client = httpx.Client(transport=httpx.MockTransport(respond))
    result = execute_hf_name_search(first.pk, client=client)
    assert result["outcome"] == "found" and result["request_count"] == 1
    request = models.CollectionRequest.objects.get()
    assert request.archive_id and request.transport_outcome == "received"
    observation = models.CollectionObservation.objects.get(run_id=result["run_id"])
    assert observation_object_documents(observation)[0]["id"] == "lab/Nanbeige4.3-33B"
    assert observation.inputs.get().input_request_id == request.pk
    observation.payload_sha256 = "0" * 64
    with pytest.raises(ValueError, match="identity or content"):
        observation_object_documents(observation)
    assert execute_hf_name_search(first.pk, client=client)["run_id"] == result["run_id"]
    assert len(requests) == 1 and models.CollectionObservation.objects.count() == 1
    assert not models.Product.objects.exists()


def test_name_search_selects_at_most_three_exact_followups_with_retained_evidence():
    import httpx

    from core.collection_capture import observation_object_documents
    from core.product_release_acquisition import (
        execute_hf_name_search,
        queue_hf_name_search,
    )
    from core.product_release_dossiers import record_release_report

    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    post = models.Post.objects.create(tweet_id="no-link-followups", text="Announcing Model4")
    dossier, _, _ = record_release_report(
        post=post, record={"model_name": "Model4"}, release_identity="no-link-followups",
        observed_name="Model4", source_url=None, maturity_code="unknown", release_value=None,
        release_precision="unknown", extraction_version="test",
    )
    claim = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=dossier, claim_kind_reference__code="release_report"
    )
    job = queue_hf_name_search(claim.pk)
    calls = []
    def respond(request):
        calls.append(request.url.path)
        if request.url.path == "/api/models":
            return httpx.Response(200, json=[{"id": f"lab{i}/Model4"} for i in range(4)])
        return httpx.Response(200, json={"id": request.url.path.removeprefix("/api/models/")})
    client = httpx.Client(transport=httpx.MockTransport(respond))
    result = execute_hf_name_search(job.pk, client=client)
    assert result["physical_requests"] == 1
    children = models.CollectionJob.objects.filter(targets__target_role="exact_model")
    assert children.count() == 3
    assert set(children.values_list("targets__native_identifier", flat=True)) == {
        "lab0/Model4", "lab1/Model4", "lab2/Model4"
    }
    for child in children:
        parent = child.dossier_claim_links.get().claim.event_dossier_source.collection_observation
        assert str(parent.run_id) == result["run_id"]
        assert observation_object_documents(parent)[0]["id"] == child.targets.get().native_identifier
    first = children.order_by("created_at").first()
    exact = execute_hf_name_search(first.pk, client=client)
    exact_obs = models.CollectionObservation.objects.get(run_id=exact["run_id"])
    assert observation_object_documents(exact_obs)[0]["id"] == first.targets.get().native_identifier
    assert dossier.sources.filter(collection_observation=exact_obs).exists()
    assert exact_obs.processing_outcome == "unresolved" and not models.Product.objects.exists()
    execute_hf_name_search(job.pk, client=client)
    assert children.count() == 3 and len(calls) == 2


@pytest.mark.parametrize("followup", ["search_hit", "publisher_socials"])
def test_failed_followup_registration_is_recovered_without_refetch(followup, monkeypatch):
    from datetime import timedelta

    import httpx
    from django.utils import timezone

    from core import product_release_acquisition as acquisition
    from core.product_release_dossiers import record_release_report

    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    url = "https://huggingface.co/lab/Model4" if followup == "publisher_socials" else None
    post = models.Post.objects.create(tweet_id="followup-recovery", text=f"Announcing Model4 {url or ''}")
    dossier, _, _ = record_release_report(
        post=post, record={"model_name": "Model4", "source_url": url},
        release_identity="followup-recovery", observed_name="Model4", source_url=url,
        maturity_code="unknown", release_value=None, release_precision="unknown", extraction_version="test",
    )
    claim = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=dossier, claim_kind_reference__code="release_report"
    )
    job = acquisition.queue_hf_name_search(claim.pk)
    function_name = "queue_hf_search_hit" if followup == "search_hit" else "queue_hf_publisher_socials"
    original = getattr(acquisition, function_name)
    def fail(*_args):
        raise RuntimeError("temporary registration failure")
    monkeypatch.setattr(acquisition, function_name, fail)
    calls = []
    def respond(request):
        calls.append(request)
        body = [{"id": "lab/Model4"}] if followup == "search_hit" else {"id": "lab/Model4"}
        return httpx.Response(200, json=body)
    client = httpx.Client(transport=httpx.MockTransport(respond))
    result = acquisition.execute_hf_name_search(job.pk, client=client)
    assert result["integration"]["status"] == "pending"
    scope = models.CollectionRun.objects.get(pk=result["run_id"]).scopes.get(scope_kind="release_integration")
    assert scope.raw_count == 1 and scope.retry_at is not None
    assert acquisition.drain_due_hf_acquisitions(client=client, job_ids=[str(job.pk)])["selected"] == 0
    monkeypatch.setattr(acquisition, function_name, original)
    models.CollectionScopeRun.objects.filter(pk=scope.pk).update(retry_at=timezone.now() - timedelta(seconds=1))
    recovered = acquisition.drain_due_hf_acquisitions(client=client, execute=True, job_ids=[str(job.pk)])
    assert recovered["provider_calls"] == 0 and recovered["jobs"][0]["integration"]["status"] == "complete"
    expected = "exact_model" if followup == "search_hit" else "publisher_socials"
    assert models.CollectionJob.objects.filter(targets__target_role=expected).count() == 1
    assert len(calls) == 1 and not models.Product.objects.exists()


def test_crash_after_capture_completion_recovers_pending_integration(monkeypatch):
    import httpx

    from core import product_release_acquisition as acquisition
    from core.product_release_dossiers import record_release_report

    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    post = models.Post.objects.create(tweet_id="integration-crash", text="Announcing Model4")
    dossier, _, _ = record_release_report(
        post=post, record={"model_name": "Model4"}, release_identity="integration-crash",
        observed_name="Model4", source_url=None, maturity_code="unknown", release_value=None,
        release_precision="unknown", extraction_version="test",
    )
    claim = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=dossier, claim_kind_reference__code="release_report"
    )
    job = acquisition.queue_hf_name_search(claim.pk)
    calls = []
    client = httpx.Client(transport=httpx.MockTransport(lambda request: (
        calls.append(request) or httpx.Response(200, json=[{"id": "lab/Model4"}])
    )))
    original = acquisition.integrate_acquisition_run
    def crash(_run_id):
        raise RuntimeError("crash after capture completion")
    monkeypatch.setattr(acquisition, "integrate_acquisition_run", crash)
    with pytest.raises(RuntimeError, match="crash after capture"):
        acquisition.execute_hf_name_search(job.pk, client=client)
    job.refresh_from_db()
    assert job.last_success_id is not None
    assert job.last_success.scopes.get(scope_kind="release_integration").outcome == "pending"
    monkeypatch.setattr(acquisition, "integrate_acquisition_run", original)
    recovered = acquisition.drain_due_hf_acquisitions(client=client, execute=True, job_ids=[str(job.pk)])
    assert recovered["provider_calls"] == 0
    assert recovered["jobs"][0]["integration"]["status"] == "complete"
    assert models.CollectionJob.objects.filter(targets__target_role="exact_model").count() == 1
    assert len(calls) == 1


def test_followup_registration_stops_after_three_failed_attempts(monkeypatch):
    from datetime import timedelta

    import httpx
    from django.utils import timezone

    from core import product_release_acquisition as acquisition
    from core.product_release_dossiers import record_release_report

    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    post = models.Post.objects.create(tweet_id="followup-limit", text="Announcing Model4")
    dossier, _, _ = record_release_report(
        post=post, record={"model_name": "Model4"}, release_identity="followup-limit",
        observed_name="Model4", source_url=None, maturity_code="unknown", release_value=None,
        release_precision="unknown", extraction_version="test",
    )
    claim = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=dossier, claim_kind_reference__code="release_report"
    )
    job = acquisition.queue_hf_name_search(claim.pk)
    calls, failures = [], []
    def fail(*_args):
        failures.append(1)
        raise RuntimeError("persistent failure")
    monkeypatch.setattr(acquisition, "queue_hf_search_hit", fail)
    client = httpx.Client(transport=httpx.MockTransport(lambda request: (
        calls.append(request) or httpx.Response(200, json=[{"id": "lab/Model4"}])
    )))
    result = acquisition.execute_hf_name_search(job.pk, client=client)
    scope = models.CollectionRun.objects.get(pk=result["run_id"]).scopes.get(scope_kind="release_integration")
    for _ in range(2):
        models.CollectionScopeRun.objects.filter(pk=scope.pk).update(retry_at=timezone.now() - timedelta(seconds=1))
        assert acquisition.drain_due_hf_acquisitions(client=client, execute=True, job_ids=[str(job.pk)])["selected"] == 1
    scope.refresh_from_db()
    assert scope.outcome == "failed" and scope.raw_count == 3
    assert acquisition.drain_due_hf_acquisitions(client=client, execute=True, job_ids=[str(job.pk)])["selected"] == 0
    assert len(failures) == 3 and len(calls) == 1


def test_bounded_claim_sweep_recovers_unqueued_reports_and_reuses_shared_jobs():
    import json
    from io import StringIO

    from django.core.management import call_command

    from core.product_release_acquisition import queue_saved_release_claims
    from core.product_release_dossiers import record_release_report

    brand = models.Brand.objects.create(nickname="sweep-publisher")
    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    for index in range(2):
        post = models.Post.objects.create(tweet_id=f"sweep-post-{index}", text="Announcing Model Alpha")
        record_release_report(
            post=post, record={"model_name": "Model Alpha"},
            release_identity=f"sweep-release-{index}", observed_name="Model Alpha",
            source_url=None, brand=brand, maturity_code="unknown", release_value=None,
            release_precision="unknown", extraction_version="test",
        )
    preview = queue_saved_release_claims(limit=1, persist=False)
    assert preview["scanned"] == 1 and preview["queued"] == 0
    assert not models.CollectionJob.objects.exists()
    out = StringIO()
    call_command("queue_release_acquisition", limit=1, stdout=out)
    assert json.loads(out.getvalue())["scanned"] == 1
    assert not models.CollectionJob.objects.exists()
    first = queue_saved_release_claims(limit=1, persist=True)
    assert first["scanned"] == 1 and first["queued"] == 1
    second = queue_saved_release_claims(limit=1, after=first["next_cursor"], persist=True)
    assert second["scanned"] == 1 and second["queued"] == 1
    assert models.CollectionJob.objects.count() == 1
    assert models.EventDossierClaimCollectionJob.objects.count() == 2
    assert queue_saved_release_claims(limit=10, persist=True)["scanned"] == 0
    assert not models.CollectionRun.objects.exists()
    assert not models.CollectionRequest.objects.exists()


def test_claim_sweep_reports_unsearchable_and_excluded_without_marking_fraud():
    from core.product_release_acquisition import queue_saved_release_claims
    from core.product_release_dossiers import record_release_report
    from core.product_release_pipeline import record_intake_decision

    brand = models.Brand.objects.create(nickname="sweep-edge-publisher")
    for index, name in enumerate(("x" * 257, "Excluded Model")):
        post = models.Post.objects.create(tweet_id=f"sweep-edge-{index}", text="Announcing a model")
        event, _, _ = record_release_report(
            post=post, record={"model_name": name}, release_identity=f"sweep-edge-{index}",
            observed_name=name, source_url=None, brand=brand, maturity_code="unknown",
            release_value=None, release_precision="unknown", extraction_version="test",
        )
        if index == 1:
            claim = models.EventDossierClaim.objects.get(
                event_dossier_source__event_dossier=event, claim_kind_reference__code="release_report"
            )
            record_intake_decision(event.pk, claim_id=claim.pk, outcome="scam", actor="test",
                                   reason="Documented impersonation")
    result = queue_saved_release_claims(limit=10, persist=True)
    assert [row["outcome"] for row in result["claims"]] == ["ineligible", "excluded"]
    assert result["scanned"] == 2 and result["queued"] == 0 and result["complete"]
    assert not models.CollectionJob.objects.exists()
    assert models.EventDossierIntakeDecision.objects.filter(outcome="scam").count() == 1
    with pytest.raises(ValueError, match="cursor"):
        queue_saved_release_claims(after={"recorded_at": "2026-10-30", "claim_id": "bad"})


def test_bounded_due_drain_previews_then_executes_only_due_jobs():
    import json
    from datetime import timedelta
    from io import StringIO

    import httpx
    from django.core.management import call_command
    from django.utils import timezone

    from core.product_release_acquisition import (
        drain_due_hf_acquisitions,
        queue_hf_name_search,
    )
    from core.product_release_dossiers import record_release_report

    brand = models.Brand.objects.create(nickname="due-publisher")
    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    jobs = []
    for index, name in enumerate(("Due Model", "Later Model")):
        post = models.Post.objects.create(tweet_id=f"due-post-{index}", text=f"Announcing {name}")
        event, _, _ = record_release_report(
            post=post, record={"model_name": name}, release_identity=f"due-release-{index}",
            observed_name=name, source_url=None, brand=brand, maturity_code="unknown",
            release_value=None, release_precision="unknown", extraction_version="test",
        )
        claim = models.EventDossierClaim.objects.get(
            event_dossier_source__event_dossier=event, claim_kind_reference__code="release_report"
        )
        jobs.append(queue_hf_name_search(claim.pk))
    models.CollectionJob.objects.filter(pk=jobs[1].pk).update(next_retry_at=timezone.now() + timedelta(hours=1))
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=[{"id": "lab/Due-Model"}])

    client = httpx.Client(transport=httpx.MockTransport(respond))
    preview = drain_due_hf_acquisitions(client=client, limit=1)
    assert preview["selected"] == 1 and preview["provider_calls"] == 0
    assert not calls and not models.CollectionRun.objects.exists()
    assert drain_due_hf_acquisitions(client=client, limit=1, job_ids=[str(jobs[1].pk)])["selected"] == 0
    output = StringIO()
    call_command("run_release_acquisition", limit=1, job_ids=[str(jobs[0].pk)], stdout=output)
    assert json.loads(output.getvalue())["selected"] == 1
    assert not models.CollectionRun.objects.exists()
    result = drain_due_hf_acquisitions(client=client, limit=1, execute=True)
    assert result["selected"] == 1 and result["provider_calls"] == 1
    assert result["jobs"][0]["outcome"] == "found" and len(calls) == 1
    assert drain_due_hf_acquisitions(
        client=client, limit=1, execute=True, job_ids=[str(jobs[0].pk)]
    )["selected"] == 0


def test_empty_search_is_retried_and_later_result_keeps_both_request_receipts():
    from datetime import timedelta

    import httpx
    from django.utils import timezone

    from core.product_release_acquisition import (
        execute_hf_name_search,
        queue_hf_name_search,
    )
    from core.product_release_dossiers import record_release_report

    post = models.Post.objects.create(tweet_id="delayed-repo", text="We announce Delayed-Model")
    brand = models.Brand.objects.create(nickname="delayed-publisher")
    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    event, _, _ = record_release_report(
        post=post, record={"model_name": "Delayed-Model"},
        release_identity="delayed-release", observed_name="Delayed-Model", source_url=None,
        brand=brand, maturity_code="unknown", release_value=None,
        release_precision="unknown", extraction_version="test",
    )
    claim = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=event, claim_kind_reference__code="release_report"
    )
    job = queue_hf_name_search(claim.pk)
    answers = iter([[], [{"id": "publisher/Delayed-Model"}]])
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=next(answers))))
    first = execute_hf_name_search(job.pk, client=client)
    assert first["outcome"] == "empty"
    assert models.CollectionRun.objects.get(pk=first["run_id"]).status == "partial"
    assert not models.Product.objects.exists()
    models.CollectionJob.objects.filter(pk=job.pk).update(next_retry_at=timezone.now() - timedelta(seconds=1))
    second = execute_hf_name_search(job.pk, client=client)
    assert second["run_id"] == first["run_id"] and second["outcome"] == "found"
    run = models.CollectionRun.objects.get(pk=first["run_id"])
    assert run.request_count == 2 and run.attempts.count() == 2
    assert models.CollectionRequest.objects.filter(attempt__run=run).count() == 2


def test_exact_source_repo_is_captured_after_delayed_availability_without_confirmation():
    from datetime import timedelta

    import httpx
    from django.utils import timezone

    from core.collection_capture import observation_object_documents
    from core.product_release_acquisition import (
        execute_hf_name_search,
        queue_hf_name_search,
    )
    from core.product_release_dossiers import record_release_report

    url = "https://huggingface.co/unknown-lab/model-z"
    post = models.Post.objects.create(tweet_id="exact-delayed", text=f"Announcing Model Z {url}")
    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    event, _, _ = record_release_report(
        post=post, record={"model_name": "Model Z", "source_url": url},
        release_identity="exact-delayed", observed_name="Model Z", source_url=url,
        maturity_code="unknown", release_value=None, release_precision="unknown",
        extraction_version="test",
    )
    claim = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=event, claim_kind_reference__code="release_report"
    )
    job = queue_hf_name_search(claim.pk)
    assert job.targets.get().target_role == "exact_model"
    responses = iter([httpx.Response(404), httpx.Response(200, json={
        "id": "unknown-lab/model-z", "downloads": 17, "likes": 3,
    })])
    calls = []
    def respond(request):
        calls.append(request)
        return next(responses)
    client = httpx.Client(transport=httpx.MockTransport(respond))
    first = execute_hf_name_search(job.pk, client=client)
    assert first["outcome"] == "not_found" and first["physical_requests"] == 1
    models.CollectionJob.objects.filter(pk=job.pk).update(next_retry_at=timezone.now() - timedelta(seconds=1))
    second = execute_hf_name_search(job.pk, client=client)
    assert second["outcome"] == "found" and second["run_id"] == first["run_id"]
    observation = models.CollectionObservation.objects.get(run_id=second["run_id"])
    assert observation.processing_outcome == "unresolved"
    assert observation_object_documents(observation)[0]["downloads"] == 17
    assert observation.observed_at is not None
    assert all(str(call.url).startswith("https://huggingface.co/api/models/unknown-lab/model-z?") for call in calls)
    assert models.CollectionRequest.objects.filter(attempt__run_id=second["run_id"]).count() == 2
    assert not models.Product.objects.exists()
    assert not models.ProductReleaseDetail.objects.exists()
    assert execute_hf_name_search(job.pk, client=client)["physical_requests"] == 0
    assert len(calls) == 2
    # A later dossier shares the retained capture without another request.
    other, _, _ = record_release_report(
        post=post, record={"model_name": "Model Z", "source_url": url},
        release_identity="another-exact-claim", observed_name="Model Z", source_url=url,
        maturity_code="unknown", release_value=None, release_precision="unknown",
        extraction_version="test",
    )
    other_claim = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=other, claim_kind_reference__code="release_report"
    )
    assert queue_hf_name_search(other_claim.pk).pk == job.pk
    assert other.sources.filter(collection_observation=observation).exists()
    assert len(calls) == 2


def test_unbound_hf_link_does_not_select_exact_lookup():
    from core.product_release_acquisition import queue_hf_name_search
    from core.product_release_dossiers import record_release_report

    post = models.Post.objects.create(tweet_id="unbound-repo", text="Announcing Model Z")
    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    event, _, _ = record_release_report(
        post=post, record={"model_name": "Model Z", "candidate_repo_id": "somebody/model-z"},
        release_identity="unbound-repo", observed_name="Model Z", source_url=None,
        maturity_code="unknown", release_value=None, release_precision="unknown",
        extraction_version="test",
    )
    claim = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=event, claim_kind_reference__code="release_report"
    )
    assert queue_hf_name_search(claim.pk).targets.get().target_role == "name_search"


def test_exact_release_enqueues_expanded_metadata_and_retains_base_model_claims():
    import httpx

    from core.collection_capture import observation_object_documents
    from core.product_release_acquisition import (
        execute_hf_name_search,
        queue_hf_name_search,
    )
    from core.product_release_dossiers import record_release_report

    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    url = "https://huggingface.co/author/derived"
    post = models.Post.objects.create(tweet_id="expanded-derived", text=f"We release a model {url}")
    dossier, _, _ = record_release_report(
        post=post, record={"model_name": "derived", "source_url": url},
        release_identity="expanded-derived", observed_name="derived", source_url=url,
        maturity_code="unknown", release_value=None, release_precision="unknown", extraction_version="test",
    )
    claim = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=dossier, claim_kind_reference__code="release_report"
    )
    job = queue_hf_name_search(claim.pk)
    requests = []
    def respond(request):
        requests.append(request)
        if request.url.params.get("blobs"):
            return httpx.Response(200, json={"id": "author/derived"})
        if len(request.url.params.get_list("expand")) > 10:
            return httpx.Response(400)
        return httpx.Response(200, json={
            "id": "author/derived", "cardData": {
                "base_model": ["Qwen/base", "Gemma/base"], "base_model_relation": "merge"
            },
        })
    client = httpx.Client(transport=httpx.MockTransport(respond))
    assert execute_hf_name_search(job.pk, client=client)["outcome"] == "found"
    expanded_job = models.CollectionJob.objects.get(targets__target_role="expanded_model")
    result = execute_hf_name_search(expanded_job.pk, client=client)
    assert result["outcome"] == "found" and result["metadata_coverage"] == "partial_expansion"
    assert result["physical_requests"] == 2
    observation = models.CollectionObservation.objects.get(run_id=result["run_id"])
    assert observation.processing_outcome == "partial_expansion"
    assert observation_object_documents(observation)[0]["cardData"]["base_model_relation"] == "merge"
    lineage = models.EventDossierClaim.objects.filter(
        event_dossier_source__event_dossier=dossier, scope_key__startswith="hf_base_model:"
    )
    assert {row.source_excerpt for row in lineage} == {"Qwen/base", "Gemma/base"}
    assert all(row.source_archive_id == observation.inputs.get().input_request.archive_id for row in lineage)
    assert not models.ProductRelationship.objects.exists() and not models.Product.objects.exists()
    assert execute_hf_name_search(expanded_job.pk, client=client)["physical_requests"] == 0
    assert len(requests) == 3


def test_unknown_publisher_socials_are_separate_unverified_source_evidence():
    import httpx
    from django.utils import timezone

    from core.collection_capture import observation_object_documents
    from core.product_release_acquisition import (
        execute_hf_name_search,
        queue_hf_name_search,
    )
    from core.product_release_dossiers import record_release_report

    url = "https://huggingface.co/newlab/Model"
    post = models.Post.objects.create(tweet_id="new-publisher-socials", text=f"Announcing Model {url}")
    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    now = timezone.now()
    candidate = models.BrandDiscoveryCandidate.objects.create(
        observed_name="New Lab", candidate_identity="newlab-socials", source_post=post,
        first_observed_at=now, last_observed_at=now,
    )
    dossier, _, _ = record_release_report(
        post=post, record={"model_name": "Model", "source_url": url},
        release_identity="newlab-socials", observed_name="Model", source_url=url,
        candidate=candidate, maturity_code="unknown", release_value=None,
        release_precision="unknown", extraction_version="test",
    )
    claim = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=dossier, claim_kind_reference__code="release_report"
    )
    job = queue_hf_name_search(claim.pk)
    calls = []
    def respond(request):
        calls.append(request.url.path)
        if request.url.path == "/api/models/newlab/Model":
            return httpx.Response(200, json={"id": "newlab/Model", "author": "newlab"})
        assert request.url.path == "/api/organizations/newlab/socials"
        return httpx.Response(200, json={"org": "newlab", "socialHandles": {"twitter": "newlab"}})
    client = httpx.Client(transport=httpx.MockTransport(respond))
    assert execute_hf_name_search(job.pk, client=client)["outcome"] == "found"
    social_job = models.CollectionJob.objects.get(targets__target_role="publisher_socials")
    assert social_job.dossier_claim_links.filter(claim=claim).exists()
    result = execute_hf_name_search(social_job.pk, client=client)
    observation = models.CollectionObservation.objects.get(run_id=result["run_id"])
    assert observation_object_documents(observation)[0]["socialHandles"]["twitter"] == "newlab"
    assert dossier.sources.filter(collection_observation=observation).exists()
    assert observation.processing_outcome == "unresolved"
    assert dossier.current_review_id is None and not models.Product.objects.exists()
    assert candidate.verification_status == "pending"
    assert execute_hf_name_search(social_job.pk, client=client)["physical_requests"] == 0
    assert len(calls) == 2


def test_partial_search_integration_recovers_during_provider_cooldown(monkeypatch):
    import httpx
    from django.utils import timezone

    from core import product_release_acquisition as acquisition
    from core.product_release_dossiers import record_release_report

    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    post = models.Post.objects.create(tweet_id="partial-recovery", text="We announce Model4")
    dossier, _, _ = record_release_report(
        post=post, record={"model_name": "Model4"}, release_identity="partial-recovery",
        observed_name="Model4", source_url=None, maturity_code="unknown", release_value=None,
        release_precision="unknown", extraction_version="test",
    )
    claim = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=dossier, claim_kind_reference__code="release_report"
    )
    job = acquisition.queue_hf_name_search(claim.pk)
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=[{"id": "lab/Model4"}], headers={
            "link": '<https://huggingface.co/api/models?cursor=next>; rel="next"'
        })
    client = httpx.Client(transport=httpx.MockTransport(respond))
    original = acquisition.integrate_acquisition_run
    monkeypatch.setattr(acquisition, "integrate_acquisition_run",
                        lambda _run_id: (_ for _ in ()).throw(RuntimeError("interrupted")))
    with pytest.raises(RuntimeError, match="interrupted"):
        acquisition.execute_hf_name_search(job.pk, client=client)
    job.refresh_from_db()
    assert job.last_attempt.status == "partial" and job.next_retry_at > timezone.now()
    assert job.last_attempt.scopes.get(scope_kind="release_integration").outcome == "pending"
    monkeypatch.setattr(acquisition, "integrate_acquisition_run", original)
    result = acquisition.drain_due_hf_acquisitions(client=client, execute=True, job_ids=[str(job.pk)])
    assert result["provider_calls"] == 0 and result["jobs"][0]["outcome"] == "integration_only"
    assert models.CollectionJob.objects.filter(targets__target_role="exact_model").count() == 1
    assert len(calls) == 1 and not models.Product.objects.exists()


def test_search_resumes_next_page_and_deduplicates_repeated_hits():
    from datetime import timedelta

    import httpx
    from django.utils import timezone

    from core.collection_capture import observation_object_documents
    from core.product_release_acquisition import (
        execute_hf_name_search,
        queue_hf_name_search,
    )
    from core.product_release_dossiers import record_release_report

    post = models.Post.objects.create(tweet_id="paged-release", text="We announce Paged Model")
    brand = models.Brand.objects.create(nickname="paged-publisher")
    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    event, _, _ = record_release_report(
        post=post, record={"model_name": "Paged Model"},
        release_identity="paged-release", observed_name="Paged Model", source_url=None,
        brand=brand, maturity_code="unknown", release_value=None,
        release_precision="unknown", extraction_version="test",
    )
    claim = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=event, claim_kind_reference__code="release_report"
    )
    job = queue_hf_name_search(claim.pk)
    requests = []

    def respond(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[{"id": "lab/one"}], headers={
                "link": '<https://huggingface.co/api/models?cursor=opaque>; rel="next"'
            })
        assert request.url.params["cursor"] == "opaque"
        return httpx.Response(200, json=[
            {"id": "lab/one"}, {"id": "lab/two"}, {"id": "lab/one", "likes": 2}
        ])

    client = httpx.Client(transport=httpx.MockTransport(respond))
    first = execute_hf_name_search(job.pk, client=client)
    assert first["outcome"] == "incomplete"
    models.CollectionJob.objects.filter(pk=job.pk).update(next_retry_at=timezone.now() - timedelta(seconds=1))
    second = execute_hf_name_search(job.pk, client=client)
    assert second["run_id"] == first["run_id"] and second["outcome"] == "found"
    run = models.CollectionRun.objects.get(pk=first["run_id"])
    assert run.request_count == 2 and run.observations.count() == 3
    assert run.observations.filter(source_identifier="lab/one").count() == 2
    assert {observation_object_documents(row)[0]["id"] for row in run.observations.all()} == {"lab/one", "lab/two"}
    scope = run.scopes.get(scope_kind="release_acquisition")
    assert scope.cursor is None and scope.recorded_cursors == ["opaque"]
    assert scope.raw_count == 4


def test_search_stops_when_provider_repeats_continuation_cursor():
    from datetime import timedelta

    import httpx
    from django.utils import timezone

    from core.product_release_acquisition import (
        execute_hf_name_search,
        queue_hf_name_search,
    )
    from core.product_release_dossiers import record_release_report

    post = models.Post.objects.create(tweet_id="loop-release", text="Announcing Loop Model")
    brand = models.Brand.objects.create(nickname="loop-publisher")
    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    event, _, _ = record_release_report(
        post=post, record={"model_name": "Loop Model"}, release_identity="loop-release",
        observed_name="Loop Model", source_url=None, brand=brand, maturity_code="unknown",
        release_value=None, release_precision="unknown", extraction_version="test",
    )
    claim = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=event, claim_kind_reference__code="release_report"
    )
    job = queue_hf_name_search(claim.pk)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=[{"id": "lab/loop"}], headers={
            "link": '<https://huggingface.co/api/models?cursor=loop>; rel="next"'
        })

    client = httpx.Client(transport=httpx.MockTransport(respond))
    first = execute_hf_name_search(job.pk, client=client)
    assert first["outcome"] == "incomplete"
    models.CollectionJob.objects.filter(pk=job.pk).update(next_retry_at=timezone.now() - timedelta(seconds=1))
    second = execute_hf_name_search(job.pk, client=client)
    assert second["outcome"] == "cursor_cycle"
    run = models.CollectionRun.objects.get(pk=first["run_id"])
    assert run.status == "failed" and run.observations.count() == 1
    with pytest.raises(ValueError, match="cursor"):
        execute_hf_name_search(job.pk, client=client)
    assert len(calls) == 2


def test_search_resumes_after_checkpoint_without_repeating_provider_request(monkeypatch):
    from datetime import timedelta

    import httpx
    from django.utils import timezone

    import core.collection_state as state
    from core.product_release_acquisition import (
        execute_hf_name_search,
        queue_hf_name_search,
    )
    from core.product_release_dossiers import record_release_report

    post = models.Post.objects.create(tweet_id="crash-release", text="Announcing Crash Model")
    brand = models.Brand.objects.create(nickname="crash-publisher")
    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    event, _, _ = record_release_report(
        post=post, record={"model_name": "Crash Model"}, release_identity="crash-release",
        observed_name="Crash Model", source_url=None, brand=brand, maturity_code="unknown",
        release_value=None, release_precision="unknown", extraction_version="test",
    )
    source_claim = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=event, claim_kind_reference__code="release_report"
    )
    job = queue_hf_name_search(source_claim.pk)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=[{"id": "lab/model"}])

    client = httpx.Client(transport=httpx.MockTransport(respond))
    finish = state.finish_run
    monkeypatch.setattr(state, "finish_run", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("simulated crash")))
    with pytest.raises(RuntimeError, match="simulated crash"):
        execute_hf_name_search(job.pk, client=client)
    run = models.CollectionRun.objects.get(job=job)
    assert run.observations.count() == 1 and run.scopes.get(scope_kind="release_acquisition").enumeration_complete
    models.CollectionRun.objects.filter(pk=run.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
    monkeypatch.setattr(state, "finish_run", finish)
    result = execute_hf_name_search(job.pk, client=client)
    assert result["outcome"] == "found" and result["run_id"] == str(run.pk)
    assert len(calls) == 1 and models.CollectionRequest.objects.filter(attempt__run=run).count() == 1


def test_queued_search_does_not_run_if_every_linked_release_is_excluded():
    import httpx

    from core.product_release_acquisition import (
        drain_due_hf_acquisitions,
        execute_hf_name_search,
        queue_hf_name_search,
    )
    from core.product_release_dossiers import record_release_report
    from core.product_release_pipeline import record_intake_decision

    post = models.Post.objects.create(tweet_id="excluded-queued", text="Announcing Fake Model")
    brand = models.Brand.objects.create(nickname="excluded-publisher")
    models.DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    event, _, _ = record_release_report(
        post=post, record={"model_name": "Fake Model"},
        release_identity="excluded-queued-release", observed_name="Fake Model", source_url=None,
        brand=brand, maturity_code="unknown", release_value=None,
        release_precision="unknown", extraction_version="test",
    )
    claim = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=event, claim_kind_reference__code="release_report"
    )
    job = queue_hf_name_search(claim.pk)
    record_intake_decision(event.pk, claim_id=claim.pk, outcome="scam", actor="test",
                           reason="Documented impersonation")
    client = httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("unexpected request")))
    result = execute_hf_name_search(job.pk, client=client)
    assert result["outcome"] == "excluded"
    assert not models.CollectionRequest.objects.exists()
    assert not models.CollectionRun.objects.exists()

    # An excluded job must not occupy the entire worker page forever. Another
    # release remains eligible, and a later correction can make the first due.
    other_post = models.Post.objects.create(tweet_id="eligible-queued", text="Announcing Real Model")
    other, _, _ = record_release_report(
        post=other_post, record={"model_name": "Real Model"},
        release_identity="eligible-queued-release", observed_name="Real Model", source_url=None,
        brand=brand, maturity_code="unknown", release_value=None,
        release_precision="unknown", extraction_version="test",
    )
    other_claim = models.EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=other, claim_kind_reference__code="release_report"
    )
    other_job = queue_hf_name_search(other_claim.pk)
    preview = drain_due_hf_acquisitions(client=client, limit=1)
    assert preview["skipped_excluded"] == 1
    assert preview["jobs"][0]["job_id"] == str(other_job.pk)
    record_intake_decision(event.pk, claim_id=claim.pk, outcome="pending", actor="test",
                           reason="Corrected earlier decision")
    preview = drain_due_hf_acquisitions(client=client, limit=1)
    assert preview["jobs"][0]["job_id"] == str(job.pk)


def test_merge_preserves_original_claims_and_rejects_cycles():
    from core.product_release_pipeline import merge_dossiers

    first, original = evidence("merge-source")
    target, _ = evidence("merge-target")
    merge_dossiers(first.pk, target.pk, actor="test", reason="Same identified release")
    first.refresh_from_db()
    assert first.merged_into_id == target.pk
    original.refresh_from_db()
    assert original.event_dossier_source.event_dossier_id == first.pk
    assert target.sources.count() == 2
    merge_dossiers(first.pk, target.pk, actor="test", reason="Same identified release")
    with pytest.raises(ValueError, match="self|cycle"):
        merge_dossiers(target.pk, first.pk, actor="test", reason="Invalid cycle")


def test_management_command_is_dry_by_default_and_resumes_without_duplicates():
    import json
    from datetime import timedelta
    from io import StringIO

    from django.core.management import CommandError, call_command
    from django.utils import timezone

    now = timezone.now()
    for key, text in (
        ("command-1", "Announcing Model A"),
        ("command-2", "ordinary discussion"),
        ("command-3", "New release of Model B"),
    ):
        models.Post.objects.create(tweet_id=key, text=text, created_at=now)
    args = {
        "start": (now - timedelta(minutes=1)).isoformat(),
        "end": (now + timedelta(minutes=1)).isoformat(),
        "source": "post",
        "clock": "publication",
        "batch_size": 2,
    }

    def run(**extra):
        output = StringIO()
        call_command("detect_product_releases", **args, **extra, stdout=output)
        return json.loads(output.getvalue())

    preview = run()
    assert (
        preview["counts"]["candidates"] == 1
        and not models.EventDossier.objects.exists()
    )
    first = run(persist=True)
    second = run(persist=True, cursor=json.dumps(first["next_cursor"]))
    assert second["complete"] and models.EventDossier.objects.count() == 2
    run(persist=True)
    assert models.EventDossier.objects.count() == 2
    bad = dict(first["next_cursor"], selection="wrong")
    with pytest.raises(CommandError, match="Cursor"):
        run(cursor=json.dumps(bad))


def test_supported_non_post_document_can_initiate_pending_release():
    import json
    from datetime import timedelta

    from django.utils import timezone

    from core.collection_capture import archive_document
    from core.product_release_pipeline import persist_source
    from core.product_release_replay import ReplayWindow
    from core.product_release_sources import observation_page
    from tests.collection_fixtures import evidence_job

    now = timezone.now()
    models.DataSource.objects.get_or_create(
        id="github", defaults={"name": "GitHub", "source_type": "model_adoption"}
    )
    run = models.CollectionRun.objects.create(
        job=evidence_job(source_id="github"),
        ingestion_key="f" * 64,
        status="success",
        completed_at=now,
    )
    archive = archive_document(
        json.dumps(
            {
                "listing": {
                    "body": "Today we announce Small Harness",
                    "tag_name": "v1",
                    "draft": False,
                },
                "dimensions": {"kind": "releases"},
                "source_metadata": {},
            }
        ).encode(),
        encoding="selected-json-canonical-v1",
        capture_kind="test",
    )
    observation = models.CollectionObservation.objects.create(
        run=run,
        source_identifier="owner/harness",
        source_subject_kind="repository",
        observation_key="a" * 64,
        legacy_archive=archive,
        published_at=now,
        publication_precision="instant",
    )
    models.CollectionResourceSnapshot.objects.create(
        observation=observation,
        resource_kind="releases",
        native_identifier="owner/harness",
    )
    rows = observation_page(
        ReplayWindow(now - timedelta(minutes=1), now + timedelta(minutes=1))
    )
    assert len(rows) == 1
    result = persist_source(rows[0])
    assert result["disposition"] == "pending"
    assert (
        models.EventDossierSource.objects.get().collection_observation_id
        == observation.pk
    )
    assert not models.Post.objects.exists()


def test_confirmation_refuses_missing_publisher_proof_and_provisional_review_replays():
    from django.utils import timezone

    from core.event_dossiers import ProductReleaseInput
    from core.product_release_pipeline import review_release

    event, claim = evidence("unverified-publisher")
    values = {
        "release": ProductReleaseInput(observed_name="Model A"),
        "claim_ids": [claim.pk],
        "actor": "session analyst",
        "reason": "Source attribution unresolved",
        "evidence_cutoff_at": timezone.now(),
    }
    with pytest.raises(ValueError, match="verified publisher"):
        review_release(event.pk, **values, state="confirmed")
    first = review_release(event.pk, **values)
    assert review_release(event.pk, **values).pk == first.pk
    assert models.EventDossierReview.objects.count() == 1


def test_collection_clock_follows_physical_request_through_cached_page_use():
    from datetime import timedelta

    from django.utils import timezone

    from core.collection_capture import archive_legacy
    from core.collection_pages import append_page_receipt
    from core.collection_state import claim_job, import_scope_checkpoints
    from core.product_release_replay import ReplayWindow
    from core.product_release_sources import post_page
    from core.provider_batches import record_post_membership
    from tests.test_backfill_collection import ready_job

    now = timezone.now()
    models.Post.objects.create(
        tweet_id="refetched-release",
        text="Announcing A",
        created_at=now - timedelta(days=3),
    )
    models.Post.objects.filter(pk="refetched-release").update(
        fetched_at=now - timedelta(days=2)
    )
    job = ready_job()
    claim = claim_job(
        job.pk, invocation_id="release-replay-clock", manual_authorized=True, typed=True
    )
    import_scope_checkpoints(
        claim,
        definition_sha256=job.definition_sha256,
        scopes=job.scope["units"],
        provenance={"format": "fixture"},
        typed=True,
    )
    scope = models.CollectionScopeRun.objects.get(
        run_id=claim.run_id, scope_kind="x_query"
    )
    with transaction.atomic():
        record_post_membership(scope.run, scope, ["refetched-release"])
    request = models.CollectionRequest.objects.create(
        attempt=scope.run.attempts.get(),
        scope_run=scope,
        ordinal=1,
        transport_outcome="received",
        http_status=200,
        received_at=now,
        archive=archive_legacy({"tweets": []}),
    )
    later = now + timedelta(hours=1)
    append_page_receipt(
        scope,
        {
            "observed_at": later.isoformat(),
            "pages_received": 1,
            "raw_count": 1,
            "received_post_ids": ["refetched-release"],
            "post_ids": ["refetched-release"],
            "prefetch_request_id": str(request.pk),
            "prefetch_request_run_id": str(scope.run_id),
            "prefetch_replayed": True,
        },
    )
    physical = post_page(
        ReplayWindow(now - timedelta(seconds=1), now + timedelta(seconds=1)),
        clock="collection",
    )
    assert len(physical) == 1 and physical[0].clock_basis == "physical_receipt"
    cached = post_page(
        ReplayWindow(later - timedelta(seconds=1), later + timedelta(seconds=1)),
        clock="collection",
    )
    assert cached == []
