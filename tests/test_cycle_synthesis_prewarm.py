"""Regression net for CycleRunner's bounded synthesis-demand prewarm."""

from __future__ import annotations

import pytest
from django.test import override_settings

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _run_cycle(
    monkeypatch,
    *,
    prewarm_enabled: bool,
    prewarm_per_cycle: int,
    selected_call_ids: list[str] | None = None,
):
    from core.models import Brand
    from monitor import cycle as cycle_mod
    from monitor.cycle import CycleRunner
    from x_monitor.attribution import MentionRow
    from x_monitor.config import Config, SynthesisConfig
    from x_monitor.query_plan import PlannedCall

    Brand.objects.get_or_create(
        nickname="deepseek",
        defaults={"display_name": "DeepSeek", "is_sentinel": False},
    )

    calls = [
        PlannedCall(
            call_id=call_id,
            call_kind="brand_wide",
            brand_id="deepseek",
            bucket=None,
            query_string=call_id,
            query_length=len(call_id),
        )
        for call_id in ("B1", "B2")
    ]

    class FakeApi:
        timeout_s = 1
        max_retries = 0

        def run_search(self, query, **_kwargs):
            ids = (
                ("prewarm-0", "prewarm-1")
                if query == "B1"
                else ("prewarm-1", "prewarm-2")
            )
            return [
                {
                    "id": post_id,
                    "author_id": f"author-{post_id}",
                    "author_handle": f"author_{post_id}",
                    "text": "DeepSeek release",
                    "lang": "en",
                    "created_at": "2026-09-19T00:00:01+00:00",
                }
                for post_id in ids
            ], False

    def attribute(_self, items, _index, _search_terms):
        for item in items:
            post_id = str(item["id"])
            item["_unattributed"] = False
            item["brand_id"] = "deepseek"
            item["brand_ids"] = ["deepseek"]
            item["mentions"] = [
                MentionRow(
                    post_id=post_id,
                    brand_id="deepseek",
                    source="body_keyword",
                    raw_token="deepseek",
                    mentioned_at=item["created_at"],
                )
            ]
            item["classifications"] = {}
        return len(items)

    monkeypatch.setattr(CycleRunner, "_plan_calls", lambda self: calls)
    monkeypatch.setattr(CycleRunner, "_attribute_items", attribute)
    monkeypatch.setattr(cycle_mod, "_build_brand_index", lambda _models: (None, {}))
    monkeypatch.setattr(cycle_mod, "_load_brand_search_terms", dict)
    monkeypatch.setattr(
        cycle_mod.TwitterApiClient,
        "from_env",
        classmethod(lambda cls, _purpose: FakeApi()),
    )
    monkeypatch.setattr(cycle_mod, "_advance_cursor", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(CycleRunner, "_run_post_fetch", lambda self, *_args, **_kwargs: {})
    monkeypatch.setattr(
        "monitor.metrics_refresh.run_metrics_refresh",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "scripts.harvest_cost.emit.finalize_and_persist",
        lambda summary, _api: summary,
    )

    cfg = Config(
        enabled_models=["deepseek"],
        daily_ceiling=100,
        synthesis=SynthesisConfig(
            prewarm_enabled=prewarm_enabled,
            prewarm_per_cycle=prewarm_per_cycle,
        ),
    )
    with override_settings(
        X_MONITOR_CYCLE_SINCE_TIME=1_789_776_000,
        X_MONITOR_CYCLE_UNTIL_TIME=1_789_776_060,
        X_MONITOR_CYCLE_SKIP_FETCH=False,
    ):
        return CycleRunner(
            cfg=cfg,
            cycle_kind="manual",
            _backfill_call_ids=selected_call_ids,
        ).run()


def test_cycle_prewarm_is_disabled_by_default_and_creates_no_demand(monkeypatch):
    from core.models import PostSynthesisDemand

    summary = _run_cycle(
        monkeypatch,
        prewarm_enabled=False,
        prewarm_per_cycle=0,
    )

    assert summary["synthesis_prewarm"] == {
        "enabled": False,
        "configured_cap": 0,
        "candidate_count": 0,
        "selected_count": 0,
        "requested_count": 0,
        "failed_count": 0,
    }
    assert PostSynthesisDemand.objects.count() == 0


def test_cycle_prewarm_is_bounded_and_dedupes_across_fetch_calls(monkeypatch):
    from core.models import PostSynthesisDemand

    summary = _run_cycle(
        monkeypatch,
        prewarm_enabled=True,
        prewarm_per_cycle=2,
    )

    evidence = summary["synthesis_prewarm"]
    assert evidence["enabled"] is True
    assert evidence["configured_cap"] == 2
    assert evidence["candidate_count"] == 3
    assert evidence["selected_count"] == 2
    assert evidence["requested_count"] == 2
    assert evidence["failed_count"] == 0
    assert list(
        PostSynthesisDemand.objects.order_by("post_id").values_list(
            "post_id", "reason", "state"
        )
    ) == [
        ("prewarm-0", "prewarm", "pending"),
        ("prewarm-1", "prewarm", "pending"),
    ]


def test_bounded_call_selection_reports_only_selected_plan(monkeypatch):
    summary = _run_cycle(
        monkeypatch,
        prewarm_enabled=False,
        prewarm_per_cycle=0,
        selected_call_ids=["B2"],
    )

    assert summary["totals"]["n_calls_planned"] == 1
    assert [row["call_id"] for row in summary["planned_calls"]] == ["B2"]
    assert [row["call_id"] for row in summary["calls"]] == ["B2"]


def test_prewarm_request_rolls_back_the_full_selected_batch_on_partial_failure(
    monkeypatch,
):
    """A failed second demand cannot leave the first prewarmed on its own."""
    from core.models import Post, PostSynthesisDemand
    from monitor import post_synthesis
    from monitor.post_synthesis import request_post_synthesis
    from x_monitor.config import SynthesisConfig

    first = Post.objects.create(tweet_id="prewarm-atomic-first", text="first")
    second = Post.objects.create(tweet_id="prewarm-atomic-second", text="second")
    original_upsert = post_synthesis._upsert_demand
    attempts = 0

    def fail_after_first(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise RuntimeError("simulated demand write failure")
        return original_upsert(**kwargs)

    monkeypatch.setattr(post_synthesis, "_upsert_demand", fail_after_first)

    with pytest.raises(RuntimeError, match="simulated demand write failure"):
        request_post_synthesis(
            post_ids=[first.pk, second.pk],
            reason="prewarm",
            config=SynthesisConfig(prewarm_enabled=True, prewarm_per_cycle=2),
        )

    assert attempts == 2
    assert PostSynthesisDemand.objects.count() == 0


def test_cycle_reports_atomic_prewarm_failure_as_counts_only(monkeypatch):
    """The real caller cannot report a partial demand batch as requested."""
    from core.models import PostSynthesisDemand
    from monitor import post_synthesis

    original_upsert = post_synthesis._upsert_demand
    attempts = 0

    def fail_after_first(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise RuntimeError("simulated demand write failure")
        return original_upsert(**kwargs)

    monkeypatch.setattr(post_synthesis, "_upsert_demand", fail_after_first)

    summary = _run_cycle(
        monkeypatch,
        prewarm_enabled=True,
        prewarm_per_cycle=2,
    )

    assert summary["synthesis_prewarm"] == {
        "enabled": True,
        "configured_cap": 2,
        "candidate_count": 3,
        "selected_count": 2,
        "requested_count": 0,
        "failed_count": 1,
    }
    assert summary["n_errors_by_type"]["synthesis_prewarm_failed"] == 1
    assert "synthesis_prewarm_failed" in summary["errors"]
    assert "simulated demand write failure" not in str(summary)
    assert attempts == 2
    assert PostSynthesisDemand.objects.count() == 0
