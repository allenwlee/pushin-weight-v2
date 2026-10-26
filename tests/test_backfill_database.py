"""Moving storage must preserve frozen instructions and every paid receipt."""

import copy
import hashlib
import json

import pytest
from django.conf import settings
from django.db import connection

from core.collection_jobs import register_job, set_job_state
from core.measurement_taxonomy import digest
from core.models import CollectionRequest, Post
from monitor.backfill_collection import execute_job
from tests.test_backfill_native_enrichment import native as native_fixture
from tests.test_backfill_prefetch import (
    http_pages as http_pages_fixture,
)
from tests.test_backfill_prefetch import (
    job_for_scopes,
)
from tests.test_backfill_prefetch import pipeline as pipeline_fixture
from tests.test_backfill_staging import result_for

native = native_fixture
http_pages = http_pages_fixture
pipeline = pipeline_fixture

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def verified_destination(monkeypatch):
    # The transfer tests exercise the commit marker; runtime tests use the
    # shared DB and must not alter its database-level comment.
    monkeypatch.setattr(
        "monitor.backfill_database.copy_verified", lambda sha: sha == "a" * 64
    )


def receipt_for(job, tmp_path):
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database(),session_user")
        name, user = cursor.fetchone()
    value = {
        "format": "x-backfill-database-relocation/v1",
        "source": {
            "name": "former_backfill",
            "user": "former_writer",
            "hosts": ["former-host"],
        },
        "destination": {
            "name": name,
            "user": user,
            "hosts": [settings.DATABASES["default"]["HOST"]],
        },
        "verified": True,
        "snapshot_sha256": "a" * 64,
        "definitions": [job.definition_sha256],
        "scopes": [digest(job.scope)],
        "manifests": [],
    }
    body = json.dumps(value, sort_keys=True).encode()
    path = tmp_path / "move.json"
    path.write_bytes(body)
    return path, hashlib.sha256(body).hexdigest()


def moved_job(seed=None):
    seed = seed or job_for_scopes(1)
    definition = copy.deepcopy(seed.definition)
    definition["scope"].update(
        database={"name": "former_backfill", "user": "former_writer"},
        response_storage="staging",
        staging_host="former-host",
    )
    job = register_job(
        job_key="moved-job",
        source=seed.source,
        purpose="content",
        operation="x_backfill",
        mode="historical",
        definition=definition,
    )
    return set_job_state(job.pk, "ready")


def test_moved_job_still_rejects_ordinary_execution(monkeypatch):
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "backfill")
    job = moved_job()
    with pytest.raises(ValueError, match="database identity changed"):
        execute_job(job.pk)
    assert not CollectionRequest.objects.exists()


def test_relocated_enrichment_publishes_and_reuses_without_x(
    native, monkeypatch, tmp_path
):
    from core.models import CollectionRun, PostEnrichmentState
    from monitor.backfill_database import relocated_database
    from tests.test_backfill_direct_enrichment import DirectProvider, run_direct

    seed, cfg, delegates, policy = native
    job = moved_job(seed)
    CollectionRun.objects.filter(job=seed).update(job=job)
    PostEnrichmentState.objects.filter(source_collection_job=seed).update(
        source_collection_job=job
    )
    native = job, cfg, delegates, policy
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "backfill")
    path, signature = receipt_for(job, tmp_path)
    provider = DirectProvider()
    with relocated_database(path, signature):
        for turn in range(15):
            result = run_direct(native, provider, initial=turn == 0)
            if result["status"] == "completed":
                break
        assert result["status"] == "completed", result
        assert result["twitterapi_requests"] == 0
        assert result["persisted_output_invalid_count"] == 0
        sent = provider.sent
        assert run_direct(native, provider)["status"] == "completed"
        assert provider.sent == sent


def test_explicit_relocation_resumes_same_job_without_repeating_pages(
    http_pages, monkeypatch, tmp_path
):
    from monitor.backfill_database import relocated_database

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "backfill")
    job = moved_job()
    original = copy.deepcopy(job.definition)
    path, signature = receipt_for(job, tmp_path)
    with relocated_database(path, signature), http_pages(result_for) as state:
        result = execute_job(job.pk, collection_options={"concurrency": 20})
        assert result["collection_drained"]
        assert execute_job(job.pk)["state"] == "completed"
    assert len(state["requests"]) == 1
    assert Post.objects.count() == 1
    job.refresh_from_db()
    assert job.definition == original
    assert job.last_attempt.report["database_relocation"]["receipt_sha256"] == signature
    with pytest.raises(ValueError, match="database identity changed"):
        execute_job(job.pk)


@pytest.mark.parametrize(
    "change",
    [
        "digest",
        "destination",
        "definition",
        "verified",
        "unknown",
        "environment",
        "copy",
    ],
)
def test_relocation_rejects_unapproved_bindings(change, monkeypatch, tmp_path):
    from monitor.backfill_database import relocated_database

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "backfill")
    job = moved_job()
    path, signature = receipt_for(job, tmp_path)
    value = json.loads(path.read_text())
    if change == "destination":
        value["destination"]["hosts"] = ["wrong-host"]
    elif change == "definition":
        value["definitions"] = ["b" * 64]
    elif change == "verified":
        value["verified"] = False
    elif change == "unknown":
        value["allow_any_database"] = True
    elif change == "environment":
        monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    elif change == "copy":
        value["snapshot_sha256"] = "b" * 64
    body = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(body)
    signature = "c" * 64 if change == "digest" else hashlib.sha256(body).hexdigest()
    with pytest.raises(ValueError), relocated_database(path, signature):
        execute_job(job.pk)
    assert not CollectionRequest.objects.exists()


@pytest.mark.parametrize('wrong', [None, 'environment', 'host', 'database', 'user'])
def test_dedicated_mode_requires_its_actual_database(monkeypatch, wrong):
    from monitor.backfill_staging import validate_staging
    from scripts.backfill_month import execution_options

    actual = {'name': 'xbackfiller', 'user': 'xbackfiller', 'host': 'dedicated-host'}
    scope = {'response_storage': 'database', 'database_host': 'dedicated-host'}
    monkeypatch.setenv('X_MONITOR_DEPLOYMENT_ENVIRONMENT', 'backfill')
    if wrong == 'environment':
        monkeypatch.setenv('X_MONITOR_DEPLOYMENT_ENVIRONMENT', 'production')
    elif wrong == 'database':
        actual['name'] = 'production'
    elif wrong == 'user':
        actual['user'] = 'someone_else'
    elif wrong == 'host':
        scope['database_host'] = 'wrong-host'
    monkeypatch.setattr('monitor.backfill_database.identity', lambda: actual)
    if wrong:
        with pytest.raises(ValueError, match='dedicated backfill database required'):
            validate_staging(scope)
    else:
        validate_staging(scope)
        frozen = {'direct_concurrency': 32, 'windows': [{'collection_definition': {'scope': scope}}]}
        assert execution_options(frozen, phase='enrich')['enrichment_concurrency'] == 8
