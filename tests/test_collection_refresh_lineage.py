"""A staging copy clears runtime work without deleting measurement evidence."""

import pytest
from django.db import connection, transaction

from core.models import CollectionObservation, CollectionRun, MetricValue
from scripts.staging_refresh.database import purge_collection_runtime

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_shadow_scrub_removes_unused_attempts_but_keeps_immutable_archives():
    from core.collection_capture import archive_document
    from core.models import CollectionAttempt, CollectionEvidenceArchive
    from tests.test_collection_relational_storage import execution

    run, _, _ = execution()
    archive_document(b"{}")
    with transaction.atomic(), connection.cursor() as cursor:
        purge_collection_runtime(cursor)
    assert not CollectionRun.objects.filter(pk=run.pk).exists()
    assert not CollectionAttempt.objects.exists()
    assert CollectionEvidenceArchive.objects.count() == 1


def test_shadow_scrub_retains_catalog_inputs_needed_by_numeric_values():
    from tests.test_source_metric_projection import configured, evidence, project

    contract, raw, _, _ = configured()
    origin = evidence("hf", raw)
    numeric = project(contract, "hf", [origin])
    before = list(MetricValue.objects.order_by("pk").values())
    with transaction.atomic(), connection.cursor() as cursor:
        purge_collection_runtime(cursor)
        assert not any(purge_collection_runtime(cursor).values())
    assert list(MetricValue.objects.order_by("pk").values()) == before
    assert CollectionRun.objects.filter(pk=numeric.pk).exists()
    assert CollectionObservation.objects.filter(pk=origin.pk).exists()
    assert numeric.observations.get().inputs.get().input_observation_id == origin.pk


def test_shadow_scrub_preserves_dossier_sources_linked_to_catalog_observations():
    from core.event_dossiers import attach_source, create_dossier, identity_key
    from tests.test_collection_relational_storage import execution

    run, _, scope = execution()
    observation = CollectionObservation.objects.create(
        run=run,
        scope_run=scope,
        source_identifier="publisher/model",
        source_subject_kind="model",
        observation_key="d" * 64,
        resource_key="publisher/model",
    )
    dossier = create_dossier(
        event_kind="product_release",
        identity_key=identity_key("refresh-test", "dossier"),
    )
    source = attach_source(dossier.pk, observation_id=observation.pk)

    with transaction.atomic(), connection.cursor() as cursor:
        purge_collection_runtime(cursor)

    assert CollectionRun.objects.filter(pk=run.pk).exists()
    assert CollectionObservation.objects.filter(pk=observation.pk).exists()
    source.refresh_from_db()
    assert source.collection_observation_id == observation.pk


def test_shadow_scrub_clears_login_accounts_without_erasing_correction_performers():
    from pathlib import Path

    from django.contrib.auth import get_user_model

    from core.collection_corrections import correct_attribution
    from core.models import Actor, CollectionCorrection
    from scripts.staging_refresh.database import scrub_candidate_data
    from scripts.staging_refresh.policy import load_policy
    from tests.test_source_metric_projection import configured, evidence, project

    get_user_model().objects.create_user(username="environment-local-operator")
    contract, raw, _, _ = configured(mapped=True, product_type="llm-model")
    observation = project(contract, "hf", [evidence("hf", raw)]).observations.get()
    actor = Actor.objects.create(actor_kind="human", actor_key="stable-operator")
    correction = correct_attribution(
        observation,
        product=None,
        mapping=None,
        actor_identity=actor,
        reason="incorrect_product",
    )
    before = CollectionCorrection.objects.values().get(pk=correction.pk)
    policy = load_policy(
        Path(__file__).resolve().parents[1] / "config/staging_refresh.yaml"
    )
    with transaction.atomic(), connection.cursor() as cursor:
        scrub_candidate_data(cursor, policy)
    assert not get_user_model().objects.exists()
    assert Actor.objects.get(pk=actor.pk).actor_key == "stable-operator"
    assert CollectionCorrection.objects.values().get(pk=correction.pk) == before
