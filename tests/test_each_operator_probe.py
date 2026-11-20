"""Real-PostgreSQL proof that optimized Python cannot bypass operator gates."""
import os
import subprocess
import sys
from datetime import timedelta
from importlib import import_module
from urllib.parse import quote, urlsplit, urlunsplit

import pytest
from django.db import connection
from django.utils import timezone

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def _historical_fact():
    from core.models import Brand, Post, PostBrand

    brand = Brand.objects.create(nickname='operator-page-fixture')
    post = Post.objects.create(tweet_id='operator-page-fixture', created_at=timezone.now()-timedelta(days=5))
    PostBrand.objects.create(post=post, brand=brand)


def test_complete_parity_does_not_count_the_entire_live_source_in_one_statement(capsys):
    from core.models import Brand, Post, PostBrand
    from scripts.probes.each_dashboard_latency import prepare_materialization

    first = Brand.objects.create(nickname='operator-page-a')
    second = Brand.objects.create(nickname='operator-page-z')
    created_at = timezone.now()-timedelta(days=5)
    posts = [Post(tweet_id=f'000-{number:04}', created_at=created_at) for number in range(2047)]
    boundary = Post(tweet_id='zzz-page-boundary', created_at=created_at)
    Post.objects.bulk_create([*posts, boundary])
    PostBrand.objects.bulk_create([
        *[PostBrand(post=post, brand=first) for post in posts],
        PostBrand(post=boundary, brand=first),
        PostBrand(post=boundary, brand=second),
    ])

    def bounded(execute, sql, params, many, context):
        normalized = ' '.join(sql.lower().split())
        if normalized.startswith('select count(*) from each_brand_post_facts_source'):
            raise AssertionError('Whole-source count exceeds the measured production statement budget')
        return execute(sql, params, many, context)

    with connection.execute_wrapper(bounded):
        prepare_materialization()
    assert '"event": "parity", "rows_checked": 2049' in capsys.readouterr().out


@pytest.mark.parametrize('mutation', ['source_only_key', 'missing_oracle'])
def test_paged_parity_rejects_missing_and_extra_keys_against_the_live_oracle(mutation):
    from core.models import Post
    from scripts.probes.each_dashboard_latency import prepare_materialization

    _historical_fact()
    Post.objects.create(tweet_id='operator-oracle-only', created_at=timezone.now()-timedelta(days=5))
    columns = [name.strip() for name in import_module('core.migrations.0235_each_chart_facts').COLUMNS.split(',')]
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_viewdef('each_brand_post_facts_source'::regclass,true)")
        original = cursor.fetchone()[0].rstrip().rstrip(';')
        if mutation == 'source_only_key':
            projected = ','.join('extra.tweet_id AS post_id' if name == 'post_id' else f'base."{name}"' for name in columns)
            changed = f"({original}) UNION ALL (SELECT {projected} FROM ({original}) base CROSS JOIN posts extra WHERE extra.tweet_id='operator-oracle-only')"
        else:
            changed = f'SELECT * FROM ({original}) base WHERE FALSE'
        cursor.execute('CREATE OR REPLACE VIEW each_brand_post_facts_source AS '+changed)
    try:
        with pytest.raises(RuntimeError, match='(?i)parity'):
            prepare_materialization()
    finally:
        with connection.cursor() as cursor:
            cursor.execute('CREATE OR REPLACE VIEW each_brand_post_facts_source AS '+original)

def test_optimized_python_rejects_duplicate_source_facts():
    from core.models import Brand, Post, PostBrand
    # The child must use pytest's disposable database, never the original URL's database.
    database = connection.settings_dict["NAME"]
    assert database.startswith("test_")
    original_url = urlsplit(os.environ["DATABASE_URL"])
    child_url = urlunsplit(original_url._replace(path="/"+quote(database, safe="")))
    brand = Brand.objects.create(nickname="operator-gate-fixture")
    post = Post.objects.create(tweet_id="operator-gate-fixture", created_at=timezone.now()-timedelta(days=5))
    PostBrand.objects.create(post=post, brand=brand)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_viewdef('each_brand_post_facts_source'::regclass,true)")
        original = cursor.fetchone()[0].rstrip().rstrip(";")
        cursor.execute("CREATE OR REPLACE VIEW each_brand_post_facts_source AS ("+original+") UNION ALL ("+original+")")
    try:
        env = dict(os.environ, DATABASE_URL=child_url, DJANGO_SETTINGS_MODULE="project.settings", PYTHONDONTWRITEBYTECODE="1")
        command = "import django;django.setup();from scripts.probes.each_dashboard_latency import prepare_materialization;prepare_materialization()"
        completed = subprocess.run([sys.executable,"-O","-c",command],env=env,text=True,capture_output=True,timeout=30,check=False)
        assert completed.returncode != 0, "Optimized Python wrongly passed a source/cache count mismatch: "+completed.stdout
        assert '"event": "parity"' not in completed.stdout, completed.stdout
    finally:
        with connection.cursor() as cursor:
            cursor.execute("CREATE OR REPLACE VIEW each_brand_post_facts_source AS "+original)
