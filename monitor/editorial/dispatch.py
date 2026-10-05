"""Optional post-commit adapters; broker failure cannot change the source pipeline."""

import logging

from django.db import transaction

from .config import load_editorial_config

logger = logging.getLogger(__name__)


def editorial_task():
    from monitor.tasks import refresh_editorial

    return refresh_editorial


def _send(task, args, countdown=0):
    try:
        task.apply_async(
            args=args, queue="trend-narratives", expires=900, countdown=countdown
        )
    except Exception:
        logger.exception("editorial queue dispatch failed")


def dispatch_editorial(envelope):
    try:
        if load_editorial_config().enabled:
            transaction.on_commit(lambda: _send(editorial_task(), [envelope]))
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
                edit_content_picture, [content_kind, str(content_id), source_platform]
            )
        )
    except Exception:
        logger.exception("picture dispatch unavailable")


def dispatch_poll(picture_id):
    from monitor.tasks import poll_editorial_picture

    transaction.on_commit(lambda: _send(poll_editorial_picture, [str(picture_id)], 30))
