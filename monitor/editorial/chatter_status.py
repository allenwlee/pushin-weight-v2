"""Delay age comes from existing successful evaluations, without operations tables."""

from datetime import datetime, timedelta

from django.utils import timezone

from core.models import OriginalContentRun

from .chatter_history import SCOPE, WORKFLOW


def delay_status(now=None, *, activated_at=None):
    now = now or timezone.now()
    rows = list(
        OriginalContentRun.objects.filter(workflow_key=WORKFLOW, scope_key=SCOPE)
        .order_by("-interval")
        .values("outcome__healthy_at", "created_at")[:192]
    )
    successes = []
    for row in rows:
        try:
            at = datetime.fromisoformat(row["outcome__healthy_at"])
            if at.tzinfo and at <= now:
                successes.append(at)
        except (KeyError, ValueError, TypeError):
            continue
    last = max(successes) if successes else None
    starts = [row["created_at"] for row in rows]
    if activated_at is not None:
        starts.append(activated_at)
    activated = min(starts, default=now)
    return {
        "delayed": now - (last or activated) >= timedelta(minutes=45),
        "last_success_at": last.isoformat() if last else None,
    }
