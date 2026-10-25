"""Typed serving queries agree with the published JSON-backed scalar views."""

import pytest
from django.db import connection

from core.migrations._benchmark_serving_v2 import VIEWS

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def _rows(view_name, query, run_id):
    order = "1,2,4" if view_name == "benchmark_endpoint_revisions" else "1,2"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM " + view_name + " WHERE "
            + ("id" if view_name == "benchmark_observation_provenance" else "run_id")
            + " = %s ORDER BY " + order,
            [run_id],
        )
        old = cursor.fetchall()
        key = "id" if view_name == "benchmark_observation_provenance" else "run_id"
        cursor.execute(
            "SELECT * FROM (" + query + ") typed WHERE " + key
            + " = %s ORDER BY " + order,
            [run_id],
        )
        return old, cursor.fetchall()


def test_arena_publication_dates_match_when_no_model_is_selected():
    from core.benchmark_metric_store import persist_source
    from core.measurement_taxonomy import digest
    from tests.test_benchmark_download_persistence import provider_contract

    contract = provider_contract(
        "arena", ["rating", "rating_lower", "rating_upper", "rank"]
    )
    run = persist_source(
        contract, "arena", digest("rg6-publication-view"),
        {"status": "ok", "config": "text_style_control",
         "coverage": "publication_window", "rows": []},
        source_metadata={"publication_dates": ["2026-09-27"]},
    )
    old, typed = _rows(
        "benchmark_publication_dates",
        VIEWS["benchmark_publication_dates"],
        run.pk,
    )
    assert old == typed and len(typed) == 1


def test_opencode_endpoint_rows_match_with_typed_links():
    from core.benchmark_metric_store import persist_source
    from tests.test_benchmark_opencode import configured, endpoint, read

    contract = configured()
    run = persist_source(contract, "opencode", "e" * 64, read(endpoint()))
    old, typed = _rows(
        "benchmark_endpoint_revisions",
        VIEWS["benchmark_endpoint_revisions"],
        run.pk,
    )
    assert old == typed and len(typed) == 2


def test_observation_provenance_matches_after_bounded_projection():
    from core.benchmark_metric_store import persist_source
    from core.collection_storage_migration import (
        project_benchmark_provenance_batch,
        project_run_ingestion_mode,
    )
    from core.measurement_taxonomy import digest
    from core.models import CollectionObservation
    from tests.test_benchmark_download_persistence import provider_contract

    contract = provider_contract(
        "arena", ["rating", "rating_lower", "rating_upper", "rank"]
    )
    run = persist_source(
        contract, "arena", digest("rg6-provenance-view"),
        {"status": "ok", "config": "text_style_control",
         "coverage": "publication_window", "rows": []},
        source_metadata={"publication_dates": ["2026-09-27"], "ingestion_mode": "direct"},
    )
    observation = CollectionObservation.objects.create(
        run=run, source_identifier="history", source_subject_kind="aggregate",
        observation_key="a" * 64,
        source_metadata={
            "history_basis": "reconstructed_current_relationships",
            "secondary_source": True, "publication_complete": False,
            "archive_snapshot_date": "2026-09-26",
            "reconstruction_date": "2026-09-27", "period_status": "partial",
        },
    )
    project_run_ingestion_mode()
    project_benchmark_provenance_batch(after_id=observation.pk - 1)
    old, typed = _rows(
        "benchmark_observation_provenance",
        VIEWS["benchmark_observation_provenance"],
        observation.pk,
    )
    assert old == typed and len(typed) == 1
