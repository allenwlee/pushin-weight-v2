"""Real-PostgreSQL proof that optimized Python cannot bypass operator gates."""
import os
import subprocess
import sys
from datetime import timedelta
from urllib.parse import quote, urlsplit, urlunsplit

import pytest
from django.db import connection
from django.utils import timezone

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]

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
