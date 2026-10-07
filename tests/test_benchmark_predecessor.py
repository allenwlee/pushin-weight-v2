import pytest

from core.benchmark_metric_identity import configure_collection
from core.benchmark_metric_series import build_comparison
from core.benchmark_metric_store import persist_source
from core.measurement_taxonomy import configure_taxonomy, digest, subject_id
from core.models import Product
from tests.test_benchmark_download_db_identity import setup_spec

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def proxy_spec():
    successor, spec = setup_spec()
    previous = Product.objects.create(
        repo_id="lab/Previous",
        hf_org=successor.hf_org,
        brand=successor.brand,
        type="llm-model",
        private=False,
        disabled=False,
    )
    p, s = str(previous.product_key), str(successor.product_key)
    version = configure_taxonomy(
        {
            "reviewed_by": "fixture",
            "subjects": [{"kind": "product", "key": k} for k in (p, s)],
            "relationships": [
                {
                    "parent": p,
                    "child": s,
                    "type": "new_version",
                    "evidence": {
                        "source_url": "https://example.org/releases",
                        "basis": "manual_review",
                    },
                }
            ],
        }
    )
    spec["taxonomy_version"] = str(version.pk)
    spec["source_configuration"] = {
        "arena": {"metrics": ["rank", "rating"], "config": "text"}
    }
    spec["mappings"] = [
        {
            "source": "arena",
            "external_identifier": identifier,
            "identifier_scope": "",
            "source_subject_kind": "model",
            "subject_id": str(subject_id("product", key)),
            "evidence_url": "https://example.org/model",
        }
        for key, identifier in ((p, "previous"), (s, "successor"))
    ]
    spec["methodology"]["comparisons"] = {
        "history": {
            "title": "Release history",
            "release_history": {"lookback_days": 3},
            "launch_anchor": {
                "product_subject_id": str(subject_id("product", s)),
                "announced_date": "2026-09-10",
                "precision": "date",
                "source_url": "https://example.org/launch",
                "event_kind": "announcement",
                "reviewed_by": "fixture",
            },
            "lines": [
                {
                    "key": "rank",
                    "label": "Arena rank",
                    "source": "arena",
                    "metric_key": "rank",
                    "subject_id": str(subject_id("product", s)),
                    "mapping_identifiers": ["successor"],
                    "baseline": "first_observed",
                    "predecessor": {
                        "subject_id": str(subject_id("product", p)),
                        "mapping_identifiers": ["previous"],
                        "rationale": "Reviewed prior release",
                    },
                }
            ],
        }
    }
    return spec


def test_predecessor_switches_at_evaluation_not_launch_and_never_falls_back():
    contract = configure_collection(proxy_spec())
    rows = [
        {
            "model_name": model,
            "category": "overall",
            "leaderboard_publish_date": day,
            "rating": 1400.0,
            "rank": rank,
        }
        for day, model, rank in [
            ("2026-09-07", "previous", 10.0),
            ("2026-09-10", "previous", 8.0),
            ("2026-09-12", "successor", 4.0),
            ("2026-09-14", "previous", 7.0),
        ]
    ]
    persist_source(
        contract,
        "arena",
        digest(rows),
        {
            "status": "ok",
            "config": "text",
            "coverage": "publication_window",
            "rows": rows,
        },
        source_metadata={
            "publication_dates": [
                "2026-09-07",
                "2026-09-10",
                "2026-09-12",
                "2026-09-14",
            ],
            "publication_start": "2026-09-07",
            "publication_end": "2026-09-14",
        },
    )
    result = build_comparison(contract, "history", end_date="2026-09-15")
    line = result["lines"][0]
    assert result["start_date"] == "2026-09-07"
    assert [p["raw_value"] for p in line["points"]] == [
        "10",
        "10",
        "10",
        "8",
        "8",
        "4",
        "4",
        None,
        None,
    ]
    assert line["baseline"]["value"] == "10"
    assert line["points"][5]["percent_change"] == -60
    assert line["points"][5]["model_changed"]
    assert line["points"][0]["proxy_label"].startswith("Previous release proxy")
    assert line["points"][0]["measured_subject_id"] != line["subject_id"]
    assert line["points"][5]["measured_subject_id"] == line["subject_id"]


def test_only_reviewed_compatible_successor_relationship_is_allowed():
    spec = proxy_spec()
    spec["source_configuration"]["arena"]["config"] = "text_style_control"
    with pytest.raises(ValueError, match="no style control"):
        configure_collection(spec)


def test_corrected_publication_does_not_start_switch_and_export_keeps_proxy():
    from core.benchmark_metric_report import report_from_comparison

    contract = configure_collection(proxy_spec())

    def publish(key, day, models):
        return persist_source(
            contract,
            "arena",
            digest(key),
            {
                "status": "ok",
                "config": "text",
                "coverage": "publication_window",
                "rows": [
                    {
                        "model_name": m,
                        "category": "overall",
                        "leaderboard_publish_date": day,
                        "rating": 1400.0,
                        "rank": r,
                    }
                    for m, r in models
                ],
            },
            source_metadata={
                "publication_dates": [day],
                "publication_start": day,
                "publication_end": day,
            },
        )

    publish("earlier", "2026-09-07", [("previous", 10.0), ("successor", 5.0)])
    publish("correction", "2026-09-07", [("previous", 9.0)])
    publish("valid", "2026-09-12", [("successor", 4.0)])
    comparison = build_comparison(contract, "history", end_date="2026-09-14")
    line = comparison["lines"][0]
    assert line["interpretation"]["switch_date"] == "2026-09-12"
    assert line["points"][0]["proxy"] is True
    report = report_from_comparison(comparison)
    rank = report["series"][0]["points"][0]["rank"]
    assert rank["proxy_label"].startswith("Previous release proxy")
    assert rank["measured_subject"] == line["points"][0]["measured_subject"]
    assert rank["percent_change"] == 0
    # Narrowing the requested window cannot bring the predecessor back.
    late = build_comparison(
        contract, "history", start_date="2026-09-13", end_date="2026-09-14"
    )
    assert all(not p["proxy"] for p in late["lines"][0]["points"])


def test_missing_predecessor_is_gap_and_ambiguous_mapping_is_rejected():
    spec = proxy_spec()
    line = spec["methodology"]["comparisons"]["history"]["lines"][0]
    predecessor = line.pop("predecessor")
    c = configure_collection(spec)
    result = build_comparison(c, "history", end_date="2026-09-12")
    assert all(
        p["raw_value"] is None and not p["proxy"] for p in result["lines"][0]["points"]
    )
    assert result["lines"][0]["baseline"]["status"] == "baseline_missing"
    line["predecessor"] = predecessor
    spec["methodology"]["comparisons"]["history"]["lines"][0]["predecessor"][
        "mapping_identifiers"
    ] = ["previous", "successor"]
    with pytest.raises(ValueError, match="one exact Arena mapping"):
        configure_collection(spec)
