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
