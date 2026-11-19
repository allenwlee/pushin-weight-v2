"""Typed benchmark flags keep the old scalar view's three-valued meaning."""

from core.collection_resources import observation_fact_values
from core.models import CollectionJob, CollectionObservation, CollectionRun


def _facts(metadata):
    context = CollectionObservation(
        source_identifier="publisher/model",
        run=CollectionRun(job=CollectionJob(source_id="hf")),
    )
    values = observation_fact_values(context, documents=({}, {}, metadata))
    # Missing evidence leaves the typed model's NULL default; explicit false
    # remains false. No legacy document attributes or database are needed.
    return CollectionObservation(**values)


def test_missing_and_explicit_false_provenance_remain_distinct():
    missing = _facts({})
    assert missing.history_reconstructed is None
    assert missing.secondary_source is None
    assert missing.publication_complete is None
    assert missing.reconstruction_date is None

    reported = _facts({
        "history_basis": "reported",
        "secondary_source": False,
        "publication_complete": False,
        "reconstruction_date": "2026-10-25",
    })
    assert reported.history_reconstructed is False
    assert reported.secondary_source is False
    assert reported.publication_complete is False
    assert reported.reconstruction_date.isoformat() == "2026-10-25"

    reconstructed = _facts({
        "history_basis": "reconstructed_current_relationships",
        "secondary_source": True,
        "publication_complete": True,
        "reconstruction_date": "not-a-date",
    })
    assert reconstructed.history_reconstructed is True
    assert reconstructed.secondary_source is True
    assert reconstructed.publication_complete is True
    assert reconstructed.reconstruction_date is None


def test_source_artifact_hash_and_revision_reuse_existing_typed_fields():
    facts = _facts({
        "raw_artifact_sha256": "a" * 64,
        "immutable_revision": "dataset-revision-7",
    })
    assert facts.payload_sha256 == "a" * 64
    assert facts.provider_revision == "dataset-revision-7"
