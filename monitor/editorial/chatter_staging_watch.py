"""Run the Chatter part of a real staging harvest tick during a bounded watch."""

import os
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection

from monitor.staging_acceptance import (
    EXPECTED_DEPLOYMENT_ENVIRONMENT,
    EXPECTED_SERVICE_NAME,
    _inspect_database,
)
from scripts.staging_refresh.policy import load_policy

from .config import EditorialConfig, load_editorial_config
from .dispatch import dispatch_chatter_cycle


def watch_profile(base, scope, limit, carry):
    data = base.model_dump(mode="json")
    ranking = data["chatter"]["ranking"]
    writer = data["routes"]["chatter"]
    for field in (
        "model",
        "endpoint",
        "key_env",
        "input_usd_per_million",
        "output_usd_per_million",
    ):
        writer[field] = ranking[field]
    data["voices"] = {
        k: v
        for k, v in data["voices"].items()
        if not k.startswith("chatter:") or k == "chatter:en"
    }
    data["locale_routes"] = {
        k: v for k, v in data["locale_routes"].items() if k in data["voices"]
    }
    data["enabled"] = True
    data["chatter"].update(
        enabled=True,
        discovery_lane="personalized-trends-v2",
        selector=ranking,
        trial={
            "scope": scope,
            "limit_usd": limit,
            "carry_usd": carry,
            "publication_limit": 1,
        },
    )
    return EditorialConfig.model_validate(data)


def scheduled_watch_tick(start, end, scope, limit, carry, *, now):
    start, end = datetime.fromisoformat(start), datetime.fromisoformat(end)
    if start.utcoffset() is None or end.utcoffset() is None or end <= start:
        raise CommandError("The staging watch requires an absolute start and end")
    if (
        os.environ.get("RENDER_SERVICE_NAME") != EXPECTED_SERVICE_NAME
        or os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT")
        != EXPECTED_DEPLOYMENT_ENVIRONMENT
    ):
        raise CommandError("The Chatter watch requires the staging harvest service")
    if not start <= now < end:
        return {"status": "outside_watch"}
    root = Path(settings.BASE_DIR)
    _inspect_database(connection, load_policy(root / "config/staging_refresh.yaml"))
    cfg = watch_profile(
        load_editorial_config(root / "config/editorial-chatter-staging.yaml"),
        scope,
        limit,
        carry,
    )
    source = f"{EXPECTED_SERVICE_NAME}:{now.isoformat()}"
    result = dispatch_chatter_cycle(
        source, now, kind="scheduled", dry_run=False, cfg=cfg
    )
    if result["status"] == "unavailable":
        raise CommandError("Scheduled Chatter dispatch failed")
    return {**result, "source_cycle_id": source, "watch_ends": end.isoformat()}
