"""Inspect first; explicitly apply bounded database-backed campaign operations."""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from core import data_source_backfill as service
from core.collection_jobs import set_job_state
from core.data_source_backfill_target import validate_backfill_target
from core.models import (
    CollectionJob,
    CollectionRun,
    DataSource,
    MetricCollectionContract,
)


def readonly_call(function, **kwargs):
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute('SET TRANSACTION READ ONLY')
        return function(**kwargs)


class Command(BaseCommand):
    help = 'Inspect source campaigns; --apply explicitly registers, executes, resumes or pauses.'

    def add_arguments(self, parser):
        parser.add_argument('--operation', default='inspect', choices=[
            'inspect', 'prepare-0813', 'plan-0813', 'register', 'execute', 'resume', 'pause', 'replay', 'replay-retained', 'report'])
        selection = parser.add_mutually_exclusive_group()
        selection.add_argument('--job')
        selection.add_argument('--campaign')
        parser.add_argument('--specifications', help='Reviewed JSON source-job instructions; never a checkpoint file.')
        parser.add_argument('--reference', help='Reviewed 0813 product/publisher reference JSON for prepare-0813.')
        parser.add_argument('--contract', help='Reviewed numeric contract for plan-0813.')
        parser.add_argument('--run', help='Committed numeric run for replay-retained.')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--limit', type=int, default=25, help='Report page size, at most100.')
        parser.add_argument('--after', dest='after_job_key', help='Next-page cursor returned as next_after.')

    def handle(self, *args, **options):
        operation, apply = options['operation'], options['apply']
        try:
            target = validate_backfill_target(
                require_write=apply and operation not in {'inspect', 'report'})
            if not target['schema_ready']:
                self.stdout.write(json.dumps({'target': target, 'operation': operation,
                    'applied': False, 'requires_schema_upgrade': True}))
                return
            if options['run'] and operation != 'replay-retained':
                raise ValueError('run is only accepted for replay-retained')
            selection = {'campaign_key': options['campaign'], 'job_id': options['job']}
            def report():
                return readonly_call(service.report_campaign, **selection,
                    limit=options['limit'], after_job_key=options['after_job_key'])
            if operation == 'replay-retained':
                from core.data_source_backfill_reuse import (
                    prepare_retained_replay,
                    replay_retained_run,
                )

                if not options['run'] or options['reference'] or options['contract'] or options['specifications'] or any(selection.values()):
                    raise ValueError('replay-retained requires only one explicit run')
                if apply:
                    run = replay_retained_run(options['run'])
                    result = {'run_id': str(run.pk), 'status': run.status, 'provider_calls': 0}
                else:
                    run, *_ = readonly_call(prepare_retained_replay, run_id=options['run'])
                    result = {'run_id': str(run.pk), 'writes': 0, 'provider_calls': 0}
            elif operation == 'plan-0813':
                from core.data_source_backfill_cohort import campaign_specifications

                if not options['contract'] or options['reference'] or options['specifications'] or options['campaign'] or apply:
                    raise ValueError('plan-0813 requires a contract and optional completed discovery job; it is read-only')
                result = {'specifications': readonly_call(campaign_specifications,
                    contract=options['contract'], discovery_job_id=options['job']), 'writes': 0}
            elif options['contract']:
                raise ValueError('contract is only accepted for plan-0813')
            elif operation == 'prepare-0813':
                from core.data_source_backfill_cohort import (
                    configure_cohort,
                    preview_cohort,
                )

                if not options['reference'] or options['specifications'] or any(selection.values()):
                    raise ValueError('prepare-0813 requires only its explicit reference JSON')
                reference = json.loads(options['reference'])
                result = (configure_cohort(reference, reviewed_by='0813 backfill plan: exact reviewed cohort')
                          if apply else readonly_call(preview_cohort, reference=reference))
            elif options['reference']:
                raise ValueError('reference JSON is only accepted for prepare-0813')
            elif operation == 'register':
                if not options['specifications']:
                    raise ValueError('registration specifications required')
                specifications = json.loads(options['specifications'])
                prepared = readonly_call(service.prepare_campaign, specifications=specifications)
                if apply:
                    jobs = service.register_campaign(specifications)
                    selection = {'campaign_key': jobs[0].campaign_settings['key']}
                    result = report()
                else:
                    result = {'job_keys': [spec['job_key'] for spec in prepared], 'writes': 0}
            else:
                if options['specifications']:
                    raise ValueError('specifications are only accepted for registration')
                if operation in {'execute', 'resume', 'replay'} and not options['job']:
                    raise ValueError('execution requires one explicit source job')
                if operation == 'pause' and not any(selection.values()):
                    raise ValueError('pause requires a job or campaign')
                # Always resolve and validate before mutation, including preview.
                result = report()
                if apply and operation in {'execute', 'resume', 'replay'}:
                    service.execute_phase(options['job'], replay=operation == 'replay')
                elif apply and operation == 'pause':
                    with transaction.atomic():
                        for job in service.campaign_jobs(**selection):
                            set_job_state(job.pk, 'paused')
                if apply and operation not in {'inspect', 'report'}:
                    result = report()
            result.update(operation=operation, applied=apply and operation not in {'inspect', 'report'})
            result['target'] = target
            self.stdout.write(json.dumps(result, ensure_ascii=False))
        except (ValueError, TypeError, KeyError, CollectionJob.DoesNotExist, CollectionRun.DoesNotExist,
                DataSource.DoesNotExist, MetricCollectionContract.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
