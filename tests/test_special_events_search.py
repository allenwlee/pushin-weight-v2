"""Selected query pack, shared paid allowance and real scheduler dispatch contracts."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from django.db import close_old_connections

from core.discovery import plan_discovery_calls
from core.models import (
    Brand,
    Post,
    PostEnrichmentState,
    RareTypeSearchDailyBudget,
    RareTypeSearchHit,
    RareTypeSearchRun,
    SearchQuery,
)
from core.rare_type_search import reserve_search_run
from monitor.cycle import CycleRunner, plan_calls_for_cycle
from tests.test_rare_type_cycle import FakeApi, _canonical, _enable
from x_monitor.config import load_config
from x_monitor.rare_type_quality_gate import runtime_assessment_identity
from x_monitor.special_events_search import (
    CALL_IDS,
    GENERAL_QUERY,
    QUERIES,
    QUERY_VERSION,
    RELEASE_QUERY,
    RUN_LANES,
    assessment_query_pack,
    render_query,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
NOW = datetime(2026, 10, 27, 8, 0, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[1]


def enabled_config(tmp_path):
    cfg = load_config(REPO / "config.yaml")
    assessment = _enable(cfg, tmp_path)  # Synthetic test evidence only.
    cfg.discovery.rare_types.query_pack = "special-events-v1"
    assessment["identity"].update(
        runtime_assessment_identity(
            query_version=QUERY_VERSION,
            planner_query=assessment_query_pack(),
            config=cfg.discovery.rare_types.jev,
        )
    )
    assessment.pop("assessment_digest")
    assessment["assessment_digest"] = hashlib.sha256(_canonical(assessment)).hexdigest()
    Path(cfg.discovery.rare_types.assessment_path).write_text(json.dumps(assessment))
    cfg.discovery.rare_types.assessment_digest = assessment["assessment_digest"]
    return cfg


def test_deployed_query_pack_reaches_real_planner(tmp_path, monkeypatch):
    selected = enabled_config(tmp_path)
    lane = selected.discovery.rare_types
    for key, value in {
        "X_MONITOR_DEPLOYMENT_ENVIRONMENT": "production",
        "X_MONITOR_RARE_TYPES_ENABLED": "True",
        "X_MONITOR_RARE_TYPES_TARGETED_EXTRACTION_ENABLED": "True",
        "X_MONITOR_RARE_TYPES_QUERY_PACK": "special-events-v1",
        "X_MONITOR_RARE_TYPES_ASSESSMENT_PATH": lane.assessment_path,
        "X_MONITOR_RARE_TYPES_ASSESSMENT_DIGEST": lane.assessment_digest,
    }.items():
        monkeypatch.setenv(key, value)
    cfg = load_config(REPO / "config.yaml")
    calls = plan_discovery_calls(cfg, list_id=42, now=NOW)
    assert [call.call_id for call in calls] == list(CALL_IDS)
    assert [call.query_string for call in calls] == list(QUERIES.values())
    assert cfg.discovery.rare_types.daily_credit_ceiling == 28800


@pytest.mark.parametrize("blueprint", ["render.yaml", "render-staging.yaml"])
def test_release_blueprints_pin_the_real_assessed_queries(blueprint, monkeypatch):
    services = yaml.safe_load((REPO / blueprint).read_text())["services"]
    selected = 0
    for service in services:
        environment = {
            row["key"]: str(row["value"])
            for row in service.get("envVars", [])
            if "value" in row
        }
        if environment.get("X_MONITOR_RARE_TYPES_ENABLED", "").lower() != "true":
            continue
        selected += 1
        with monkeypatch.context() as context:
            for key, value in environment.items():
                if key.startswith("X_MONITOR_"):
                    context.setenv(key, value)
            cfg = load_config(REPO / "config.yaml")
            calls = plan_discovery_calls(cfg, list_id=42, now=NOW)
            assert [call.call_id for call in calls] == list(CALL_IDS)
            assert [call.query_string for call in calls] == list(QUERIES.values())
    assert selected == (2 if blueprint == "render.yaml" else 1)


def test_exact_selected_pack_fits_provider_renderer_with_eleven_digit_epochs():
    assert [len(QUERIES[key]) for key in CALL_IDS] == [382, 412]
    assert [
        len(render_query(key, since_time=10000000000, until_time=10000000900))
        for key in CALL_IDS
    ] == [428, 458]
    assert RELEASE_QUERY.endswith(" OR url:huggingface.co OR url:hf.co) min_faves:0")
    assert '"is here" OR available OR arrived' in RELEASE_QUERY
    assert all(
        term not in assessment_query_pack()
        for term in (
            "step 5",
            "new release",
            "now releasing",
            "open source",
            "release*",
        )
    )
    assert all(
        term in GENERAL_QUERY
        for term in ('"I joined"', "我加入", "を退職", "招聘", "登壇", "fellowship")
    )


def test_new_pack_refuses_old_assessment_and_keeps_legacy_text_frozen(tmp_path):
    from x_monitor.rare_type_extra_search import planned_query_string

    cfg = load_config(REPO / "config.yaml")
    _enable(cfg, tmp_path)
    original = plan_discovery_calls(cfg, list_id=42, now=NOW)
    assert original[-1].call_id == "RARE_EXTRA"
    assert original[-1].query_string == planned_query_string()
    cfg.discovery.rare_types.query_pack = "special-events-v1"
    with pytest.raises(ValueError, match="identity"):
        plan_discovery_calls(cfg, list_id=42, now=NOW)


@pytest.mark.parametrize("selected_ids", [None, ["SPECIALEVENTS2"]])
def test_stale_assessment_aborts_real_run_before_provider_creation(
    tmp_path, monkeypatch, selected_ids
):
    cfg = load_config(REPO / "config.yaml")
    _enable(cfg, tmp_path)
    cfg.discovery.rare_types.query_pack = "special-events-v1"
    monkeypatch.setattr(
        "monitor.cycle.XClient.from_env",
        lambda purpose: pytest.fail("invalid assessment reached provider construction"),
    )
    result = CycleRunner(cfg=cfg, _backfill_call_ids=selected_ids).run()
    assert result["status"] == "aborted"
    assert any("assessment identity" in error for error in result["errors"])
    assert result["totals"]["n_calls_run"] == 0


@pytest.mark.parametrize("call_id", CALL_IDS)
def test_each_query_keeps_its_provenance_through_real_post_ingestion(tmp_path, call_id):
    cfg = enabled_config(tmp_path)
    Brand.objects.create(
        nickname="_unattributed", display_name="Unattributed", is_sentinel=True
    )
    runner = CycleRunner(cfg=cfg, _clock=lambda: NOW)
    call = next(
        call
        for call in plan_discovery_calls(cfg, list_id=42, now=NOW)
        if call.call_id == call_id
    )
    runner._run_rare_type_search(
        call,
        FakeApi(
            [
                {
                    "tweets": [
                        {
                            "id": "special-post",
                            "text": "A new model has arrived",
                            "created_at": "2026-10-27T07:59:00Z",
                            "author_id": "author-1",
                            "author_handle": "researcher",
                        }
                    ]
                }
            ]
        ),
        now=NOW,
    )
    hit = RareTypeSearchHit.objects.get()
    hit.gate_state = RareTypeSearchHit.GateState.KEPT
    hit.gate_completed_at = NOW
    hit.save(update_fields=["gate_state", "gate_completed_at", "updated_at"])
    assert runner._ingest_kept_rare_type_hits(run_id="special-test") == {
        "selected": 1,
        "persisted": 1,
        "failed": 0,
    }
    hit.refresh_from_db()
    post = Post.objects.get(pk=hit.post_id)
    assert post.source_query_id == call_id
    assert hit.run.lane == RUN_LANES[call_id]
    assert hit.run.source_query.query_text == QUERIES[call_id]
    assert PostEnrichmentState.objects.get(post=post).classification_status == "pending"


@pytest.mark.parametrize("call_id", CALL_IDS)
def test_staging_acceptance_selects_one_new_query_with_existing_bounds(
    tmp_path, call_id
):
    from monitor.staging_acceptance import (
        evaluate_staging_acceptance,
        prepare_staging_acceptance,
    )
    from scripts.staging_refresh.policy import load_policy
    from tests.test_staging_harvest_acceptance import (
        POLICY_PATH,
        _accepted_stats,
        _Connection,
        _environment,
        _options,
    )

    prepared = prepare_staging_acceptance(
        call_id,
        options=_options(),
        cfg=enabled_config(tmp_path),
        environ=_environment(TYPESAFE_API_KEY="fixture"),
        database=_Connection(),
        policy=load_policy(POLICY_PATH),
    )
    assert prepared.profile.selected_call == call_id
    assert prepared.config.discovery.rare_types.jev.staging_decisions_per_cycle == 5
    assert prepared.profile.as_dict()["caps"]["hf_requests"] == 1
    stats = _accepted_stats()
    stats["calls"][0].update(
        call_id=call_id, status="stored", normalized_count=2, provider_called=True,
        raw_count=2, cursor_advanced=False, run_id=1, request_count=1,
        normalization_errors=0, reserved_credits=300, estimated_credits=30,
    )
    assert evaluate_staging_acceptance(prepared, stats).status == "accepted"


def test_real_planner_scheduled_runner_dispatches_two_once_then_one_decision_drain(
    tmp_path, monkeypatch
):
    cfg = enabled_config(tmp_path)
    # Only ordinary searches are replaced; discovery planning and CycleRunner.run are real.
    monkeypatch.setattr("monitor.cycle.plan_calls", lambda *args, **kwargs: [])
    monkeypatch.setattr("monitor.cycle._build_brand_index", lambda models: (None, {}))
    monkeypatch.setattr("monitor.cycle._load_brand_search_terms", dict)
    api = FakeApi([{"tweets": []}, {"tweets": []}])
    purposes, drains = [], []
    monkeypatch.setattr(
        "monitor.cycle.XClient.from_env",
        lambda purpose: purposes.append(purpose.value) or api,
    )
    monkeypatch.setattr(
        "scripts.harvest_cost.emit.finalize_and_persist", lambda summary, api: summary
    )
    monkeypatch.setattr(
        CycleRunner,
        "_drain_rare_type_hits",
        lambda self, **kwargs: drains.append(len(api.calls)) or {"selected": 0},
    )
    assert [call.call_id for call in plan_calls_for_cycle(cfg)] == list(CALL_IDS)
    first = CycleRunner(cfg=cfg, cycle_kind="scheduled", _clock=lambda: NOW).run()
    duplicate = CycleRunner(cfg=cfg, cycle_kind="scheduled", _clock=lambda: NOW).run()
    assert [call["call_id"] for call in first["calls"]] == list(CALL_IDS)
    assert [call["status"] for call in duplicate["calls"]] == [
        "slot_already_reserved"
    ] * 2
    assert [call[0] for call in api.calls] == [GENERAL_QUERY, RELEASE_QUERY]
    assert [call[2] for call in api.calls] == [0, 0]
    assert all(call[1]["max_pages"] == 1 for call in api.calls)
    assert purposes == ["scheduled", "scheduled"]
    assert drains == [2, 2]
    assert first["rare_types"]["n_provider_attempts"] == 2
    assert first["rare_types"]["search_credits_estimated"] == 30
    assert duplicate["rare_types"]["n_provider_attempts"] == 0
    assert RareTypeSearchRun.objects.count() == 2
    budget = RareTypeSearchDailyBudget.objects.get()
    assert budget.lane == "rare_types"
    assert budget.search_credits_reserved == 0
    assert budget.search_credits_accounted == 30


def test_query_windows_are_independent_and_roll_over_midnight_without_new_allowance(
    tmp_path,
):
    cfg = enabled_config(tmp_path)
    calls = plan_discovery_calls(cfg, list_id=42, now=NOW)
    runner = CycleRunner(cfg=cfg)
    start = NOW.replace(hour=23, minute=45)
    api = FakeApi([{"tweets": []}] * 5)
    runner._run_rare_type_search(calls[0], api, now=start)
    runner._run_rare_type_search(calls[1], api, now=start + timedelta(minutes=3))
    runner._run_rare_type_search(calls[0], api, now=start + timedelta(minutes=15))
    runner._run_rare_type_search(calls[1], api, now=start + timedelta(minutes=18))
    for index, lane in enumerate(RUN_LANES.values()):
        runs = list(
            RareTypeSearchRun.objects.filter(lane=lane).order_by("attempted_end")
        )
        assert (
            runs[1].window_start
            == runs[0].window_end
            == start + timedelta(minutes=3 * index)
        )
    assert RareTypeSearchDailyBudget.objects.count() == 2
    assert list(
        RareTypeSearchDailyBudget.objects.order_by("usage_date").values_list(
            "search_credits_accounted", flat=True
        )
    ) == [30, 30]


def test_concurrent_queries_share_one_last_reservation_including_legacy_spend():
    budget = RareTypeSearchDailyBudget.objects.create(
        lane="rare_types", usage_date=NOW.date(), search_credits_accounted=28500
    )
    queries = {
        key: SearchQuery.objects.create(query_id=key, query_text=query)
        for key, query in QUERIES.items()
    }

    def reserve(key):
        close_old_connections()
        try:
            return reserve_search_run(
                lane=RUN_LANES[key],
                slot_start=NOW,
                source_query=queries[key],
                query_string=QUERIES[key],
                query_hash=hashlib.sha256(QUERIES[key].encode()).hexdigest(),
                query_version=QUERY_VERSION,
                environment="test",
                release_sha="test",
                now=NOW,
                daily_credit_limit=28800,
            ).created
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, CALL_IDS)) == [False, True]
    budget.refresh_from_db()
    assert budget.search_credits_reserved + budget.search_credits_accounted == 28800
    assert RareTypeSearchDailyBudget.objects.count() == 1


@pytest.mark.parametrize("call_id", CALL_IDS)
@pytest.mark.parametrize("truncated", [False, True])
def test_discovery_cycle_preserves_inserted_cohort_for_bounded_acceptance(
    tmp_path, monkeypatch, call_id, truncated
):
    """A paid discovery page must reach the same persisted-ID acceptance path."""
    from types import SimpleNamespace

    from monitor.post_enrichment import ENRICHMENT_COUNT_KEYS
    from monitor.staging_acceptance import (
        BoundedXClient,
        evaluate_staging_acceptance,
        prepare_staging_acceptance,
    )
    from scripts.staging_refresh.policy import load_policy
    from tests.test_staging_harvest_acceptance import (
        POLICY_PATH,
        _Connection,
        _environment,
        _options,
    )

    prepared = prepare_staging_acceptance(
        call_id, options=_options(), cfg=enabled_config(tmp_path),
        environ=_environment(TYPESAFE_API_KEY="fixture"), database=_Connection(),
        policy=load_policy(POLICY_PATH),
    )
    Brand.objects.create(nickname="_unattributed", display_name="Unattributed", is_sentinel=True)
    items = [{"id": f"discovery-{i}", "text": "An AI model arrived", "author_id": f"researcher-{i}",
                  "author_handle": f"researcher{i}", "created_at": NOW.isoformat()} for i in range(2)]
    api = FakeApi([{"tweets": items, "has_next_page": truncated}])
    monkeypatch.setenv("RENDER_SERVICE_NAME", "pushinweight-staging-harvest")
    monkeypatch.setattr("monitor.cycle._build_brand_index", lambda _models: (None, {}))
    monkeypatch.setattr("monitor.cycle._load_brand_search_terms", dict)
    monkeypatch.setattr("monitor.cycle.XClient.from_env", lambda purpose: BoundedXClient(api))
    monkeypatch.setattr("scripts.harvest_cost.emit.finalize_and_persist", lambda summary, _api: summary)

    class Gate:
        def process_hit(self, hit_id, **kwargs):
            RareTypeSearchHit.objects.filter(pk=hit_id).update(gate_state="kept", gate_completed_at=NOW)
            return SimpleNamespace(outcome="kept")

    monkeypatch.setattr("monitor.cycle.build_jev_decision_gate", lambda *a, **kw: Gate())
    seen = []

    def completed_post_fetch(self, kept_posts, **kwargs):
        # Model transports are outside this regression: inspect the actual persisted cohort.
        ids = self._unclaimed_post_fetch_cohort(kept_posts)["inserted_post_ids"]
        seen.extend(ids)
        assert set(ids) <= set(Post.objects.values_list("pk", flat=True))
        counts = dict.fromkeys(ENRICHMENT_COUNT_KEYS, 0)
        for key in ("n_enrichment_claimed", "n_enrichment_claimed_current_cycle",
                    "n_enrichment_succeeded", "n_enrichment_succeeded_current_cycle"):
            counts[key] = len(ids)
        return {**counts, "inserted_post_ids": ids,
                "enrichment_current_cycle_post_ids": ids, "enrichment_carryover_post_ids": [],
                "enrichment_state_facts": [{"post_id": pk, "lane": "current_cycle",
                    "translation_status": "succeeded", "classification_status": "succeeded",
                    "output_complete": True} for pk in ids]}

    monkeypatch.setattr(CycleRunner, "_run_post_fetch", completed_post_fetch)
    monkeypatch.setattr(CycleRunner, "_request_synthesis_prewarm", lambda *a, **kw: {})
    monkeypatch.setattr("monitor.cycle.drain_pending_verifications",
                        lambda **kw: SimpleNamespace(attempted=0, resolved=0, deferred=0))
    runner = CycleRunner(cfg=prepared.config, _backfill_call_ids=[call_id], _clock=lambda: NOW)
    stats = runner.run()
    assert len(api.calls) == 1
    assert stats["totals"]["n_results"] == 2
    assert stats["totals"]["n_inserted"] == 2
    assert seen == ["discovery-0", "discovery-1"]
    evaluation = evaluate_staging_acceptance(prepared, stats)
    assert evaluation.status == "accepted", (evaluation, stats["errors"])
    assert evaluation.selected_call["coverage_complete"] is (not truncated)


@pytest.mark.parametrize("status", ["stored", "truncated"])
@pytest.mark.parametrize("invalid", [
    {"raw_count": 21}, {"normalized_count": 6}, {"estimated_credits": 301},
    {"reserved_credits": 301}, {"run_id": None}, {"cursor_advanced": True},
    {"normalization_errors": 1}, {"raw_count": 1}, {"request_count": 2},
])
def test_discovery_acceptance_rejects_invalid_page_evidence(tmp_path, status, invalid):
    from monitor.staging_acceptance import (
        evaluate_staging_acceptance,
        prepare_staging_acceptance,
    )
    from scripts.staging_refresh.policy import load_policy
    from tests.test_staging_harvest_acceptance import (
        POLICY_PATH,
        _accepted_stats,
        _Connection,
        _environment,
        _options,
    )
    prepared = prepare_staging_acceptance(
        "SPECIALEVENTS2", options=_options(), cfg=enabled_config(tmp_path),
        environ=_environment(TYPESAFE_API_KEY="fixture"), database=_Connection(),
        policy=load_policy(POLICY_PATH),
    )
    stats = _accepted_stats()
    stats["calls"][0].update(call_id="SPECIALEVENTS2", status=status, normalized_count=2,
        raw_count=2, provider_called=True, cursor_advanced=False, run_id=1,
        normalization_errors=0, request_count=1, reserved_credits=300, estimated_credits=30)
    stats["calls"][0].update(invalid)
    assert evaluate_staging_acceptance(prepared, stats).status == "failed"
