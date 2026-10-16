"""A login may assume a database role; job identity binds the real login."""

from copy import deepcopy
from uuid import uuid4

import pytest
from django.db import connection

from core.collection_jobs import register_job
from core.provider_batches import BatchAdmissionError, enrichment_control_status
from monitor.backfill_enrichment import execute_enrichment
from tests.test_backfill_direct_enrichment import DirectProvider, run_direct
from tests.test_backfill_native_enrichment import native as native_fixture

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
native = native_fixture


@pytest.fixture
def assumed_role(native):
    role = "pw_backfill_runtime_" + uuid4().hex
    quoted = connection.ops.quote_name(role)
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE ROLE {quoted} NOLOGIN")
        cursor.execute(f"GRANT pg_read_all_data, pg_write_all_data TO {quoted}")
        cursor.execute(f"SET ROLE {quoted}")
        cursor.execute("SELECT session_user,current_user")
        login, effective = cursor.fetchone()
    assert login != effective == role
    try:
        yield native, role
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP ROLE {quoted}")


def test_controls_accept_the_frozen_authenticated_login(assumed_role):
    fixture, _role = assumed_role
    result = enrichment_control_status(fixture[0].pk)
    assert result["processing_paused"] is False


def test_read_only_enrichment_accepts_a_legitimate_assumed_role(assumed_role):
    fixture, _role = assumed_role
    job, cfg, delegates, _policy = fixture
    result = execute_enrichment(job.pk, cfg=cfg, api_key="test", delegates=delegates, read_only=True)
    assert result["cohort_count"] == 2 and result["pending_count"] == 2
    assert result["model_requests_sent"] == 0


def test_effective_role_cannot_impersonate_the_pinned_login(assumed_role):
    fixture, role = assumed_role
    job = fixture[0]
    definition = deepcopy(job.definition)
    definition["scope"]["database"]["user"] = role
    wrong = register_job(
        job_key=job.job_key + ":wrong-login", source=job.source, purpose=job.purpose,
        operation=job.operation, mode=job.mode, definition=definition,
    )
    with pytest.raises(BatchAdmissionError, match="database_identity_mismatch"):
        enrichment_control_status(wrong.pk)


def test_assumed_role_runs_actual_http_replay_and_canonical_publishers(assumed_role):
    fixture, _role = assumed_role
    provider = DirectProvider()
    for turn in range(15):
        result = run_direct(fixture, provider, initial=turn == 0)
        if result["status"] == "completed":
            break
    assert result["status"] == "completed"
    assert result["persisted_output_invalid_count"] == 0
    assert provider.sent == result["model_requests_sent"] > 0
