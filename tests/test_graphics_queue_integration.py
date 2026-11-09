"""Opt-in, local Redis/Celery integration; never makes provider requests."""
import os
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest
from django.db import connection
from django.utils import timezone

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]

WORKER = '''
import os, time
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')
import django
django.setup()
from core.models import OriginalContentRun
from monitor.editorial import graphics_dispatch, graphics_pipeline
from monitor.editorial.graphics_packages import claim_package, release_package
from django.db import transaction
from project.celery import app

graphics_dispatch.RECOVERY_INTERVAL = 2

def fake_advance(run_id):
    owner = 'probe-' + str(os.getpid())
    claim = claim_package(run_id, owner=owner, lease_seconds=15)
    if claim is None:
        with transaction.atomic():
            run = OriginalContentRun.objects.select_for_update().get(pk=run_id)
            if run.execution_state == 'running':
                outcome = dict(run.outcome)
                outcome['overlap_worker'] = owner
                run.outcome = outcome
                run.save(update_fields=['outcome'])
        return {'state': 'busy', 'next_action': None}
    try:
        time.sleep(5)
        with transaction.atomic():
            run = OriginalContentRun.objects.select_for_update().get(pk=run_id)
            outcome = dict(run.outcome)
            outcome['probe_completions'] = outcome.get('probe_completions', 0) + 1
            outcome['probe_worker'] = owner
            run.outcome = outcome
            run.save(update_fields=['outcome'])
    finally:
        release_package(run_id, owner=owner, fence=claim.fence)
    OriginalContentRun.objects.filter(pk=run_id).update(execution_state='complete')
    return {'state': 'done', 'next_action': None}

def fake_pending(run_id):
    run = OriginalContentRun.objects.get(pk=run_id)
    return {'action': 'advance'} if run.scope_key.startswith('queue-probe-') else None

graphics_pipeline.advance_step = fake_advance
graphics_pipeline.pending_action = fake_pending
graphics_pipeline.finalize_if_done = lambda run_id: False
app.worker_main(['worker', '-Q', 'graphics-creation', '--pool=solo', '--concurrency=1',
                 '--prefetch-multiplier=1', '--without-gossip', '--without-mingle',
                 '--without-heartbeat', '-l', 'INFO', '-n', 'probe-' + str(os.getpid())])
'''


def wait_until(predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.2)
    raise AssertionError('timed out waiting for Graphics queue integration')


@pytest.mark.skipif(os.getenv('GRAPHICS_QUEUE_INTEGRATION') != '1', reason='opt-in real worker test')
def test_two_workers_overlap_and_recover_after_broker_restart(tmp_path, monkeypatch):
    from celery import Celery

    from core.models import OriginalContentRun

    producer = None

    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    broker_url = f'redis://127.0.0.1:{port}/0'
    db_url = urlsplit(os.environ['DATABASE_URL'])
    assert connection.settings_dict['NAME'].startswith('test_pw_graphics_')
    test_db_url = urlunsplit((db_url.scheme, db_url.netloc, '/' + connection.settings_dict['NAME'], db_url.query, db_url.fragment))
    env = {**os.environ, 'DATABASE_URL': test_db_url, 'CELERY_BROKER_URL': broker_url,
           'CELERY_RESULT_BACKEND': broker_url, 'GRAPHICS_RECONCILER_ENABLED': 'True',
           'GRAPHICS_REQUIRE_SHARED_MEDIA': 'False', 'OPENROUTER_API_KEY': '', 'XAI_API_KEY_PW': '',
           'PYTHONPATH': os.getcwd()}
    script = tmp_path / 'queue_worker.py'
    script.write_text(WORKER)
    log = (tmp_path / 'workers.log').open('w+')
    processes = []
    def start_redis():
        return subprocess.Popen(['redis-server', '--port', str(port), '--bind', '127.0.0.1',
                                 '--save', '', '--appendonly', 'no'], stdout=log, stderr=log)
    def redis_ready():
        return subprocess.run(['redis-cli', '-p', str(port), 'ping'], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, check=False).returncode == 0
    def make_run():
        return OriginalContentRun.objects.create(source_cycle_id=str(uuid4()), workflow_key='graphics-package',
            scope_key='queue-probe-' + str(uuid4()), facts_as_of=timezone.now(), packet_schema_version=1,
            snapshot={}, execution_state='pending')
    try:
        redis = start_redis()
        wait_until(redis_ready)
        for _ in range(2):
            processes.append(subprocess.Popen([sys.executable, str(script)], env=env, stdout=log, stderr=log,
                                              cwd=os.getcwd()))
        # Wait for both consumers and their initial empty recovery scans.
        wait_until(lambda: (tmp_path / 'workers.log').read_text().count(' ready.') >= 2)
        assert all(p.poll() is None for p in processes), 'worker exited; see worker log'
        producer = Celery('graphics-test-producer', broker=broker_url)
        def dispatch_creation(*, run_id):
            producer.send_task('monitor.tasks.advance_graphics_package', args=[run_id],
                               queue='graphics-creation', retry=False)
            return True
        first = make_run()
        assert dispatch_creation(run_id=first.pk)
        def running():
            first.refresh_from_db()
            return first.execution_state == 'running'
        wait_until(running)
        for _ in range(4):
            assert dispatch_creation(run_id=first.pk)
        def completed(run):
            run.refresh_from_db()
            return run.execution_state == 'complete'
        wait_until(lambda: completed(first))
        time.sleep(3)
        first.refresh_from_db()
        assert first.outcome['probe_completions'] == 1
        assert first.outcome['overlap_worker'] != first.outcome['probe_worker']
        redis.terminate()
        redis.wait(timeout=5)
        second = make_run()
        time.sleep(3)
        redis = start_redis()
        wait_until(redis_ready)
        wait_until(lambda: completed(second), timeout=35)
        assert second.outcome['probe_completions'] == 1
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if 'redis' in locals() and redis.poll() is None:
            redis.terminate()
            redis.wait(timeout=5)
        if producer is not None:
            producer.close()
        log.close()
