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
