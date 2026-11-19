"""Recovery stays local to saved identities and advances past unusable work."""

from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from core.models import Language, Locale, OriginalContent, OriginalContentCall, Post
from monitor.editorial.chatter_trends import reserve_due_slot
from tests.test_chatter_graphics_recovery import ready
from tests.test_chatter_trends import configured as configured  # noqa: PLC0414
from tests.test_chatter_trends import discover, official_response, rank_wire

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def slot(cfg, hours):
    at = timezone.now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=hours)
    return reserve_due_slot(f"review-{hours}", at, cfg=cfg, purpose="on-demand")[0]


def rank_slot(run, cfg, count=12):
    with patch("monitor.editorial.chatter_trends.timezone.now", return_value=run.facts_as_of):
        result = discover(run, cfg, official_response(count), Mock(return_value=rank_wire(count)))[0]
    assert result["status"] == "ranked", result


def selected_package(cfg, hours):
    from monitor.editorial.chatter_gathering import gather_trends
    from monitor.editorial.config import load_editorial_config
    from monitor.editorial.graphics_entry import prepare_selected_story
    from monitor.editorial.graphics_packages import materialize_package

    saved = load_editorial_config(Path(__file__).resolve().parents[1] / "config/editorial-chatter-staging.yaml")
    cfg = cfg.model_copy(update={"routes": saved.routes, "voices": saved.voices,
                                "locale_routes": saved.locale_routes})
    for code in ("en", "ja", "zh-CN"):
        Language.objects.get_or_create(pk=code.split("-")[0])
        Locale.objects.get_or_create(pk=code, defaults={"language_id": code.split("-")[0]})
    run = slot(cfg, hours)
    rank_slot(run, cfg, 1)
    Post.objects.create(tweet_id=f"9900{hours}", text="Original headline 1 confirmed by the lab.",
                        author_handle="reporter", lang="en", created_at=run.facts_as_of - timedelta(minutes=1))
    assert gather_trends(run.pk, cfg=cfg, x_client=Mock(), enqueue=lambda *args: None)["status"] == "discovered"
    row = OriginalContent.objects.get(run=run)
    row.consideration_state = "selected"
    row.source_locale_id, row.editorial_group = "en", "rest"
    row.save(update_fields=["consideration_state", "source_locale", "editorial_group"])
    ready(run, "selected")
    package, output = materialize_package(prepare_selected_story(content_id=row.pk, run_id=run.pk, locale="en"))
    return run, row, package, output, cfg


def test_four_terminal_no_copy_packages_hold_locally_and_new_delivery_recovers(
    configured, django_capture_on_commit_callbacks, monkeypatch,
):
    from monitor.editorial.chatter_chain import write_chatter
    from monitor.editorial.dispatch import recover_chatter_starts

    runs = []
    dispatch = Mock(return_value=True)
    monkeypatch.setattr("monitor.editorial.graphics_dispatch.dispatch_creation", dispatch)
    for hours in range(5, 1, -1):
        run, row, package, _, cfg = selected_package(configured, hours)
        package.execution_state = "suspended"
        package.decisions = {"graphics_skipped_stages": {"C1": "credential_unavailable"}}
        package.save(update_fields=["execution_state", "decisions"])
        if hours == 5:
            assert write_chatter(row.pk, "en", cfg=cfg)["status"] == "held"
        runs.append((run, package))
    dispatch.assert_not_called()
    newest = slot(configured, 1)
    task = Mock()
    with django_capture_on_commit_callbacks(execute=True):
        assert recover_chatter_starts(cfg=configured, task=task) == {"enqueued": 1}
    assert task.apply_async.call_args.kwargs["args"][1]["run_id"] == newest.pk
    for run, package in runs:
        run.refresh_from_db()
        assert run.outcome["phase"] == "held"
        assert run.outcome["error_code"] == "graphics_no_copy"
        assert run.outcome["graphics_hold"] == {
            "run_id": package.pk, "stage": "C1", "reason": "credential_unavailable",
            "execution_state": "suspended",
        }


@pytest.mark.parametrize("unusable", ["invalid", "leased", "throttled", "missing_rank"])
def test_four_old_unusable_rows_do_not_starve_new_broker_loss(
    configured, django_capture_on_commit_callbacks, unusable,
):
    from monitor.editorial.dispatch import recover_chatter_starts

    old = [slot(configured, hours) for hours in range(5, 1, -1)]
    newest = slot(configured, 1)
    for run in old:
        if unusable == "missing_rank":
            rank_slot(run, configured)
            ready(run, "ranked")
            # A valid-looking checkpoint points at no owned completed call.
            run.outcome["trends"]["rank_call_id"] = 999999999
        elif unusable == "invalid":
            run.outcome["trends"]["invented"] = True
        elif unusable == "leased":
            run.claim_owner = "live-peer"
            run.lease_until = timezone.now() + timedelta(minutes=5)
        else:
            run.outcome["trends"]["last_enqueue_at"] = timezone.now().isoformat()
        run.save(update_fields=["outcome", "claim_owner", "lease_until"])
    task = Mock()
    with django_capture_on_commit_callbacks(execute=True):
        assert recover_chatter_starts(cfg=configured, task=task) == {"enqueued": 1}
    assert task.apply_async.call_args.kwargs["args"][1]["run_id"] == newest.pk
    if unusable in {"invalid", "missing_rank"}:
        for run in old:
            run.refresh_from_db()
            assert run.outcome["phase"] == "held"
            assert run.outcome["error_code"] == "invalid_recovery_checkpoint"


def test_manual_one_shot_does_not_recover_an_older_trial(configured, django_capture_on_commit_callbacks):
    from monitor.editorial.dispatch import dispatch_chatter_due_slot

    older = slot(configured, 2)
    other = configured.model_copy(update={"chatter": configured.chatter.model_copy(update={
        "trial": configured.chatter.trial.model_copy(update={"scope": "selected-trial"}),
    })})
    task = Mock()
    with django_capture_on_commit_callbacks(execute=True):
        result = dispatch_chatter_due_slot("selected-one-shot", timezone.now(), cfg=other,
                                          task=task, purpose="on-demand")
    assert result["status"] == "enqueued"
    assert task.apply_async.call_count == 1
    assert task.apply_async.call_args.kwargs["args"][1]["run_id"] == result["run_id"]
    assert result["run_id"] != older.pk


def test_scheduled_clock_still_recovers_an_older_trial(configured, django_capture_on_commit_callbacks):
    from monitor.editorial.dispatch import dispatch_chatter_cycle

    older = slot(configured, 2)
    other = configured.model_copy(update={"chatter": configured.chatter.model_copy(update={
        "trial": configured.chatter.trial.model_copy(update={"scope": "new-recurring-trial"}),
    })})
    task = Mock()
    with patch("monitor.editorial.dispatch.load_editorial_config", return_value=other), django_capture_on_commit_callbacks(execute=True):
        result = dispatch_chatter_cycle("scheduled", timezone.now(), kind="scheduled", dry_run=False, task=task)
    identities = {call.kwargs["args"][1]["run_id"] for call in task.apply_async.call_args_list}
    assert identities == {older.pk, result["run_id"]}


def test_explicit_manual_resume_rejects_another_saved_trial(configured, monkeypatch):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    run = slot(configured, 1)
    other = configured.model_copy(update={"chatter": configured.chatter.model_copy(update={
        "trial": configured.chatter.trial.model_copy(update={"scope": "another-manual-trial"}),
    })})
    monkeypatch.setattr("monitor.management.commands.editorial.load_editorial_config", lambda: other)
    send = Mock(side_effect=AssertionError("another saved grant must not execute"))
    monkeypatch.setattr("monitor.editorial.chatter_chain.resume_chatter_discovery", send)
    with pytest.raises(CommandError, match="authority"):
        call_command("editorial", "chatter", chatter_run=run.pk, execute=True)
    send.assert_not_called()


@pytest.mark.parametrize("changed", ["purpose", "scope", "limit", "carry"])
def test_existing_slot_rejects_changed_manual_authority(configured, changed):
    now = timezone.now()
    cfg = configured
    purpose = "on-demand"
    reserve_due_slot("first", now, cfg=cfg, purpose=purpose)
    if changed == "purpose":
        cfg = cfg.model_copy(update={"chatter": cfg.chatter.model_copy(update={"trial": None})})
        purpose = "scheduled"
    else:
        key = {"scope": "scope", "limit": "limit_usd", "carry": "carry_usd"}[changed]
        value = "another-trial" if changed == "scope" else 1
        cfg = cfg.model_copy(update={"chatter": cfg.chatter.model_copy(update={
            "trial": cfg.chatter.trial.model_copy(update={key: value}),
        })})
    with pytest.raises(ValueError, match="authority"):
        reserve_due_slot("second", now, cfg=cfg, purpose=purpose)


def test_split_discovered_checkpoint_goes_through_gather_repair(configured, django_capture_on_commit_callbacks):
    from monitor.editorial.dispatch import recover_chatter_starts

    run = slot(configured, 1)
    rank_slot(run, configured)
    ready(run, "discovered")
    run.discovery_state = "pending"
    run.save(update_fields=["discovery_state"])
    task = Mock()
    with django_capture_on_commit_callbacks(execute=True):
        assert recover_chatter_starts(cfg=configured, task=task) == {"enqueued": 1}
    assert task.apply_async.call_args.kwargs["args"] == ["resume-discovery", run.pk]
    assert OriginalContentCall.objects.filter(run=run).count() == 1


@pytest.mark.parametrize("execution", ["running", "completed"])
def test_empty_split_checkpoint_reaches_saved_only_completion_repair(
    configured, django_capture_on_commit_callbacks, execution,
):
    from monitor.editorial.chatter_chain import resume_chatter_discovery
    from monitor.editorial.dispatch import recover_chatter_starts

    run = slot(configured, 1)
    with patch("monitor.editorial.chatter_trends.timezone.now", return_value=run.facts_as_of):
        result = discover(run, configured, official_response(0))[0]
    assert result["status"] == "empty"
    ready(run, "complete")
    run.execution_state = execution
    run.save(update_fields=["execution_state"])
    task = Mock()
    with django_capture_on_commit_callbacks(execute=True):
        assert recover_chatter_starts(cfg=configured, task=task) == {"enqueued": 1}
    assert task.apply_async.call_args.kwargs["args"] == ["resume-discovery", run.pk]
    assert resume_chatter_discovery(run.pk, cfg=configured)["status"] in {"already_discovered", "empty"}
    run.refresh_from_db()
    assert run.discovery_state == "complete" and run.execution_state == "completed"
    assert not run.provider_calls.exists()


@pytest.mark.parametrize("captured", [False, True])
def test_live_source_lease_waits_then_expired_capture_resumes_or_unknown_holds(
    configured, django_capture_on_commit_callbacks, captured,
):
    from core.models import CollectionRequest, CollectionRun
    from monitor.editorial.chatter_sources import SourceSession
    from monitor.editorial.dispatch import recover_chatter_starts
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose

    run = slot(configured, 1)
    rank_slot(run, configured)
    run.refresh_from_db()
    run.lease_until = timezone.now() + timedelta(minutes=10)
    run.save(update_fields=["lease_until"])
    session = SourceSession(run, configured, purpose=TwitterApiCredentialPurpose.ON_DEMAND)
    request = session.start("/twitter/tweet/advanced_search", {"query": '"Original headline 1"', "queryType": "Latest"})
    if captured:
        session.finish(request, {"body": b'{"tweets":[],"has_next_page":false,"next_cursor":""}',
                                 "outcome": "received", "status_code": 200})
    ready(run, "ranked")
    task = Mock()
    with django_capture_on_commit_callbacks(execute=True):
        assert recover_chatter_starts(cfg=configured, task=task) == {"enqueued": 0}
    run.refresh_from_db()
    assert run.outcome["phase"] == "ranked"
    CollectionRun.objects.filter(pk=session.claim.run_id).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
    with django_capture_on_commit_callbacks(execute=True):
        assert recover_chatter_starts(cfg=configured, task=task) == {"enqueued": int(captured)}
    if captured:
        assert task.apply_async.call_args.kwargs["args"] == ["resume-discovery", run.pk]
    else:
        task.apply_async.assert_not_called()
        run.refresh_from_db()
        assert run.outcome["phase"] == "held"
        assert run.outcome["error_code"] == "source_send_requires_reconciliation"
    assert CollectionRequest.objects.filter(attempt__run__content_run=run).count() == 2
