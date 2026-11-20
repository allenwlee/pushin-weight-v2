"""Optional post-commit adapters; broker failure cannot change the source pipeline."""

import logging

from django.db import transaction

from .config import load_editorial_config

logger = logging.getLogger(__name__)


def editorial_task():
    from monitor.tasks import refresh_editorial

    return refresh_editorial


def _send(task, args, countdown=0, priority=None):
    try:
        task.apply_async(
            args=args, queue="trend-narratives", expires=900, countdown=countdown,
            **({"priority": priority} if priority is not None else {}),
        )
    except Exception:
        logger.exception("editorial queue dispatch failed")


def dispatch_chatter_cycle(source_cycle_id, started, *, kind, dry_run, task=None, cfg=None):
    """Isolated start notification on the existing fifteen-minute harvest clock."""
    if kind != "scheduled" or dry_run:
        return {"status": "ineligible"}
    try:
        cfg = cfg or load_editorial_config()
        if not cfg.chatter.enabled:
            return {"status": "disabled"}
        if cfg.chatter.discovery_lane in {"personalized-trends-v1", "personalized-trends-v2"}:
            return dispatch_chatter_due_slot(source_cycle_id, started, cfg=cfg, task=task,
                purpose="on-demand" if cfg.chatter.trial else "scheduled", recover_pending=True)
        if task is None:
            from monitor.tasks import chatter_stage
            task = chatter_stage
        envelope = {"schema_version": 1, "source_cycle_id": str(source_cycle_id),
                    "cycle_started_at": started.isoformat(), "cutoff": started.isoformat(), "dry_run": False,
                    "credential_purpose": "on-demand" if cfg.chatter.trial else "scheduled"}
        transaction.on_commit(lambda: _send(task, ["discover", envelope], priority=0))
        return {"status": "enqueued"}
    except Exception:
        logger.exception("Chatter start dispatch unavailable")
        return {"status": "unavailable"}


def dispatch_chatter_due_slot(source_cycle_id, started, *, cfg=None, task=None, purpose, recover_pending=False):
    """The same durable hourly path serves harvest ticks and bounded manual proof."""
    from .chatter_trends import checkpoint, reserve_due_slot

    cfg = cfg or load_editorial_config()
    if not cfg.chatter.enabled:
        return {"status": "disabled"}
    if cfg.chatter.discovery_lane == "personalized-trends-v2":
        from datetime import UTC, timedelta

        from django.utils import timezone

        from .chatter_trends import CAPTURE_SCOPE, DECISION_SCOPE

        if task is None:
            from monitor.tasks import chatter_stage
            task = chatter_stage
        tick = started.astimezone(UTC)
        slot = tick.replace(minute=tick.minute // 15 * 15, second=0, microsecond=0)
        capture, _ = reserve_due_slot(source_cycle_id, started, cfg=cfg, purpose=purpose, scope=CAPTURE_SCOPE)
        decision = None
        if slot.minute % 30 == 0:
            decision, created = reserve_due_slot(source_cycle_id, started, cfg=cfg, purpose=purpose, scope=DECISION_SCOPE)
            if created:
                from .chatter_trends import envelope_for

                delay = max(0, (slot + timedelta(minutes=5) - timezone.now()).total_seconds())
                transaction.on_commit(lambda: _send(task, ["discover", envelope_for(decision)], countdown=delay, priority=0))
        enqueued = capture.interval == slot and _enqueue_chatter_start(capture, task)
        if recover_pending:
            recover_chatter_starts(cfg=cfg, task=task)
        return {"status":"enqueued" if enqueued else "already_dispatched", "run_id":capture.pk,
                "decision_run_id":decision.pk if decision else None}
    run, created = reserve_due_slot(source_cycle_id, started, cfg=cfg, purpose=purpose)
    if task is None:
        from monitor.tasks import chatter_stage

        task = chatter_stage
    if not created:
        state = checkpoint(run)
        # A manual proof owns only its selected hour. A cross-slot rate/auth hold
        # may return an older owner, which is never a new execution grant.
        selected_slot = started.astimezone(state.slot.tzinfo).replace(minute=0, second=0, microsecond=0)
        if run.interval == selected_slot:
            from .chatter_trends import validate_slot_authority

            validate_slot_authority(run, cfg=cfg, purpose=purpose)
            _enqueue_chatter_start(run, task)
        if recover_pending:
            recover_chatter_starts(cfg=cfg, task=task)
        status = "deferred" if state.deferred_until and state.deferred_until > started else "already_dispatched"
        if state.error_code == "official_authentication_failed":
            status = "held"
        return {"status": status,
                "run_id": run.pk}
    _enqueue_chatter_start(run, task)
    if recover_pending:
        recover_chatter_starts(cfg=cfg, task=task)
    return {"status": "enqueued", "run_id": run.pk}


def _enqueue_chatter_start(run, task):
    from datetime import timedelta

    from django.utils import timezone

    from core.models import CollectionRun, OriginalContentCall, OriginalContentRun

    from .chatter_trends import (
        checkpoint,
        envelope_for,
        read_ranked_batch,
    )

    with transaction.atomic():
        current = OriginalContentRun.objects.select_for_update().get(pk=run.pk)
        state = checkpoint(current)
        now = timezone.now()
        phase = current.outcome.get("phase")
        empty_repair = state.phase == "empty" and phase == "complete" and (
            current.execution_state != "completed" or current.discovery_state != "complete")
        continuation = state.phase in {"ranked", "empty"} and phase != "held" and (
            phase != "complete" or empty_repair)
        if (current.execution_state == "completed" and not empty_repair
                or state.phase in {"ranked", "empty"} and not continuation
                or state.phase not in {"queued", "observing", "observed", "ranking", "ranked", "empty"}
                or state.deferred_until and state.deferred_until > now
                or state.last_enqueue_at and state.last_enqueue_at > now - timedelta(seconds=60)
                or current.claim_owner and current.lease_until and current.lease_until > now):
            return False
        if phase == "selected":
            from .chatter_chain import reconcile_chatter_graphics

            if reconcile_chatter_graphics(current):
                return False
        error = None
        if state.phase == "observing":
            error = "official_send_requires_reconciliation"
        elif OriginalContentCall.objects.filter(run=current).exclude(state="completed").exists():
            error = "model_send_requires_reconciliation" if continuation else "ranking_send_requires_reconciliation"
        source_runs = CollectionRun.objects.filter(content_run=current).exclude(
            job__job_key__startswith="chatter-personalized-trends:")
        if continuation:
            from .chatter_sources import source_resume_is_safe

            if source_runs.filter(completed_at__isnull=True, lease_expires_at__gt=now).exists():
                return False
            if not source_resume_is_safe(current):
                error = "source_send_requires_reconciliation"
        if error:
            state = type(state).model_validate({**state.model_dump(), "phase": "held", "error_code": error})
            current.outcome = {**current.outcome, "phase": "held", "error_code": error,
                               "trends": state.model_dump(mode="json")}
            current.discovery_state = "failed"
            current.fence += 1
            current.claim_owner = ""
            current.save(update_fields=["outcome", "discovery_state", "fence", "claim_owner", "updated_at"])
            return False
        if continuation and state.phase == "ranked":
            # Validate the completed ranking and exact official archive before
            # queueing any continuation. This performs no provider I/O.
            read_ranked_batch(current.pk)
        if continuation and phase in {"discovered", "selected"} and current.discovery_state == "complete":
            stage, args = "select", [current.pk]
            # Only completed saved work reaches this branch. Renew its local
            # mutation lease so the existing fenced selector/handoff can resume.
            current.lease_until = now + timedelta(minutes=10)
            current.execution_state = "running"
            current.save(update_fields=["lease_until", "execution_state", "updated_at"])
        elif continuation and (source_runs.exists() or phase in {"discovered", "selected", "complete"}):
            stage, args = "resume-discovery", [current.pk]
        else:
            stage, args = "discover", [envelope_for(current)]
        state = type(state).model_validate({**state.model_dump(), "last_enqueue_at": now})
        current.outcome = {**current.outcome, "trends": state.model_dump(mode="json")}
        current.save(update_fields=["outcome", "updated_at"])
        transaction.on_commit(lambda: _send(task, [stage, *args], priority=0))
    return True


def recover_chatter_starts(*, cfg=None, task=None, limit=4):
    """Bounded existing-clock/worker-start recovery for a dropped broker delivery."""
    from datetime import timedelta

    from django.core.exceptions import ObjectDoesNotExist
    from django.db.models import Q
    from django.utils import timezone

    from core.models import CollectionRun, OriginalContentRun

    from .chatter_trends import (
        ROLLING_LANE,
        ROLLING_SCOPES,
        TRENDS_SCOPE,
        runs_in_trial,
    )

    cfg = cfg or load_editorial_config()
    if not cfg.chatter.enabled or cfg.chatter.discovery_lane not in {ROLLING_LANE,"personalized-trends-v1"}:
        return {"enqueued": 0}
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("Chatter recovery limit exceeded")
    if task is None:
        from monitor.tasks import chatter_stage

        task = chatter_stage
    count = 0
    now = timezone.now()
    candidates = OriginalContentRun.objects.filter(
        scope_key__in=ROLLING_SCOPES if cfg.chatter.discovery_lane == ROLLING_LANE else (TRENDS_SCOPE,), interval__gte=now - timedelta(days=8),
    ).filter(
        Q(outcome__trends__phase__in=["queued", "observing", "observed", "ranking"])
        | Q(outcome__trends__phase__in=["ranked", "empty"],
            outcome__phase__in=["ranked", "empty", "gathering", "discovered", "selected", "complete"])
    ).exclude(execution_state="completed", discovery_state="complete").exclude(outcome__phase="held").exclude(
        Q(claim_owner__gt="", lease_until__gt=now)
        | Q(outcome__trends__last_enqueue_at__gt=(now - timedelta(seconds=60)).isoformat())
        | Q(outcome__trends__deferred_until__gt=now.isoformat())
    ).exclude(
        pk__in=CollectionRun.objects.filter(completed_at__isnull=True, lease_expires_at__gt=now,
            content_run__isnull=False).exclude(job__job_key__startswith="chatter-personalized-trends:").values("content_run_id")
    ).order_by("interval")
    if cfg.chatter.discovery_lane == ROLLING_LANE:
        trial = cfg.chatter.trial
        candidates = runs_in_trial(candidates, trial.scope if trial else None)
    # The enqueue budget counts eligible deliveries. Invalid rows are held and
    # removed from later scans; a separate finite scan cap bounds local work.
    for run in candidates[:100]:
        if count >= limit:
            break
        try:
            count += int(_enqueue_chatter_start(run, task))
        except (ValueError, KeyError, TypeError, ObjectDoesNotExist):
            with transaction.atomic():
                current = OriginalContentRun.objects.select_for_update().get(pk=run.pk)
                current.outcome = {**current.outcome, "phase": "held", "error_code": "invalid_recovery_checkpoint"}
                current.discovery_state = "failed"
                current.fence += 1
                current.claim_owner = ""
                current.save(update_fields=["outcome", "discovery_state", "fence", "claim_owner", "updated_at"])
            logger.exception("Chatter recovery checkpoint unavailable")
    return {"enqueued": count}


def dispatch_chatter_stage(stage, *args, countdown=0):
    from monitor.tasks import chatter_stage

    priorities = {"discover": 0, "select": 0, "resume-discovery": 0, "gather": 0, "review": 9}
    if stage == "write":
        priority = 3 if args[-1] == "en" else 6
    else:
        if stage not in priorities:
            raise ValueError("unsupported Chatter stage")
        priority = priorities[stage]
    transaction.on_commit(lambda: _send(chatter_stage, [stage, *args], countdown=countdown, priority=priority))


def dispatch_editorial(envelope):
    try:
        if load_editorial_config().enabled:
            transaction.on_commit(lambda: _send(editorial_task(), [envelope], priority=6))
    except Exception:
        logger.exception("editorial configuration unavailable")


def dispatch_picture(content_kind, content_id, source_platform="x"):
    try:
        cfg = load_editorial_config()
        if cfg.picture_mode(content_kind, source_platform) == "off":
            return
        from monitor.tasks import edit_content_picture

        transaction.on_commit(
            lambda: _send(
                edit_content_picture, [content_kind, str(content_id), source_platform], priority=9
            )
        )
    except Exception:
        logger.exception("picture dispatch unavailable")


def dispatch_poll(picture_id):
    from monitor.tasks import poll_editorial_picture

    transaction.on_commit(lambda: _send(poll_editorial_picture, [str(picture_id)], 30, priority=9))
