"""Exercise real chart routes with a separate, restricted PostgreSQL login."""

from unittest.mock import patch

import psycopg
import pytest
from django.db import connections, transaction
from django.test import override_settings
from django.urls import reverse

from tests.test_geolocation_access import serving_login  # noqa: F401

# ruff: noqa: F811

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@override_settings(BENCHMARK_METRICS_ENABLED=True, SECURE_SSL_REDIRECT=False)
def test_populated_chart_and_series_keep_source_documents_private(serving_login, client):
    from core.benchmark_metric_store import persist_source
    from tests.test_benchmark_download_persistence import payload
    from tests.test_benchmark_pulse_views import comparison

    contract = comparison()
    data = payload()
    data["rows"][0]["_source_metadata"] = {"location": "PRIVATE-GEO-SENTINEL"}
    run = persist_source(contract, "hf", "d" * 64, data,
                         source_metadata={"location": "PRIVATE-GEO-SENTINEL", "ingestion_mode": "direct"})
    assert run.source_metadata["location"] == "PRIVATE-GEO-SENTINEL"
    assert run.observations.get().source_metadata["location"] == "PRIVATE-GEO-SENTINEL"
    day = run.observed_at.date().isoformat()
    serving, _role, _owner, _report = serving_login
    with patch.object(connections["default"], "connection", serving):
        for locale in ("en", "ja", "zh-cn"):
            for route in ("benchmark_pulse", "benchmark_series"):
                response = client.get(reverse(route, args=[contract.pk, "fixture"]),
                                      {"end": day, "lang": locale})
                assert response.status_code == 200
                assert b"PRIVATE-GEO-SENTINEL" not in response.content
                if route == "benchmark_series":
                    assert any(point.get("raw_value") == "10"
                               for point in response.json()["lines"][0]["points"])
    with serving.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
                       "WHERE c.relname=ANY(%s) AND a.attnum>0 AND NOT a.attisdropped "
                       "AND a.atttypid IN ('json'::regtype,'jsonb'::regtype)",
                       [["benchmark_observation_provenance", "benchmark_publication_dates", "benchmark_endpoint_revisions"]])
        assert cursor.fetchone() == (0,)
        for table in ("collection_observations", "collection_runs"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute(f"SELECT source_metadata FROM {table}")
        cursor.execute("SELECT has_table_privilege(current_user,'benchmark_observation_provenance','UPDATE')")
        assert cursor.fetchone() == (False,)
        with pytest.raises((psycopg.errors.InsufficientPrivilege, psycopg.errors.ObjectNotInPrerequisiteState)):
            cursor.execute("UPDATE benchmark_observation_provenance SET reconstructed=true")


def test_grants_reject_same_named_view_exposing_raw_evidence(serving_login):
    from django.db import connection

    from core.geolocation_access import apply_serving_grants

    _serving, role, _owner, _report = serving_login
    with pytest.raises(ValueError, match="Unreviewed benchmark"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("DROP VIEW benchmark_observation_provenance")
            cursor.execute("CREATE VIEW benchmark_observation_provenance WITH (security_barrier=true) "
                           "AS SELECT id,source_metadata FROM collection_observations")
        apply_serving_grants(connection, role)


def test_restricted_opencode_selection_retains_latest_revision(serving_login):
    from core.benchmark_metric_operations import collection_health
    from core.benchmark_metric_store import persist_source
    from core.benchmark_opencode import selected_rows
    from tests.test_benchmark_opencode import configured, endpoint, read

    contract = configured()
    persist_source(contract, "opencode", "1" * 64, read(endpoint()))
    persist_source(contract, "opencode", "2" * 64,
                   read(endpoint(tokens=10, updated="2026-10-07T13:00:18Z")))
    mappings = list(contract.mappings.values_list("pk", flat=True))
    expected = selected_rows(contract, mappings, "2026-10-06", "2026-10-07")
    expected_health = collection_health(contract)["opencode"]["publication_updated_at"]
    serving, _role, _owner, _report = serving_login
    with patch.object(connections["default"], "connection", serving):
        actual = selected_rows(contract, mappings, "2026-10-06", "2026-10-07", canonical=True)
        assert actual.keys() == expected.keys()
        for key, row in actual.items():
            assert row["observation_id"] == expected[key]["observation_id"]
            assert row["revision"] == expected[key]["revision"]
            assert row["check_run_id"] == expected[key]["check_run_id"]
        assert collection_health(contract)["opencode"]["publication_updated_at"] == expected_health
