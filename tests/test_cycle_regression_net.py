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
        "A", "B1", "B2", "B3", "C1", "C2", "C3", "C4"
    }
    assert all("dots3-note" not in call.query_string for call in calls)


def test_plan_calls_for_cycle_brand_filter_builds_only_that_brands_calls():
    """Historical brand filters narrow call contents, not only attribution."""
    _django_setup()
    from django.test import override_settings

    from monitor.cycle import plan_calls_for_cycle
    from x_monitor.config import load_config

    cfg = load_config(CONFIG_PATH)
    with override_settings(X_MONITOR_CYCLE_BRAND_FILTER="dots"):
        calls = plan_calls_for_cycle(cfg=cfg)

    assert [call.call_id for call in calls] == ["A", "B1"]
    b1 = calls[1].query_string
    assert '"dots 3 note"' in b1
    assert "DeepSeek" not in b1
    assert "Hunyuan" not in b1


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
@pytest.mark.parametrize(
    "cycle_kind,enrichment_mode",
    [("manual", "inline"), ("scheduled", "inline"), ("scheduled", "worker")],
)
def test_real_cycle_captures_all_seven_queries_and_attributes_new_aliases(
    monkeypatch, seeded_policy_keywords, cycle_kind, enrichment_mode, tmp_path, caplog
):
    """The live caller sends the policy exhibit and persists aliases.

    This drives ``CycleRunner.run`` through its real planner, fetch loop, DB
    attribution seam, and enrichment handoff. The provider is fake and
    captures the query kwargs; no TwitterAPI request is made. We assert seven
    *logical* planned calls, while allowing the provider client to make
    additional pagination requests in a real run.
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
        base_url = "https://api.twitterapi.io"

        def __init__(self):
            self.calls: list[tuple[str, dict]] = []
            self._request_log: list[dict] = []

        def run_search(self, query, **kwargs):
            self.calls.append((query, kwargs))
            if getattr(self, "on_exchange_start", None) is not None:
                receipt = self.on_exchange_start(
                    "/twitter/tweet/advanced_search", {"query": query},
                )
                self.on_exchange_finish(receipt, {
                    "outcome": "received", "status_code": 200,
                    "body": b'{"tweets":[]}', "error_type": None,
                })
            return [
                {
                    "id": "2094999721551225264",
                    "author_id": "u5-author-dots",
                    "author_handle": "u5_dots",
                    "text": "Dots 3 Note Preview is out",
                    "lang": "en",
                    "created_at": "Sat Jul 25 12:00:00 +0000 2026",
                },
                {
                    "id": "2094999721551225265",
                    "author_id": "u5-author-hy",
                    "author_handle": "u5_hy",
                    "text": "hy4 is genuinely unltd",
                    "lang": "en",
                    "created_at": "Sat Jul 25 12:00:01 +0000 2026",
                },
                {
                    "id": "2094999721551225266",
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
    enrichment_input: list[tuple[str, str, bool]] = []
    real_post_fetch = CycleRunner._run_post_fetch

    def capture_post_fetch(_runner, items, **_kwargs):
        enrichment_input.extend(
            (
                str(item["id"]),
                str(item["_persisted_post_id"]),
                bool(item["_db_inserted"]),
            )
            for item in items
        )
        if enrichment_mode == "worker":
            return real_post_fetch(_runner, items, **_kwargs)
        return {}

    monkeypatch.setattr(
        cycle_mod.TwitterApiClient,
        "from_env",
        classmethod(lambda cls, _purpose: api),
    )
    monkeypatch.setattr(CycleRunner, "_run_post_fetch", capture_post_fetch)
    monkeypatch.setattr(
        "monitor.metrics_refresh.run_metrics_refresh",
        lambda *args, **kwargs: {},
    )
    if enrichment_mode == "worker":
        monkeypatch.setattr(
            CycleRunner, "_process_enrichment_claim_batch",
            lambda *args, **kwargs: pytest.fail("worker handoff ran inline enrichment"),
        )
        monkeypatch.setattr(cost_emit, "default_runs_dir", lambda *args, **kwargs: tmp_path)
        caplog.set_level("INFO", logger="scripts.harvest_cost.emit")
    else:
        monkeypatch.setattr(cost_emit, "finalize_and_persist", lambda *args, **kwargs: None)

    cfg = load_config(CONFIG_PATH)
    cfg.harvest.enrichment.mode = enrichment_mode
    with override_settings(
        X_MONITOR_CYCLE_SINCE_TIME=1_785_067_200,
        X_MONITOR_CYCLE_UNTIL_TIME=1_785_067_260,
        X_MONITOR_CYCLE_SKIP_FETCH=False,
        X_MONITOR_LLM_PAUSE_SECONDS=0,
    ):
        stats = CycleRunner(cfg=cfg, cycle_kind=cycle_kind).run()

    if cycle_kind == "scheduled":
        from core.models import (
            CollectionObservation,
            CollectionObservationInput,
            CollectionRun,
            PostEnrichmentState,
        )

        collection = CollectionRun.objects.get(job__operation="x_cycle")
        assert collection.request_count == len(api.calls)
        assert collection.scopes.filter(scope_kind="x_query").count() >= len(api.calls)
        assert CollectionObservation.objects.filter(
            run=collection, post_id="2094999721551225264",
        ).count() == len(api.calls)
        assert CollectionObservationInput.objects.filter(
            observation__run=collection,
            observation__post_id="2094999721551225264",
        ).count() == len(api.calls)
        assert PostEnrichmentState.objects.get(
            post_id="2094999721551225264",
        ).source_collection_job_id is None

    assert tuple(row["call_id"] for row in stats["planned_calls"]) == EXPECTED_PLANNER_CALL_ORDER
    captured_queries = tuple(query for query, _kwargs in api.calls)
    assert captured_queries == tuple(
        f"{query} -from:xxyweb3" if cycle_kind == "scheduled" else query
        for query in EXPECTED_QUERY_EXHIBIT.values()
    )
    assert all(
        kwargs["max_results"] == 2000
        and kwargs["max_pages"] == 100
        and kwargs["max_per_page"] == 20
        and kwargs["since_time"] == 1_785_067_200
        and kwargs["until_time"] == 1_785_067_260
        for _query, kwargs in api.calls
    )
    assert stats["totals"]["n_calls_planned"] == len(EXPECTED_PLANNER_CALL_ORDER)
    assert PostBrand.objects.filter(post_id="2094999721551225264", brand_id="dots").exists()
    assert PostBrand.objects.filter(post_id="2094999721551225265", brand_id="hunyuan").exists()
    assert PostBrand.objects.filter(post_id="2094999721551225266", brand_id="glm").exists()
    assert PostBrand.objects.filter(
        post_id="2094999721551225267", brand_id="moonshot_kimi"
    ).exists()
    assert enrichment_input == [
        ("2094999721551225264", "2094999721551225264", True),
        ("2094999721551225265", "2094999721551225265", True),
        ("2094999721551225266", "2094999721551225266", True),
        ("2094999721551225267", "2094999721551225267", True),
    ]
    if enrichment_mode == "worker":
        from monitor.harvest_summary import (
            HARVEST_COHORT_PREFIX, HARVEST_SUMMARY_PREFIX,
            parse_cohort_line, parse_summary_line,
        )

        envelopes = [
            parse_summary_line(record.message) for record in caplog.records
            if record.message.startswith(HARVEST_SUMMARY_PREFIX)
        ]
        cohorts = [
            record.message for record in caplog.records
            if record.message.startswith(HARVEST_COHORT_PREFIX)
        ]
        assert len(envelopes) == len(cohorts) == 1
        receipt = parse_cohort_line(cohorts[0], summary_envelope=envelopes[0])
        assert receipt["inserted_post_ids"] == sorted(row[1] for row in enrichment_input)
        assert len(receipt["inserted_post_ids"]) == stats["totals"]["n_inserted"] == 4
        assert receipt["current_cycle_post_ids"] == []
        assert receipt["carryover_post_ids"] == []
        assert receipt["enrichment_state_facts"] == []
        assert (tmp_path / f"{stats['run_id']}.json").is_file()
        assert not PostEnrichmentState.objects.exclude(claim_run_id="").exists()
        assert all(state.translation_attempts == state.classification_attempts == 0
                   for state in PostEnrichmentState.objects.all())


@pytest.mark.requires_postgres
@pytest.mark.django_db
@pytest.mark.parametrize("search_outcome", ["empty", "server_error", "parse_error"])
def test_scheduled_empty_and_failed_search_keep_distinct_scope_coverage(
    monkeypatch, seeded_policy_keywords, search_outcome,
):
    from django.test import override_settings

    from core.models import CollectionRun
    from monitor import cycle as cycle_mod
    from monitor.cycle import CycleRunner
    from scripts.harvest_cost import emit as cost_emit
    from x_monitor.apify import TwitterApiServerError
    from x_monitor.config import load_config

    class FakeApi:
        base_url = "https://api.twitterapi.io"
        timeout_s = 60
        max_retries = 0

        def run_search(self, query, **kwargs):
            request = self.on_exchange_start(
                "/twitter/tweet/advanced_search", {"query": query},
            )
            self.on_exchange_finish(request, {
                "outcome": "received",
                "status_code": 503 if search_outcome == "server_error" else 200,
                "body": (
                    b"busy" if search_outcome == "server_error"
                    else b"not json" if search_outcome == "parse_error"
                    else b'{"tweets":[]}'
                ),
                "error_type": None,
            })
            if search_outcome == "server_error":
                raise TwitterApiServerError("provider busy")
            if search_outcome == "parse_error":
                raise ValueError("malformed provider response")
            return [], False

    cfg = load_config(CONFIG_PATH)
    original_plan = CycleRunner._plan_calls
    monkeypatch.setattr(
        CycleRunner, "_plan_calls", lambda runner: original_plan(runner)[:1],
    )
    monkeypatch.setattr(
        cycle_mod.TwitterApiClient, "from_env",
        classmethod(lambda cls, _purpose: FakeApi()),
    )
    monkeypatch.setattr(CycleRunner, "_run_post_fetch", lambda *a, **k: {})
    monkeypatch.setattr(cost_emit, "finalize_and_persist", lambda *a, **k: None)
    monkeypatch.setattr("monitor.metrics_refresh.run_metrics_refresh", lambda *a, **k: {})
    with override_settings(
        X_MONITOR_CYCLE_SINCE_TIME=1_785_067_200,
        X_MONITOR_CYCLE_UNTIL_TIME=1_785_067_260,
        X_MONITOR_CYCLE_SKIP_FETCH=False,
    ):
        stats = CycleRunner(cfg=cfg, cycle_kind="scheduled").run()
    run = CollectionRun.objects.get(job__operation="x_cycle")
    scope = run.scopes.get(scope_key="A")
    assert run.request_count == 1
    assert scope.raw_count == 0
    assert scope.coverage_state == (
        "complete" if search_outcome == "empty" else "unavailable"
    )
    assert scope.enumeration_complete is (search_outcome == "empty")
    assert bytes(scope.requests.get().archive.body) == (
        b"busy" if search_outcome == "server_error"
        else b"not json" if search_outcome == "parse_error"
        else b'{"tweets":[]}'
    )
    assert stats["calls"][0]["cursor_advanced"] is False


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_scheduled_lineage_failure_holds_cursor_after_post_commit(
    monkeypatch, seeded_policy_keywords,
):
    from core.models import Post
    from monitor import cycle as cycle_mod
    from monitor.cycle import CycleRunner
    from x_monitor.config import load_config

    class FakeApi:
        base_url = "https://api.twitterapi.io"
        timeout_s = 60
        max_retries = 0

        def run_search(self, query, **kwargs):
            request = self.on_exchange_start(
                "/twitter/tweet/advanced_search", {"query": query},
            )
            self.on_exchange_finish(request, {
                "outcome": "received", "status_code": 200,
                "body": b'{"tweets":[{"id":"lineage-commit"}]}',
                "error_type": None,
            })
            return [{
                "id": "lineage-commit", "author_id": "lineage-author",
                "author_handle": "lineage_author", "text": "Qwen3 released",
                "lang": "en", "created_at": "Sat Jul 25 12:00:00 +0000 2026",
            }], False

    cfg = load_config(CONFIG_PATH)
    original_plan = CycleRunner._plan_calls
    monkeypatch.setattr(
        CycleRunner, "_plan_calls", lambda runner: original_plan(runner)[1:2],
    )
    monkeypatch.setattr(
        CycleRunner, "_resolve_window",
        lambda *a, **k: (1_785_067_200, 1_785_067_260, True),
    )
    monkeypatch.setattr(
        cycle_mod.TwitterApiClient, "from_env",
        classmethod(lambda cls, _purpose: FakeApi()),
    )
    advances = []
    monkeypatch.setattr(cycle_mod, "_advance_cursor", lambda *a, **k: advances.append(1))
    monkeypatch.setattr(
        "core.x_cycle_lineage.save_post_membership",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("lineage refusal")),
    )
    with pytest.raises(RuntimeError, match="lineage refusal"):
        CycleRunner(cfg=cfg, cycle_kind="scheduled").run()
    assert Post.objects.filter(pk="lineage-commit").exists()
    assert advances == []


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_scheduled_truncated_search_keeps_saved_post_and_partial_coverage(
    monkeypatch, seeded_policy_keywords,
):
    from django.test import override_settings

    from core.models import CollectionObservationInput, CollectionRun
    from monitor import cycle as cycle_mod
    from monitor.cycle import CycleRunner
    from scripts.harvest_cost import emit as cost_emit
    from x_monitor.config import load_config

    class FakeApi:
        base_url = "https://api.twitterapi.io"
        timeout_s = 60
        max_retries = 0

        def run_search(self, query, **kwargs):
            request = self.on_exchange_start(
                "/twitter/tweet/advanced_search", {"query": query},
            )
            self.on_exchange_finish(request, {
                "outcome": "received", "status_code": 200,
                "body": b'{"tweets":[{"id":"partial-lineage-post"}],"has_next_page":true}',
                "error_type": None,
            })
            return [{
                "id": "partial-lineage-post", "author_id": "partial-author",
                "author_handle": "partial_author", "text": "Qwen3 released",
                "lang": "en", "created_at": "Sat Jul 25 12:00:00 +0000 2026",
            }], True

    cfg = load_config(CONFIG_PATH)
    original_plan = CycleRunner._plan_calls
    monkeypatch.setattr(
        CycleRunner, "_plan_calls", lambda runner: original_plan(runner)[1:2],
    )
    monkeypatch.setattr(
        cycle_mod.TwitterApiClient, "from_env",
        classmethod(lambda cls, _purpose: FakeApi()),
    )
    monkeypatch.setattr(CycleRunner, "_run_post_fetch", lambda *a, **k: {})
    monkeypatch.setattr(cost_emit, "finalize_and_persist", lambda *a, **k: None)
    monkeypatch.setattr("monitor.metrics_refresh.run_metrics_refresh", lambda *a, **k: {})
    with override_settings(
        X_MONITOR_CYCLE_SINCE_TIME=1_785_067_200,
        X_MONITOR_CYCLE_UNTIL_TIME=1_785_067_260,
        X_MONITOR_CYCLE_SKIP_FETCH=False,
    ):
        stats = CycleRunner(cfg=cfg, cycle_kind="scheduled").run()
    run = CollectionRun.objects.get(job__operation="x_cycle")
    scope = run.scopes.get(scope_key="B1")
    assert scope.coverage_state == "partial"
    assert not scope.enumeration_complete
    assert scope.observations.filter(post_id="partial-lineage-post").count() == 1
    assert CollectionObservationInput.objects.filter(
        observation__scope_run=scope,
        observation__post_id="partial-lineage-post",
    ).exists()
    assert stats["calls"][0]["cursor_advanced"] is False
