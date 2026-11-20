"""Shared, provider-free headline context for Each page and narrow refresh."""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.utils import timezone

from monitor.each_request_budget import EachRequestBudget
from monitor.trend_narrative_demand import record_visible_trend_narrative_demand
from monitor.trend_narrative_projection import project_trend_narrative
from x_monitor.config import load_config


def headline_context(*, brand: str | None, window_days: int, locale: str, now=None):
    requested_at = now or timezone.now()
    with EachRequestBudget(seconds=3) as budget, budget.query_scope():
        config = load_config(Path(settings.BASE_DIR) / 'config.yaml').headline_narrative
        narrative = project_trend_narrative(
            window_days, locale=locale,
            selected_brand_keys=[brand] if brand else [],
            now=requested_at, computed_at=requested_at.isoformat(), config=config,
        )
        if brand and config.demand_shaping_enabled:
            record_visible_trend_narrative_demand(
                brand_keys=[brand], window_days=window_days,
                config=config, now=requested_at,
            )
        return {
            'trend_narrative': narrative, 'top_voices': [],
            'active_locale': locale,
            'is_zh_chrome': locale.lower().replace('-', '_') in {'zh', 'zh_cn', 'zh_hans'},
            'is_ja_chrome': locale.lower().split('-')[0] == 'ja',
        }
