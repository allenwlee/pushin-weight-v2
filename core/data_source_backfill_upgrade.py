"""One-process compatibility for the existing pre-detachment projection helpers.

This operator never creates storage. It temporarily exposes the thirteen still
physical JSON fields to the current ORM so the canonical one-time copiers can
read their source. Call only in an isolated, single-threaded migration process;
normal collectors never enter this context. Physical retirement stays separate.
"""
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cache

from django.db import connection, transaction
from django.db.migrations.loader import MigrationLoader

from core.measurement_taxonomy import require
from core.migrations._rg6_retirement_v1 import FIELDS
from core.models import (
    CollectionJob,
    CollectionObservation,
    CollectionRun,
    CollectionScopeRun,
)

EXPAND = ('core', '0195_rg6_archive_import_scope_guard')
MODELS = (CollectionRun, CollectionScopeRun, CollectionObservation)
_projection_lock = threading.Lock()


@cache
def _historical_fields():
    historical = MigrationLoader(None).project_state([EXPAND]).apps
    return {model: {name: historical.get_model('core', model.__name__)._meta.get_field(name)
                    for name in FIELDS[model._meta.db_table]} for model in MODELS}


@dataclass(frozen=True)
class PageBatch:
    last_id: int
    scanned: int
    updated: int


def project_x_pages_batch(*, after_id=0, batch_size=100, verify_only=False):
    from core.collection_pages import PAGE_KIND, project_page_receipts

    require(type(after_id) is int and after_id >= 0, 'page cursor must be a nonnegative integer')
    rows = list(CollectionScopeRun.objects.filter(scope_kind='x_query', pk__gt=after_id)
                .order_by('pk').values_list('pk', 'run_id', 'run__job_id')[:batch_size])
    updated = 0
    for scope_id, run_id, job_id in rows:
        # Preserve the live writer's job -> run -> scope lock order. One source
        # scope is atomic; a timeout retains every previously verified scope.
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout='2s'; SET LOCAL statement_timeout='30s'")
            CollectionJob.objects.select_for_update().only('pk').get(pk=job_id)
            CollectionRun.objects.select_for_update().only('pk').get(pk=run_id)
            scope = CollectionScopeRun.objects.select_for_update().get(pk=scope_id)
            require(scope.run_id == run_id, 'historical page owner changed')
            before = scope.child_scopes.filter(scope_kind=PAGE_KIND).count()
            require(not verify_only or before == len(scope.envelopes),
                    'historical page receipts are not fully projected')
            project_page_receipts(scope, scope.envelopes, cursor=scope.cursor,
                                  legacy_archive=scope.legacy_archive)
            updated += int(before != len(scope.envelopes))
    return PageBatch(rows[-1][0] if rows else after_id, len(rows), updated)


@contextmanager
def legacy_projection_models():
    """Expose only verified existing JSONB columns, then restore the ORM exactly."""
    require(threading.active_count() == 1, 'legacy projection requires an isolated process')
    require(_projection_lock.acquire(blocking=False), 'legacy projection already active')
    added = []
    try:
        expected = {(table, field) for table, fields in FIELDS.items() for field in fields}
        with connection.cursor() as cursor:
            cursor.execute("""SELECT c.relname,a.attname,format_type(a.atttypid,a.atttypmod)
                FROM pg_class c JOIN pg_attribute a ON a.attrelid=c.oid
                WHERE c.relnamespace=current_schema()::regnamespace
                  AND c.relname=ANY(%s) AND a.attnum>0 AND NOT a.attisdropped""",
                [list(FIELDS)])
            physical = {(table, field): kind for table, field, kind in cursor.fetchall()}
        require(all(physical.get(key) == 'jsonb' for key in expected),
                'legacy projection requires all thirteen pre-retirement JSONB columns')
        for model in MODELS:
            fields = {field.name for field in model._meta.fields}
            require(not fields.intersection(FIELDS[model._meta.db_table]),
                    'legacy projection requires the current detached ORM')
        for model in MODELS:
            for name in FIELDS[model._meta.db_table]:
                field = _historical_fields()[model][name].clone()
                model.add_to_class(name, field)
                added.append((model, name, field))
        yield
    finally:
        for model, name, field in reversed(added):
            model._meta.local_fields.remove(field)
            delattr(model, name)
            model._meta._expire_cache()
        _projection_lock.release()


def project_batch(stage, *, after_id=None, batch_size=100, verify_only=False):
    """Dispatch bounded, idempotent existing copiers; never change source receipts."""
    from core import collection_storage_migration as copy

    require(type(batch_size) is int and 1 <= batch_size <= 500, 'batch size must be1 through500')
    stages = {
        'invocations': (copy.project_run_invocations_batch, None, True),
        'continuations': (copy.project_run_continuations_batch, None, True),
        'cursors': (copy.project_scope_cursors_batch, 0, True),
        'bounds': (copy.project_scope_bounds_batch, 0, False),
        'targets': (copy.project_x_query_targets_batch, 0, False),
        'rare_hits': (copy.project_scope_rare_hits_batch, 0, False),
        'request_uses': (copy.project_scope_request_uses_batch, 0, False),
        'pages': (project_x_pages_batch, 0, True),
    }
    require(stage in stages, 'unsupported legacy projection stage')
    function, initial, verifies = stages[stage]
    require(not verify_only or verifies, 'use the stage-specific parity counter to verify this stage')
    options = {'after_id': initial if after_id is None else after_id, 'batch_size': batch_size}
    if verifies:
        options['verify_only'] = verify_only
    with legacy_projection_models():
        return function(**options)
