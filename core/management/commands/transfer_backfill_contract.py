"""Export reviewed backfill captures, or replay them into an explicitly named database.

Export (backfill database, read-only):
    manage.py transfer_backfill_contract --export --contract <uuid> --out <bundle.json>
Rehearse (always rolled back) and apply on the target:
    manage.py transfer_backfill_contract --bundle <bundle.json> --target-database <name> [--apply]
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

DEFAULT_REVIEWER = '0813 production transfer: owner-authorized replay of reviewed backfill contract'


class Command(BaseCommand):
    help = 'Export a reviewed backfill contract bundle, or replay one; --apply keeps a fully verified replay.'

    def add_arguments(self, parser):
        parser.add_argument('--export', action='store_true')
        parser.add_argument('--contract', help='Backfill contract to export.')
        parser.add_argument('--out', help='Bundle path to write on export.')
        parser.add_argument('--bundle', help='Bundle path to replay.')
        parser.add_argument('--target-database', help='Exact current_database() of the replay target.')
        parser.add_argument('--reviewed-by', default=DEFAULT_REVIEWER)
        parser.add_argument('--apply', action='store_true', help='Commit when every check passes.')

    def handle(self, *args, **options):
        from core.data_source_backfill_transfer import apply_bundle, build_bundle
        from core.models import MetricCollectionContract

        try:
            if options['export']:
                if not options['contract'] or not options['out'] or options['bundle'] or options['apply']:
                    raise ValueError('export requires only --contract and --out')
                from core.data_source_backfill_target import validate_backfill_target

                validate_backfill_target(require_write=False)
                with transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION READ ONLY')
                    bundle = build_bundle(MetricCollectionContract.objects.get(pk=options['contract']))
                Path(options['out']).write_text(
                    json.dumps(bundle, sort_keys=True, indent=1, ensure_ascii=False, allow_nan=False) + '\n')
                self.stdout.write(json.dumps({'exported': options['out'], 'bundle_sha256': bundle['bundle_sha256'],
                    'captures': len(bundle['captures']), 'values': bundle['value_count'], 'writes': 0}))
                return
            if not options['bundle'] or options['contract'] or options['out']:
                raise ValueError('replay requires --bundle and --target-database')
            bundle = json.loads(Path(options['bundle']).read_text())
            report = apply_bundle(bundle, expected_database=options['target_database'],
                                  reviewed_by=options['reviewed_by'], commit=options['apply'])
            report.update(mode='apply' if options['apply'] else 'rehearsal', provider_calls=0)
            self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
            if report['problems']:
                raise CommandError(f"transfer verification failed with {len(report['problems'])} problem(s); nothing committed")
        except (ValueError, TypeError, KeyError, MetricCollectionContract.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
