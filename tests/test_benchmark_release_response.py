"""Shared PostgreSQL arithmetic, publication evidence and real HTTP output."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from django.test import override_settings
from django.urls import reverse

from core.benchmark_metric_history import import_history
from core.benchmark_metric_identity import configure_collection
from core.benchmark_metric_series import build_comparison
from core.benchmark_metric_store import persist_source
from core.measurement_taxonomy import configure_taxonomy, digest, subject_id
from core.models import Post, PostBrand
from tests.test_benchmark_download_db_identity import setup_spec
from tests.test_benchmark_pulse_views import allow_fixture_uses

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def response_contract():
    product, spec = setup_spec()
    version = configure_taxonomy(
        {
            "reviewed_by": "fixture",
            "subjects": [
                {"kind": "product", "key": str(product.product_key)},
                {"kind": "brand", "key": "lab"},
            ],
        }
    )
    spec["taxonomy_version"] = str(version.pk)
    sid = spec["mappings"][0]["subject_id"]
    for source in ("openrouter", "arena"):
        spec["mappings"].append(
            {
                **deepcopy(spec["mappings"][0]),
                "source": source,
                "source_subject_kind": "model",
                "identifier_scope": "",
                "external_identifier": "lab/model",
            }
        )
    spec["source_configuration"]["hf"]["metrics"] = ["downloads"]
    spec["source_configuration"]["openrouter"] = {"metrics": ["total_tokens"]}
    spec["source_configuration"]["arena"] = {
        "config": "text",
        "metrics": ["rating", "rating_lower", "rating_upper", "vote_count", "rank"],
        "metric_versions": {"rating_lower": 2, "rating_upper": 2, "vote_count": 2},
    }
    hf = {
        "key": "downloads",
        "label": "HF net rolling-counter change",
        "source": "hf",
        "subject_id": sid,
        "metric_key": "downloads",
        "mapping_identifiers": ["lab/Model"],
        "aggregation": "single",
        "transform": "adjacent_snapshot_difference",
    }
    usage = {
        **hf,
        "key": "tokens",
        "label": "OpenRouter daily tokens",
        "source": "openrouter",
        "metric_key": "total_tokens",
        "mapping_identifiers": ["lab/model"],
        "transform": "identity",
    }
    arena = {
        **hf,
        "key": "arena_score",
        "label": "Arena score",
        "source": "arena",
        "metric_key": "rating",
        "mapping_identifiers": ["lab/model"],
        "transform": "identity",
        "dimensions": {"category": "overall", "config": "text"},
    }
    spec["methodology"].update(
        post_coverage={"start": "2026-09-01", "end": "2026-09-20"},
        comparisons={
            "response": {
                "title": "Fixture release response",
                "chart_kind": "release_response_v1",
                "launch_anchor": {
                    "product_subject_id": sid,
                    "announced_date": "2026-09-10",
                    "precision": "date",
                    "source_url": "https://example.org/launch",
                    "event_kind": "announcement",
                    "source_timezone": "unknown",
                    "reviewed_by": "fixture",
                },
                "reference_search": {
                    "start_date": "2026-09-11",
                    "end_date": "2026-09-20",
                },
                "lines": [
                    {
                        "key": "posts",
                        "label": "Brand posts",
                        "source": "x",
                        "metric_key": "post_volume",
                        "subject_id": str(subject_id("brand", "lab")),
                        "post_policy": "legacy_brand",
                        "transform": "identity",
                    },
                    hf,
                    usage,
                ],
                "arena_line": arena,
            }
        },
    )
    allow_fixture_uses(spec)
    return configure_collection(spec)


def seed(contract, *, missing_hf_days=(19,)):
    snapshots, tokens = [], []
    counter = 100
    for day in range(9, 21):
        label = f"2026-09-{day:02d}"
        counter += -20 if day == 18 else 10
        if day not in missing_hf_days:
            payload = {
                "status": "ok",
                "rows": [
                    {
                        "repo_id": "lab/Model",
                        "status": "ok",
                        "raw": {"downloads": counter},
                    }
                ],
            }
            snapshots.append(
                {
                    "date": label,
                    "immutable_revision": digest(label),
                    "file_path": "models.json",
                    "raw_artifact_sha256": digest(payload),
                    "payload": payload,
                }
            )
        tokens.append(
            {
                "date": label,
                "model_permaslug": "lab/model",
                "total_tokens": "40" if day == 18 else "20",
            }
        )
        for index in range(20 if day == 18 else 10):
            post = Post.objects.create(
                tweet_id=f"{day}-{index}", created_at=datetime(2026, 9, day, tzinfo=UTC)
            )
            PostBrand.objects.create(post=post, brand_id="lab")
    import_history(
        {
            "schema_version": 1,
            "contract_id": str(contract.pk),
            "source": "hf",
            "dataset_id": "cfahlgren1/hub-stats",
            "archive_publisher": "cfahlgren1",
            "artifact_kind": "selected_json",
            "start_date": "2026-09-09",
            "end_date": "2026-09-20",
            "snapshots": snapshots,
        },
        apply=True,
    )
    persist_source(
        contract,
        "openrouter",
        digest("tokens"),
        {"status": "ok", "meta": {"version": "v1"}, "rows": tokens},
    )
    rows = [
        {
            "model_name": "lab/model",
            "leaderboard_publish_date": f"2026-09-{day}",
            "category": "overall",
            "rating": score,
            "rating_lower": score - 10,
            "rating_upper": score + 10,
            "vote_count": votes,
            "rank": rank,
        }
        for day, score, votes, rank in [(11, 1400, 100, 1), (18, 1390, 50, 2)]
    ]
    persist_source(
        contract,
        "arena",
        digest("arena"),
        {
            "status": "ok",
            "config": "text",
            "coverage": "publication_window",
            "rows": rows,
        },
        source_metadata={"publication_dates": ["2026-09-11", "2026-09-18"]},
    )


def test_reference_week_signed_hf_difference_smoothing_and_range_are_shared():
    contract = response_contract()
    seed(contract)
    result = build_comparison(contract, "response", "2026-09-09", "2026-09-20")
    assert result["chart_kind"] == "release_response_v1" and len(result["lines"]) == 3
    assert result["reference"]["dates"] == [f"2026-09-{i}" for i in range(11, 18)]
    downloads = result["lines"][1]
    assert downloads["baseline"]["value"] == "10"
    selected = {p["date"]: p for p in downloads["points"]}
    assert selected["2026-09-18"]["raw_value"] == "-20"
    assert selected["2026-09-18"]["daily_percent_change"] == -300
    assert selected["2026-09-18"]["percent_change"] == -100
    assert selected["2026-09-19"]["raw_value"] is None
    assert selected["2026-09-20"]["raw_value"] is None
    assert len(selected["2026-09-18"]["evidence"]) == 2
    restricted = build_comparison(contract, "response", "2026-09-18", "2026-09-20")
    assert restricted["reference"] == result["reference"]
    assert restricted["lines"][1]["points"][0]["percent_change"] == -100


def test_arena_same_publication_bounds_battles_decreases_and_unknown_anchor():
    contract = response_contract()
    seed(contract)
    panel = build_comparison(contract, "response", "2026-09-10", "2026-09-20")[
        "arena_panel"
    ]
    points = {p["date"]: p for p in panel["points"]}
    assert points["2026-09-10"]["score"] is None
    assert points["2026-09-11"]["actual_publication"] is True
    assert points["2026-09-12"]["actual_publication"] is False
    assert points["2026-09-18"]["battles"] == "50"
    assert points["2026-09-18"]["lower"] == 1380 and points["2026-09-18"]["rank"] == "2"
    assert points["2026-09-11"]["segment"] != points["2026-09-18"]["segment"]
    assert points["2026-09-18"]["comparability"] == "unknown"


@override_settings(BENCHMARK_METRICS_ENABLED=True, SECURE_SSL_REDIRECT=False)
def test_real_response_exports_same_computation_and_no_provider_requests(client):
    contract = response_contract()
    seed(contract)
    from unittest.mock import patch

    with patch("httpx.Client", side_effect=AssertionError("provider fetch on serving")):
        response = client.get(
            reverse("benchmark_series", args=[contract.pk, "response"]),
            {"start": "2026-09-09", "end": "2026-09-20"},
        )
    assert response.status_code == 200
    assert response.json()["lines"][1]["points"][9]["raw_value"] == "-20"


def test_new_comparison_reuses_reviewed_history_without_copying_facts(tmp_path):
    from core.benchmark_forecast_inputs import forecast_inputs
    from core.benchmark_metric_report import report_from_comparison
    from core.models import MetricValue
    from scripts.benchmark_download_collector.report import render_report

    parent = response_contract()
    seed(parent)
    before = MetricValue.objects.count()
    spec = {
        "taxonomy_version": str(parent.taxonomy_version_id),
        "reviewed_by": "fixture",
        "source_configuration": deepcopy(parent.source_configuration),
        "methodology": deepcopy(parent.methodology),
        "mappings": [
            {
                "source": m.source_id,
                "source_subject_kind": m.source_subject_kind,
                "identifier_scope": m.identifier_scope,
                "external_identifier": m.external_identifier,
                "subject_id": str(m.subject_id),
                "evidence_url": m.evidence_url,
                "identifier_metadata": m.identifier_metadata,
            }
            for m in parent.mappings.all()
        ],
    }
    preset = spec["methodology"]["comparisons"]["response"]
    for line in preset["lines"] + [preset["arena_line"]]:
        if line["source"] != "x":
            line["measurement_contract"] = {
                "id": str(parent.pk),
                "contract_hash": parent.contract_hash,
            }
    from django.utils import timezone

    before_review = timezone.now()
    child = configure_collection(spec)
    assert child.pk != parent.pk
    result = build_comparison(child, "response", "2026-09-09", "2026-09-20")
    assert result["lines"][1]["baseline"]["value"] == "10"
    assert MetricValue.objects.count() == before
    assert (
        forecast_inputs(
            child, before_review, use="isolated_review", isolated_review=True
        )["values"]
        == []
    )
    cutoff = timezone.now()
    evidence = forecast_inputs(
        child, cutoff, use="isolated_review", isolated_review=True
    )["values"]
    assert {r["source"] for r in evidence} == {"hf", "arena", "openrouter"}
    selected_mapping = child.mappings.get(source_id="hf")
    selected_evidence = forecast_inputs(
        child,
        cutoff,
        mapping_ids=[selected_mapping.pk],
        use="isolated_review",
        isolated_review=True,
    )["values"]
    assert selected_evidence and {r["source"] for r in selected_evidence} == {"hf"}
    later = persist_source(
        parent,
        "hf",
        digest("late correction"),
        {
            "status": "ok",
            "rows": [
                {"repo_id": "lab/Model", "status": "ok", "raw": {"downloads": 999}}
            ],
        },
    )
    assert str(later.pk) not in {
        r["run_id"]
        for r in forecast_inputs(
            child, cutoff, use="isolated_review", isolated_review=True
        )["values"]
    }
    output = tmp_path / "response.html"
    render_report(report_from_comparison(result), output)
    assert 'id="pulse-preloaded"' in output.read_text()
    assert "reference-band" in output.read_text()
    assert "/static/benchmark-pulse.js" not in output.read_text()
    assert result["input_revision"] in output.read_text()


def test_incomplete_reference_keeps_raw_evidence_without_percentages():
    contract = response_contract()
    seed(contract, missing_hf_days=(12, 16, 19))
    result = build_comparison(contract, "response", "2026-09-09", "2026-09-20")
    assert not result["reference"]["dates"]
    assert any(p["raw_value"] is not None for p in result["lines"][0]["points"])
    assert all(
        p["percent_change"] is None for line in result["lines"] for p in line["points"]
    )


def test_zero_reference_mean_is_not_divided_and_observed_zero_remains_visible():
    contract = response_contract()
    seed(contract)
    PostBrand.objects.filter(
        post__created_at__date__range=["2026-09-11", "2026-09-17"]
    ).delete()
    result = build_comparison(contract, "response", "2026-09-11", "2026-09-20")
    posts = result["lines"][0]
    assert posts["baseline"]["value"] == "0"
    assert posts["points"][0]["raw_value"] == "0"
    assert all(p["percent_change"] is None for p in posts["points"])
    assert result["lines"][2]["points"][0]["percent_change"] is not None
