"""Restartable online expansion for staging receipts and retry state.

Resume an interrupted application with ``manage.py migrate core 0190``. Matching
nullable columns, signed CHECKs, FK and valid index are retained. Only an invalid
index with this exact owner/key/predicate is rebuilt. Shape mismatches stop for
inspection; never fake-apply this migration. Each validation/concurrent build has
a five-minute statement ceiling, while lock acquisition is limited to five
seconds. This migration can span harvest cycles; its scans permit ordinary writes.
Rollback after request appearances exist is refused by the old shape validation.
"""

import hashlib
import re
from typing import ClassVar

import django.contrib.postgres.fields
import django.db.models.deletion
import django.db.models.lookups
from django.contrib.postgres.operations import AddConstraintNotValid, ValidateConstraint
from django.db import migrations, models, transaction

# Exact validated 0188 pg_get_constraintdef, checked on local PostgreSQL 18 and
# staging on 2026-10-26. An unmarked object with another definition is not ours.
PAGE_0188_SHA256 = '1466c62943a24dc4032793317601c4510eb333bb0de442c58405617c82812aec'


def _signature(definition):
    return 'rg6-0190:' + hashlib.sha256(str(definition).encode()).hexdigest()


def _check_signature(declared, actual):
    return _signature(declared) + ':' + hashlib.sha256(actual.removesuffix(' NOT VALID').encode()).hexdigest()


class AddNullableFieldIfMissing(migrations.AddField):
    """Resume an interrupted online migration without accepting schema drift."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        field = model._meta.get_field(self.name)
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                "SELECT format_type(a.atttypid,a.atttypmod),a.attnotnull,pg_get_expr(d.adbin,d.adrelid) "
                "FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
                "WHERE a.attrelid=%s::regclass AND a.attname=%s AND NOT a.attisdropped",
                [model._meta.db_table, field.column],
            )
            existing = cursor.fetchone()
        if existing is not None:
            expected = re.sub(r'\[\d+\]', '[]', field.db_type(schema_editor.connection))
            if existing != (expected, False, None):
                raise RuntimeError('0190 existing column differs: ' + field.column)
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)


class AddCheckIfMissing(AddConstraintNotValid):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = from_state.apps.get_model(app_label, self.model_name)
        definition = self.constraint.constraint_sql(model, schema_editor)
        with transaction.atomic(using=schema_editor.connection.alias), schema_editor.connection.cursor() as cursor:
            cursor.execute("SELECT contype,obj_description(oid,'pg_constraint'),pg_get_constraintdef(oid) FROM pg_constraint "
                           "WHERE conrelid=%s::regclass AND conname=%s", [model._meta.db_table, self.constraint.name])
            existing = cursor.fetchone()
            if existing is not None:
                if existing[0] != 'c' or existing[1] != _check_signature(definition, existing[2]):
                    raise RuntimeError('0190 existing CHECK differs: ' + self.constraint.name)
                return
            super().database_forwards(app_label, schema_editor, from_state, to_state)
            cursor.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid=%s::regclass AND conname=%s",
                           [model._meta.db_table, self.constraint.name])
            expected = _check_signature(definition, cursor.fetchone()[0])
            cursor.execute('COMMENT ON CONSTRAINT ' + schema_editor.quote_name(self.constraint.name)
                           + ' ON ' + schema_editor.quote_name(model._meta.db_table) + ' IS %s', [expected])


def install_request_index(apps, schema_editor):
    """A failed concurrent build may leave only this matching invalid index."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT i.indrelid='collection_observations'::regclass,i.indisvalid,i.indisunique,"
            "pg_get_indexdef(i.indexrelid) FROM pg_index i "
            "WHERE i.indexrelid=to_regclass('uq_observation_request_position')"
        )
        existing = cursor.fetchone()
    if existing is not None:
        correct_table, valid, unique, definition = existing
        expected_tail = 'USING btree (request_id, receipt_ordinal) WHERE (request_id IS NOT NULL)'
        if not correct_table or not unique or not definition.endswith(expected_tail):
            raise RuntimeError('0190 request index differs; refusing to replace it')
        if valid:
            return
        schema_editor.execute('DROP INDEX CONCURRENTLY uq_observation_request_position')
    schema_editor.execute('CREATE UNIQUE INDEX CONCURRENTLY uq_observation_request_position '
                          'ON collection_observations (request_id, receipt_ordinal) WHERE request_id IS NOT NULL')


def remove_request_index(apps, schema_editor):
    schema_editor.execute('DROP INDEX CONCURRENTLY IF EXISTS uq_observation_request_position')


def install_request_fk(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT contype,confrelid='collection_requests'::regclass,condeferrable,condeferred,"
            "pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='collection_observations'::regclass "
            "AND conname='fk_observation_request'"
        )
        existing = cursor.fetchone()
    if existing is not None:
        shape = existing[4].removesuffix(' NOT VALID')
        expected = 'FOREIGN KEY (request_id) REFERENCES collection_requests(id) DEFERRABLE INITIALLY DEFERRED'
        if existing[:4] != ('f', True, True, True) or shape != expected:
            raise RuntimeError('0190 request foreign key differs')
        return
    schema_editor.execute('ALTER TABLE collection_observations ADD CONSTRAINT fk_observation_request '
                          'FOREIGN KEY (request_id) REFERENCES collection_requests(id) '
                          'DEFERRABLE INITIALLY DEFERRED NOT VALID')


def remove_request_fk(apps, schema_editor):
    schema_editor.execute('ALTER TABLE collection_observations DROP CONSTRAINT IF EXISTS fk_observation_request')


def page_check(include_request):
    kinds = ['x_page_appearance', 'x_page_diagnostic']
    condition = models.Q(
        observation_kind='x_page_appearance', source_subject_kind='post_appearance',
        scope_run__isnull=False, receipt_ordinal__isnull=False,
        source_identifier_is_null__isnull=False, processing_outcome__isnull=False,
    )
    if include_request:
        kinds.insert(1, 'x_request_appearance')
        condition |= models.Q(
            observation_kind='x_request_appearance', source_subject_kind='post_appearance',
            scope_run__isnull=True, receipt_ordinal__isnull=False,
            source_identifier_is_null__isnull=False, processing_outcome='received',
        )
    condition |= models.Q(
        observation_kind='x_page_diagnostic', source_subject_kind='aggregate',
        scope_run__isnull=False, receipt_ordinal__isnull=False,
        source_identifier_is_null__isnull=True,
    ) | (
        models.Q(receipt_ordinal__isnull=True, source_identifier_is_null__isnull=True)
        & ~models.Q(source_subject_kind='post_appearance')
        & (models.Q(observation_kind__isnull=True) | ~models.Q(observation_kind__in=kinds))
    )
    return models.CheckConstraint(condition=condition, name='ck_observation_page_receipt')


def _replace_page_check(apps, schema_editor, include_request):
    model = apps.get_model('core', 'CollectionObservation')
    definition = page_check(include_request).constraint_sql(model, schema_editor)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT contype,obj_description(oid,'pg_constraint'),pg_get_constraintdef(oid) FROM pg_constraint "
                       "WHERE conrelid='collection_observations'::regclass AND conname='ck_observation_page_receipt'")
        existing = cursor.fetchone()
        if existing is not None and existing[0] == 'c' and existing[1] == _check_signature(definition, existing[2]):
            return
        # Only the pinned validated 0188 expression may be replaced unmarked.
        # Marked guards must match both this migration's declared and SQL shape.
        prior = page_check(not include_request).constraint_sql(model, schema_editor)
        if existing is None or existing[0] != 'c':
            raise RuntimeError('0190 page receipt CHECK differs')
        if existing[1] is None:
            if not include_request or hashlib.sha256(existing[2].encode()).hexdigest() != PAGE_0188_SHA256:
                raise RuntimeError('0190 unmarked page receipt CHECK differs from 0188')
        elif existing[1] != _check_signature(prior, existing[2]):
            raise RuntimeError('0190 page receipt CHECK differs')
    # One short metadata change replaces the guard without an unguarded gap.
    # Validation is a separate operation and permits ordinary INSERT/UPDATE.
    schema_editor.execute(
        'ALTER TABLE collection_observations DROP CONSTRAINT ck_observation_page_receipt, '
        'ADD ' + definition + ' NOT VALID', params=None,
    )
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='collection_observations'::regclass "
                       "AND conname='ck_observation_page_receipt'")
        expected = _check_signature(definition, cursor.fetchone()[0])
        cursor.execute("COMMENT ON CONSTRAINT ck_observation_page_receipt ON collection_observations IS %s", [expected])


def replace_page_check(apps, schema_editor):
    _replace_page_check(apps, schema_editor, True)


def restore_page_check(apps, schema_editor):
    _replace_page_check(apps, schema_editor, False)
    # Refuse a rollback that would strand already-written request appearances.
    schema_editor.execute('ALTER TABLE collection_observations VALIDATE CONSTRAINT ck_observation_page_receipt')


OWNERSHIP_GUARD = """
CREATE FUNCTION collection_observation_request_membership() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE request_run uuid;
BEGIN
    IF NEW.request_id IS NOT NULL THEN
        SELECT a.run_id INTO request_run FROM collection_requests r
        JOIN collection_attempts a ON a.id=r.attempt_id WHERE r.id=NEW.request_id;
        IF request_run IS NULL OR NEW.run_id <> request_run OR NEW.scope_run_id IS NOT NULL THEN
            RAISE EXCEPTION 'request appearance requires its original run and request owner' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER collection_observation_request_membership BEFORE INSERT OR UPDATE ON collection_observations
FOR EACH ROW EXECUTE FUNCTION collection_observation_request_membership();
"""
REMOVE_OWNERSHIP_GUARD = """
DROP TRIGGER collection_observation_request_membership ON collection_observations;
DROP FUNCTION collection_observation_request_membership();
"""


def install_ownership_guard(apps, schema_editor):
    expected_body = OWNERSHIP_GUARD.split('$$', 2)[1]
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT prosrc FROM pg_proc WHERE oid=to_regprocedure('collection_observation_request_membership()')")
        function = cursor.fetchone()
        if function is not None and function != (expected_body,):
            raise RuntimeError('0190 request ownership function differs')
        cursor.execute("SELECT tgtype,tgenabled,tgfoid=to_regprocedure('collection_observation_request_membership()'),"
                       "tgqual IS NULL,octet_length(tgargs)=0 FROM pg_trigger "
                       "WHERE tgrelid='collection_observations'::regclass AND tgname='collection_observation_request_membership'")
        trigger = cursor.fetchone()
        if trigger is not None and trigger != (23, 'O', True, True, True):
            raise RuntimeError('0190 request ownership trigger differs')
    if function is None:
        schema_editor.execute(OWNERSHIP_GUARD.split('CREATE TRIGGER', 1)[0])
    if trigger is None:
        schema_editor.execute('CREATE TRIGGER' + OWNERSHIP_GUARD.split('CREATE TRIGGER', 1)[1])


def remove_ownership_guard(apps, schema_editor):
    schema_editor.execute(REMOVE_OWNERSHIP_GUARD)


class Migration(migrations.Migration):

    atomic = False

    dependencies: ClassVar[list] = [
        ('core', '0189_hf_numeric_selections'),
    ]

    operations: ClassVar[list] = [
        migrations.RunSQL("SET lock_timeout = '5s'; SET statement_timeout = '5min'", migrations.RunSQL.noop),
        AddNullableFieldIfMissing(
            model_name='collectionobservation',
            name='request',
            field=models.ForeignKey(db_constraint=False, db_index=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='received_appearances', to='core.collectionrequest'),
        ),
        AddNullableFieldIfMissing(
            model_name='collectionrequest',
            name='body_lost',
            field=models.BooleanField(null=True),
        ),
        AddNullableFieldIfMissing(
            model_name='collectionrequest',
            name='raw_count',
            field=models.PositiveBigIntegerField(null=True),
        ),
        AddNullableFieldIfMissing(
            model_name='collectionrequest',
            name='response_sha256',
            field=models.BinaryField(null=True),
        ),
        AddNullableFieldIfMissing(
            model_name='collectionrequest',
            name='selection_accounted',
            field=models.BooleanField(null=True),
        ),
        AddNullableFieldIfMissing(
            model_name='collectionrun',
            name='staging_retry_cooldowns',
            field=models.PositiveSmallIntegerField(null=True),
        ),
        AddNullableFieldIfMissing(
            model_name='collectionrun',
            name='staging_retry_failures',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.FloatField(), null=True, size=3),
        ),
        AddNullableFieldIfMissing(
            model_name='collectionrun',
            name='staging_retry_phase',
            field=models.PositiveSmallIntegerField(null=True),
        ),
        AddNullableFieldIfMissing(
            model_name='collectionrun',
            name='staging_retry_successes',
            field=models.PositiveSmallIntegerField(null=True),
        ),
        AddNullableFieldIfMissing(
            model_name='collectionrun',
            name='staging_retry_until',
            field=models.FloatField(null=True),
        ),
        AddNullableFieldIfMissing(
            model_name='collectionrun',
            name='staging_retry_version',
            field=models.PositiveSmallIntegerField(null=True),
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(install_request_index, remove_request_index, atomic=False)],
            state_operations=[migrations.AddConstraint(
                model_name='collectionobservation',
                constraint=models.UniqueConstraint(condition=models.Q(request__isnull=False),
                    fields=('request', 'receipt_ordinal'), name='uq_observation_request_position'),
            )],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(install_request_fk, remove_request_fk, atomic=True)],
            state_operations=[migrations.AlterField(
                model_name='collectionobservation', name='request',
                field=models.ForeignKey(db_index=False, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='received_appearances', to='core.collectionrequest'),
            )],
        ),
        migrations.RunSQL('ALTER TABLE collection_observations VALIDATE CONSTRAINT fk_observation_request', migrations.RunSQL.noop),
        AddCheckIfMissing(
            model_name='collectionobservation',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('observation_kind', 'x_request_appearance'), ('observation_kind__isnull', False), ('request__isnull', False)), models.Q(('request__isnull', True), models.Q(('observation_kind__isnull', True), models.Q(('observation_kind', 'x_request_appearance'), _negated=True), _connector='OR')), _connector='OR'), name='ck_observation_request_owner'),
        ),
        ValidateConstraint('collectionobservation', 'ck_observation_request_owner'),
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(replace_page_check, restore_page_check, atomic=True)],
            state_operations=[
                migrations.RemoveConstraint(model_name='collectionobservation', name='ck_observation_page_receipt'),
                migrations.AddConstraint(model_name='collectionobservation', constraint=page_check(True)),
            ],
        ),
        ValidateConstraint('collectionobservation', 'ck_observation_page_receipt'),
        AddCheckIfMissing(
            model_name='collectionrequest',
            constraint=models.CheckConstraint(condition=models.Q(('response_sha256__isnull', True), django.db.models.lookups.Exact(models.Func(models.F('response_sha256'), function='octet_length', output_field=models.IntegerField()), models.Value(32)), _connector='OR'), name='ck_request_response_sha256'),
        ),
        ValidateConstraint('collectionrequest', 'ck_request_response_sha256'),
        AddCheckIfMissing(
            model_name='collectionrequest',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('body_lost__isnull', True), ('raw_count__isnull', True), ('response_sha256__isnull', True), ('selection_accounted__isnull', True)), models.Q(('body_lost__isnull', False), ('selection_accounted__isnull', False), models.Q(models.Q(('body_lost', False), ('raw_count__isnull', True), ('response_sha256__isnull', True), ('selection_accounted', False)), models.Q(('raw_count__isnull', False), ('response_bytes__isnull', False), ('response_sha256__isnull', False), ('transport_outcome', 'received')), _connector='OR')), _connector='OR'), name='ck_request_staging_receipt'),
        ),
        ValidateConstraint('collectionrequest', 'ck_request_staging_receipt'),
        AddCheckIfMissing(
            model_name='collectionrun',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('staging_retry_cooldowns__isnull', True), ('staging_retry_failures__isnull', True), ('staging_retry_phase__isnull', True), ('staging_retry_successes__isnull', True), ('staging_retry_until__isnull', True), ('staging_retry_version__isnull', True)), models.Q(('staging_retry_cooldowns__isnull', False), ('staging_retry_cooldowns__lte', 3), ('staging_retry_failures__isnull', False), ('staging_retry_failures__len__lte', 3), ('staging_retry_phase__isnull', False), ('staging_retry_phase__lte', 3), ('staging_retry_successes__isnull', False), ('staging_retry_successes__lte', 4), ('staging_retry_until__gte', 0), ('staging_retry_until__isnull', False), ('staging_retry_until__lt', float("inf")), ('staging_retry_version', 1), ('staging_retry_version__isnull', False)), _connector='OR'), name='ck_run_staging_retry_shape'),
        ),
        ValidateConstraint('collectionrun', 'ck_run_staging_retry_shape'),
        AddCheckIfMissing(
            model_name='collectionrun',
            constraint=models.CheckConstraint(condition=models.Q(('staging_retry_failures__isnull', True), models.Q(django.db.models.lookups.IsNull(models.Func(models.F('staging_retry_failures'), models.Value(None, output_field=models.FloatField()), function='array_position', output_field=models.IntegerField()), True), models.Q(('staging_retry_failures__len__lte', 0), models.Q(('staging_retry_failures__0__gte', 0), ('staging_retry_failures__0__lt', float("inf"))), _connector='OR'), models.Q(('staging_retry_failures__len__lte', 1), models.Q(('staging_retry_failures__1__gte', 0), ('staging_retry_failures__1__lt', float("inf"))), _connector='OR'), models.Q(('staging_retry_failures__len__lte', 2), models.Q(('staging_retry_failures__2__gte', 0), ('staging_retry_failures__2__lt', float("inf"))), _connector='OR')), _connector='OR'), name='ck_run_staging_retry_times'),
        ),
        ValidateConstraint('collectionrun', 'ck_run_staging_retry_times'),
        migrations.RunPython(install_ownership_guard, remove_ownership_guard, atomic=True),
        migrations.RunSQL('RESET lock_timeout; RESET statement_timeout', migrations.RunSQL.noop),
    ]
