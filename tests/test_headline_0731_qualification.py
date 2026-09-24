"""A high average cannot erase a critical case or missing operational proof."""

import pytest

from scripts.headline_0731_qualification import FIELDS, MODEL, assess


@pytest.fixture
def evidence():
    manifest = {"reviewers": {f"R{i}": f"reviewer-{i}" for i in (1, 2, 3)}, "cases": []}
    reviews = []
    for reviewer, model in manifest["reviewers"].items():
        cases = []
        for number in range(8):
            case_id = f"{reviewer}-{number}"
            manifest["cases"].append({"case_id": case_id, "reviewer": reviewer,
                                      "window_days": 1 if number < 4 else 7, "brand_key": case_id})
            cases.append({"case_id": case_id, **dict.fromkeys(FIELDS, 5), "critical_failure": False})
        reviews.append({"reviewer": reviewer, "model": model, "review": {"cases": cases, "controls": []}})
    controls = []
    for number in range(8):
        control_id = f"control-{number}"
        controls.append({"control": control_id})
        reviews[number % 3]["review"]["controls"].append({"control_id": control_id,
            "fully_supported": True, "unsupported_claim_survives": False, "new_material_error": False})
    calls = [{"stage": "rank", "batch_key": f"{window}d:rank",
              "envelope": {"analysis_packet": {"window_days": window}},
              "mechanical": {"valid": True}, "usage": {"provider_usage": {
                  "model": MODEL, "provider": "DeepInfra", "service_tier": "priority",
                  "reasoning_tokens": 0, "provider_request_id": f"receipt-{window}",
                  "cost_usd": .01, "input_tokens": 1000, "output_tokens": 100}}} for window in (1, 7)]
    artifact = {"calls": calls, "brand_outcomes": [], "configuration_lock": {"pinned": True},
                "preflight": {"planned_call_count": 2},
                "activation_assessment": {"complete": True, "every_eligible_brand_decided": True},
                "critic_calibration": {"complete_control_set": True, "unsupported_false_accepts": 0,
                                       "supported_false_holds": 0, "controls": controls}}
    operations = {"configuration_lock": {"pinned": True},
                  "timing": {"concurrency": 3, "one_day_p95_seconds": 400,
                             "seven_day_p95_seconds": 500, "arrival_drain_utilization": .2},
                  "render_memory": {"worker_processes": 3, "bounded_queue": True,
                                    "peak_bytes": 300, "limit_bytes": 512},
                  "observed_monthly_runs": {"1": 626, "7": 30},
                  **{k: {"passed": True} for k in ("SC7", "SC8", "SC9")}}
    return artifact, reviews, manifest, operations


def test_ready_requires_every_criterion_and_reports_monthly_actual_billing(evidence):
    result = assess(*evidence)
    assert result["decision"] == "ready_0731"
    assert result["projected_monthly_headline_cost_usd"] == "6.56"
    assert result["unmet_success_criteria"] == []


@pytest.mark.parametrize("defect,criterion", [
    ("critical", "SC2"), ("missing_control", "SC2"), ("duplicate_case", "SC2"),
    ("false_hold", "SC2"), ("bad_schema", "SC3"), ("wrong_tier", "SC1"),
    ("over_budget", "SC5"), ("missing_bill", "SC5"), ("memory", "SC6"),
    ("slow", "SC4"), ("changed_config", "SC8"),
])
def test_individual_failure_cannot_be_hidden_by_other_passing_gates(evidence, defect, criterion):
    artifact, reviews, manifest, operations = evidence
    if defect == "critical":
        reviews[0]["review"]["cases"][0]["critical_failure"] = True
    elif defect == "missing_control":
        reviews[0]["review"]["controls"].pop()
    elif defect == "duplicate_case":
        reviews[0]["review"]["cases"][1] = reviews[0]["review"]["cases"][0].copy()
    elif defect == "false_hold":
        assigned = manifest["cases"][0]
        artifact["brand_outcomes"].append({"window_days": assigned["window_days"],
                                         "brand_key": assigned["brand_key"], "outcome": "hold"})
        reviews[0]["review"]["cases"][0]["secondary_usefulness"] = 1
    elif defect == "bad_schema":
        artifact["calls"][0]["mechanical"]["valid"] = False
    elif defect == "wrong_tier":
        artifact["calls"][0]["usage"]["provider_usage"]["service_tier"] = "standard"
    elif defect == "over_budget":
        artifact["calls"][0]["usage"]["provider_usage"]["cost_usd"] = .31
    elif defect == "missing_bill":
        artifact["calls"][0]["usage"]["provider_usage"].pop("cost_usd")
    elif defect == "memory":
        operations["render_memory"]["peak_bytes"] = 400
    elif defect == "slow":
        operations["timing"]["one_day_p95_seconds"] = 721
    else:
        operations["configuration_lock"] = {}
    result = assess(*evidence)
    assert result["decision"] == "improve_0731"
    assert criterion in result["unmet_success_criteria"]


def test_absent_operational_evidence_cannot_be_ready(evidence):
    result = assess(*evidence[:3], {})
    assert result["decision"] == "improve_0731"
    assert set(result["unmet_success_criteria"]) == {"SC4", "SC5", "SC6", "SC7", "SC8", "SC9"}


def test_minor_control_wording_does_not_block_a_supported_final_result(evidence):
    control = evidence[1][0]["review"]["controls"][0]
    control.update(fully_supported=False, minor_issues=["Awkward but intelligible idiom."])
    result = assess(*evidence)
    assert result["decision"] == "ready_0731"
    assert result["control_reviews"][0]["minor_issues"]


def test_critic_recovery_is_reported_separately_from_raw_failure():
    from scripts.headline_0731_qualification import mechanical_results

    calls = [
        {"stage": "editor", "batch_key": "1d:001", "mechanical": {"valid": False}},
        {"stage": "critic", "batch_key": "1d:001", "mechanical": {"valid": True}},
        {"stage": "editor", "batch_key": "7d:001", "mechanical": {"valid": False}},
        {"stage": "critic", "batch_key": "7d:001", "mechanical": {"valid": False}},
    ]
    raw, recovered, unresolved = mechanical_results(calls)
    assert len(raw) == 3
    assert recovered == ["editor:1d:001"]
    assert unresolved == ["editor:7d:001", "critic:7d:001"]


def test_fixture_defect_is_inconclusive_and_is_not_a_model_critical_error(evidence):
    evidence[1][0]["review"]["controls"][0]["fixture_defect"] = True
    result = assess(*evidence)
    assert result["decision"] == "improve_0731"
    assert result["fixture_defects"]
    assert result["critical_cases"] == []
