import pytest

from core.benchmark_metric_history import import_history
from core.benchmark_metric_identity import configure_collection
from core.measurement_taxonomy import digest
from tests.test_benchmark_download_db_identity import setup_spec

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_percentage_is_change_from_fixed_baseline_with_missing_day_preserved():
    from core.benchmark_metric_series import build_comparison

    _, spec = setup_spec()
    subject = spec["mappings"][0]["subject_id"]
    spec["source_configuration"]["hf"]["metrics"] = ["downloads"]
    spec["methodology"]["comparisons"] = {
        "fixture": {
            "title": "Fixture",
            "launch_anchor": {
                "product_subject_id": subject,
                "announced_date": "2026-09-10",
                "precision": "date",
                "source_url": "https://example.org/launch",
                "event_kind": "announcement",
                "source_timezone": "unknown",
                "reviewed_by": "fixture",
            },
            "lines": [
                {
                    "key": "downloads",
                    "label": "Rolling downloads",
                    "source": "hf",
                    "subject_id": subject,
                    "metric_key": "downloads",
                    "mapping_identifiers": ["lab/Model"],
                    "aggregation": "sum_fixed_cohort",
                    "baseline": "launch",
                }
            ],
        }
    }
    contract = configure_collection(spec)
    snapshots = []
    for day, count in [("2026-09-10", 10), ("2026-09-12", 11), ("2026-09-13", 13)]:
        payload = {
            "status": "ok",
            "rows": [
                {"repo_id": "lab/Model", "status": "ok", "raw": {"downloads": count}}
            ],
        }
        snapshots.append(
            {
                "date": day,
                "immutable_revision": "a" * 40,
                "file_path": "models.parquet",
                "raw_artifact_sha256": digest(payload),
                "payload": payload,
            }
        )
    import_history(
        {
            "schema_version": 1,
            "contract_id": str(contract.pk),
            "source": "hf",
            "dataset_id": "cfahlgren1/hub-stats",
            "archive_publisher": "cfahlgren1",
            "artifact_kind": "selected_json",
            "start_date": "2026-09-10",
            "end_date": "2026-09-13",
            "snapshots": snapshots,
        },
        apply=True,
    )
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as queries:
        result = build_comparison(contract, "fixture", "2026-09-10", "2026-09-13")
    assert not any('"raw_payload"' in q["sql"] for q in queries), (
        "Serving must not load source envelopes"
    )
    line = result["lines"][0]
    assert [p["percent_change"] for p in line["points"]] == [0.0, None, 10.0, 30.0]
    assert line["points"][1]["coverage"] == "missing"
    assert line["points"][0]["raw_value"] == "10"
    assert line["points"][0]["window_end_at"] is None
    assert line["baseline"]["date"] == "2026-09-10"


def test_missing_launch_and_zero_baselines_are_explicit():
    from core.benchmark_metric_series import normalize_points

    points = [
        {"date": "2026-09-10", "raw_value": None},
        {"date": "2026-09-11", "raw_value": "10"},
    ]
    baseline = normalize_points(points, "2026-09-10", "launch")
    assert baseline["status"] == "baseline_missing"
    assert all(p["percent_change"] is None for p in points)
    baseline = normalize_points(points, "2026-09-10", "first_observed")
    assert baseline["status"] == "later_baseline" and points[1]["percent_change"] == 0
    baseline = normalize_points(
        [{"date": "2026-09-10", "raw_value": "0"}], "2026-09-10", "launch"
    )
    assert baseline["status"] == "baseline_zero"


@pytest.mark.parametrize("empty_cohort", [False, True])
def test_arena_stops_carrying_after_complete_publication_drops_selected_product(
    empty_cohort,
):
    from core.benchmark_metric_series import metric_points
    from core.benchmark_metric_store import persist_source
    from tests.test_benchmark_download_persistence import provider_contract

    contract = provider_contract(
        "arena", ["rating", "rating_lower", "rating_upper", "rank"]
    )
    row = {
        "model_name": "lab/model",
        "category": "overall",
        "leaderboard_publish_date": "2026-09-25",
        "rating": 1400.0,
        "rating_lower": 1390.0,
        "rating_upper": 1410.0,
        "rank": 10.0,
    }
    persist_source(
        contract,
        "arena",
        digest("first"),
        {
            "status": "ok",
            "config": "text_style_control",
            "coverage": "latest_publication_only",
            "rows": [row],
        },
    )
    persist_source(
        contract,
        "arena",
        digest("removed"),
        {
            "status": "ok",
            "config": "text_style_control",
            "coverage": "latest_publication_only",
            "rows": [
                {
                    **row,
                    "model_name": "other/model",
                    "leaderboard_publish_date": "2026-09-27",
                }
            ]
            if not empty_cohort
            else [],
        },
        source_metadata={
            "publication_dates": ["2026-09-27"],
            "publication_start": "2026-09-27",
            "publication_end": "2026-09-27",
        },
    )
    line = {
        "source": "arena",
        "subject_id": str(contract.mappings.get().subject_id),
        "metric_key": "rating",
        "mapping_identifiers": ["lab/model"],
        "aggregation": "single",
    }
    points, _, _ = metric_points(
        contract, line, ["2026-09-25", "2026-09-26", "2026-09-27", "2026-09-28"]
    )
    assert [p["raw_value"] for p in points] == [1400.0, 1400.0, None, None]
    assert points[1]["coverage"] == "carried_forward"


def test_archive_credit_survives_offscreen_baseline():
    from core.benchmark_attribution import comparison_attributions

    contract = configure_collection(setup_spec()[1])
    credits = comparison_attributions(
        contract,
        [
            {
                "source": "hf",
                "points": [],
                "baseline": {
                    "evidence": [
                        {
                            "archive": {
                                "dataset_id": "cfahlgren1/hub-stats",
                                "immutable_revision": "a" * 40,
                            }
                        }
                    ]
                },
            }
        ],
    )
    assert credits[0]["publisher"] == "cfahlgren1"
    assert credits[0]["license_url"] == "https://www.apache.org/licenses/LICENSE-2.0"
