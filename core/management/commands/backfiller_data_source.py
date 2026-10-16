"""Inspect first; explicitly apply bounded database-backed campaign operations."""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core import data_source_backfill as service
from core.collection_jobs import set_job_state
from core.models import CollectionJob, DataSource, MetricCollectionContract


class Command(BaseCommand):
    help = 'Inspect source campaigns; --apply explicitly registers, executes, resumes or pauses.'

    def add_arguments(self, parser):
        parser.add_argument('--operation', default='inspect', choices=[
            'inspect', 'register', 'execute', 'resume', 'pause', 'replay', 'report'])
        selection = parser.add_mutually_exclusive_group()
        selection.add_argument('--job')
        selection.add_argument('--campaign')
        parser.add_argument('--specifications', help='Reviewed JSON source-job instructions; never a checkpoint file.')
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        operation, apply = options['operation'], options['apply']
        try:
            selection = {'campaign_key': options['campaign'], 'job_id': options['job']}
            if operation == 'register':
                if not options['specifications']:
                    raise ValueError('registration specifications required')
                specifications = json.loads(options['specifications'])
                prepared = service.prepare_campaign(specifications)
                if apply:
                    jobs = service.register_campaign(specifications)
                    selection = {'campaign_key': jobs[0].definition['campaign']['key']}
                    report = service.report_campaign(**selection)
                else:
                    report = {'job_keys': [spec['job_key'] for spec in prepared], 'writes': 0}
            else:
                if options['specifications']:
                    raise ValueError('specifications are only accepted for registration')
                if operation in {'execute', 'resume', 'replay'} and not options['job']:
                    raise ValueError('execution requires one explicit source job')
                if operation == 'pause' and not any(selection.values()):
                    raise ValueError('pause requires a job or campaign')
                # Always resolve and validate before mutation, including preview.
                report = service.report_campaign(**selection)
                if apply and operation in {'execute', 'resume', 'replay'}:
                    service.execute_phase(options['job'], replay=operation == 'replay')
                elif apply and operation == 'pause':
                    with transaction.atomic():
                        for job in service.campaign_jobs(**selection):
                            set_job_state(job.pk, 'paused')
                report = service.report_campaign(**selection)
            report.update(operation=operation, applied=apply and operation not in {'inspect', 'report'})
            self.stdout.write(json.dumps(report, ensure_ascii=False))
        except (ValueError, TypeError, KeyError, CollectionJob.DoesNotExist,
                DataSource.DoesNotExist, MetricCollectionContract.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
