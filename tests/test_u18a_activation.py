"""Frozen U18A activation policy and fail-closed behavior."""

from core.u18a_activation import FAMILY_DECISIONS, enabled_audience_topics, is_enabled


def test_owner_activation_exposes_all_audience_topics():
    assert {key for key, value in FAMILY_DECISIONS.items() if value == "enabled"} == {
        "local_inference",
        "cost_performance",
        "model_distillation",
        "evals_benchmarks",
        "openness_license",
        "agents_tools",
        "api_developer_surface",
    }
    assert len(FAMILY_DECISIONS) == 11


def test_unknown_and_unactivated_families_fail_closed():
    assert is_enabled("news_reporting") is False
    assert is_enabled("unknown_future_family") is False
    assert enabled_audience_topics((
        "local_inference",
        "cost_performance",
        "model_distillation",
        "evals_benchmarks",
        "openness_license",
        "agents_tools",
        "api_developer_surface",
    )) == (
        "local_inference",
        "cost_performance",
        "model_distillation",
        "evals_benchmarks",
        "openness_license",
        "agents_tools",
        "api_developer_surface",
    )
