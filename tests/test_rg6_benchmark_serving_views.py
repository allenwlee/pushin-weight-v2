"""Independent expected results for the typed benchmark cutover queries."""

from datetime import UTC, date, datetime

import pytest
from django.db import connection

from core.collection_capture import archive_legacy
from core.migrations._benchmark_serving_v3 import VIEWS

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


def _typed(view_name, owner_id):
    return _rows(view_name, VIEWS[view_name], owner_id)[1]


def _install_typed_views():
    # These tests run inside pytest's rollback transaction. The shared database
    # stays on its deployed migration/view version when each test finishes.
    with connection.cursor() as cursor:
        for name, query in VIEWS.items():
            cursor.execute(f"CREATE OR REPLACE VIEW {name} WITH (security_barrier=true) AS {query}")


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
    assert typed == [(run.pk, date(2026, 9, 27))]
    from core.models import CollectionObservation

    marker = run.observations.get()
    CollectionObservation.objects.create(
        run=run, source_identifier="arena:duplicate-publication", source_subject_kind="aggregate",
        observation_key="b" * 64, published_date=marker.published_date,
        publication_precision="date", observation_kind="publication_marker",
        publication_complete=True,
    )
    assert _typed("benchmark_publication_dates", run.pk) == typed
    assert not hasattr(marker, "source_metadata")
    assert _typed("benchmark_publication_dates", run.pk) == typed
    run.observations.update(publication_complete=False)
    assert _typed("benchmark_publication_dates", run.pk) == []


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
    assert {row[3] for row in typed} == {date(2026, 10, 6), date(2026, 10, 7)}
    assert all(row[5] == datetime(2026, 10, 7, 12, 44, 18, tzinfo=UTC) for row in typed)
    assert all(row[7] is None for row in typed)
    assert all(not hasattr(row, "dimensions") for row in run.observations.all())
    assert _typed("benchmark_endpoint_revisions", run.pk) == typed


def test_observation_provenance_matches_retained_capture_projection():
    from core.benchmark_metric_store import persist_source
    from core.collection_resources import project_observation_facts
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
        legacy_archive=archive_legacy({"listing": {}, "dimensions": {},
                                     "envelopes": [], "groups": {}, "source_metadata": {
            "history_basis": "reconstructed_current_relationships",
            "secondary_source": True, "publication_complete": False,
            "archive_snapshot_date": "2026-09-26",
            "reconstruction_date": "2026-09-27", "period_status": "partial",
        }}),
    )
    project_observation_facts(observation)
    old, typed = _rows(
        "benchmark_observation_provenance",
        VIEWS["benchmark_observation_provenance"],
        observation.pk,
    )
    assert old == typed and len(typed) == 1
    assert typed == [(observation.pk, True, True, date(2026, 9, 26), date(2026, 9, 27), False, True, True)]


@pytest.mark.parametrize("flag", [None, False, True])
def test_typed_provenance_keeps_unknown_distinct_from_false(flag):
    from core.benchmark_metric_store import persist_source
    from core.models import CollectionObservation, CollectionRun
    from tests.test_benchmark_download_persistence import configured, payload

    run = persist_source(configured(), "hf", "d" * 64, payload())
    observation = run.observations.get()
    CollectionRun.objects.filter(pk=run.pk).update(direct_ingestion=flag)
    CollectionObservation.objects.filter(pk=observation.pk).update(
        history_reconstructed=flag, secondary_source=flag, publication_complete=flag,
        period_status=None if flag is None else ("partial" if flag else "completed"),
        archive_snapshot_date=None, reconstruction_date=None,
        # Retained historical evidence cannot override authoritative typed facts.
        legacy_archive=archive_legacy({"listing": {}, "dimensions": {},
                                     "envelopes": [], "groups": {}, "source_metadata": {
            "history_basis": "reconstructed_current_relationships",
            "archive_snapshot_date": "2026-02-31", "secondary_source": True,
        }}),
    )
    assert _typed("benchmark_observation_provenance", observation.pk) == [
        (observation.pk, flag, flag, None, None, flag, flag, flag)
    ]
    from core.benchmark_serving import observation_provenance_metadata

    _install_typed_views()
    observation.refresh_from_db()
    observation.run.refresh_from_db()
    metadata = observation_provenance_metadata(observation)
    assert metadata.get("secondary_source") is flag
    assert metadata.get("publication_complete") is flag
    assert metadata.get("period_status") == (
        None if flag is None else "partial" if flag else "completed"
    )
    assert observation.run.direct_ingestion is flag


@pytest.mark.parametrize("body_hash", [None, "invalid", "A" * 64, "a" * 63])
def test_endpoint_invalid_digest_stays_unknown(body_hash):
    from core.benchmark_metric_store import persist_source
    from tests.test_benchmark_opencode import configured, endpoint, read

    run = persist_source(configured(), "opencode", "d" * 64, read(endpoint()))
    run.observations.filter(observation_kind="endpoint_check").update(payload_sha256=body_hash)
    rows = _typed("benchmark_endpoint_revisions", run.pk)
    assert len(rows) == 2
    assert all(row[6] is None for row in rows)


@pytest.mark.parametrize("fault", [
    "marker_identifier", "marker_mapping", "marker_status", "row_identifier",
    "row_mapping", "row_status", "row_date", "link_date",
])
def test_endpoint_excludes_unqualified_or_mismatched_input_edges(fault):
    from core.benchmark_metric_store import persist_source
    from core.models import CollectionObservation, CollectionObservationInput
    from tests.test_benchmark_opencode import configured, endpoint, read

    run = persist_source(configured(), "opencode", "d" * 64, read(endpoint()))
    marker = run.observations.get(observation_kind="endpoint_check")
    link = CollectionObservationInput.objects.filter(
        observation=marker, input_role="endpoint_revision_row"
    ).order_by("row_locator").first()
    changes = {
        "identifier": {"source_identifier": "another/model"},
        "mapping": {"mapping_id": None},
        "status": {"status": "error", "error_code": "source_failed"},
        "date": {"source_record_date": None},
    }
    owner, _, attribute = fault.partition("_")
    if owner == "link":
        CollectionObservationInput.objects.filter(pk=link.pk).update(row_locator="2026-10-05")
    else:
        key = marker.pk if owner == "marker" else link.input_observation_id
        CollectionObservation.objects.filter(pk=key).update(**changes[attribute])
    rows = _typed("benchmark_endpoint_revisions", run.pk)
    assert len(rows) == (0 if owner == "marker" else 1)
    assert all(row[4] != link.input_observation_id for row in rows)


@pytest.mark.parametrize("source,purpose", [("hf", "metric"), ("opencode", "catalog")])
def test_endpoint_reused_row_must_belong_to_the_measurement_source(source, purpose):
    from core.benchmark_metric_store import persist_source
    from core.models import CollectionRun
    from tests.collection_fixtures import evidence_job
    from tests.test_benchmark_opencode import configured, endpoint, read

    contract = configured()
    first = persist_source(contract, "opencode", "1" * 64, read(endpoint()))
    second = persist_source(contract, "opencode", "2" * 64, read(endpoint(updated="2026-10-07T12:59:18Z")))
    assert {row[4] for row in _typed("benchmark_endpoint_revisions", second.pk)} <= set(first.observations.values_list("pk", flat=True))
    job = evidence_job(source_id=source, purpose=purpose,
                       contract_id=contract.pk if purpose == "metric" else None)
    CollectionRun.objects.filter(pk=first.pk).update(job=job)
    assert _typed("benchmark_endpoint_revisions", second.pk) == []


@pytest.mark.parametrize("fault", ["source", "purpose", "contract"])
def test_endpoint_requires_mapping_source_purpose_and_contract(fault):
    from uuid import uuid4

    from core.benchmark_metric_store import persist_source
    from core.models import SourceIdentifierNamespace, SourceSubjectMapping
    from tests.test_benchmark_opencode import configured, endpoint, read

    contract = configured()
    run = persist_source(contract, "opencode", "d" * 64, read(endpoint()))
    mapping = contract.mappings.get()
    if fault == "source":
        namespace, _ = SourceIdentifierNamespace.objects.get_or_create(
            data_source_id="hf", subject_kind="model", code=""
        )
        changes = {"source_id": "hf", "identifier_scope": namespace}
    elif fault == "purpose":
        changes = {"purpose": "catalog", "contract_id": None}
    else:
        contract.pk = uuid4()
        contract.contract_hash = "f" * 64
        contract.save(force_insert=True)
        changes = {"contract_id": contract.pk}
    SourceSubjectMapping.objects.filter(pk=mapping.pk).update(**changes)
    assert _typed("benchmark_endpoint_revisions", run.pk) == []


def test_typed_endpoint_selection_preserves_cross_run_reuse_conflicts_and_cutoff():
    from core.benchmark_metric_store import persist_source
    from core.benchmark_serving import selected_endpoint_rows
    from core.models import CollectionRun
    from tests.test_benchmark_opencode import configured, endpoint, read

    contract = configured()
    runs = []
    for index, tokens, stamp in ((1, 40, "12:00:00"), (2, 40, "12:30:00"), (3, 10, "12:30:00")):
        run = persist_source(contract, "opencode", str(index) * 64,
                             read(endpoint(tokens, "2026-10-07T" + stamp + "Z")))
        CollectionRun.objects.filter(pk=run.pk).update(
            completed_at=datetime(2026, 10, 7, 13, index, tzinfo=UTC)
        )
        runs.append(run)
    mappings = list(contract.mappings.values_list("pk", flat=True))
    cutoffs = [None, datetime(2026, 10, 7, 13, 1, 30, tzinfo=UTC),
               datetime(2026, 10, 7, 13, 2, 30, tzinfo=UTC)]
    expected = [selected_endpoint_rows(contract, mappings, "2026-10-06", "2026-10-07", cutoff)
                for cutoff in cutoffs]
    _install_typed_views()
    for cutoff, before in zip(cutoffs, expected, strict=True):
        assert selected_endpoint_rows(contract, mappings, "2026-10-06", "2026-10-07", cutoff) == before
    assert {row[3] for row in expected[1]} == {runs[0].pk}
    assert {row[3] for row in expected[2]} == {runs[1].pk}
    assert {row[2] for row in expected[1]} == {row[2] for row in expected[2]}
    assert any(row[4].get("revision_anomaly") == "same_update_different_body" for row in expected[0])
