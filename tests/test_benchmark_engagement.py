import pytest

from core.benchmark_metric_identity import configure_collection, configure_hf_account
from core.benchmark_metric_store import persist_source
from core.measurement_taxonomy import configure_taxonomy, subject_id
from core.models import MetricValue
from tests.test_benchmark_download_db_identity import setup_spec

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def engagement_spec():
    product, spec = setup_spec()
    account = configure_hf_account(
        "lab", reviewed_by="fixture", evidence_url="https://huggingface.co/lab"
    )
    taxonomy = configure_taxonomy(
        {
            "reviewed_by": "fixture",
            "subjects": [
                {"kind": "product", "key": str(product.product_key)},
                {"kind": "account", "key": str(account.pk)},
            ],
        }
    )
    spec["taxonomy_version"] = str(taxonomy.pk)
    spec["source_configuration"]["hf"]["metrics"] += ["likes", "followers"]
    spec["mappings"].append(
        {
            "source": "hf",
            "source_subject_kind": "account",
            "identifier_scope": "organization",
            "external_identifier": "lab",
            "subject_id": str(subject_id("account", account.pk)),
            "evidence_url": "https://huggingface.co/lab",
        }
    )
    return spec


def test_mixed_hf_accounts_repos_replay_and_decrease():
    contract = configure_collection(engagement_spec())
    data = {
        "status": "ok",
        "rows": [
            {
                "repo_id": "lab/Model",
                "raw": {"downloads": 10, "downloadsAllTime": 100, "likes": 8},
            },
            {
                "account_identifier": "lab",
                "account_kind": "organization",
                "raw": {"numFollowers": 12},
            },
        ],
    }
    run = persist_source(contract, "hf", "1" * 64, data)
    assert run.status == "success"
    assert run.observations.count() == 2
    values = MetricValue.objects.filter(
        source_metric__metric_key__in=["likes", "followers"]
    )
    assert sorted(int(v.integer_value) for v in values) == [8, 12]
    assert all(v.window_start_at is None and v.window_end_at is None for v in values)
    assert persist_source(contract, "hf", "1" * 64, data).pk == run.pk
    data["rows"][1]["raw"]["numFollowers"] = 10
    assert persist_source(contract, "hf", "2" * 64, data).status == "success"
    assert list(
        MetricValue.objects.filter(source_metric__metric_key="followers")
        .order_by("pk")
        .values_list("integer_value", flat=True)
    ) == [12, 10]


def test_wrong_hf_account_identity_rejected():
    spec = engagement_spec()
    spec["mappings"][-1]["external_identifier"] = "someone-else"
    with pytest.raises(ValueError, match="account identity"):
        configure_collection(spec)


def test_arena_configuration_is_pinned_and_old_history_is_not_relabelled():
    from core.benchmark_metric_store import prepare_rows
    from tests.test_benchmark_download_persistence import provider_contract

    old = provider_contract("arena", ["rating", "rating_lower", "rating_upper"])
    row = {
        "model_name": "lab/model",
        "category": "overall",
        "leaderboard_publish_date": "2026-09-25",
        "rating": 1476.5,
        "rating_lower": 1460.0,
        "rating_upper": 1480.0,
    }
    assert prepare_rows(
        old, "arena", {"status": "ok", "config": "text_style_control", "rows": [row]}
    )
    with pytest.raises(ValueError, match="contract configuration"):
        prepare_rows(old, "arena", {"status": "ok", "config": "text", "rows": [row]})


def test_reconstructed_likes_are_separate_from_observed_stock():
    from core.benchmark_metric_series import metric_points

    spec = engagement_spec()
    contract = configure_collection(spec)
    line = {
        "source": "hf",
        "metric_key": "likes",
        "subject_id": spec["mappings"][0]["subject_id"],
        "mapping_identifiers": ["lab/Model"],
        "aggregation": "single",
    }
    rows = [
        {
            "repo_id": "lab/Model",
            "raw": {"likes": count},
            "_source_metadata": {
                "history_basis": "reconstructed_current_relationships",
                "includes_removed_relationships": False,
                "reconstruction_date": day,
                "reconstruction_timezone": "UTC",
            },
        }
        for day, count in [("2026-09-10", 8), ("2026-09-11", 10)]
    ]
    run = persist_source(contract, "hf", "3" * 64, {"status": "ok", "rows": rows})
    assert run.status == "partial"  # account is not in this batch
    points, _, _ = metric_points(
        contract,
        {**line, "history_basis": "reconstructed_current_relationships"},
        ["2026-09-10", "2026-09-11"],
    )
    assert [p["raw_value"] for p in points] == ["8", "10"]
    assert all(p["coverage"] == "reconstructed" and not p["observed"] for p in points)
    assert all(
        p["raw_value"] is None
        for p in metric_points(contract, line, ["2026-09-10", "2026-09-11"])[0]
    )
