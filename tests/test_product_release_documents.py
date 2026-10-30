"""Primary documents must be usable evidence without manufacturing X posts."""

import hashlib
import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from core import models
from core.product_release_study import apply_study

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def captured_document(tmp_path):
    body = b"<html><body><h1>Model Flash</h1><p>We announce Model Flash.</p><p>API access is available now.</p></body></html>"
    path = tmp_path / "announcement.html"
    path.write_bytes(body)
    options = dict(  # noqa: C408
        url="https://publisher.example/news/flash",
        observed_at=(timezone.now() - timedelta(minutes=1)).isoformat(),
        sha256=hashlib.sha256(body).hexdigest(),
        media_type="text/html",
        source="publisher_web",
        subject_kind="model",
    )
    output = StringIO()
    call_command("import_release_document", str(path), stdout=output, **options)
    assert not models.CollectionObservation.objects.exists()
    output = StringIO()
    call_command(
        "import_release_document", str(path), persist=True, stdout=output, **options
    )
    return json.loads(output.getvalue()), path, options


def assessment(observation_id):
    return {
        "schema": "product-release-study-v1",
        "actor": "session-review",
        "assessed_at": timezone.now().isoformat(),
        "cases": [
            {
                "case_id": "document-test",
                "identity": "publisher/flash/1",
                "name": "Model Flash",
                "reason": "Captured primary announcement.",
                "evidence": [
                    {
                        "observation_id": observation_id,
                        "excerpt": "We announce Model Flash.",
                        "kind": "announcement",
                        "effective_date": "2026-10-17",
                    }
                ],
                "significance": {
                    "product_kind": "general_model",
                    "lineage": "primary",
                    "change": "substantial",
                    "reason": "Assessed primary model.",
                },
            }
        ],
    }


def test_document_command_study_and_repeat_preserve_real_sources(tmp_path):
    saved, path, options = captured_document(tmp_path)
    value = assessment(saved["observation_id"])
    value["cases"][0]["evidence"][0]["exclusive_source"] = True
    result = apply_study(value)
    row = result["releases"][0]
    assert row["state"] == "provisional"
    assert row["source_documents"][0]["url"] == options["url"]
    claim = models.EventDossierClaim.objects.get(
        claim_kind_reference__code="announcement",
        review_decisions__review_id=result["cases"][0]["review_id"],
    )
    assert (
        claim.event_dossier_source.collection_observation_id == saved["observation_id"]
    )
    assert claim.source_archive_id
    assert claim.effective_at is None
    assert claim.effective_date.isoformat() == "2026-10-17"
    assert claim.source_locator == options["url"]
    assert not models.Post.objects.exists()
    assert not models.CollectionRequest.objects.exists()
    from core.product_release_replay import ReplayWindow
    from core.product_release_sources import observation_page

    observation = models.CollectionObservation.objects.get(pk=saved["observation_id"])
    window = ReplayWindow(
        observation.observed_at - timedelta(seconds=1),
        observation.observed_at + timedelta(seconds=1),
    )
    assert (
        observation_page(window, clock="collection")[0].clock_basis
        == "imported_capture_time"
    )
    assert observation_page(window, clock="first_storage") == []
    counts = {
        m: m.objects.count()
        for m in (
            models.CollectionObservation,
            models.CollectionRun,
            models.CollectionEvidenceArchive,
            models.EventDossier,
            models.EventDossierClaim,
            models.EventDossierReview,
            models.EventDossierIntakeDecision,
        )
    }
    out = StringIO()
    call_command(
        "import_release_document", str(path), persist=True, stdout=out, **options
    )
    assert json.loads(out.getvalue())["observation_id"] == saved["observation_id"]
    assert apply_study(value) == result
    assert counts == {m: m.objects.count() for m in counts}


def test_website_confirmation_requires_exact_document_control(tmp_path):
    saved, _, options = captured_document(tmp_path)
    value = assessment(saved["observation_id"])
    case = value["cases"][0]
    case.update(state="confirmed", issuer_company_id="document-publisher")
    models.Company.objects.create(nickname="document-publisher")
    proof = {
        "url": options["url"],
        "text": "Reviewed publisher identity and control of this official publication.",
        "observed_at": options["observed_at"],
    }
    case["verification"] = {
        "observation_id": saved["observation_id"],
        "entity": proof,
        "ownership": dict(proof, url="https://other.example/fake"),
    }
    with pytest.raises(ValueError, match="ownership|control"):
        apply_study(value)
    assert not models.EventDossierReview.objects.exists()
    case["verification"]["ownership"] = proof
    result = apply_study(value)
    assert result["releases"][0]["state"] == "confirmed"
    assert not models.Account.objects.exists()


def test_document_checksum_and_invented_quote_fail_without_partial_reviews(tmp_path):
    saved, path, options = captured_document(tmp_path)
    from django.core.management import CommandError

    with pytest.raises(CommandError, match="checksum"):
        call_command(
            "import_release_document",
            str(path),
            persist=True,
            **dict(options, sha256="0" * 64),
        )
    value = assessment(saved["observation_id"])
    value["cases"][0]["evidence"][0]["excerpt"] = "Weights were released on October 17."
    with pytest.raises(ValueError, match="excerpt|quotation"):
        apply_study(value)
    assert not models.EventDossierReview.objects.exists()
    assert models.CollectionObservation.objects.count() == 1


def test_mixed_source_study_command_keeps_source_kinds_and_clocks(tmp_path):
    saved, _, _ = captured_document(tmp_path)
    models.Post.objects.create(
        tweet_id="release-reaction", text="I tried the new model."
    )
    value = assessment(saved["observation_id"])
    value["cases"][0]["evidence"].append(
        {
            "post_id": "release-reaction",
            "excerpt": "I tried the new model.",
            "kind": "first_observed_usage",
        }
    )
    path = tmp_path / "study.json"
    path.write_text(json.dumps(value))
    out = StringIO()
    call_command("study_product_releases", str(path), persist=True, stdout=out)
    review = models.EventDossierReview.objects.get()
    sources = review.event_dossier.sources.all()
    assert sources.filter(post_id="release-reaction").count() == 1
    assert (
        sources.filter(collection_observation_id=saved["observation_id"]).count() == 1
    )
    assert (
        review.claim_decisions.filter(
            claim__claim_kind_reference__code="first_observed_usage",
            claim__effective_precision="unknown",
        ).count()
        == 1
    )


@pytest.mark.parametrize(
    "fault", ["missing", "both", "future_capture", "corrupt_capture"]
)
def test_invalid_document_evidence_cannot_create_a_review(tmp_path, fault):
    saved, _, _ = captured_document(tmp_path)
    value = assessment(saved["observation_id"])
    item = value["cases"][0]["evidence"][0]
    if fault == "missing":
        item["observation_id"] += 10000
    elif fault == "both":
        item["post_id"] = "unrelated"
    elif fault == "future_capture":
        value["assessed_at"] = (timezone.now() - timedelta(days=1)).isoformat()
    else:
        models.CollectionObservation.objects.filter(pk=saved["observation_id"]).update(
            payload_sha256="0" * 64
        )
    with pytest.raises(ValueError):
        apply_study(value)
    assert not models.EventDossierReview.objects.exists()


def test_import_options_reject_unknown_keys_in_database_and_runtime():
    from django.db import IntegrityError, transaction

    from core.collection_jobs import validate_definition

    with pytest.raises(ValueError, match="unknown|relocated"):
        validate_definition(
            source_id="publisher_web",
            purpose="content",
            operation="release_document_import",
            mode="manual",
            contract_id=None,
            definition={"version": 2, "options": {"trust_publisher": True}},
        )
    source = models.DataSource.objects.create(
        id="publisher_web", name="Public documents", source_type="model_adoption"
    )
    with (
        pytest.raises(IntegrityError, match="unknown or mistyped"),
        transaction.atomic(),
    ):
        models.CollectionJob.objects.create(
            job_key="bad-document-options",
            source=source,
            purpose="content",
            operation="release_document_import",
            mode="manual",
            instruction_version=2,
            owner_kind="source",
            definition_sha256="0" * 64,
            definition={"version": 2, "options": {"trust_publisher": True}},
            max_requests=1,
            max_bytes=2000000,
            max_seconds=60,
            max_items=1,
        )
