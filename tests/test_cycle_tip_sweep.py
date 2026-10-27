from __future__ import annotations

from datetime import UTC, datetime, timezone
from types import SimpleNamespace

import pytest

from monitor import cycle as cycle_mod
from monitor.cycle import CycleRunner
from x_monitor.config import Config, HarvestConfig, SearchConfig
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


def test_all_seven_searches_use_configured_pages_before_enrichment(monkeypatch):
    call_ids = ["A", "B1", "B2", "B3", "C1", "C2", "C3"]
    calls = [_call(call_id) for call_id in call_ids]
    events: list[str] = []

    class Api:
        timeout_s = 1
        max_retries = 0

        def run_search(self, query, **kwargs):
            assert kwargs["max_pages"] == 5
            assert kwargs["max_results"] == 100
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
    monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", lambda cfg=None, **_kwargs: calls)
    monkeypatch.setattr(
        cycle_mod.XClient,
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


@pytest.mark.parametrize("stop", ["provider_end", "late_error", "deadline", "page_cap", "no_time"])
def test_scheduled_cursor_pages_are_stored_before_enrichment(
    monkeypatch, seeded_policy_keywords, stop,
):
    from datetime import timedelta

    from core.models import CallState, HarvestBacklogWindow, Post, PostBrand
    from x_monitor.x_client import XClient, XClientServerError

    now = datetime.now(UTC).replace(microsecond=0)
    call = _call("B1")
    api = XClient(api_key="fake-only", timeout_s=1, max_retries=0)
    requests = []
    expected_ids = {str(1000 + n) for n in range(43)}

    class Deadline:
        def remaining(self):
            return 0 if stop == "no_time" or (stop == "deadline" and requests) else 400

    def get(path, params, **_kwargs):
        requests.append(dict(params))
        if stop == "late_error" and len(requests) == 2:
            raise XClientServerError("fake second-page timeout")
        idx = len(requests) - 1
        start, end = [(0, 20), (20, 23), (23, 43), (43, 43)][idx]
        data = {
            "tweets": [{
                "id": str(1000 + n), "text": "DeepSeek release", "lang": "en",
                "createdAt": (now - timedelta(minutes=4)).isoformat(),
                "author": {"id": "author1", "userName": "test_author"},
            } for n in range(start, end)],
            "has_next_page": idx < 3,
            "next_cursor": f"cursor{idx + 1}" if idx < 3 else "",
        }

        import json

        from requests import Response

        response = Response()
        response.status_code = 200
        response._content = json.dumps(data).encode()
        return response

    monkeypatch.setattr("x_monitor.x_client.requests.get", get)
    monkeypatch.setattr(cycle_mod.XClient, "from_env", classmethod(lambda cls, purpose: api))
    monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", lambda *args, **kwargs: [call])
    monkeypatch.setattr(HarvestConfig, "start_deadline", lambda *a, **k: Deadline())
    # Backlog cannot hide a failure to page the current interval in this test.
    monkeypatch.setattr(CycleRunner, "_replay_backlog", lambda *a, **k: [])
    monkeypatch.setattr("monitor.metrics_refresh.run_metrics_refresh", lambda *a, **k: {})
    seen_at_enrichment = []

    def post_fetch(self, items, **kwargs):
        seen_at_enrichment.append(set(Post.objects.values_list("tweet_id", flat=True)))
        return {}

    monkeypatch.setattr(CycleRunner, "_run_post_fetch", post_fetch)
    cfg = Config(
        enabled_models=["deepseek"], daily_ceiling=100,
        search=SearchConfig(max_results=100, max_pages=1 if stop == "page_cap" else 10),
    )
    result = CycleRunner(cfg=cfg, cycle_kind="scheduled", _collection_window_end=now).run()

    stored = set(Post.objects.values_list("tweet_id", flat=True))
    wanted = (expected_ids if stop == "provider_end" else set() if stop == "no_time"
              else {str(1000+n) for n in range(20)})
    assert stored == wanted
    assert seen_at_enrichment == [wanted]
    assert set(PostBrand.objects.filter(brand_id="deepseek").values_list("post_id", flat=True)) == wanted
    assert result["totals"]["n_inserted"] == len(wanted)
    assert len({r["query"] for r in requests}) == (0 if stop == "no_time" else 1)
    assert [r.get("cursor") for r in requests] == (
        [None, "cursor1", "cursor2", "cursor3"] if stop == "provider_end"
        else [None, "cursor1"] if stop == "late_error" else [] if stop == "no_time" else [None]
    )
    if stop == "provider_end":
        assert not HarvestBacklogWindow.objects.exists()
        assert CallState.objects.get().last_completed_at == now
        assert result["calls"][0]["status"] == "completed"
    elif stop == "no_time":
        backlog = HarvestBacklogWindow.objects.get()
        assert backlog.remaining_until == now
        assert backlog.remaining_since == now - timedelta(minutes=15)
        assert result["calls"][0]["status"] == "truncated_replay_queued"
    else:
        assert HarvestBacklogWindow.objects.filter(reason_code="page_cap").exists()
        assert result["calls"][0]["status"] == "truncated_replay_queued"
