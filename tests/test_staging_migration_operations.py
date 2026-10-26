"""Database-free recovery checks for each non-atomic 0190 operation."""

import hashlib
from contextlib import nullcontext
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.db import migrations

migration = import_module("core.migrations.0190_x_staging_receipts")
INDEX = ("CREATE UNIQUE INDEX uq_observation_request_position ON public.collection_observations "
         "USING btree (request_id, receipt_ordinal) WHERE (request_id IS NOT NULL)")
FK = "FOREIGN KEY (request_id) REFERENCES collection_requests(id) DEFERRABLE INITIALLY DEFERRED"


def editor(*results):
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchone.side_effect = results
    value = MagicMock()
    value.connection.cursor.return_value = cursor
    value.connection.alias = "default"
    value.quote_name.side_effect = lambda name: '"' + name + '"'
    return value, cursor


def test_every_column_add_is_restartable_and_constraints_validate_separately():
    fields = [op for op in migration.Migration.operations if isinstance(op, migrations.AddField)]
    assert len(fields) == 11
    assert all(isinstance(op, migration.AddNullableFieldIfMissing) and op.field.null for op in fields)
    assert migration.Migration.atomic is False
    assert any(isinstance(op, migration.ValidateConstraint) for op in migration.Migration.operations)
    assert "5s" in migration.Migration.operations[0].sql


@pytest.mark.parametrize("db_type,catalog_type", [("uuid", "uuid"), ("double precision[3]", "double precision[]")])
def test_column_add_resumes_after_creation_without_adding_twice(monkeypatch, db_type, catalog_type):
    operation = migration.AddNullableFieldIfMissing(model_name="collectionrun", name="fixture", field=MagicMock())
    field = SimpleNamespace(column="fixture", db_type=lambda connection: db_type)
    model = SimpleNamespace(_meta=SimpleNamespace(db_table="collection_runs", get_field=lambda name: field))
    state = SimpleNamespace(apps=SimpleNamespace(get_model=lambda *args: model))
    schema, _ = editor(None, (catalog_type, False, None))
    add = MagicMock()
    monkeypatch.setattr(migrations.AddField, "database_forwards", add)
    operation.database_forwards("core", schema, state, state)
    operation.database_forwards("core", schema, state, state)
    assert add.call_count == 1


@pytest.mark.parametrize("existing", [("text", False, None), ("uuid", True, None), ("uuid", False, "gen_random_uuid()")])
def test_column_shape_mismatch_never_skips_or_replaces(monkeypatch, existing):
    operation = migration.AddNullableFieldIfMissing(model_name="collectionrun", name="fixture", field=MagicMock())
    field = SimpleNamespace(column="fixture", db_type=lambda connection: "uuid")
    model = SimpleNamespace(_meta=SimpleNamespace(db_table="collection_runs", get_field=lambda name: field))
    state = SimpleNamespace(apps=SimpleNamespace(get_model=lambda *args: model))
    schema, _ = editor(existing)
    add = MagicMock()
    monkeypatch.setattr(migrations.AddField, "database_forwards", add)
    with pytest.raises(RuntimeError, match="column differs"):
        operation.database_forwards("core", schema, state, state)
    add.assert_not_called()


def test_valid_index_is_not_rebuilt_and_matching_invalid_index_resumes():
    schema, _ = editor((True, False, True, INDEX), (True, True, True, INDEX))
    migration.install_request_index(None, schema)
    migration.install_request_index(None, schema)
    assert [call.args[0].split()[0] for call in schema.execute.call_args_list] == ["DROP", "CREATE"]


def test_failed_concurrent_build_can_be_retried():
    schema, _ = editor(None, (True, False, True, INDEX), (True, True, True, INDEX))
    schema.execute.side_effect = [TimeoutError("fixture build interrupted"), None, None]
    with pytest.raises(TimeoutError):
        migration.install_request_index(None, schema)
    migration.install_request_index(None, schema)
    migration.install_request_index(None, schema)
    assert schema.execute.call_count == 3


@pytest.mark.parametrize("existing", [
    (False, False, True, INDEX), (True, False, False, INDEX),
    (True, False, True, INDEX.replace("receipt_ordinal", "id")),
    (True, False, True, INDEX.replace("IS NOT NULL", "IS NULL")),
])
def test_foreign_or_changed_index_is_never_dropped(existing):
    schema, _ = editor(existing)
    with pytest.raises(RuntimeError, match="refusing to replace"):
        migration.install_request_index(None, schema)
    schema.execute.assert_not_called()


def test_foreign_key_resume_accepts_both_validation_states():
    schema, _ = editor(None, ("f", True, True, True, FK + " NOT VALID"), ("f", True, True, True, FK))
    for _ in range(3):
        migration.install_request_fk(None, schema)
    assert schema.execute.call_count == 1


@pytest.mark.parametrize("existing", [("f", False, True, True, FK), ("f", True, False, True, FK),
                                     ("f", True, True, True, FK.replace("(request_id)", "(run_id)"))])
def test_foreign_key_shape_mismatch_is_not_accepted(existing):
    schema, _ = editor(existing)
    with pytest.raises(RuntimeError, match="foreign key differs"):
        migration.install_request_fk(None, schema)
    schema.execute.assert_not_called()


def test_check_resume_verifies_declared_and_actual_shape(monkeypatch):
    operation = next(op for op in migration.Migration.operations if isinstance(op, migration.AddCheckIfMissing))
    monkeypatch.setattr(operation.constraint, "constraint_sql", lambda *args: "declared CHECK")
    monkeypatch.setattr(migration.transaction, "atomic", lambda **kwargs: nullcontext())
    actual = "CHECK (request_id IS NOT NULL)"
    stamp = migration._check_signature("declared CHECK", actual)
    schema, _ = editor(None, (actual + " NOT VALID",), ("c", stamp, actual + " NOT VALID"), ("c", stamp, actual))
    model = SimpleNamespace(_meta=SimpleNamespace(db_table="collection_observations"))
    state = SimpleNamespace(apps=SimpleNamespace(get_model=lambda *args: model))
    create = MagicMock()
    monkeypatch.setattr(migration.AddConstraintNotValid, "database_forwards", create)
    for _ in range(3):
        operation.database_forwards("core", schema, state, state)
    assert create.call_count == 1
    bad, _ = editor(("c", stamp, actual.replace("NOT NULL", "NULL")))
    with pytest.raises(RuntimeError, match="CHECK differs"):
        operation.database_forwards("core", bad, state, state)


def test_ownership_function_and_trigger_resume_each_partial_step():
    body = migration.OWNERSHIP_GUARD.split("$$", 2)[1]
    trigger = (23, "O", True, True, True)
    schema, _ = editor(None, None, (body,), None, (body,), trigger)
    for _ in range(3):
        migration.install_ownership_guard(None, schema)
    assert schema.execute.call_count == 3  # function+trigger; then missing trigger; then neither


def test_changed_ownership_objects_are_not_replaced():
    body = migration.OWNERSHIP_GUARD.split("$$", 2)[1]
    for results in ((("foreign function",),), ((body,), (23, "D", True, True, True))):
        schema, _ = editor(*results)
        with pytest.raises(RuntimeError, match="differs"):
            migration.install_ownership_guard(None, schema)
        schema.execute.assert_not_called()


def test_unmarked_page_guard_requires_exact_pinned_predecessor(monkeypatch):
    old = "CHECK (reviewed 0188 fixture)"
    new = "CHECK (reviewed 0190 fixture)"
    monkeypatch.setattr(migration, "PAGE_0188_SHA256", hashlib.sha256(old.encode()).hexdigest())
    monkeypatch.setattr(migration, "page_check", lambda include: SimpleNamespace(
        constraint_sql=lambda *args: new if include else old,
    ))
    apps = SimpleNamespace(get_model=lambda *args: None)
    foreign, _ = editor(("c", None, "CHECK (true)"))
    with pytest.raises(RuntimeError, match="differs from 0188"):
        migration.replace_page_check(apps, foreign)
    foreign.execute.assert_not_called()
    known, _ = editor(("c", None, old), (new,))
    migration.replace_page_check(apps, known)
    assert known.execute.call_count == 1
    stamp = migration._check_signature(new, new)
    resumed, _ = editor(("c", stamp, new))
    migration.replace_page_check(apps, resumed)
    resumed.execute.assert_not_called()
