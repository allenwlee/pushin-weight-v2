"""Shared performers have stable identity and cannot become false login proofs."""

import uuid

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError

from core.collection_corrections import correct_attribution
from core.models import Actor
from tests.test_source_metric_projection import configured, evidence, project

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.mark.parametrize("kind", ["human", "agent", "system"])
def test_unique_actor_identity_is_scoped_by_kind(kind):
    first = Actor.objects.create(actor_kind=kind, actor_key="performer")
    with pytest.raises(IntegrityError), transaction.atomic():
        Actor.objects.create(actor_kind=kind, actor_key="performer")
    for other in {"human", "agent", "system"} - {kind}:
        assert (
            Actor.objects.create(actor_kind=other, actor_key="performer").pk != first.pk
        )


@pytest.mark.parametrize(
    "kind,key",
    [
        ("unknown", "performer"),
        ("human", ""),
        ("human", " "),
        ("agent", " leading"),
        ("system", "trailing\t"),
        ("human", "\nname"),
    ],
)
def test_raw_writes_reject_invalid_identity(kind, key):
    with (
        pytest.raises(IntegrityError),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "INSERT INTO actors(id,actor_kind,actor_key) VALUES (%s,%s,%s)",
            [uuid.uuid4(), kind, key],
        )


@pytest.mark.parametrize(
    "column,value",
    [
        ("id", uuid.uuid4()),
        ("actor_kind", "human"),
        ("actor_key", "different"),
    ],
)
def test_bulk_updates_cannot_rewrite_performer_identity(column, value):
    actor = Actor.objects.create(actor_kind="agent", actor_key="stable")
    with pytest.raises(IntegrityError, match="immutable"), transaction.atomic():
        Actor.objects.filter(pk=actor.pk).update(**{column: value})
    actor.refresh_from_db()
    assert actor.actor_kind == "agent" and actor.actor_key == "stable"


def test_referenced_performer_cannot_be_deleted_by_orm_or_sql():
    contract, raw, _, _ = configured(mapped=True, product_type="llm-model")
    observation = project(contract, "hf", [evidence("hf", raw)]).observations.get()
    actor = Actor.objects.create(actor_kind="human", actor_key="reviewer")
    correction = correct_attribution(
        observation,
        product=None,
        mapping=None,
        actor="Retained operator label",
        actor_identity=actor,
        reason="incorrect_product",
    )
    with pytest.raises(ProtectedError):
        actor.delete()
    with (
        pytest.raises(IntegrityError),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("DELETE FROM actors WHERE id=%s", [actor.pk])
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    correction.refresh_from_db()
    assert correction.actor == actor


@pytest.mark.usefixtures("isolated_migration_database")
@pytest.mark.django_db(transaction=True)
def test_expansion_and_reverse_preserve_legacy_corrections_and_old_writer():
    from django.db.migrations.executor import MigrationExecutor

    target = ("core", "0115_shared_actors_and_correction_identity")
    MigrationExecutor(connection).migrate([target])
    contract, raw, _, _ = configured(mapped=True, product_type="llm-model")
    observation = project(contract, "hf", [evidence("hf", raw)]).observations.get()
    correction = correct_attribution(
        observation,
        product=None,
        mapping=None,
        actor="Unverified legacy label",
        reason="incorrect_product",
    )
    base = ("core", "0114_collection_latest_attempt_pointer")
    MigrationExecutor(connection).migrate([base])
    state = MigrationExecutor(connection).loader.project_state([base])
    old_model = state.apps.get_model("core", "CollectionCorrection")
    before = old_model.objects.values().get(pk=correction.pk)
    MigrationExecutor(connection).migrate([target])
    from core.models import CollectionCorrection

    after = CollectionCorrection.objects.values().get(pk=correction.pk)
    assert after.pop("actor_id") is None
    assert after == before
    seed = Actor.objects.get(
        actor_kind="system", actor_key="benchmark_metric_timing_repair"
    )
    assert seed.pk == uuid.uuid5(
        uuid.NAMESPACE_URL, "pushinweight:actor:system:benchmark_metric_timing_repair"
    )
    old_write = old_model.objects.create(
        observation_id=observation.pk,
        predecessor_id=correction.pk,
        correction_kind="attribution",
        policy_version="legacy-writer-v1",
        actor_identifier="Unverified legacy label",
        reason_code="confirmed_unassigned",
    )
    assert CollectionCorrection.objects.get(pk=old_write.pk).actor_id is None
    with pytest.raises(IntegrityError, match="immutable"), transaction.atomic():
        CollectionCorrection.objects.filter(pk=correction.pk).update(actor_id=seed.pk)
    MigrationExecutor(connection).migrate([base])
    assert old_model.objects.count() == 2
    assert old_model.objects.values().get(pk=correction.pk) == before
    assert "actors" not in connection.introspection.table_names()
    MigrationExecutor(connection).migrate([target])
