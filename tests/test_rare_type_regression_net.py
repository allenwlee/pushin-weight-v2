"""Production-call-chain regression net for the optional rare-type lane."""

from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.db import DatabaseError, close_old_connections

from core.discovery import RARE_EXTRA_CALL_ID, plan_discovery_calls
from core.models import (
    Brand,
    BrandDiscoveryCandidate,
    BrandDiscoveryCandidateToken,
    BrandDiscoveryCandidateTokenEvidence,
    ModelRelease,
    ModelReleaseEvidence,
    Post,
    PostEnrichmentState,
    RareTypeSearchDailyBudget,
    RareTypeSearchHit,
    RareTypeSearchRun,
)
from monitor.cycle import CycleRunner, plan_calls_for_cycle
from monitor.harvest_summary import (
    HARVEST_SUMMARY_PREFIX,
    build_summary_envelope,
    parse_summary_line,
    serialize_summary_envelope,
)
from monitor.rare_type_telemetry import build_rare_type_cycle_summary
from x_monitor.config import load_config
from x_monitor.rare_type_extra_search import QUERY_VERSION, planned_query_string

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
REPO = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 24, 8, 7, tzinfo=UTC)


def _canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _enabled_call(tmp_path: Path):
    cfg = load_config(REPO / "config.yaml")
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
        "role_opening_threshold": format(jev.role_opening_threshold, "f"),
        "attendance_event_threshold": format(
            jev.attendance_event_threshold, "f"
        ),
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
    call = next(
        call
        for call in plan_discovery_calls(cfg, list_id=42, now=NOW)
        if call.call_id == RARE_EXTRA_CALL_ID
    )
    return cfg, call


class FakeApi:
    timeout_s = 30
    max_retries = 2

    def __init__(self, response=None, error: Exception | None = None):
        self.response = response or {"tweets": []}
        self.error = error
        self.calls = []
        self._lock = threading.Lock()

    def run_search_page_with_raw(self, query, **kwargs):
        with self._lock:
            self.calls.append((query, kwargs))
        if self.error is not None:
            raise self.error
        items = self.response.get("tweets", [])
        return b"{}", self.response, items, False, 0


def _patch_cycle_shell(monkeypatch, *, call, api, drain=True, post_fetch=True):
    monkeypatch.setattr(CycleRunner, "_plan_calls", lambda self: [call])
    monkeypatch.setattr("monitor.cycle._resolve_enabled_models", lambda *_a: [])
    monkeypatch.setattr("monitor.cycle._build_brand_index", lambda *_a: (None, {}))
    monkeypatch.setattr("monitor.cycle._load_brand_search_terms", dict)
    monkeypatch.setattr("monitor.cycle._resolve_x_monitor_list_id", lambda *_a: None)
    monkeypatch.setattr(
        "monitor.cycle.TwitterApiClient.from_env", lambda _purpose: api
    )
    monkeypatch.setattr(
        "scripts.harvest_cost.emit.finalize_and_persist",
        lambda _summary, _api=None: Path("provider-free-summary.json"),
    )
    monkeypatch.setattr(
        "monitor.metrics_refresh.run_metrics_refresh", lambda *_a, **_kw: {}
    )
    monkeypatch.setattr(
        CycleRunner, "_request_synthesis_prewarm", lambda *_a, **_kw: {}
    )
    if drain:
        monkeypatch.setattr(
            CycleRunner,
            "_drain_rare_type_hits",
            lambda *_a, **_kw: {"selected": 0, "kept": 0, "junk": 0, "pending": 0},
        )
    if post_fetch:
        monkeypatch.setattr(CycleRunner, "_run_post_fetch", lambda *_a, **_kw: {})


def test_ten_concurrent_cycle_starts_make_one_physical_paid_search(
    tmp_path, monkeypatch
):
    cfg, call = _enabled_call(tmp_path)
    api = FakeApi()
    _patch_cycle_shell(monkeypatch, call=call, api=api)

    def run_one(_index):
        close_old_connections()
        try:
            return CycleRunner(cfg=cfg, _clock=lambda: NOW).run()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=10) as pool:
        summaries = list(pool.map(run_one, range(10)))

    assert len(api.calls) == 1
    assert RareTypeSearchRun.objects.count() == 1
    assert sum(
        row["calls"][0]["provider_called"] for row in summaries
    ) == 1
    assert {
        row["calls"][0]["status"] for row in summaries
    } == {"no_results", "slot_already_reserved"}


def test_reservation_database_failure_makes_zero_provider_calls(tmp_path, monkeypatch):
    cfg, call = _enabled_call(tmp_path)
    api = FakeApi()
    _patch_cycle_shell(monkeypatch, call=call, api=api)
    monkeypatch.setattr(
        "monitor.cycle.reserve_search_run",
        lambda **_kwargs: (_ for _ in ()).throw(DatabaseError("database unavailable")),
    )

    summary = CycleRunner(cfg=cfg, _clock=lambda: NOW).run()

    assert api.calls == []
    assert summary["calls"][0]["status"] == "reservation_failed"
    assert summary["calls"][0]["provider_called"] is False
    assert summary["rare_types"]["n_provider_attempts"] == 0


def test_paid_return_database_failure_records_gap_and_unknown_usage(
    tmp_path, monkeypatch
):
    cfg, call = _enabled_call(tmp_path)
    api = FakeApi(
        response={"tweets": [{"id": "db-gap", "text": "I joined Example AI"}]}
    )
    _patch_cycle_shell(monkeypatch, call=call, api=api)
    monkeypatch.setattr(
        "monitor.cycle.persist_hit_batch",
        lambda *_a, **_kw: (_ for _ in ()).throw(DatabaseError("insert interrupted")),
    )

    summary = CycleRunner(cfg=cfg, _clock=lambda: NOW).run()

    run = RareTypeSearchRun.objects.get()
    assert len(api.calls) == 1
    assert summary["calls"][0]["status"] == "error"
    assert run.status == RareTypeSearchRun.Status.USAGE_UNKNOWN
    assert run.has_coverage_gap is True
    assert run.complete_start is None
    assert summary["rare_types"]["n_search_usage_unknown"] == 1


def test_jev_outage_leaves_paid_hit_pending_and_unpublished(tmp_path, monkeypatch):
    cfg, call = _enabled_call(tmp_path)
    api = FakeApi(
        response={"tweets": [{"id": "jev-pending", "text": "I joined Example AI"}]}
    )
    _patch_cycle_shell(monkeypatch, call=call, api=api, drain=False)
    monkeypatch.setattr(
        "monitor.cycle.build_jev_decision_gate",
        lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("Jev unavailable")),
    )

    summary = CycleRunner(cfg=cfg, _clock=lambda: NOW).run()

    hit = RareTypeSearchHit.objects.get()
    assert hit.gate_state == RareTypeSearchHit.GateState.DECISION_PENDING
    assert hit.post_id is None
    assert not Post.objects.filter(pk="jev-pending").exists()
    assert summary["rare_type_ingestion"]["pending"] == 1
    assert summary["rare_types"]["n_pending_hits_global"] == 1


def test_interrupted_post_insert_replays_saved_hit_without_second_search(
    tmp_path, monkeypatch
):
    cfg, call = _enabled_call(tmp_path)
    api = FakeApi(
        response={
            "tweets": [
                {
                    "id": "resume-post",
                    "text": "Example AI released Resume Model",
                    "created_at": NOW.isoformat(),
                    "author_id": "resume-author",
                }
            ]
        }
    )
    _patch_cycle_shell(monkeypatch, call=call, api=api, drain=False)
    Brand.objects.create(
        nickname="_unattributed", display_name="Unattributed", is_sentinel=True
    )
    monkeypatch.setattr(
        CycleRunner,
        "_attribute_items",
        lambda self, items, *_a, **_kw: [
            item.update(_unattributed=True) for item in items
        ],
    )

    class KeepGate:
        def process_hit(self, hit_id, **_kwargs):
            RareTypeSearchHit.objects.filter(pk=hit_id).update(
                gate_state=RareTypeSearchHit.GateState.KEPT,
                gate_completed_at=NOW,
            )
            return SimpleNamespace(outcome="kept")

    monkeypatch.setattr(
        "monitor.cycle.build_jev_decision_gate", lambda *_a, **_kw: KeepGate()
    )
    original_persist = CycleRunner._persist_items
    persistence_calls = 0

    def interrupted_once(self, items):
        nonlocal persistence_calls
        persistence_calls += 1
        if persistence_calls == 1:
            return 0, 0, 0, 1
        return original_persist(self, items)

    monkeypatch.setattr(CycleRunner, "_persist_items", interrupted_once)

    first = CycleRunner(cfg=cfg, _clock=lambda: NOW).run()
    second = CycleRunner(cfg=cfg, _clock=lambda: NOW).run()

    hit = RareTypeSearchHit.objects.get()
    assert len(api.calls) == 1
    assert first["rare_type_ingestion"]["ingestion_failed"] == 1
    assert second["calls"][0]["status"] == "slot_already_reserved"
    assert second["rare_type_ingestion"]["ingestion_persisted"] == 1
    assert hit.post_id == "resume-post"


def test_daily_budget_race_permits_all_ninety_six_scheduled_attempts(
    tmp_path,
):
    cfg, call = _enabled_call(tmp_path)
    api = FakeApi(error=RuntimeError("ambiguous provider failure"))
    day_start = NOW.replace(hour=0, minute=0, second=0, microsecond=0)

    def run_slot(index):
        close_old_connections()
        try:
            now = day_start + timedelta(minutes=15 * index)
            return CycleRunner(cfg=cfg, _clock=lambda: now)._run_rare_type_search(
                call, api, now=now
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(run_slot, range(96)))

    assert len(api.calls) == 96
    assert sum(result["provider_called"] for result in results) == 96
    assert all(result["status"] != "daily_budget_exhausted" for result in results)
    budget = RareTypeSearchDailyBudget.objects.get()
    assert budget.search_credits_reserved == 28800


def test_shared_deadline_defers_jev_without_a_gate_provider_call(
    tmp_path, monkeypatch
):
    cfg, call = _enabled_call(tmp_path)
    api = FakeApi(
        response={"tweets": [{"id": "deadline-hit", "text": "I joined Example AI"}]}
    )
    _patch_cycle_shell(monkeypatch, call=call, api=api, drain=False)
    gate_provider_calls = 0

    class Deadline:
        deadline_at = 0.0

        def can_start(self, _seconds):
            return False

    deadline = Deadline()
    monkeypatch.setattr(type(cfg.harvest), "start_deadline", lambda _self: deadline)

    class Gate:
        def process_hit(self, _hit_id, *, shared_deadline_monotonic, **_kwargs):
            nonlocal gate_provider_calls
            assert shared_deadline_monotonic == deadline.deadline_at
            if not deadline.can_start(1):
                return SimpleNamespace(outcome="pending")
            gate_provider_calls += 1
            raise AssertionError("exhausted deadline reached Jev transport")

    monkeypatch.setattr("monitor.cycle.build_jev_decision_gate", lambda *_a, **_kw: Gate())

    summary = CycleRunner(cfg=cfg, _clock=lambda: NOW).run()

    assert gate_provider_calls == 0
    assert summary["rare_type_ingestion"]["pending"] == 1
    assert RareTypeSearchHit.objects.get().post_id is None


def test_hf_drain_runs_after_post_persistence_and_classification_with_bound(
    tmp_path, monkeypatch
):
    cfg, call = _enabled_call(tmp_path)
    cfg.discovery.rare_types.product_verification_enabled = True
    cfg.discovery.rare_types.product_verification_normal_requests = 3
    api = FakeApi(
        response={
            "tweets": [
                {
                    "id": "hf-order",
                    "text": "Example AI released Model One",
                    "created_at": NOW.isoformat(),
                    "author_id": "hf-author",
                }
            ]
        }
    )
    _patch_cycle_shell(monkeypatch, call=call, api=api, drain=False, post_fetch=False)
    Brand.objects.create(
        nickname="_unattributed", display_name="Unattributed", is_sentinel=True
    )
    monkeypatch.setattr(
        CycleRunner,
        "_attribute_items",
        lambda self, items, *_a, **_kw: [
            item.update(_unattributed=True) for item in items
        ],
    )

    class KeepGate:
        def process_hit(self, hit_id, **_kwargs):
            RareTypeSearchHit.objects.filter(pk=hit_id).update(
                gate_state=RareTypeSearchHit.GateState.KEPT,
                gate_completed_at=NOW,
            )
            return SimpleNamespace(outcome="kept")

    monkeypatch.setattr(
        "monitor.cycle.build_jev_decision_gate", lambda *_a, **_kw: KeepGate()
    )
    order = []

    def post_fetch(_self, *_args, **_kwargs):
        order.append("post_fetch")
        PostEnrichmentState.objects.filter(post_id="hf-order").update(
            translation_status=PostEnrichmentState.Status.SUCCEEDED,
            classification_status=PostEnrichmentState.Status.SUCCEEDED,
        )
        return {"n_enrichment_succeeded": 1}

    monkeypatch.setattr(CycleRunner, "_run_post_fetch", post_fetch)

    def hf_drain(*, max_requests, deadline):
        order.append("hf")
        assert max_requests == 3
        assert deadline is not None
        assert Post.objects.filter(pk="hf-order").exists()
        state = PostEnrichmentState.objects.get(post_id="hf-order")
        assert state.classification_status == PostEnrichmentState.Status.SUCCEEDED
        return SimpleNamespace(attempted=1, resolved=0, deferred=1)

    monkeypatch.setattr("monitor.cycle.drain_pending_verifications", hf_drain)

    summary = CycleRunner(cfg=cfg, _clock=lambda: NOW).run()

    assert len(api.calls) == 1
    assert order == ["post_fetch", "hf"]
    assert summary["product_verification"] == {
        "attempted": 1,
        "resolved": 0,
        "deferred": 1,
    }


def test_feature_off_keeps_exact_seven_call_shape():
    cfg = load_config(REPO / "config.yaml")

    assert cfg.discovery.rare_types.enabled is False
    assert [call.call_id for call in plan_calls_for_cycle(cfg)] == [
        "A",
        "B1",
        "C1",
        "C2",
        "C3",
        "B2",
        "B3",
    ]


def test_counts_only_summary_excludes_raw_text_queries_and_credentials():
    envelope = build_summary_envelope(
        {
            "run_id": "rare-redaction",
            "calls": [
                {
                    "call_id": "RARE_EXTRA",
                    "provider_called": True,
                    "n_results": 1,
                    "estimated_credits": 15,
                    "query_string": "secret release text",
                    "original_text": "verbatim private-looking post",
                    "headers": {"Authorization": "Bearer fake-token"},
                }
            ],
            "rare_types": {
                "schema_version": "1",
                "n_provider_attempts": 1,
                "n_raw_paid_results": 1,
                "n_normalized_hits": 1,
                "search_credits_estimated": 15,
            },
        },
        service_id="cron-test",
        deploy_sha="abc123",
    )

    line = serialize_summary_envelope(envelope)
    parsed = parse_summary_line(line)

    assert line.startswith(HARVEST_SUMMARY_PREFIX)
    assert "secret release text" not in line
    assert "verbatim private-looking post" not in line
    assert "fake-token" not in line
    assert parsed["summary"]["rare_types"]["n_raw_paid_results"] == 1


def test_lane_telemetry_separates_records_evidence_tokens_and_latency(
    tmp_path,
):
    cfg, call = _enabled_call(tmp_path)
    api = FakeApi(
        response={"tweets": [{"id": "telemetry-post", "text": "Model T released"}]}
    )
    search = CycleRunner(cfg=cfg, _clock=lambda: NOW)._run_rare_type_search(
        call, api, now=NOW
    )
    hit = RareTypeSearchHit.objects.get()
    brand = Brand.objects.create(nickname="telemetry", display_name="Telemetry AI")
    post = Post.objects.create(tweet_id="telemetry-post", text="Model T released")
    hit.gate_state = RareTypeSearchHit.GateState.KEPT
    hit.post = post
    hit.gate_completed_at = NOW + timedelta(seconds=1)
    hit.post_persisted_at = NOW + timedelta(seconds=2)
    hit.classified_at = NOW + timedelta(seconds=3)
    hit.extracted_at = NOW + timedelta(seconds=4)
    hit.first_visible_at = NOW + timedelta(seconds=5)
    hit.save()
    release = ModelRelease.objects.create(
        brand=brand,
        observed_model_name="Model T",
        version="1",
        release_channel="stable",
        release_value="2026-09-24",
        release_precision="day",
        release_identity="telemetry-model-t",
        first_seen_at=NOW,
        last_seen_at=NOW,
        extraction_version="model-release-extraction-v1",
    )
    ModelReleaseEvidence.objects.create(
        release=release,
        source_post=post,
        observed_at=NOW,
        observed_claim={"model_name": "Model T"},
        evidence_hash="telemetry-release-evidence",
        extraction_version="model-release-extraction-v1",
    )
    candidate = BrandDiscoveryCandidate.objects.create(
        observed_name="Unknown Telemetry Lab",
        aliases=[],
        candidate_handles=[],
        source_post=post,
        source_identities=[],
        candidate_identity="unknown-telemetry-lab",
        first_observed_at=NOW,
        last_observed_at=NOW,
    )
    token = BrandDiscoveryCandidateToken.objects.create(
        candidate=candidate,
        form="Unknown Telemetry Lab",
        kind="spelling",
        script="latn",
        first_observed_at=NOW,
        last_observed_at=NOW,
    )
    BrandDiscoveryCandidateTokenEvidence.objects.create(
        token=token,
        source_hit=hit,
        source_post=post,
        rare_type="model_releases",
        observed_at=NOW,
    )
    second_search = CycleRunner(
        cfg=cfg, _clock=lambda: NOW + timedelta(minutes=15)
    )._run_rare_type_search(call, api, now=NOW + timedelta(minutes=15))
    second_hit = RareTypeSearchHit.objects.get(run_id=second_search["run_id"])
    second_hit.gate_state = RareTypeSearchHit.GateState.KEPT
    second_hit.post = post
    second_hit.gate_completed_at = NOW + timedelta(minutes=15, seconds=1)
    second_hit.post_persisted_at = NOW + timedelta(minutes=15, seconds=2)
    second_hit.classified_at = NOW + timedelta(minutes=15, seconds=3)
    second_hit.extracted_at = NOW + timedelta(minutes=15, seconds=4)
    second_hit.first_visible_at = NOW + timedelta(minutes=15, seconds=5)
    second_hit.save()

    telemetry = build_rare_type_cycle_summary(
        {
            "calls": [
                {
                    "call_id": "RARE_EXTRA",
                    "run_id": search["run_id"],
                    "provider_called": True,
                    "raw_count": 1,
                    "normalized_count": 1,
                },
                {
                    "call_id": "RARE_EXTRA",
                    "run_id": second_search["run_id"],
                    "provider_called": True,
                    "raw_count": 1,
                    "normalized_count": 1,
                },
            ]
        }
    )

    assert telemetry is not None
    assert telemetry["n_raw_paid_results"] == 2
    assert telemetry["n_posts_persisted"] == 1
    assert telemetry["n_posts_classified"] == 1
    assert telemetry["n_posts_extracted"] == 1
    assert telemetry["n_posts_visible"] == 1
    assert telemetry["n_canonical_records"] == 1
    assert telemetry["n_evidence_attachments"] == 1
    assert telemetry["n_model_releases"] == 1
    assert telemetry["n_model_release_evidence"] == 1
    assert telemetry["n_unknown_tokens"] == 1
    assert telemetry["n_unknown_token_evidence"] == 1
    assert telemetry["fetch_to_visible_p95_ms"] == 5000
