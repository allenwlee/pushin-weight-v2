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


def dispatch_chatter_cycle(source_cycle_id, started, *, kind, dry_run, task=None):
    """Isolated start notification on the existing fifteen-minute harvest clock."""
    if kind != "scheduled" or dry_run:
        return {"status": "ineligible"}
    try:
        cfg = load_editorial_config()
        if not cfg.chatter.enabled:
            return {"status": "disabled"}
        if cfg.chatter.discovery_lane == "personalized-trends-v1":
            return dispatch_chatter_due_slot(source_cycle_id, started, cfg=cfg, task=task,
                purpose="on-demand" if cfg.chatter.trial else "scheduled")
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


def dispatch_chatter_due_slot(source_cycle_id, started, *, cfg=None, task=None, purpose):
    """The same durable hourly path serves harvest ticks and bounded manual proof."""
    from .chatter_trends import checkpoint, reserve_due_slot

    cfg = cfg or load_editorial_config()
    if not cfg.chatter.enabled:
        return {"status": "disabled"}
    run, created = reserve_due_slot(source_cycle_id, started, cfg=cfg, purpose=purpose)
    if task is None:
        from monitor.tasks import chatter_stage

        task = chatter_stage
    if not created:
        state = checkpoint(run)
        recover_chatter_starts(cfg=cfg, task=task)
        status = "deferred" if state.deferred_until and state.deferred_until > started else "already_dispatched"
        if state.error_code == "official_authentication_failed":
            status = "held"
        return {"status": status,
                "run_id": run.pk}
    _enqueue_chatter_start(run, task)
    recover_chatter_starts(cfg=cfg, task=task)
    return {"status": "enqueued", "run_id": run.pk}


def _enqueue_chatter_start(run, task):
    from datetime import timedelta

    from django.utils import timezone

    from core.models import OriginalContentCall, OriginalContentRun

    from .chatter_trends import RANK_STAGE, Checkpoint, checkpoint, envelope_for

    with transaction.atomic():
        current = OriginalContentRun.objects.select_for_update().get(pk=run.pk)
        state = checkpoint(current)
        now = timezone.now()
        if (state.phase not in {"queued", "observing", "observed", "ranking"}
                or state.last_enqueue_at and state.last_enqueue_at > now - timedelta(seconds=60)
                or current.claim_owner and current.lease_until and current.lease_until > now):
            return False
        # Interrupted sends are held. Completed matching work is validated by
        # the worker, and a missing model row proves that no ranker was sent.
        if state.phase == "observing" or OriginalContentCall.objects.filter(run=current, stage=RANK_STAGE).exclude(state="completed").exists():
            state = Checkpoint.model_validate({**state.model_dump(), "phase": "held",
                "error_code": "official_send_requires_reconciliation" if state.phase == "observing" else "ranking_send_requires_reconciliation"})
            current.outcome = {**current.outcome, "phase": "held", "trends": state.model_dump(mode="json")}
            current.discovery_state = "failed"
            current.fence += 1
            current.claim_owner = ""
            current.save(update_fields=["outcome", "discovery_state", "fence", "claim_owner", "updated_at"])
            return False
        state = Checkpoint.model_validate({**state.model_dump(), "last_enqueue_at": now})
        current.outcome = {**current.outcome, "trends": state.model_dump(mode="json")}
        current.save(update_fields=["outcome", "updated_at"])
        envelope = envelope_for(current)
        transaction.on_commit(lambda: _send(task, ["discover", envelope], priority=0))
    return True


def recover_chatter_starts(*, cfg=None, task=None, limit=4):
    """Bounded existing-clock/worker-start recovery for a dropped broker delivery."""
    from datetime import timedelta

    from django.utils import timezone

    from core.models import OriginalContentRun

    from .chatter_trends import TRENDS_SCOPE

    cfg = cfg or load_editorial_config()
    if not cfg.chatter.enabled or cfg.chatter.discovery_lane != "personalized-trends-v1":
        return {"enqueued": 0}
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("Chatter recovery limit exceeded")
    if task is None:
        from monitor.tasks import chatter_stage

        task = chatter_stage
    count = 0
    for run in OriginalContentRun.objects.filter(scope_key=TRENDS_SCOPE,
            interval__gte=timezone.now() - timedelta(days=8),
            outcome__trends__phase__in=["queued", "observing", "observed", "ranking"]).order_by("interval")[:limit]:
        count += int(_enqueue_chatter_start(run, task))
    return {"enqueued": count}


def dispatch_chatter_stage(stage, *args):
    from monitor.tasks import chatter_stage

    if stage not in {"select", "write", "review", "resume-discovery"}:
        raise ValueError("unsupported Chatter stage")
    priority = 0 if stage in {"select", "resume-discovery"} else 9 if stage == "review" else 3 if args[-1] == "en" else 6
    transaction.on_commit(lambda: _send(chatter_stage, [stage, *args], priority=priority))


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
