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
def test_actor_cutover_backfills_registered_identity_and_keeps_old_writer_label():
    from django.db.migrations.executor import MigrationExecutor

    before_cutover = ("core", "0124_metric_unit_writer_cutover")
    target = ("core", "0125_correction_actor_writer_cutover")
    executor = MigrationExecutor(connection)
    executor.migrate([before_cutover])
    contract, raw, _, _ = configured(mapped=True, product_type="llm-model")
    observation = project(contract, "hf", [evidence("hf", raw)]).observations.get()
    Actor.objects.create(actor_kind="agent", actor_key="legacy")
    existing_id = uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO collection_corrections
                (id,observation_id,correction_kind,policy_version,
                 actor_identifier,actor_id,reason_code,recorded_at_precision)
            VALUES (%s,%s,'attribution','legacy-v1','agent:legacy',NULL,
                    'incorrect_product','unknown')
            """,
            [existing_id, observation.pk],
        )

    # Apply the actor cutover from its preceding state with the old stored label
    # present and no FK, exercising the exact-match migration directly.
    MigrationExecutor(connection).migrate([target])
    target_apps = MigrationExecutor(connection).loader.project_state([target]).apps
    CollectionCorrection = target_apps.get_model("core", "CollectionCorrection")
    TargetActor = target_apps.get_model("core", "Actor")
    registered = TargetActor.objects.get(actor_kind="agent", actor_key="legacy")
    assert CollectionCorrection.objects.get(pk=existing_id).actor_id == registered.pk

    created = CollectionCorrection.objects.create(
        observation_id=observation.pk,
        predecessor_id=existing_id,
        correction_kind="attribution",
        policy_version="current-v1",
        actor=registered,
        reason_code="confirmed_unassigned",
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT actor_identifier FROM collection_corrections WHERE id=%s",
            [created.pk],
        )
        assert cursor.fetchone()[0] == "agent:legacy"

    old_model = MigrationExecutor(connection).loader.project_state(
        [before_cutover]
    ).apps.get_model("core", "CollectionCorrection")
    old_write = old_model.objects.create(
        observation_id=observation.pk,
        predecessor_id=created.pk,
        correction_kind="attribution",
        policy_version="legacy-writer-v1",
        actor_identifier="Unverified legacy label",
        reason_code="confirmed_unassigned",
    )
    assert CollectionCorrection.objects.get(pk=old_write.pk).actor_id is None

    legacy_registered_write = old_model.objects.create(
        observation_id=observation.pk,
        predecessor_id=old_write.pk,
        correction_kind="attribution",
        policy_version="legacy-writer-v1",
        actor_identifier="agent:legacy",
        reason_code="confirmed_unassigned",
    )
    assert (
        CollectionCorrection.objects.get(pk=legacy_registered_write.pk).actor_id
        == registered.pk
    )
