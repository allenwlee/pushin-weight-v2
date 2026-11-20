"""The release probe rejects wrong windows and terminates a stalled handler."""
import os
import subprocess
import sys
from urllib.parse import quote, urlsplit, urlunsplit

import pytest
from django.core.management import call_command
from django.db import connection

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def _environment():
    database = connection.settings_dict['NAME']
    assert database.startswith('test_')
    original = urlsplit(os.environ['DATABASE_URL'])
    return dict(os.environ, DATABASE_URL=urlunsplit(original._replace(path='/'+quote(database, safe=''))),
                DJANGO_SETTINGS_MODULE='project.settings', PYTHONDONTWRITEBYTECODE='1')


def test_operator_rejects_actual_route_returning_a_different_window():
    from django.utils import timezone

    from core.models import Brand, Post, PostBrand

    call_command('seed_i18n_labels', verbosity=0)
    brand = Brand.objects.create(nickname='deepseek', display_name='DeepSeek')
    post = Post.objects.create(tweet_id='each-operator-window', created_at=timezone.now(), lang='en')
    PostBrand.objects.create(post=post, brand=brand)
    command = '''
import sys,django
django.setup()
from monitor import views
views._resolve_home_window=lambda request:7
from scripts.probes.each_dashboard_latency import main
sys.argv=['probe','--rounds','1','--brands','deepseek','--windows','30']
raise SystemExit(main())
'''
    result = subprocess.run([sys.executable, '-c', command], env=_environment(),
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode != 0, result.stdout
    assert '"reason": "chart_latency_or_response"' in result.stdout, result.stdout+result.stderr


def test_operator_shutdown_does_not_wait_for_a_stalled_read_only_handler():
    command = '''
import sys,django
from threading import Event
django.setup()
from django.core import wsgi
def stalled(environ,start_response):
    Event().wait(30)
    start_response('200 OK',[('Content-Type','application/json')])
    return [b'{}']
wsgi.get_wsgi_application=lambda:stalled
from scripts.probes import each_dashboard_latency as probe
real_urlopen=probe.urlopen
probe.urlopen=lambda request,timeout:real_urlopen(request,timeout=.1)
sys.argv=['probe','--rounds','1','--brands','deepseek','--windows','7']
raise SystemExit(probe.main())
'''
    try:
        result = subprocess.run([sys.executable, '-c', command], env=_environment(),
                                capture_output=True, text=True, timeout=4, check=False)
    except subprocess.TimeoutExpired:
        pytest.fail('Operator shutdown waited for a stalled local HTTP handler')
    assert result.returncode != 0, result.stdout+result.stderr
    assert '"reason": "chart_latency_or_response"' in result.stdout
    assert '"reason": "operator_shutdown_timeout"' in result.stdout
