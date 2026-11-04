"""Explicit additive schema and bounded legacy-copy operations for backfill DB."""
import json
from dataclasses import asdict
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor

from core.data_source_backfill_target import validate_backfill_target
from core.data_source_backfill_upgrade import EXPAND, project_batch
from core.measurement_taxonomy import require


class Command(BaseCommand):
    help = 'Inspect or explicitly expand/copy the dedicated backfill DB; never retire storage implicitly.'

    def add_arguments(self, parser):
        parser.add_argument('--stage', choices=['inspect', 'expand', 'archives', 'parity',
            'invocations', 'continuations', 'cursors', 'bounds', 'targets', 'rare_hits',
            'request_uses', 'pages'], default='inspect')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--verify-only', action='store_true')
        parser.add_argument('--after-id')
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--table', choices=['collection_runs', 'collection_scope_runs',
                                               'collection_observations'])

    def handle(self, *args, **options):
        try:
            # Upgrade deliberately admits 0183; collectors retain their stricter
            # current-schema gate. Authenticated destination checks are identical.
            target = validate_backfill_target()
            stage = options['stage']
            require(not options['apply'] or not target['read_only'],
                    'schema/copy operation requires a writable backfill login')
            require(1 <= options['limit'] <= 500, 'limit must be1 through500')
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan([EXPAND])
            if stage in {'inspect', 'expand'}:
                if options['apply'] and stage == 'expand':
                    require(not any(backwards for _, backwards in plan),
                            'schema expansion cannot reverse an applied migration')
                    executor.migrate([EXPAND])
                result = {'expansion_target': EXPAND[1],
                          'migration_plan': [{'name': migration.name, 'backwards': backwards}
                                             for migration, backwards in plan]}
            else:
                require(EXPAND in executor.loader.applied_migrations,
                        'apply additive schema through0195 before projection')
                require(options['apply'] or options['verify_only'],
                        'choose --apply for bounded copying or --verify-only for parity')
                from core import collection_storage_migration as copy
                if stage == 'archives':
                    require(options['apply'] and not options['verify_only'] and options['table'],
                            'archive copying requires --apply and one explicit table')
                    result = asdict(copy.archive_legacy_batch(options['table'],
                        batch_size=options['limit'], repair_stale=True))
                elif stage == 'parity':
                    require(options['verify_only'] and not options['apply'],
                            'parity requires --verify-only')
                    with transaction.atomic(), connection.cursor() as cursor:
                        cursor.execute('SET TRANSACTION READ ONLY')
                        result = {'archives': {table: copy.stale_legacy_archive_count(table)
                                              for table in copy.LEGACY_FIELDS},
                                  'bounds': copy.scope_bounds_mismatch_counts(),
                                  'targets': copy.x_query_target_mismatch_counts(),
                                  'rare_hits': copy.scope_rare_hit_mismatch_counts(),
                                  'request_uses': copy.scope_request_use_mismatch_counts()}
                else:
                    value = options['after_id']
                    after = (UUID(value) if stage in {'invocations', 'continuations'} else int(value)) if value else None
                    result = asdict(project_batch(stage, after_id=after,
                        batch_size=options['limit'], verify_only=options['verify_only']))
            self.stdout.write(json.dumps({'target': target, 'stage': stage,
                'applied': options['apply'] and stage != 'inspect', 'result': result}, default=str))
        except (ValueError, TypeError) as exc:
            raise CommandError(str(exc)) from exc
