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
    from core.collection_capture import read_document

    assert read_document(run.source_metadata_archive)["location"] == "PRIVATE-GEO-SENTINEL"
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
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute("SELECT body FROM collection_evidence_archives")
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
                           "AS SELECT id,body FROM collection_evidence_archives")
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


@pytest.mark.parametrize("source", ["hf", "arena", "openrouter", "opencode"])
@override_settings(BENCHMARK_METRICS_ENABLED=True, SECURE_SSL_REDIRECT=False)
def test_source_routes_forecasts_and_exports_need_no_retiring_columns(source, serving_login, client):
    """Exercise real consumers after removing every old collection-column grant."""
    import json
    from io import StringIO

    from django.core.management import call_command
    from django.db import connection
    from django.utils import timezone
    from psycopg import sql

    from core.benchmark_forecast_inputs import forecast_inputs
    from core.benchmark_metric_identity import configure_collection
    from core.benchmark_metric_store import persist_source
    from tests.test_benchmark_download_db_identity import setup_spec
    from tests.test_benchmark_download_persistence import payload
    from tests.test_benchmark_opencode import SELECTED, endpoint, read

    _, spec = setup_spec()
    mapping = spec["mappings"][0]
    metrics, day, expected = ["downloads"], timezone.now().date().isoformat(), "10"
    data = payload()
    if source != "hf":
        mapping.update(source=source, source_subject_kind="model", identifier_scope="", external_identifier="lab/model")
    if source == "arena":
        metrics, day, expected = ["rating", "rating_lower", "rating_upper", "rank"], "2026-09-25", 1400.0
        data = {"status": "ok", "config": "text_style_control", "coverage": "latest_publication_only",
                "rows": [{"model_name": "lab/model", "category": "overall", "leaderboard_publish_date": day,
                          "rating": 1400.0, "rating_lower": 1390.0, "rating_upper": 1410.0, "rank": 10.0}]}
    elif source == "openrouter":
        metrics, day, expected = ["total_tokens"], "2026-10-05", "9007199254740993123"
        data = {"status": "ok", "meta": {"version": "v1"}, "as_of": "2026-10-06T00:30:00Z",
                "rows": [{"date": day, "model_permaslug": "lab/model", "total_tokens": expected}]}
    elif source == "opencode":
        metrics, day, expected = ["tokens", "unique_users", "sessions"], "2026-10-06", "9007199254740993123"
        mapping.update(external_identifier=SELECTED[0]["external_identifier"],
                       identifier_metadata={"endpoint_path": SELECTED[0]["endpoint_path"]},
                       evidence_url="https://opencode.ai/data/deepseek/deepseek-v4-1-flash.json")
        data = read(endpoint())
    spec["source_configuration"] = {source: {"metrics": metrics}}
    spec["methodology"]["comparisons"] = {"fixture": {
        "title": "Fixture product",
        "launch_anchor": {"product_subject_id": mapping["subject_id"], "announced_date": day,
                          "precision": "date", "source_url": "https://example.org/launch",
                          "event_kind": "announcement", "source_timezone": "unknown", "reviewed_by": "fixture"},
        "lines": [{"key": metrics[0], "label": "Fixture measurement", "source": source,
                   "subject_id": mapping["subject_id"], "metric_key": metrics[0],
                   "mapping_identifiers": [mapping["external_identifier"]],
                   "aggregation": "single", "baseline": "launch"}],
    }}
    contract = configure_collection(spec)
    run = persist_source(contract, source, "b" * 64, data)
    cutoff = timezone.now()
    serving, role, _owner, _report = serving_login
    retired = {
        "collection_runs": {"request_params", "source_metadata", "raw_payload", "invocations", "report"},
        "collection_observations": {"dimensions", "source_metadata", "listing", "envelopes", "groups"},
    }
    with connection.cursor() as cursor:
        for table, candidates in retired.items():
            cursor.execute("SELECT attname FROM pg_attribute WHERE attrelid=%s::regclass "
                           "AND attnum>0 AND NOT attisdropped AND attname=ANY(%s)", [table, list(candidates)])
            columns = [row[0] for row in cursor.fetchall()]
            if columns:
                cursor.execute(sql.SQL("REVOKE SELECT ({}) ON {} FROM {}").format(
                    sql.SQL(",").join(map(sql.Identifier, columns)), sql.Identifier(table), sql.Identifier(role)))
    with patch.object(connections["default"], "connection", serving):
        for locale in ("en", "ja", "zh-cn"):
            for route in ("benchmark_pulse", "benchmark_series"):
                response = client.get(reverse(route, args=[contract.pk, "fixture"]),
                                      {"start": day, "end": day, "lang": locale})
                assert response.status_code == 200, response.content
                if route == "benchmark_series":
                    assert response.json()["lines"][0]["points"][0]["raw_value"] == expected
        forecast = forecast_inputs(contract, cutoff, use="isolated_review", isolated_review=True)
        assert {row["run_id"] for row in forecast["values"]} == {str(run.pk)}
        assert any(row["metric"] == metrics[0] and row["value"] == expected for row in forecast["values"])
        if source == "opencode":
            output = StringIO()
            call_command("benchmark_opencode_snapshots", contract=str(contract.pk),
                         start_date=day, end_date=day, stdout=output)
            rows = json.loads(output.getvalue())["rows"]
            assert rows[0]["period_status"] == "completed"
            assert next(value for value in rows[0]["values"] if value["metric"] == "tokens")["value"] == expected
