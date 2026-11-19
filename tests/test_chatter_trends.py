"""Hourly discovery preserves physical calls and accepted ranking evidence."""

import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from core.models import CollectionRequest, OriginalContentCall, OriginalContentRun
from monitor.editorial.config import Route
from tests.test_chatter_chain import chain_config

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def trends_config():
    cfg = chain_config()
    return cfg.model_copy(update={"chatter": cfg.chatter.model_copy(update={
        "discovery_lane": "personalized-trends-v1",
        "ranking": Route(model="openai/gpt-6-sol", endpoint="https://openrouter.ai/api/v1/chat/completions",
                         key_env="OPENROUTER_API_KEY", reasoning="medium", max_output_tokens=8192,
                         input_usd_per_million=2.5, output_usd_per_million=10),
    })})


def official_response(count=12, *, status=200, headers=None):
    return SimpleNamespace(status_code=status, headers=headers or {}, content=json.dumps({
        "data": [{"trend_name": f"Original headline {i}", "post_count": i,
                  "category": "Technology", "trending_since": "verbatim-clock"}
                 for i in range(1, count + 1)]}).encode())


def rank_wire(count=12):
    return 200, json.dumps({"id": "rank-fixture", "model": "openai/gpt-6-sol",
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
            "ranked_stories": [{"title": f"Story {i}", "headline_ids": [i], "reason": "A lead."}
                               for i in range(1, count + 1)]})}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 100, "cost": 0.053301},
    }).encode()


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture-only")
    return trends_config()


def start(cfg):
    from monitor.editorial.chatter_trends import reserve_due_slot
    return reserve_due_slot("fixture-cycle", timezone.now(), cfg=cfg, purpose="on-demand")[0]


def discover(run, cfg, response=None, transport=None):
    from monitor.editorial.chatter_trends import discover_trends
    store = SimpleNamespace(access_token=lambda: "fixture-only", check_access_expiry=lambda: None,
                            revision=7, redactions=set())
    official = Mock(return_value=response or official_response())
    ranker = transport or Mock(return_value=rank_wire())
    return discover_trends(run.pk, cfg=cfg, official_get=official, token_store=store,
                           transport=ranker), official, ranker


def test_four_ticks_own_one_hour_before_delivery_and_broker_loss_is_recoverable(configured, django_capture_on_commit_callbacks):
    from monitor.editorial.chatter_trends import TRENDS_SCOPE
    from monitor.editorial.dispatch import (
        dispatch_chatter_cycle,
        recover_chatter_starts,
    )
    task = Mock()
    task.apply_async.side_effect = ConnectionError("fixture dropped delivery")
    at = timezone.now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    with patch("monitor.editorial.dispatch.load_editorial_config", return_value=configured):
        for offset in (0, 15, 30, 45):
            with django_capture_on_commit_callbacks(execute=True):
                dispatch_chatter_cycle(f"cycle-{offset}", at + timedelta(minutes=offset),
                                       kind="scheduled", dry_run=False, task=task)
        assert OriginalContentRun.objects.filter(scope_key=TRENDS_SCOPE).count() == 1
        assert task.apply_async.call_count == 1
        task.apply_async.side_effect = None
        run = OriginalContentRun.objects.get(scope_key=TRENDS_SCOPE)
        run.outcome["trends"]["last_enqueue_at"] = (timezone.now() - timedelta(seconds=61)).isoformat()
        run.save(update_fields=["outcome"])
        with django_capture_on_commit_callbacks(execute=True):
            recovered = recover_chatter_starts(cfg=configured, task=task)
        assert recovered["enqueued"] == 1
        assert task.apply_async.call_args.kwargs["args"][0] == "discover"


def test_official_archive_and_one_exact_rank_request_replay_without_credentials(configured, monkeypatch):
    from monitor.editorial.chatter_trends import ranking_prefix, read_ranked_batch
    run = start(configured)
    result, official, ranker = discover(run, configured)
    assert result["status"] == "ranked", result
    body = ranker.call_args.args[2]
    assert body["messages"] == [{"role": "user", "content": ranking_prefix() + "HEADLINES:\n" +
        json.dumps([{"id": i, "headline": f"Original headline {i}"} for i in range(1, 13)], ensure_ascii=False, indent=2)}]
    assert body["max_tokens"] == 8192 and body["reasoning"] == {"effort": "medium"}
    assert "tools" not in body and body["provider"]["allow_fallbacks"] is False
    request = CollectionRequest.objects.get(attempt__run__content_run=run)
    assert request.archive_id and request.http_method == "GET"
    assert request.estimated_usd is None  # Official-X pricing is unknown, not TwitterAPI.
    assert request.reserved_usd == Decimal(str(configured.chatter.source_request_reservation_usd))
    call = OriginalContentCall.objects.get(run=run)
    assert call.actual_usd == Decimal("0.053301")
    assert call.response_payload["usage"]["provider_reported_cost_usd"] == "0.053301"
    batch = read_ranked_batch(run.pk)
    assert len(batch["ranked_stories"]) == 12 and len(batch["leads"]) == 10
    assert batch["leads"][0]["headlines"][0]["trend_name"] == "Original headline 1"
    monkeypatch.delenv("OPENROUTER_API_KEY")
    again, _, _ = discover(run, configured, transport=Mock(side_effect=AssertionError("resend")))
    assert again["status"] == "ranked" and official.call_count == ranker.call_count == 1


def test_discovery_uses_the_encrypted_access_only_credential_without_refresh(configured, monkeypatch):
    import time

    from cryptography.fernet import Fernet

    from core.official_company_credentials import OwnerTokenStore
    from monitor.editorial.chatter_trends import discover_trends

    monkeypatch.setenv("PUSHINWEIGHT_X_LIST_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("PUSHINWEIGHT_X_LIST_CLIENT_ID", "fixture-client")
    monkeypatch.setenv("PUSHINWEIGHT_X_LIST_ACCESS_ONLY", "true")
    monkeypatch.delenv("PUSHINWEIGHT_X_LIST_CLIENT_SECRET", raising=False)
    OwnerTokenStore.from_env().provision(access_token="snapshot-access", expires_at=time.time() + 600)
    run = start(configured)
    official = Mock(return_value=official_response())
    result = discover_trends(run.pk, cfg=configured, official_get=official, transport=Mock(return_value=rank_wire()))
    assert result["status"] == "ranked", result
    assert official.call_args.kwargs["headers"]["Authorization"] == "Bearer snapshot-access"
    assert CollectionRequest.objects.get(attempt__run__content_run=run).http_status == 200


@pytest.mark.parametrize("expires_during_preparation", [False, True])
def test_expired_snapshot_stops_before_http_without_a_request_or_reservation(
    configured, monkeypatch, expires_during_preparation,
):
    import time

    from cryptography.fernet import Fernet

    from core.models import CollectionRun, OfficialCompanyOwnerCredential
    from core.official_company_credentials import OwnerTokenStore
    from monitor.editorial import chatter_trends
    from monitor.editorial.chatter_accounting import spent

    monkeypatch.setenv("PUSHINWEIGHT_X_LIST_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("PUSHINWEIGHT_X_LIST_CLIENT_ID", "fixture-client")
    monkeypatch.setenv("PUSHINWEIGHT_X_LIST_ACCESS_ONLY", "true")
    monkeypatch.delenv("PUSHINWEIGHT_X_LIST_CLIENT_SECRET", raising=False)
    expiry = time.time() + 600
    OwnerTokenStore.from_env().provision(access_token="snapshot-access", expires_at=expiry)
    owner = OfficialCompanyOwnerCredential.objects.get()
    before = (bytes(owner.encrypted_tokens), owner.revision, owner.status, owner.updated_at)
    clock = [expiry - 1 if expires_during_preparation else expiry + 1]
    monkeypatch.setattr("core.official_company_credentials.time.time", lambda: clock[0])
    if expires_during_preparation:
        save = chatter_trends._save

        def expire_after_request_preparation(*args, **kwargs):
            result = save(*args, **kwargs)
            if kwargs.get("phase") == "observing":
                assert CollectionRequest.objects.filter(attempt__run__content_run=args[0]).exists()
                clock[0] = expiry + 1
            return result

        monkeypatch.setattr(chatter_trends, "_save", expire_after_request_preparation)
    run = start(configured)
    prior_spend = spent(configured)
    official, ranker = Mock(return_value=official_response()), Mock(return_value=rank_wire())
    result = chatter_trends.discover_trends(run.pk, cfg=configured,
                                           official_get=official, transport=ranker)
    assert result == {"status": "held", "run_id": run.pk, "error_code": "owner_access_expired"}
    official.assert_not_called()
    ranker.assert_not_called()
    assert not CollectionRequest.objects.filter(attempt__run__content_run=run).exists()
    assert not CollectionRun.objects.filter(content_run=run).exists()
    assert not OriginalContentCall.objects.filter(run=run).exists()
    assert spent(configured) == prior_spend
    owner.refresh_from_db()
    assert (bytes(owner.encrypted_tokens), owner.revision, owner.status, owner.updated_at) == before
    run.refresh_from_db()
    assert run.outcome["trends"]["error_code"] == "owner_access_expired"


@pytest.mark.parametrize("ids", [[1, 1], [1], [1, 3], [True, 2]])
def test_rank_membership_is_exact_for_dynamic_batch(ids):
    from monitor.editorial.chatter_trends import validate_ranking
    with pytest.raises(ValueError):
        validate_ranking({"ranked_stories": [{"title": "A", "headline_ids": ids, "reason": "R"}]}, 2)


def test_empty_observation_auth_and_rate_limit_remain_distinct(configured):
    empty, _, ranker = discover(start(configured), configured, official_response(0))
    assert empty["status"] == "empty" and ranker.call_count == 0, empty


def test_timeout_retains_unknown_send_and_does_not_resend(configured):
    from monitor.editorial.chatter_trends import discover_trends
    run = start(configured)
    ranker = Mock(side_effect=TimeoutError("fixture uncertain send"))
    result, official, _ = discover(run, configured, transport=ranker)
    assert result["status"] == "held"
    call = OriginalContentCall.objects.get(run=run)
    assert call.state == "ambiguous" and call.actual_usd is None and call.reserved_usd > 0
    assert discover_trends(run.pk, cfg=configured, transport=ranker)["status"] == "held"
    assert ranker.call_count == official.call_count == 1


def test_accepted_prompt_prefix_has_no_saved_batch_or_seed_names():
    from monitor.editorial.chatter_trends import ranking_prefix

    assert hashlib.sha256(ranking_prefix().encode()).hexdigest() == "41b0759709e8e85a7c37b099c9fbd74ecfe742e10799ad0c2895618124626aa8"
    assert "HEADLINES:" not in ranking_prefix()


@pytest.mark.parametrize("status, code", [(401, "official_authentication_failed"), (403, "official_authentication_failed"), (429, "official_rate_limited")])
def test_received_failures_keep_their_receipts_and_do_not_rank(configured, status, code):
    from monitor.editorial.chatter_trends import checkpoint, reserve_due_slot

    run = start(configured)
    until = timezone.now() + timedelta(hours=2)
    result, official, ranker = discover(run, configured, official_response(status=status,
        headers={"x-rate-limit-reset": str(int(until.timestamp()))}))
    assert result == {"status": "held", "run_id": run.pk, "error_code": code}
    assert official.call_count == 1 and ranker.call_count == 0
    run.refresh_from_db()
    state = checkpoint(run)
    assert state.observation.http_status == status
    if status == 429:
        with patch("monitor.editorial.chatter_trends.timezone.now", return_value=until - timedelta(minutes=30)):
            held, created = reserve_due_slot("next-hour", until - timedelta(minutes=30), cfg=configured, purpose="on-demand")
        assert not created and held.pk == run.pk


@pytest.mark.parametrize("fault", ["checkpoint_extra", "checkpoint_version", "response_hash", "request_packet", "archive_hash"])
def test_tampered_checkpoint_is_held_before_any_provider(configured, fault):
    from monitor.editorial.chatter_trends import discover_trends

    run = start(configured)
    assert discover(run, configured)[0]["status"] == "ranked"
    run.refresh_from_db()
    call = run.provider_calls.get()
    if fault == "checkpoint_extra":
        run.outcome["trends"]["invented"] = 1
    elif fault == "checkpoint_version":
        run.outcome["trends"]["schema_version"] = 2
    elif fault == "response_hash":
        call.response_hash = "0" * 64
        call.save(update_fields=["response_hash"])
    elif fault == "request_packet":
        call.request_packet["max_tokens"] = 4096
        call.save(update_fields=["request_packet"])
    else:
        run.outcome["trends"]["observation"]["archive_sha256"] = "0" * 64
    run.save(update_fields=["outcome"])
    official, ranker = Mock(), Mock()
    assert discover_trends(run.pk, cfg=configured, official_get=official, transport=ranker)["status"] == "held"
    assert not official.called and not ranker.called


def test_completed_rank_reply_recovers_after_lost_checkpoint_without_keys(configured, monkeypatch):
    from monitor.editorial.chatter_trends import discover_trends

    run = start(configured)
    assert discover(run, configured)[0]["status"] == "ranked"
    run.refresh_from_db()
    run.outcome["trends"].update(phase="ranking", rank_call_id=None, ranking_sha256=None)
    run.outcome["phase"] = "ranking"
    run.save(update_fields=["outcome"])
    monkeypatch.delenv("OPENROUTER_API_KEY")
    official, ranker = Mock(), Mock()
    assert discover_trends(run.pk, cfg=configured, official_get=official, transport=ranker)["status"] == "ranked"
    assert not official.called and not ranker.called


def test_pre_rank_collection_reservation_counts_against_frozen_trial(configured, monkeypatch):
    from monitor.editorial import chatter_trends
    from monitor.editorial.chatter_accounting import spent
    from monitor.editorial.config import ChatterTrial

    cfg = configured.model_copy(update={"chatter": configured.chatter.model_copy(update={
        "trial": ChatterTrial(scope="chatter-near-limit", limit_usd=1, carry_usd=0)})})
    run = start(cfg)
    real_observe = chatter_trends._observe
    def observe(*args, **kwargs):
        state = real_observe(*args, **kwargs)
        # A fixture reservation tests aggregate admission before any model row.
        CollectionRequest.objects.filter(pk=state.observation.request_id).update(reserved_usd=Decimal("0.95"))
        assert OriginalContentCall.objects.count() == 0
        assert spent(cfg) == Decimal("0.95")
        return state
    monkeypatch.setattr(chatter_trends, "_observe", observe)
    result, official, ranker = discover(run, cfg)
    assert result["status"] == "held" and official.call_count == 1 and not ranker.called
    assert not OriginalContentCall.objects.exists()


def test_official_timeout_has_one_unknown_receipt_and_never_refetches(configured):
    from monitor.editorial.chatter_trends import discover_trends

    run = start(configured)
    store = SimpleNamespace(access_token=lambda: "fixture", check_access_expiry=lambda: None,
                            revision=7, redactions=set())
    official = Mock(side_effect=TimeoutError("fixture uncertain official send"))
    assert discover_trends(run.pk, cfg=configured, token_store=store, official_get=official)["status"] == "held"
    assert discover_trends(run.pk, cfg=configured, token_store=store, official_get=official)["status"] == "held"
    request = CollectionRequest.objects.get()
    assert request.transport_outcome == "unknown" and request.estimated_usd is None
    assert official.call_count == 1 and not OriginalContentCall.objects.exists()


def test_official_and_source_jobs_share_run_without_raw_profile_storage(configured, monkeypatch):
    from monitor.editorial.chatter_history import resolved_sources
    from monitor.editorial.chatter_sources import SourceSession
    from monitor.editorial.persistence import BudgetHeld
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose

    run = start(configured)
    assert discover(run, configured)[0]["status"] == "ranked"
    run.refresh_from_db()
    monkeypatch.setenv("TWITTERAPI_IO_ON_DEMAND_API_KEY", "fixture-only")
    session = SourceSession(run, configured, purpose=TwitterApiCredentialPurpose.ON_DEMAND)
    request = session.start("/twitter/tweets", {"tweet_ids": "123"})
    body = json.dumps({"tweets": [{"id": "123", "text": "An attributable source.",
        "createdAt": (run.facts_as_of - timedelta(minutes=1)).isoformat(), "lang": "en",
        "likeCount": 0, "author": {"id": "42", "userName": "reporter", "description": "unused-profile-secret"},
        "quoted_tweet": {"id": "122", "text": "Original speaker's words.", "createdAt": "quoted-clock",
                         "author": {"id": "41", "userName": "speaker", "description": "another-profile-secret"}}}],
        "has_next_page": False, "next_cursor": None}).encode()
    session.finish(request, {"outcome": "received", "status_code": 200, "body": body})
    request = CollectionRequest.objects.select_related("archive").get(pk=request.pk)
    assert request.response_sha256 == hashlib.sha256(body).digest()
    assert request.response_bytes == len(body) and request.raw_count == 1
    assert request.archive.encoding == "selected-json-canonical-v1"
    assert "profile-secret" not in bytes(request.archive.body).decode()
    compact = session.captured_reply(request)
    row = compact["tweets"][0]
    assert row["like_count"] == 0 and row["reply_count"] is None
    assert row["quoted_author_id"] == "41" and row["quoted_created_at"] == "quoted-clock"
    session.ingest(compact["tweets"])
    session.close(success=False)
    assert run.collection_runs.count() == 2
    resumed = SourceSession(run, configured, purpose=TwitterApiCredentialPurpose.ON_DEMAND, resume=True)
    assert resumed.captured_reply(request)["tweets"][0]["reply_count"] is None
    with pytest.raises(BudgetHeld, match="replay required"):
        resumed.start("/twitter/tweets", {"tweet_ids": "123"})
    resumed.close(success=True)
    run.refresh_from_db()
    assert resolved_sources(run.snapshot)["123"]["counters"]["likes"] == 0
    assert resolved_sources(run.snapshot)["123"]["counters"]["replies"] is None
    assert run.provider_calls.count() == 1


def test_hourly_history_cannot_relabel_semantic_appearances(configured):
    from monitor.editorial.chatter_history import appearance_history
    from tests.test_original_content_consideration import consideration

    run = start(configured)
    assert discover(run, configured)[0]["status"] == "ranked"
    run.refresh_from_db()
    row = consideration(run=run, discovery_call=run.provider_calls.get(), appearance_kind="personalized_trend")
    OriginalContentRun.objects.filter(pk=run.pk).update(discovery_state="complete")
    later = timezone.now() + timedelta(seconds=1)
    hourly = appearance_history(row.development, run.facts_as_of, observed_at=later, periods=2, lane="personalized-trends-v1")
    semantic = appearance_history(row.development, run.facts_as_of, observed_at=later, periods=2)
    assert hourly["fresh_periods"] == 1 and hourly["unknown_periods"] == 1
    assert semantic["fresh_periods"] == 0 and semantic["unknown_periods"] == 2


def test_missing_system_is_only_permitted_for_accepted_ranker(configured):
    from monitor.editorial.chatter_trends import ranking_request
    from monitor.editorial.providers import request_payload

    with pytest.raises(ValueError, match="system"):
        request_payload(configured.chatter.ranking, {"user": "Unmarked request"})
    accepted = ranking_request([{"headline_id": 1, "trend_name": "An original title."}])
    assert len(request_payload(configured.chatter.ranking, accepted)["messages"]) == 1
    assert len(request_payload(configured.chatter.ranking, {"system": "", "user": "Legacy request"})["messages"]) == 2


def test_one_shot_command_uses_same_due_enqueue_path(configured):
    from io import StringIO

    from django.core.management import call_command

    with patch("monitor.management.commands.editorial.load_editorial_config", return_value=configured), patch(
        "monitor.editorial.dispatch.dispatch_chatter_due_slot", return_value={"status": "enqueued", "run_id": 12}) as dispatch:
        call_command("editorial", "chatter", "--execute", "--chatter-trial-scope", "chatter-reconciled",
                     "--chatter-trial-limit-usd", "2", "--chatter-trial-carry-usd", "1.25", stdout=StringIO())
    assert dispatch.call_args.kwargs["purpose"] == "on-demand"
    trial = dispatch.call_args.kwargs["cfg"].chatter.trial
    assert trial.scope == "chatter-reconciled" and trial.carry_usd == 1.25 and trial.limit_usd == 2


def test_absent_reported_cost_stays_unknown_and_keeps_estimate_separate(configured):
    run = start(configured)
    status, raw = rank_wire()
    wire = json.loads(raw)
    wire["usage"].pop("cost")
    assert discover(run, configured, transport=Mock(return_value=(status, json.dumps(wire).encode())))[0]["status"] == "ranked"
    call = run.provider_calls.get()
    assert call.actual_usd is None
    assert call.provenance["billing_kind"] == "unknown" and Decimal(call.provenance["estimated_usd"]) > 0
    assert "provider_reported_cost_usd" not in call.response_payload["usage"]


def test_expired_dropped_slot_is_not_observed_under_a_false_historical_clock(configured):
    from monitor.editorial.chatter_trends import discover_trends, reserve_due_slot

    old = timezone.now() - timedelta(hours=2)
    run, _ = reserve_due_slot("missed-hour", old, cfg=configured, purpose="on-demand")
    official = Mock()
    result = discover_trends(run.pk, cfg=configured, official_get=official)
    assert result["status"] == "held" and result["error_code"] == "official_observation_window_elapsed"
    assert not official.called and not CollectionRequest.objects.exists()


@pytest.mark.parametrize("fault", ["extra", "version", "missing_version", "missing", "type", "boolean_version"])
def test_compact_source_projection_has_closed_versioned_replay(fault):
    from monitor.editorial.chatter_sources import (
        CompactSourceReply,
        compact_source_reply,
    )

    value = compact_source_reply([], {})
    if fault == "extra":
        value["profile"] = {}
    elif fault == "version":
        value["schema_version"] = 3
    elif fault == "missing":
        value.pop("tweets")
    elif fault == "missing_version":
        value.pop("schema_version")
    elif fault == "boolean_version":
        value["schema_version"] = True
    else:
        value["has_next_page"] = "false"
    with pytest.raises(ValueError):
        CompactSourceReply.model_validate(value)


def test_scheduled_hours_reuse_one_job_with_distinct_execution_receipts(configured, monkeypatch):
    from core.models import CollectionJob, CollectionRun
    from monitor.editorial.chatter_trends import discover_trends, reserve_due_slot

    cfg = configured.model_copy(update={"chatter": configured.chatter.model_copy(update={"trial": None})})
    at = timezone.now().replace(minute=1, second=0, microsecond=0)
    store = SimpleNamespace(access_token=lambda: "fixture", check_access_expiry=lambda: None,
                            revision=7, redactions=set())
    official, ranker = Mock(return_value=official_response()), Mock(return_value=rank_wire())
    runs = []
    for offset in (0, 1):
        clock = at + timedelta(hours=offset)
        monkeypatch.setattr("monitor.editorial.chatter_trends.timezone.now", lambda current=clock: current)
        run, created = reserve_due_slot(f"recurring-hour-{offset}", clock, cfg=cfg, purpose="scheduled")
        assert created
        assert discover_trends(run.pk, cfg=cfg, token_store=store, official_get=official, transport=ranker)["status"] == "ranked"
        runs.append(run)
    job = CollectionJob.objects.get(job_key__startswith="chatter-personalized-trends:")
    assert job.mode == "recurring" and job.interval_seconds == 3600
    assert job.schedule_driver == "external_render_cron"
    executions = CollectionRun.objects.filter(job=job)
    assert executions.count() == 2
    assert set(executions.values_list("content_run_id", flat=True)) == {run.pk for run in runs}
    assert CollectionRequest.objects.filter(attempt__run__job=job).count() == 2
    assert official.call_count == ranker.call_count == 2


def test_auth_hold_requires_a_reconciled_credential_revision_before_next_hour(configured, monkeypatch):
    from monitor.editorial.chatter_trends import reserve_due_slot

    run = start(configured)
    assert discover(run, configured, official_response(status=401))[0]["status"] == "held"
    next_hour = timezone.now() + timedelta(hours=1)
    monkeypatch.setattr("monitor.editorial.chatter_trends.timezone.now", lambda: next_hour)
    monkeypatch.setattr("monitor.editorial.chatter_trends.credential_diagnostics", lambda: {
        "credential_revision": 7, "credential_status": "ready"})
    held, created = reserve_due_slot("new-hour", next_hour, cfg=configured, purpose="on-demand")
    assert not created and held.pk == run.pk
    monkeypatch.setattr("monitor.editorial.chatter_trends.credential_diagnostics", lambda: {
        "credential_revision": 8, "credential_status": "ready"})
    resumed, created = reserve_due_slot("new-hour", next_hour, cfg=configured, purpose="on-demand")
    assert created and resumed.pk != run.pk
