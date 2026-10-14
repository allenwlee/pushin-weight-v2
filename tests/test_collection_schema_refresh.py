"""Actual PostgreSQL dump, restore, migrate and scrub across both source schemas."""

import json
import os
import subprocess
import sys
import uuid
from dataclasses import replace
from getpass import getuser
from pathlib import Path
from urllib.parse import quote

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from scripts.staging_refresh.database import (
    CandidateProcessor,
    DumpArtifact,
    PsycopgSnapshotAdapter,
    ShadowCandidate,
    _libpq_environment,
)
from scripts.staging_refresh.policy import load_policy

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.mark.usefixtures("isolated_migration_database")
@pytest.mark.parametrize("legacy_source", [False, True])
def test_real_snapshot_restores_numeric_history_and_clears_catalog_work(
    tmp_path, legacy_source
):
    from core.benchmark_metric_store import persist_source
    from core.models import CollectionObservation, CollectionRun, CollectionScopeRun
    from tests.test_benchmark_download_persistence import configured, payload

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
    numeric = persist_source(
        configured(), "hf", "9" * 64, payload(downloads=4_000_000_000)
    )
    catalog = CollectionRun.objects.create(
        source_id="hf", purpose="catalog", status="pending", ingestion_key="8" * 64
    )
    scope = CollectionScopeRun.objects.create(
        run=catalog, scope_key="publisher", ownership={}
    )
    CollectionObservation.objects.create(
        run=catalog,
        scope_run=scope,
        source_identifier="publisher/model",
        resource_key="publisher/model",
        source_subject_kind="repository",
        observation_key="7" * 64,
    )
    jobs = []
    if not legacy_source:
        from core.collection_jobs import register_job, set_job_state
        from core.collection_state import claim_job
        from core.models import DataSource

        limits = {"requests": 5, "seconds": 60, "bytes": 100000, "items": 100}
        definition = {
            "version": 1,
            "scope": {},
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": limits,
        }
        metric_job = register_job(
            job_key="copied-numeric",
            source=numeric.source,
            purpose="metric",
            operation="collect_metrics",
            mode="manual",
            contract=numeric.contract,
            definition=definition,
        )
        numeric.job = metric_job
        numeric.save(update_fields=["job"])
        metric_job.last_attempt = metric_job.last_success = numeric
        metric_job.save()
        catalog_job = register_job(
            job_key="copied-catalog",
            source=numeric.source,
            purpose="catalog",
            operation="hf_catalog",
            mode="manual",
            definition=definition,
        )
        catalog.job = catalog_job
        catalog.save(update_fields=["job"])
        catalog_job.active_run = catalog_job.last_attempt = catalog
        catalog_job.save()
        xsource = DataSource.objects.get(pk="x")
        content_job = register_job(
            job_key="copied-content",
            source=xsource,
            purpose="content",
            operation="x_backfill",
            mode="historical",
            definition=definition,
        )
        set_job_state(content_job.pk, "ready")
        claim_job(content_job.pk, manual_authorized=True)
        jobs = [metric_job.pk, catalog_job.pk, content_job.pk]
    if legacy_source:
        MigrationExecutor(connection).migrate(
            [("core", "0079_original_content_physical_names")]
        )

    root = Path(__file__).resolve().parents[1]
    policy = load_policy(root / "config/staging_refresh.yaml")
    # This fixture has no harvested posts; all parity/FK/schema/scrub checks stay.
    policy = replace(
        policy, validation=replace(policy.validation, required_nonempty_tables=())
    )
    source_name = connection.settings_dict["NAME"]
    assert source_name.startswith("test_pw_migration_")
    user = quote(connection.settings_dict["USER"] or getuser(), safe="")
    password = connection.settings_dict["PASSWORD"]
    if password:
        user += ":" + quote(password, safe="")
    url = f"postgresql://{user}@{connection.settings_dict['HOST']}:{connection.settings_dict['PORT']}/{source_name}"
    adapter = PsycopgSnapshotAdapter(policy)
    destination = "test_pw_collection_refresh_" + uuid.uuid4().hex[:20]
    dump = tmp_path / "snapshot.dump"
    configured_bin = os.environ.get("PW_TEST_PG_BIN")
    homebrew_bin = Path("/opt/homebrew/opt/postgresql@18/bin")
    pg_bin = (
        Path(configured_bin)
        if configured_bin
        else (homebrew_bin if homebrew_bin.exists() else Path())
    )
    environment = _libpq_environment(url, require_tls=False)
    with adapter.exported_snapshot(url) as census:
        result = subprocess.run(
            [
                str(pg_bin / "pg_dump"),
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--schema=public",
                "--extension=pg_trgm",
                "--snapshot=" + census.snapshot_id,
                *(
                    "--exclude-table-data=public." + table
                    for table in sorted(policy.relations.source_excluded_tables)
                ),
                "--file=" + str(dump),
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    marker = policy.lifecycle.marker_prefix + ":" + json.dumps({"state": "building"})
    adapter.create_shadow(url, destination, marker)
    try:
        result = subprocess.run(
            [
                str(pg_bin / "pg_restore"),
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
                "--clean",
                "--if-exists",
                "--dbname=" + destination,
                str(dump),
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        candidate = ShadowCandidate(
            destination,
            marker,
            DumpArtifact(dump, "a" * 64, dump.stat().st_size, census),
        )
        processor = CandidateProcessor(
            policy=policy, target_url=url, adapter=adapter, python=sys.executable
        )
        result = processor.process(candidate)
        assert result.census.row_counts["collection_runs"] == 1
        assert result.census.row_counts["collection_observations"] == 1
        assert all(count == 0 for count in result.census.scrubbed_counts.values())
        import psycopg

        with (
            psycopg.connect(
                dbname=destination,
                host=connection.settings_dict["HOST"],
                port=connection.settings_dict["PORT"],
                user=connection.settings_dict["USER"],
                password=connection.settings_dict["PASSWORD"],
            ) as db,
            db.cursor() as cursor,
        ):
            cursor.execute("SELECT id FROM collection_runs")
            assert cursor.fetchone()[0] == numeric.pk
            cursor.execute("SELECT integer_value FROM metric_values")
            assert cursor.fetchone()[0] == 4_000_000_000
            if jobs:
                cursor.execute(
                    "SELECT state, active_run_id, last_attempt_id, last_success_id FROM collection_jobs WHERE id = %s",
                    [jobs[0]],
                )
                assert cursor.fetchone() == ("paused", None, numeric.pk, numeric.pk)
                cursor.execute(
                    "SELECT state, active_run_id, last_attempt_id, last_success_id FROM collection_jobs WHERE id = ANY(%s)",
                    [jobs[1:]],
                )
                assert all(
                    row == ("paused", None, None, None) for row in cursor.fetchall()
                )
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP DATABASE "{destination}"')
