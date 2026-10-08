"""Consumer-boundary regression for reviewed dataset use."""

from types import SimpleNamespace

import pytest

from core import benchmark_attribution as policy


def contract(decisions=None):
    return SimpleNamespace(source_configuration={"hf": {"use_policy": decisions or {}}})


def decision(status="allowed"):
    return {
        "status": status,
        "evidence_url": "https://example.org/terms",
        "reviewed_at": "2026-10-07",
        "reviewed_by": "fixture",
        "access_route": "public metadata",
        "restrictions": [],
    }


def result(source="hf", dataset=None):
    return {
        "lines": [{"source": source, "points": [], "baseline": {"evidence": []}}],
        "attributions": [{"source": source, "dataset_id": dataset}],
    }


def test_unresolved_cannot_leave_through_any_public_consumer():
    for use in (
        "public_charts",
        "public_forecasts",
        "numeric_export",
        "external_inference",
    ):
        with pytest.raises(policy.UseNotPermitted):
            policy.enforce_use(contract(), result(), use, current_policies={})


def test_current_revocation_overrides_frozen_allowance():
    c = contract({"public_charts": decision()})
    policy.enforce_use(c, result(), "public_charts", current_policies={})
    with pytest.raises(policy.UseNotPermitted):
        policy.enforce_use(
            c,
            result(),
            "public_charts",
            current_policies={"hf": {"public_charts": decision("prohibited")}},
        )


def test_offscreen_archive_baseline_is_checked_separately():
    c = contract({"numeric_export": decision()})
    with pytest.raises(policy.UseNotPermitted):
        policy.enforce_use(
            c,
            result(dataset="unreviewed/archive"),
            "numeric_export",
            current_policies={},
        )


def test_isolated_review_is_explicit_and_not_a_public_use():
    policy.enforce_use(
        contract(),
        result(),
        "isolated_review",
        current_policies={},
        isolated_review=True,
    )
    with pytest.raises(policy.UseNotPermitted):
        policy.enforce_use(
            contract(),
            result(),
            "public_charts",
            current_policies={},
            isolated_review=True,
        )
    with pytest.raises(policy.UseNotPermitted):
        policy.enforce_use(contract(), result(), "isolated_review", current_policies={})


def test_incomplete_or_conditional_review_fails_closed():
    for d in ({"status": "allowed"}, decision("conditional")):
        with pytest.raises(policy.UseNotPermitted):
            policy.enforce_use(
                contract({"numeric_export": d}),
                result(),
                "numeric_export",
                current_policies={},
            )


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_collection_is_denied_before_fetch_or_persistence():
    from unittest.mock import Mock

    from core.benchmark_metric_store import persist_source
    from core.models import DataSource, MetricCollectionRun
    from tests.test_benchmark_download_persistence import configured

    c = configured()
    source = DataSource.objects.get(pk="hf")
    source.metadata["use_policy"] = {"collection": {"status": "prohibited"}}
    source.save(update_fields=["metadata"])
    fetch = Mock()
    with pytest.raises(policy.UseNotPermitted):
        persist_source(c, "hf", "c" * 64, fetch=fetch)
    fetch.assert_not_called()
    assert not MetricCollectionRun.objects.exists()
