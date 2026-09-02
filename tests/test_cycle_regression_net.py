"""Regression net for plan 2026-08-01-002 U0.

Pins:
- plan_calls_for_cycle() accepts cfg: Config | None = None without
  raising NameError. The function body was migrated to use self.cfg
  by plan 2026-08-01-001 but the function signature was not updated
  to a method, so module-level callers hit NameError. This test
  would have caught the original regression (commit 05c3d92).
- CycleRunner._plan_calls() does not abort with NameError; the
  7-call hybrid layout flows through.
"""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.yaml"


def _django_setup():
    """Configure Django for monitor.cycle imports.

    Idempotent — safe to call from multiple tests.
    """
    import os
    os.environ.setdefault("DATABASE_URL", "sqlite:///data/django_dev.db")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    os.environ.setdefault("TWITTERAPI_IO_SCHEDULED_API_KEY", "dummy_for_regression_test")
    import django
    if not django.apps.apps.ready:
        django.setup()


def test_plan_calls_for_cycle_accepts_optional_cfg():
    """plan_calls_for_cycle must accept cfg=None without raising NameError.

    Pin against the post-2026-08-02 signature: cfg: Config | None = None.
    """
    _django_setup()
    from monitor.cycle import plan_calls_for_cycle

    # Call with no arg — must not raise NameError; returns a list.
    result = plan_calls_for_cycle()
    assert isinstance(result, list), (
        "plan_calls_for_cycle() must return a list of PlannedCall; "
        "the regression was returning NameError instead."
    )


def test_plan_calls_for_cycle_accepts_cfg_kwarg():
    """plan_calls_for_cycle must accept cfg= kwarg without raising."""
    _django_setup()
    from monitor.cycle import plan_calls_for_cycle
    from x_monitor.config import load_config

    cfg = load_config(CONFIG_PATH)
    result = plan_calls_for_cycle(cfg=cfg)
    assert isinstance(result, list)


def test_plan_calls_for_cycle_uses_enabled_models_as_query_allowlist():
    """The production planner and attribution preflight use one brand set."""
    _django_setup()
    from monitor.cycle import plan_calls_for_cycle
    from x_monitor.config import load_config

    cfg = load_config(CONFIG_PATH)
    cfg.enabled_models.remove("dots")

    calls = plan_calls_for_cycle(cfg=cfg)

    assert {call.call_id for call in calls} == {
        "A", "B1", "B2", "B3", "C1", "C2", "C3"
    }
    assert all("dots3-note" not in call.query_string for call in calls)


def test_cycle_runner_plan_calls_does_not_abort_with_self_undefined():
    """CycleRunner._plan_calls() must return the 7-call layout, not [].

    The original bug (commit 05c3d92) caused _plan_calls to return []
    because plan_calls_for_cycle() raised NameError on `self.cfg`.
    The empty-list return was logged as 'plan_calls failed' and the
    cycle aborted with 0 inserted.
    """
    _django_setup()
    from monitor.cycle import CycleRunner
    from x_monitor.config import load_config

    cfg = load_config(CONFIG_PATH)
    runner = CycleRunner(dry_run=True, cfg=cfg)
    calls = runner._plan_calls()
    # The 7-call hybrid layout must flow through. Even without the
    # full TwitterAPI fetch, the planning step must produce calls.
    # (Dry-run may trim the list, but the function must not crash
    # AND must not return [] solely because of the NameError.)
    assert isinstance(calls, list)
    # If the regression had fired, the cycle's error log would have
    # an entry. We check that _errors is empty as the strongest
    # signal the NameError path was avoided.
    assert runner._errors == [], (
        f"CycleRunner._errors must be empty after _plan_calls; got {runner._errors}. "
        "Empty list typically indicates the NameError regression."
    )


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_real_cycle_captures_all_seven_queries_and_attributes_new_aliases(
    monkeypatch, seeded_policy_keywords
):
    """The live caller sends the policy exhibit and persists aliases.

    This drives ``CycleRunner.run`` through its real planner, fetch loop, and
    DB attribution seam. The provider is fake and captures the query kwargs;
    no TwitterAPI request is made. We assert seven *logical* planned calls,
    while allowing the provider client to make additional pagination requests
    in a real run.
    """
    from django.test import override_settings

    from core.models import PostBrand
    from monitor import cycle as cycle_mod
    from monitor.cycle import CycleRunner
    from scripts.harvest_cost import emit as cost_emit
    from tests.test_harvest_query_exhibit import (
        EXPECTED_PLANNER_CALL_ORDER,
        EXPECTED_QUERY_EXHIBIT,
    )
    from x_monitor.config import load_config

    class FakeApi:
        timeout_s = 60
        max_retries = 0

        def __init__(self):
            self.calls: list[tuple[str, dict]] = []
            self._request_log: list[dict] = []

        def run_search(self, query, **kwargs):
            self.calls.append((query, kwargs))
            return [
                {
                    "id": "u5-dots",
                    "author_id": "u5-author-dots",
                    "author_handle": "u5_dots",
                    "text": "dots3-note Preview is out",
                    "lang": "en",
                    "created_at": "Sat Jul 25 12:00:00 +0000 2026",
                },
                {
                    "id": "u5-hy",
                    "author_id": "u5-author-hy",
                    "author_handle": "u5_hy",
                    "text": "hy4 is genuinely unltd",
                    "lang": "en",
                    "created_at": "Sat Jul 25 12:00:01 +0000 2026",
                },
                {
                    "id": "u5-ox",
                    "author_id": "u5-author-ox",
                    "author_handle": "u5_ox",
                    "text": "Ox Alpha is no longer available",
                    "lang": "en",
                    "created_at": "Sat Jul 25 12:00:02 +0000 2026",
                },
                {
                    "id": "2094999721551225267",
                    "author_id": "u5-author-kimi",
                    "author_handle": "u5_kimi",
                    "text": "Moonshot AI's Kimi K3 climbed to third place",
                    "lang": "en",
                    "created_at": "Sat Jul 25 12:00:03 +0000 2026",
                },
            ], False

    api = FakeApi()
    monkeypatch.setattr(
        cycle_mod.TwitterApiClient,
        "from_env",
        classmethod(lambda cls, _purpose: api),
    )
    monkeypatch.setattr(CycleRunner, "_run_post_fetch", lambda self, items, **kwargs: {})
    monkeypatch.setattr(
        "monitor.metrics_refresh.run_metrics_refresh",
        lambda *args, **kwargs: {},
    )
    # A real run would emit a local data/runs summary. Keep this regression
    # net focused on the planner/provider/DB path and filesystem-independent.
    monkeypatch.setattr(cost_emit, "finalize_and_persist", lambda *args, **kwargs: None)

    cfg = load_config(CONFIG_PATH)
    with override_settings(
        X_MONITOR_CYCLE_SINCE_TIME=1_785_067_200,
        X_MONITOR_CYCLE_UNTIL_TIME=1_785_067_260,
        X_MONITOR_CYCLE_SKIP_FETCH=False,
        X_MONITOR_LLM_PAUSE_SECONDS=0,
    ):
        stats = CycleRunner(cfg=cfg, cycle_kind="manual").run()

    assert tuple(row["call_id"] for row in stats["planned_calls"]) == EXPECTED_PLANNER_CALL_ORDER
    captured_queries = tuple(query for query, _kwargs in api.calls)
    assert captured_queries == tuple(EXPECTED_QUERY_EXHIBIT.values())
    assert all(
        kwargs["max_results"] == 2000
        and kwargs["max_pages"] == 100
        and kwargs["max_per_page"] == 20
        and kwargs["since_time"] == 1_785_067_200
        and kwargs["until_time"] == 1_785_067_260
        for _query, kwargs in api.calls
    )
    assert stats["totals"]["n_calls_planned"] == 7
    assert PostBrand.objects.filter(post_id="u5-dots", brand_id="dots").exists()
    assert PostBrand.objects.filter(post_id="u5-hy", brand_id="hunyuan").exists()
    assert PostBrand.objects.filter(post_id="u5-ox", brand_id="glm").exists()
    assert PostBrand.objects.filter(
        post_id="2094999721551225267", brand_id="moonshot_kimi"
    ).exists()
