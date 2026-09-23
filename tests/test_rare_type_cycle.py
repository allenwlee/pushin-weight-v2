from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.discovery import RARE_EXTRA_CALL_ID, plan_discovery_calls
from core.models import RareTypeSearchDailyBudget, RareTypeSearchHit, RareTypeSearchRun
from monitor.cycle import CycleRunner
from monitor.management.commands.run_cycle import _configured_call_ids
from x_monitor.config import load_config
from x_monitor.rare_type_extra_search import QUERY_VERSION, planned_query_string

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
REPO = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 24, 8, 7, tzinfo=UTC)


def _canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _enable(cfg, tmp_path: Path):
    query = planned_query_string()
    jev = cfg.discovery.rare_types.jev
    identity = {
        "query_version": QUERY_VERSION,
        "planner_query_sha256": hashlib.sha256(query.encode()).hexdigest(),
        "requested_model": jev.model,
        "attested_model": jev.model,
        "requested_provider": jev.provider,
        "attested_provider": jev.provider,
        "question_version": jev.question_set_version,
        "question_content_sha256": jev.question_content_sha256,
        "threshold_version": jev.threshold_version,
        "threshold_values_sha256": jev.threshold_values_sha256,
        "yes_threshold": format(jev.yes_threshold, "f"),
        "no_threshold": format(jev.no_threshold, "f"),
        "fixture_sha256": "a" * 64,
        "corpus_content_sha256": "b" * 64,
    }
    assessment = {
        "schema_version": "rare-type-quality-assessment-v1",
        "identity": identity,
        "status": "pass",
        "quality_gate_passed": True,
        "enablement_eligible": False,
        "enablement_approved": False,
        "reasons": [],
    }
    assessment["assessment_digest"] = hashlib.sha256(_canonical(assessment)).hexdigest()
    path = tmp_path / "assessment.json"
    path.write_text(json.dumps(assessment))
    cfg.discovery.rare_types.enabled = True
    cfg.discovery.rare_types.assessment_path = str(path)
    cfg.discovery.rare_types.assessment_digest = assessment["assessment_digest"]
    return assessment


def _call(cfg, tmp_path):
    _enable(cfg, tmp_path)
    calls = plan_discovery_calls(cfg, list_id=42, now=NOW)
    return next(call for call in calls if call.call_id == RARE_EXTRA_CALL_ID)


class FakeApi:
    timeout_s = 30
    max_retries = 2

    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    def run_search_page_with_raw(self, query, **kwargs):
        self.calls.append((query, kwargs, self.max_retries))
        value = next(self.pages)
        if isinstance(value, Exception):
            raise value
        items = value.get("tweets", [])
        continuation = bool(value.get("has_next_page") or value.get("next_cursor"))
        return b"{}", value, items, continuation, 0


def test_checked_in_config_keeps_seven_call_lane_optional():
    cfg = load_config(REPO / "config.yaml")
    assert cfg.discovery.rare_types.enabled is False
    assert RARE_EXTRA_CALL_ID not in [
        call.call_id for call in plan_discovery_calls(cfg, list_id=42, now=NOW)
    ]
    assert RARE_EXTRA_CALL_ID in _configured_call_ids(cfg)


def test_enabled_identity_plans_one_bounded_non_paginating_call(tmp_path):
    cfg = load_config(REPO / "config.yaml")
    call = _call(cfg, tmp_path)
    assert call.query_string == planned_query_string()
    assert (call.max_results, call.max_pages, call.max_per_page) == (20, 1, 20)
    assert call.daily_credit_ceiling == 6000


def test_identity_mismatch_fails_before_planning_paid_call(tmp_path):
    cfg = load_config(REPO / "config.yaml")
    assessment = _enable(cfg, tmp_path)
    assessment["identity"]["query_version"] = "stale"
    assessment["assessment_digest"] = hashlib.sha256(
        _canonical({k: v for k, v in assessment.items() if k != "assessment_digest"})
    ).hexdigest()
    Path(cfg.discovery.rare_types.assessment_path).write_text(json.dumps(assessment))
    cfg.discovery.rare_types.assessment_digest = assessment["assessment_digest"]
    with pytest.raises(ValueError, match="identity"):
        plan_discovery_calls(cfg, list_id=42, now=NOW)


def test_same_slot_executes_one_zero_retry_page_and_persists_provenance(tmp_path):
    cfg = load_config(REPO / "config.yaml")
    call = _call(cfg, tmp_path)
    api = FakeApi(
        [
            {
                "tweets": [{"id": "rare-1", "text": "I joined Example AI"}],
                "has_next_page": True,
                "next_cursor": "unused",
            }
        ]
    )
    runner = CycleRunner(cfg=cfg, _clock=lambda: NOW)
    first = runner._run_rare_type_search(call, api, now=NOW)
    second = runner._run_rare_type_search(call, api, now=NOW)
    assert first["status"] == "truncated"
    assert second == {"status": "slot_already_reserved", "provider_called": False}
    assert len(api.calls) == 1 and api.calls[0][2] == 0
    assert api.max_retries == 2
    assert api.calls[0][1]["max_pages"] == 1
    run = RareTypeSearchRun.objects.get()
    assert run.query_version == QUERY_VERSION and run.truncated is True
    assert run.request_count == 1
    assert run.reserved_credits == cfg.discovery.rare_types.reserved_credits_per_call
    assert run.daily_budget.search_credits_accounted <= call.daily_credit_ceiling
    hit = RareTypeSearchHit.objects.get()
    assert hit.source_query_version == QUERY_VERSION
    assert hit.source_query_hash == run.query_hash


def test_query_versions_keep_immutable_source_query_rows(tmp_path):
    cfg = load_config(REPO / "config.yaml")
    call = _call(cfg, tmp_path)
    first = CycleRunner(cfg=cfg, _clock=lambda: NOW)._run_rare_type_search(
        call, FakeApi([{"tweets": []}]), now=NOW
    )
    call.query_pack_version = "rare-types-next"
    second = CycleRunner(cfg=cfg, _clock=lambda: NOW)._run_rare_type_search(
        call, FakeApi([{"tweets": []}]), now=NOW + timedelta(minutes=15)
    )
    assert first["status"] == second["status"] == "no_results"
    runs = list(RareTypeSearchRun.objects.select_related("source_query").order_by("id"))
    assert runs[0].source_query_id != runs[1].source_query_id
    assert runs[0].source_query.keywords["query_version"] == QUERY_VERSION
    assert runs[1].source_query.keywords["query_version"] == "rare-types-next"


def test_rendered_query_length_failure_makes_zero_provider_calls(tmp_path):
    cfg = load_config(REPO / "config.yaml")
    call = _call(cfg, tmp_path)
    call.query_string = "x" * 500
    api = FakeApi([])
    result = CycleRunner(cfg=cfg, _clock=lambda: NOW)._run_rare_type_search(
        call, api, now=NOW
    )
    assert result == {"status": "length_cap_exceeded", "provider_called": False}
    assert api.calls == []
    run = RareTypeSearchRun.objects.get()
    assert run.status == RareTypeSearchRun.Status.FAILED
    assert run.request_count == 0
    assert RareTypeSearchDailyBudget.objects.get().search_credits_reserved == 0


def test_error_retains_reservation_and_does_not_retry(tmp_path):
    cfg = load_config(REPO / "config.yaml")
    call = _call(cfg, tmp_path)
    api = FakeApi([RuntimeError("timeout")])
    result = CycleRunner(cfg=cfg, _clock=lambda: NOW)._run_rare_type_search(
        call, api, now=NOW
    )
    assert result["status"] == "error"
    assert len(api.calls) == 1
    run = RareTypeSearchRun.objects.get()
    assert run.status == RareTypeSearchRun.Status.USAGE_UNKNOWN
    budget = RareTypeSearchDailyBudget.objects.get()
    assert budget.search_credits_reserved == 300


def test_scheduled_cycle_call_chain_uses_scheduled_credential_and_no_replay(
    tmp_path, monkeypatch
):
    cfg = load_config(REPO / "config.yaml")
    call = _call(cfg, tmp_path)
    api = FakeApi([{"tweets": []}])
    purposes = []
    monkeypatch.setattr(CycleRunner, "_plan_calls", lambda self: [call])
    monkeypatch.setattr("monitor.cycle._build_brand_index", lambda _models: (None, {}))
    monkeypatch.setattr("monitor.cycle._load_brand_search_terms", dict)
    monkeypatch.setattr(
        "monitor.cycle.TwitterApiClient.from_env",
        lambda purpose: purposes.append(purpose) or api,
    )
    monkeypatch.setattr(
        "scripts.harvest_cost.emit.finalize_and_persist", lambda summary, _api: summary
    )
    first = CycleRunner(cfg=cfg, cycle_kind="scheduled", _clock=lambda: NOW).run()
    second = CycleRunner(cfg=cfg, cycle_kind="scheduled", _clock=lambda: NOW).run()
    assert first["calls"][0]["status"] == "no_results"
    assert second["calls"][0]["status"] == "slot_already_reserved"
    assert len(api.calls) == 1
    assert [purpose.value for purpose in purposes] == ["scheduled", "scheduled"]
    assert RareTypeSearchRun.objects.count() == 1


def test_daily_budget_exhaustion_skips_only_rare_provider_call(tmp_path):
    cfg = load_config(REPO / "config.yaml")
    call = _call(cfg, tmp_path)
    api = FakeApi([])
    runner = CycleRunner(cfg=cfg, _clock=lambda: NOW)
    for index in range(20):
        result = runner._run_rare_type_search(
            call,
            FakeApi([RuntimeError("unknown")]),
            now=NOW + timedelta(minutes=15 * index),
        )
        assert result["provider_called"] is True
    result = runner._run_rare_type_search(call, api, now=NOW + timedelta(hours=5))
    assert result == {"status": "daily_budget_exhausted", "provider_called": False}
    assert api.calls == []
