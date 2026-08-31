from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from monitor import cycle as cycle_mod
from monitor.cycle import CycleRunner
from x_monitor.config import Config, SearchConfig
from x_monitor.query_plan import PlannedCall

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def _call(call_id: str) -> PlannedCall:
    return PlannedCall(
        call_id=call_id,
        call_kind="list" if call_id == "A" else "brand_wide",
        brand_id="*" if call_id == "A" else "deepseek",
        bucket=None,
        query_string=call_id,
        query_length=len(call_id),
    )


def test_all_seven_tip_pages_are_persisted_before_any_deep_work(monkeypatch):
    call_ids = ["A", "B1", "B2", "B3", "C1", "C2", "C3"]
    calls = [_call(call_id) for call_id in call_ids]
    events: list[str] = []

    class Api:
        timeout_s = 1
        max_retries = 0

        def run_search(self, query, **kwargs):
            assert kwargs["max_pages"] == 1
            assert kwargs["max_results"] == 20
            events.append(f"fetch:{query}")
            return [
                {
                    "id": query,
                    "author_id": f"author-{query}",
                    "author_handle": f"author_{query}",
                    "text": "DeepSeek release",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ], False

    api = Api()
    monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", lambda cfg=None: calls)
    monkeypatch.setattr(
        cycle_mod.TwitterApiClient,
        "from_env",
        classmethod(lambda cls, _purpose: api),
    )
    monkeypatch.setattr(cycle_mod, "_resolve_enabled_models", lambda cfg, f: [])
    monkeypatch.setattr(cycle_mod, "_build_brand_index", lambda models: (None, {}))
    monkeypatch.setattr(cycle_mod, "_load_brand_search_terms", lambda: {})
    monkeypatch.setattr(cycle_mod, "_advance_cursor", lambda *a, **k: True)
    def post_fetch(self, items, **kwargs):
        events.append("post_fetch")
        return {}

    monkeypatch.setattr(CycleRunner, "_run_post_fetch", post_fetch)
    monkeypatch.setattr(CycleRunner, "_replay_backlog", lambda self, **kwargs: [])

    def observe(**kwargs):
        events.append("observe:A")
        return SimpleNamespace(status="observed", observed=1, degraded=[])

    def reconcile(**kwargs):
        events.append("reconcile")
        return SimpleNamespace(
            status="completed",
            observed=0,
            activated=0,
            deactivated=0,
            snapshot_id="snapshot",
            degraded=[],
        )

    monkeypatch.setattr(cycle_mod, "observe_call_a_authors", observe)
    monkeypatch.setattr(cycle_mod, "run_due_reconciliation", reconcile)

    def attribute(self, items, index, search_terms):
        for item in items:
            item["_unattributed"] = False
        return len(items)

    def persist(self, items):
        events.append(f"persist:{items[0]['id']}")
        return len(items), 0, len(items), 0

    monkeypatch.setattr(CycleRunner, "_attribute_items", attribute)
    monkeypatch.setattr(CycleRunner, "_persist_items", persist)

    cfg = Config(
        enabled_models=["deepseek"],
        daily_ceiling=100,
        x_monitor_list_id=42,
        search=SearchConfig(max_results=100, max_pages=5, max_per_page=20),
    )
    result = CycleRunner(cfg=cfg, cycle_kind="scheduled").run()

    expected = []
    for call_id in call_ids:
        expected.append(f"fetch:{call_id}")
        if call_id == "A":
            expected.append("observe:A")
        expected.append(f"persist:{call_id}")
    expected.extend(["post_fetch", "reconcile"])
    assert events == expected
    assert result["totals"]["n_calls_run"] == 7
    assert result["tip_sweep_within_target"] is True
    assert [row["call_id"] for row in result["planned_calls"]] == call_ids
    assert [row["call_id"] for row in result["calls"]] == call_ids
    assert all(row["execution_kind"] == "live" for row in result["calls"])
    assert all(row["replay"] is False for row in result["calls"])
    assert len(result["calls"]) == len(result["planned_calls"])
