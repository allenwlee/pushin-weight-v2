# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.run + x_monitor.query_rot + x_monitor.review."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from x_monitor.config import Config
from x_monitor.relevance import RelevanceConfig
from x_monitor.queries import Query
from x_monitor.query_plan import PlannedCall
from x_monitor.query_rot import apply_rot, detect_rot, read_run_zero_result_streaks
from x_monitor.review import ReviewQueue
from x_monitor.run import RunPipeline, pipeline_lock


# --- run: cost / skip order -----------------------------------------------


def test_estimate_cost_reads_yaml_at_test_time():
    """estimate_cost must reflect the actual loaded YAMLs, not a hardcoded cap."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        (data / "queries").mkdir()
        for m in ["minimax", "qwen", "deepseek"]:
            (data / "queries" / f"{m}.yaml").write_text(
                """
queries:
  - id: Q1
    query_string: 'x'
    expected_signal: release
    max_results: 50
  - id: Q2
    query_string: 'y'
    expected_signal: community_question
    max_results: 50
  - id: Q3
    query_string: 'z'
    expected_signal: criticism
    max_results: 50
  - id: Q4
    query_string: 'w'
    expected_signal: commenter_capture
    max_results: 50
  - id: Q5
    query_string: 'v'
    expected_signal: other
    max_results: 50
  - id: Q6
    query_string: 'praise'
    expected_signal: praise
    max_results: 50
""",
                encoding="utf-8",
            )
        cfg = Config(enabled_models=["minimax", "qwen", "deepseek"], daily_ceiling=333, x_monitor_list_id=1234567890)
        # Pipeline needs a data_dir; we don't call execute here
        p = RunPipeline(cfg, data, db_path=Path(d) / "x.db")
        from x_monitor.queries import load_queries

        per_model = {m: load_queries(m, data) for m in cfg.enabled_models}
        cost = p.estimate_cost(per_model)
        # 3 models × 6 queries × 50 = 900 — ABOVE 333 default
        assert cost == 900
        # Test skip order with a per-model budget smaller than cost
        # (single model cost = 5*50 = 250; budget = 100 → 3 queries dropped)
        kept, skipped = p.apply_skip_order(per_model["minimax"], budget=100)
        assert len(skipped) >= 1
        # Q1 must be in 'kept' (last to drop per R17)
        assert any(q.id == "Q1" for q in kept)


def test_apply_skip_order_drops_in_configured_order():
    """Per R17: Q5 first, then Q3, Q2, Q4, Q1 last."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        cfg = Config(enabled_models=["minimax"], daily_ceiling=50, x_monitor_list_id=1234567890)
        p = RunPipeline(cfg, data, db_path=Path(d) / "x.db")
        qs = [
            Query(id=qid, query_string=qid, expected_signal=signal, max_results=50)
            for qid, signal in [
                ("Q1", "release"),
                ("Q2", "community_question"),
                ("Q3", "criticism"),
                ("Q4", "commenter_capture"),
                ("Q5", "other"),
            ]
        ]
        kept, skipped = p.apply_skip_order(qs, budget=50)
        # Cost = 5*50 = 250. budget=50. Drop in Q5,Q3,Q2,Q4 order until fit.
        # Drop Q5 (cost 200), Q3 (150), Q2 (100), Q4 (50). Q1 is the only one left.
        kept_ids = [q.id for q in kept]
        skipped_ids = [q.id for q in skipped]
        assert "Q1" in kept_ids
        assert skipped_ids[0] == "Q5"
        assert "Q1" not in skipped_ids


# --- run: lock + idempotency ----------------------------------------------


def test_pipeline_lock_is_exclusive():
    with tempfile.TemporaryDirectory() as d:
        lock_path = Path(d) / "LOCK"
        with pipeline_lock(lock_path) as a1:
            assert a1 is True
            with pipeline_lock(lock_path) as a2:
                # Non-blocking second acquire: must fail.
                assert a2 is False


def _v15_deprecated_pipeline_writes_raw_before_db_insert():
    """The raw TwitterAPI.io response is persisted to data/runs/raw/<run_id>/<q>.json
    BEFORE the DB insert. We test by checking order via mocks."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        (data / "queries").mkdir()
        (data / "accounts").mkdir()
        (data / "queries" / "minimax.yaml").write_text(
            """
queries:
  - id: Q1
    query_string: 'from:MiniMaxAI'
    expected_signal: release
    max_results: 5
  - id: Q2
    query_string: 'minimax how'
    expected_signal: community_question
    max_results: 5
  - id: Q3
    query_string: 'minimax broken'
    expected_signal: criticism
    max_results: 5
  - id: Q4
    query_string: 'to:MiniMaxAI'
    expected_signal: commenter_capture
    max_results: 5
  - id: Q5
    query_string: 'minimax benchmark'
    expected_signal: other
    max_results: 5
  - id: Q6
    query_string: 'minimax praise min_faves:5'
    expected_signal: praise
    max_results: 5
""",
            encoding="utf-8",
        )
        (data / "accounts" / "minimax.yaml").write_text(
            """
accounts:
  - handle: MiniMaxAI
    role: official
""",
            encoding="utf-8",
        )
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333, x_monitor_list_id=1234567890)
        p = RunPipeline(cfg, data, db_path=data / "x.db")
        apify = MagicMock()
        # 5 query results (no more cookie probe)
        apify.run_search.side_effect = [
            [{"id": "t1", "text": "hello", "author_handle": "u1"}],  # Q1
            [],  # Q2
            [],  # Q3
            [],  # Q4
            [],  # Q5
            [],  # Q6
        ]
        summary = p.execute(apify, model_filter=["minimax"])
        # All 5 queries should have run (cost 5*5=25 < 333 budget).
        assert summary["totals"]["n_queries_run"] == 6
        # Raw files present
        raw_files = list((data / "runs" / "raw").rglob("*.json"))
        assert len(raw_files) == 6, f"expected 6 raw files, got {len(raw_files)}"
        # DB has the 1 post from Q1
        from x_monitor.store import Store

        store = Store(data / "x.db")
        posts = store.get_all_posts("minimax")
        assert len(posts) == 1
        assert posts[0]["tweet_id"] == "t1"
        store.close()


def test_pipeline_exits_cleanly_when_already_running():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        (data / "queries").mkdir()
        (data / "accounts").mkdir()
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333, x_monitor_list_id=1234567890)
        p = RunPipeline(cfg, data, db_path=data / "x.db")
        # Pre-acquire the lock so the pipeline's first call fails to acquire.
        with pipeline_lock(p.lock_path):
            apify = MagicMock()
            summary = p.execute(apify)
            assert summary["degraded"].get("already_running") is True
            assert summary["status"] == "degraded"
            # Apify was NOT called.
            apify.run_search.assert_not_called()


# --- run: resume ---------------------------------------------------------


def test_resume_does_not_call_apify():
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        run_id = "20260607T000000-deadbeef"
        raw_dir = data / "runs" / "raw" / run_id
        raw_dir.mkdir(parents=True)
        items = [
            {"id": "t1", "model_id": "minimax", "text": "hi"},
            {"id": "t2", "model_id": "minimax", "text": "bye"},
        ]
        (raw_dir / "minimax_Q1.json").write_text(json.dumps(items), encoding="utf-8")
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333, x_monitor_list_id=1234567890)
        p = RunPipeline(cfg, data, db_path=data / "x.db")
        apify = MagicMock()
        out = p.resume(run_id, apify)
        apify.run_search.assert_not_called()
        assert out["totals"]["n_inserted"] == 2


# --- review queue --------------------------------------------------------


def test_review_queue_add_list_resolve(tmp_path):
    q = ReviewQueue(tmp_path / "rq.json")
    e = q.add("t1", reason="suspicious_actor", model_id="minimax")
    assert e["status"] == "open"
    items = q.list()
    assert len(items) == 1
    q.resolve("t1", note="checked")
    items = q.list(status="resolved")
    assert len(items) == 1


def test_review_queue_dismiss(tmp_path):
    q = ReviewQueue(tmp_path / "rq.json")
    q.add("t1", reason="ambiguous_role")
    q.dismiss("t1", note="not actionable")
    assert q.list(status="dismissed")[0]["status"] == "dismissed"


def test_review_queue_add_is_idempotent(tmp_path):
    q = ReviewQueue(tmp_path / "rq.json")
    q.add("t1", reason="low_engagement", model_id="m1")
    q.add("t1", reason="off_topic", model_id="m1")
    items = q.list()
    assert len(items) == 1
    assert items[0]["reason"] == "off_topic"  # updated


def test_append_rule_match(tmp_path):
    q = ReviewQueue(tmp_path / "rq.json")
    q.append_rule_match("t1", "low_engagement", "m1", rule="release_min_faves")
    assert q.list()[0]["note"] == "release_min_faves"


# --- query_rot -----------------------------------------------------------


def test_read_run_zero_result_streaks(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    # Two runs: t1 with Q1=0, Q2=5; t2 with Q1=0, Q2=3
    (runs / "run1.json").write_text(
        json.dumps(
            {
                "started_at": "2026-06-15T00:00:00+00:00",
                "queries": [
                    {"model_id": "m", "query_id": "Q1", "status": "completed", "n_results": 0},
                    {"model_id": "m", "query_id": "Q2", "status": "completed", "n_results": 5},
                ],
            }
        )
    )
    # Force mtime order: run1 older than run2
    import time

    os.utime(runs / "run1.json", (1000, 1000))
    (runs / "run2.json").write_text(
        json.dumps(
            {
                "started_at": "2026-06-15T01:00:00+00:00",
                "queries": [
                    {"model_id": "m", "query_id": "Q1", "status": "completed", "n_results": 0},
                    {"model_id": "m", "query_id": "Q2", "status": "completed", "n_results": 3},
                ],
            }
        )
    )
    os.utime(runs / "run2.json", (2000, 2000))
    streaks = read_run_zero_result_streaks(runs)
    # Q1: 0 then 0 → 2 consecutive; Q2: 5 then 3 → 0 (broken)
    assert streaks[("m", "Q1")] == 2
    assert streaks[("m", "Q2")] == 0


def test_detect_rot_flips_at_threshold(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "run1.json").write_text(
        json.dumps(
            {
                "started_at": "2026-06-15T00:00:00+00:00",
                "queries": [
                    {"model_id": "m", "query_id": "Q1", "status": "completed", "n_results": 0}
                ],
            }
        )
    )
    (runs / "run2.json").write_text(
        json.dumps(
            {
                "started_at": "2026-06-15T01:00:00+00:00",
                "queries": [
                    {"model_id": "m", "query_id": "Q1", "status": "completed", "n_results": 0}
                ],
            }
        )
    )
    (runs / "run3.json").write_text(
        json.dumps(
            {
                "started_at": "2026-06-15T02:00:00+00:00",
                "queries": [
                    {"model_id": "m", "query_id": "Q1", "status": "completed", "n_results": 0}
                ],
            }
        )
    )
    flips = detect_rot(tmp_path / "queries", runs, default_threshold=3, per_model={})
    assert ("m", "Q1", 3) in flips


def test_apply_rot_disables_query_in_yaml(tmp_path):
    qdir = tmp_path / "queries"
    qdir.mkdir()
    (qdir / "m.yaml").write_text(
        """
queries:
  - id: Q1
    query_string: 'x'
    expected_signal: release
    enabled: true
  - id: Q2
    query_string: 'y'
    expected_signal: community_question
    enabled: true
""",
        encoding="utf-8",
    )
    n = apply_rot(qdir, [("m", "Q1", 3)])
    assert n == 1
    import yaml as _yaml

    data = _yaml.safe_load((qdir / "m.yaml").read_text(encoding="utf-8"))
    q1 = next(q for q in data["queries"] if q["id"] == "Q1")
    q2 = next(q for q in data["queries"] if q["id"] == "Q2")
    assert q1["enabled"] is False
    assert q2["enabled"] is True



# --- v1.2: filter integration into the pipeline ----------------------------


def _write_filter_yaml(data_dir: Path, model: str, cfg_dict: dict) -> None:
    (data_dir / "filters").mkdir(exist_ok=True)
    (data_dir / "filters" / f"{model}.yaml").write_text(
        "canonical_handles: []\n"  # placeholder, replaced below
    )
    import yaml as _yaml
    (data_dir / "filters" / f"{model}.yaml").write_text(
        _yaml.safe_dump(cfg_dict, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _v15_deprecated_pipeline_applies_filter_before_insert():
    """5 items: 2 noise (no signal), 1 banned, 2 valid. DB should have 2 rows."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        (data / "queries").mkdir()
        (data / "accounts").mkdir()
        (data / "queries" / "minimax.yaml").write_text(
            "queries:\n"
            "  - id: Q1\n    query_string: 'x'\n    expected_signal: release\n    enabled: false\n"
            "  - id: Q2\n    query_string: 'y'\n    expected_signal: community_question\n    enabled: false\n"
            "  - id: Q3\n    query_string: 'z'\n    expected_signal: criticism\n    enabled: false\n"
            "  - id: Q4\n    query_string: 'w'\n    expected_signal: commenter_capture\n    enabled: false\n"
            "  - id: Q5\n    query_string: 'minimax'\n    expected_signal: other\n    max_results: 50\n"
            "  - id: Q6\n    query_string: 'p'\n    expected_signal: praise\n    enabled: false\n",
            encoding="utf-8",
        )
        (data / "accounts" / "minimax.yaml").write_text("accounts: []\n", encoding="utf-8")
        _write_filter_yaml(
            data, "minimax",
            {
                "canonical_handles": [],
                "must_have_any": ["minimax"],
                "must_have_none": ["celebrity"],
            },
        )
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333, x_monitor_list_id=1234567890)
        p = RunPipeline(cfg, data, db_path=data / "x.db")
        apify = MagicMock()
        apify.run_search.return_value = [
            {"id": "t1", "text": "minimax is great", "author_handle": "u1",
             "favorite_count": 10, "model_id": "minimax", "source_query_id": "Q5"},
            {"id": "t2", "text": "totally unrelated", "author_handle": "u2",
             "favorite_count": 10, "model_id": "minimax", "source_query_id": "Q5"},
            {"id": "t3", "text": "celebrity post", "author_handle": "u3",
             "favorite_count": 10, "model_id": "minimax", "source_query_id": "Q5"},
            {"id": "t4", "text": "minimax M3 review", "author_handle": "u4",
             "favorite_count": 10, "model_id": "minimax", "source_query_id": "Q5"},
            {"id": "t5", "text": "random thoughts", "author_handle": "u5",
             "favorite_count": 10, "model_id": "minimax", "source_query_id": "Q5"},
        ]
        summary = p.execute(apify, model_filter=["minimax"])
        # DB has 2 rows (t1, t4); t2/t5 hard-drop, t3 soft-drop
        from x_monitor.store import Store
        store = Store(data / "x.db")
        posts = store.get_all_posts("minimax")
        assert len(posts) == 2
        assert {p_["tweet_id"] for p_ in posts} == {"t1", "t4"}
        # Summary: n_results=5, n_filtered=3, filter_reasons sums to n_filtered
        entry = summary["queries"][0]
        assert entry["n_results"] == 5
        assert entry["n_filtered"] == 3
        reasons_sum = sum(
            v for k, v in entry["filter_reasons"].items()
            if k not in ("kept", "canonical_bypass", "url_only_kept")
        )
        assert reasons_sum == 3
        # 1 soft-drop, 2 hard-drops
        assert entry["filter_reasons"]["soft_drop_banned"] == 1
        assert entry["filter_reasons"]["hard_drop_no_signal"] == 2
        store.close()


def _v15_deprecated_pipeline_soft_drop_adds_to_review_queue():
    """A banned-token post must appear in the review queue with reason=banned_token,
    and must NOT be in the DB."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        (data / "queries").mkdir()
        (data / "accounts").mkdir()
        (data / "queries" / "minimax.yaml").write_text(
            "queries:\n"
            "  - id: Q1\n    query_string: 'x'\n    expected_signal: release\n    enabled: false\n"
            "  - id: Q2\n    query_string: 'y'\n    expected_signal: community_question\n    enabled: false\n"
            "  - id: Q3\n    query_string: 'z'\n    expected_signal: criticism\n    enabled: false\n"
            "  - id: Q4\n    query_string: 'w'\n    expected_signal: commenter_capture\n    enabled: false\n"
            "  - id: Q5\n    query_string: 'minimax'\n    expected_signal: other\n    max_results: 50\n"
            "  - id: Q6\n    query_string: 'p'\n    expected_signal: praise\n    enabled: false\n",
            encoding="utf-8",
        )
        (data / "accounts" / "minimax.yaml").write_text("accounts: []\n", encoding="utf-8")
        _write_filter_yaml(
            data, "minimax",
            {"must_have_any": ["minimax"], "must_have_none": ["celebrity"]},
        )
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333, x_monitor_list_id=1234567890)
        p = RunPipeline(cfg, data, db_path=data / "x.db")
        apify = MagicMock()
        apify.run_search.return_value = [
            {"id": "t1", "text": "celebrity news", "author_handle": "u1",
             "favorite_count": 5, "model_id": "minimax", "source_query_id": "Q5"},
        ]
        p.execute(apify, model_filter=["minimax"])
        # t1 NOT in DB
        from x_monitor.store import Store
        store = Store(data / "x.db")
        assert store.get_all_posts("minimax") == []
        store.close()
        # t1 IS in review queue with reason=banned_token
        rq = ReviewQueue(data / "_review_queue.json")
        items = rq.list()
        assert len(items) == 1
        assert items[0]["tweet_id"] == "t1"
        assert items[0]["reason"] == "banned_token"
        assert items[0]["model_id"] == "minimax"


def _v15_deprecated_pipeline_low_engagement_rule_only_runs_on_kept():
    """Regression: a post that the filter HARD-DROPS must NOT appear in the
    review queue via the low_engagement rule. Previously the rule iterated
    over the unfiltered items, so dropped posts got a stale review-queue
    entry pointing at a tweet_id that wasn't in the DB."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        (data / "queries").mkdir()
        (data / "accounts").mkdir()
        (data / "queries" / "minimax.yaml").write_text(
            "queries:\n"
            "  - id: Q1\n    query_string: 'from:MiniMaxAI'\n    expected_signal: release\n    max_results: 50\n"
            "  - id: Q2\n    query_string: 'y'\n    expected_signal: community_question\n    enabled: false\n"
            "  - id: Q3\n    query_string: 'z'\n    expected_signal: criticism\n    enabled: false\n"
            "  - id: Q4\n    query_string: 'w'\n    expected_signal: commenter_capture\n    enabled: false\n"
            "  - id: Q5\n    query_string: 'v'\n    expected_signal: other\n    enabled: false\n"
            "  - id: Q6\n    query_string: 'p'\n    expected_signal: praise\n    enabled: false\n",
            encoding="utf-8",
        )
        (data / "accounts" / "minimax.yaml").write_text("accounts: []\n", encoding="utf-8")
        # Filter requires 'minimax' token; the noise post has none -> hard-drop.
        _write_filter_yaml(
            data, "minimax",
            {"must_have_any": ["minimax"]},
        )
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333, x_monitor_list_id=1234567890)
        p = RunPipeline(cfg, data, db_path=data / "x.db")
        apify = MagicMock()
        apify.run_search.return_value = [
            # Q1 release post that mentions 'minimax' — kept.
            {"id": "kept1", "text": "minimax M3 release", "author_handle": "u1",
             "favorite_count": 0, "model_id": "minimax", "source_query_id": "Q1"},
            # Q1 release post with NO 'minimax' — filter hard-drops it.
            {"id": "dropped1", "text": "totally unrelated release",
             "author_handle": "u2", "favorite_count": 0,
             "model_id": "minimax", "source_query_id": "Q1"},
        ]
        p.execute(apify, model_filter=["minimax"])
        # DB has only kept1
        from x_monitor.store import Store
        store = Store(data / "x.db")
        posts = store.get_all_posts("minimax")
        assert {p_["tweet_id"] for p_ in posts} == {"kept1"}
        store.close()
        # Review queue: kept1 lands as low_engagement, dropped1 does NOT.
        rq = ReviewQueue(data / "_review_queue.json")
        items = rq.list()
        assert len(items) == 1
        assert items[0]["tweet_id"] == "kept1"
        assert items[0]["reason"] == "low_engagement"


def _v15_deprecated_pipeline_drops_match_summary_counts():
    """The drop reason counts in the per-query summary entry must sum
    (excluding keep-reasons) to n_filtered."""
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        (data / "queries").mkdir()
        (data / "accounts").mkdir()
        (data / "queries" / "minimax.yaml").write_text(
            "queries:\n"
            "  - id: Q1\n    query_string: 'x'\n    expected_signal: release\n    enabled: false\n"
            "  - id: Q2\n    query_string: 'y'\n    expected_signal: community_question\n    enabled: false\n"
            "  - id: Q3\n    query_string: 'z'\n    expected_signal: criticism\n    enabled: false\n"
            "  - id: Q4\n    query_string: 'w'\n    expected_signal: commenter_capture\n    enabled: false\n"
            "  - id: Q5\n    query_string: 'minimax'\n    expected_signal: other\n    max_results: 50\n"
            "  - id: Q6\n    query_string: 'p'\n    expected_signal: praise\n    enabled: false\n",
            encoding="utf-8",
        )
        (data / "accounts" / "minimax.yaml").write_text("accounts: []\n", encoding="utf-8")
        _write_filter_yaml(
            data, "minimax",
            {
                "canonical_handles": ["OfficialBrand"],
                "must_have_any": ["minimax"],
                "must_have_none": ["celebrity"],
            },
        )
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333, x_monitor_list_id=1234567890)
        p = RunPipeline(cfg, data, db_path=data / "x.db")
        apify = MagicMock()
        apify.run_search.return_value = [
            {"id": "t1", "text": "minimax K2 is great", "author_handle": "u1",
             "favorite_count": 10, "model_id": "minimax", "source_query_id": "Q5"},
            {"id": "t2", "text": "hello world", "author_handle": "OfficialBrand",
             "favorite_count": 10, "model_id": "minimax", "source_query_id": "Q5"},
            {"id": "t3", "text": "celebrity post", "author_handle": "u3",
             "favorite_count": 10, "model_id": "minimax", "source_query_id": "Q5"},
            {"id": "t4", "text": "unrelated content", "author_handle": "u4",
             "favorite_count": 10, "model_id": "minimax", "source_query_id": "Q5"},
            {"id": "t5", "text": "https://t.co/abc", "author_handle": "u5",
             "favorite_count": 10, "model_id": "minimax", "source_query_id": "Q5"},
        ]
        summary = p.execute(apify, model_filter=["minimax"])
        entry = summary["queries"][0]
        # t1 kept (must), t2 canonical_bypass, t3 soft_drop_banned,
        # t4 hard_drop_no_signal, t5 url_only_kept
        assert entry["n_results"] == 5
        assert entry["n_kept"] == 3   # t1, t2, t5
        assert entry["n_filtered"] == 2  # t3, t4
        # Drop reason sum = 2
        drop_sum = sum(
            v for k, v in entry["filter_reasons"].items()
            if k not in ("kept", "canonical_bypass", "url_only_kept")
        )
        assert drop_sum == entry["n_filtered"]
        # 1 review added (t3)
        assert entry["n_review_added"] == 1


def _v15_deprecated_pipeline_short_circuits_over_cap_query():
    """A query with > 22 top-level OR operators is short-circuited BEFORE
    apify.run_search is called. The per-query summary entry has
    status="operator_cap_exceeded" and no credits are burned.

    We construct one of the six queries to be massively over-cap; the other
    five are normal. After execute(), the over-cap query must appear with
    status operator_cap_exceeded and apify.run_search must have been called
    exactly 5 times (one per under-cap query), not 6.
    """
    # 30 ORs (31 terms) — well over the 22 cap.
    over_cap_q = " OR ".join(f"x{i}" for i in range(31))
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        (data / "queries").mkdir()
        (data / "accounts").mkdir()
        (data / "queries" / "minimax.yaml").write_text(
            f"""
queries:
  - id: Q1
    query_string: 'from:MiniMaxAI'
    expected_signal: release
    max_results: 5
  - id: Q2
    query_string: 'minimax how'
    expected_signal: community_question
    max_results: 5
  - id: Q3
    query_string: '{over_cap_q}'
    expected_signal: criticism
    max_results: 5
  - id: Q4
    query_string: 'to:MiniMaxAI'
    expected_signal: commenter_capture
    max_results: 5
  - id: Q5
    query_string: 'minimax benchmark'
    expected_signal: other
    max_results: 5
  - id: Q6
    query_string: 'minimax praise min_faves:5'
    expected_signal: praise
    max_results: 5
""",
            encoding="utf-8",
        )
        (data / "accounts" / "minimax.yaml").write_text(
            """
accounts:
  - handle: MiniMaxAI
    role: official
""",
            encoding="utf-8",
        )
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333, x_monitor_list_id=1234567890)
        p = RunPipeline(cfg, data, db_path=data / "x.db")
        apify = MagicMock()
        # The 5 under-cap queries (Q1, Q2, Q4, Q5, Q6) hit the API.
        apify.run_search.side_effect = [
            [{"id": "t1", "text": "hi", "author_handle": "u1"}],  # Q1
            [],
            [],
            [],
            [],
        ]
        summary = p.execute(apify, model_filter=["minimax"])
        # The 5 under-cap queries ran. The 6th call (for Q3) was NOT made
        # because the operator-cap pre-check short-circuited it.
        assert apify.run_search.call_count == 5
        # The Q3 entry must be flagged operator_cap_exceeded.
        q3_entries = [
            q for q in summary["queries"] if q.get("query_id") == "Q3"
        ]
        assert len(q3_entries) == 1
        assert q3_entries[0]["status"] == "operator_cap_exceeded"
        assert q3_entries[0]["n_operators"] == 30
        # The degraded field carries a per-call description for triage.
        assert "operator_cap_exceeded" in summary["degraded"]
        assert any(
            "minimax/Q3" in s for s in summary["degraded"]["operator_cap_exceeded"]
        )


# --- v1.6 plan_calls stub for pipeline tests --------------------------------

def _stub_plan_calls(enabled_models):
    """Build a hand-rolled PlannedCall list for tests.

    v1.6 plan_calls reads accounts + queries yaml from disk. For
    pipeline tests we don't want to write full yaml; we just need
    deterministic call lists to drive apify mocks. Returns:
      - 1 account call per model (release)
      - 1 intent call per model (criticism, with the model's brand
        token prefixed)
    """
    out = []
    for m in enabled_models:
        out.append(PlannedCall(
            call_kind="account",
            model_id=m,
            bucket=None,
            query_string=f"(from:{m}) min_faves:1",
            expected_signal="release",
            query_length=1,
        ))
        out.append(PlannedCall(
            call_kind="intent",
            model_id=m,
            bucket="howto_criticism",
            query_string=f"({m}) how OR broken min_faves:0",
            expected_signal="criticism",
            query_length=3,
        ))
    return out


def test_pipeline_runs_via_plan_calls_account_call(monkeypatch):
    """v1.6 pipeline iterates plan_calls(...) and runs each call.

    We mock plan_calls to return 1 account + 1 intent call, mock
    apify.run_search to return 1 item per call, and verify the
    pipeline emits 2 summary entries with the correct call_kind.
    """
    monkeypatch.setattr(
        "x_monitor.run.plan_calls",
        lambda *a, **kw: _stub_plan_calls(["minimax"]),
    )
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        (data / "queries").mkdir()
        (data / "accounts").mkdir()
        (data / "accounts" / "minimax.yaml").write_text(
            "accounts:\n  - handle: MiniMaxAI\n    role: official\n",
            encoding="utf-8",
        )
        (data / "queries" / "minimax.yaml").write_text(
            "queries:\n  - id: Q1\n    query_string: 'minimax'\n    expected_signal: release\n    enabled: true\n"
            "  - id: Q2\n    query_string: 'minimax how'\n    expected_signal: community_question\n    enabled: true\n"
            "  - id: Q3\n    query_string: 'minimax broken'\n    expected_signal: criticism\n    enabled: true\n"
            "  - id: Q4\n    query_string: 'minimax'\n    expected_signal: commenter_capture\n    enabled: true\n"
            "  - id: Q5\n    query_string: 'minimax'\n    expected_signal: other\n    enabled: true\n"
            "  - id: Q6\n    query_string: 'minimax'\n    expected_signal: praise\n    enabled: true\n",
            encoding="utf-8",
        )
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333, x_monitor_list_id=1234567890)
        p = RunPipeline(cfg, data, db_path=data / "x.db")
        apify = MagicMock()
        # account call returns 1 item (t1); intent call returns 1 item (t2)
        apify.run_search.side_effect = [
            [{"id": "t1", "text": "minimax release", "author_handle": "u1"}],
            [{"id": "t2", "text": "minimax how to use", "author_handle": "u2"}],
        ]
        summary = p.execute(apify, model_filter=["minimax"])
        # 2 calls fired (account + intent) — but the v1.6 plan_calls
        # stub is what we patch; the real plan_calls in our codebase
        # builds from yaml. With the stub returning 2 calls, we expect
        # 2 apify calls.
        assert apify.run_search.call_count == 2
        # The summary has 2 query entries (1 per call).
        assert len(summary["queries"]) == 2
        kinds = {q.get("call_kind") for q in summary["queries"]}
        assert kinds == {"account", "intent"}


def test_intent_call_reclassifies_model_id(monkeypatch):
    """v1.6 intent call: a tweet mentioning "minimax" is attributed to
    the minimax brand via attribute_to_brand, even if the call came
    from a multi-brand split that started with a different model_id.
    """
    from x_monitor.intent_classifier import attribute_to_brand, classify_signal
    # Direct test: tweet mentions "minimax" and the author is a
    # known minimax official -> brand = minimax.
    assert (
        attribute_to_brand(
            "minimax is amazing",
            "MiniMaxAI",
            brand_tokens={"minimax": ["minimax", "MiniMax"]},
            staff_handles={"minimax": ["MiniMaxAI"]},
        )
        == "minimax"
    )
    # No brand match -> None.
    assert (
        attribute_to_brand(
            "totally unrelated",
            "u1",
            brand_tokens={"minimax": ["minimax"]},
            staff_handles={"minimax": ["MiniMaxAI"]},
        )
        is None
    )
    # Signal classifier maps praise -> praise.
    assert classify_signal("minimax 太强了") == "praise"
    assert classify_signal("minimax 翻车了") == "criticism"
    assert classify_signal("") == "other"


def test_pipeline_applies_filter_before_insert_v16(monkeypatch):
    """v1.6: a single intent call returns 5 tweets; the filter drops
    the same 3 (1 banned, 2 no-signal) and keeps 2 — same filter
    behavior as v1.5, just driven through the plan_calls stub.
    """
    monkeypatch.setattr(
        "x_monitor.run.plan_calls",
        lambda *a, **kw: _stub_plan_calls(["minimax"]),
    )
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        (data / "queries").mkdir()
        (data / "accounts").mkdir()
        (data / "accounts" / "minimax.yaml").write_text(
            "accounts: []\n",
            encoding="utf-8",
        )
        (data / "queries" / "minimax.yaml").write_text(
            # v1.6: queries use (brand OR alt) form so
            # _load_brand_tokens_per_model can pick up multiple brand
            # tokens per model. attribute_to_brand uses this list to
            # match text-contains attribution.
            "queries:\n  - id: Q1\n    query_string: '(minimax OR MiniMax)'\n    expected_signal: release\n    enabled: true\n"
            "  - id: Q2\n    query_string: '(minimax OR MiniMax) how'\n    expected_signal: community_question\n    enabled: true\n"
            "  - id: Q3\n    query_string: '(minimax OR MiniMax) broken'\n    expected_signal: criticism\n    enabled: true\n"
            "  - id: Q4\n    query_string: '(minimax OR MiniMax)'\n    expected_signal: commenter_capture\n    enabled: true\n"
            "  - id: Q5\n    query_string: '(minimax OR MiniMax)'\n    expected_signal: other\n    enabled: true\n"
            "  - id: Q6\n    query_string: '(minimax OR MiniMax)'\n    expected_signal: praise\n    enabled: true\n",
            encoding="utf-8",
        )
        _write_filter_yaml(
            data, "minimax",
            {
                "canonical_handles": [],
                "must_have_any": ["minimax"],
                "must_have_none": ["celebrity"],
            },
        )
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333, x_monitor_list_id=1234567890)
        p = RunPipeline(cfg, data, db_path=data / "x.db")
        apify = MagicMock()
        # account call: 0 items; intent call: 5 items (1 banned, 2 noise, 2 valid)
        apify.run_search.side_effect = [
            [],
            [
                {"id": "t1", "text": "minimax is great", "author_handle": "u1",
                 "favorite_count": 10, "model_id": "minimax", "source_query_id": "Q5"},
                {"id": "t2", "text": "totally unrelated", "author_handle": "u2",
                 "favorite_count": 10, "model_id": "minimax", "source_query_id": "Q5"},
                {"id": "t3", "text": "celebrity post", "author_handle": "u3",
                 "favorite_count": 10, "model_id": "minimax", "source_query_id": "Q5"},
                {"id": "t4", "text": "minimax M3 review", "author_handle": "u4",
                 "favorite_count": 10, "model_id": "minimax", "source_query_id": "Q5"},
                {"id": "t5", "text": "random thoughts", "author_handle": "u5",
                 "favorite_count": 10, "model_id": "minimax", "source_query_id": "Q5"},
            ],
        ]
        summary = p.execute(apify, model_filter=["minimax"])
        from x_monitor.store import Store
        store = Store(data / "x.db")
        posts = store.get_all_posts("minimax")
        # v1.6: the 5 input tweets are first reclassified by
        # attribute_to_brand. Tweets without a brand match are dropped
        # BEFORE the relevance filter runs. Only t1 ("minimax is great")
        # and t4 ("minimax M3 review") mention "minimax" and pass the
        # brand attribution; the other 3 are dropped by reclassify.
        assert len(posts) == 2
        assert {pp["tweet_id"] for pp in posts} == {"t1", "t4"}
        # Find the intent-call summary entry; n_results is POST-reclassify
        # drop (2), n_filtered is from the relevance filter (0 — both
        # pass must_have_any: [minimax] and lack banned "celebrity").
        intent_entries = [q for q in summary["queries"] if q.get("call_kind") == "intent"]
        assert len(intent_entries) == 1
        entry = intent_entries[0]
        assert entry["n_results"] == 2
        assert entry["n_filtered"] == 0
        store.close()


def test_pipeline_soft_drop_adds_to_review_queue_v16(monkeypatch):
    """F1 hijack at moonshot_kimi: a tweet mentioning F1 but no
    kimi/moonshot gets soft-dropped to the review queue.
    """
    monkeypatch.setattr(
        "x_monitor.run.plan_calls",
        lambda *a, **kw: _stub_plan_calls(["moonshot_kimi"]),
    )
    with tempfile.TemporaryDirectory() as d:
        data = Path(d)
        (data / "queries").mkdir()
        (data / "accounts").mkdir()
        (data / "accounts" / "moonshot_kimi.yaml").write_text(
            "accounts: []\n",
            encoding="utf-8",
        )
        (data / "queries" / "moonshot_kimi.yaml").write_text(
            # v1.6: queries use (kimi OR moonshot OR k2) so
            # _load_brand_tokens_per_model picks up the brand tokens.
            # attribute_to_brand matches "kimi" in the F1 tweet text
            # against this list.
            "queries:\n  - id: Q1\n    query_string: '(kimi OR moonshot OR k2)'\n    expected_signal: release\n    enabled: true\n"
            "  - id: Q2\n    query_string: '(kimi OR moonshot OR k2)'\n    expected_signal: community_question\n    enabled: true\n"
            "  - id: Q3\n    query_string: '(kimi OR moonshot OR k2)'\n    expected_signal: criticism\n    enabled: true\n"
            "  - id: Q4\n    query_string: '(kimi OR moonshot OR k2)'\n    expected_signal: commenter_capture\n    enabled: true\n"
            "  - id: Q5\n    query_string: '(kimi OR moonshot OR k2)'\n    expected_signal: other\n    enabled: true\n"
            "  - id: Q6\n    query_string: '(kimi OR moonshot OR k2)'\n    expected_signal: praise\n    enabled: true\n",
            encoding="utf-8",
        )
        # v1.6: must_have_any is empty here. The relevance filter's
        # soft-drop branch only fires when has_banned AND not has_must.
        # The F1 tweet is attributed to moonshot_kimi by
        # attribute_to_brand (text contains "kimi"), but the FILTER
        # doesn't care about that — it only sees the must/banned tokens.
        # With must_have_any=[], the tweet has no must token, so the
        # banned "F1" token drives the soft-drop to the review queue.
        _write_filter_yaml(
            data, "moonshot_kimi",
            {
                "canonical_handles": [],
                "must_have_any": [],
                "must_have_none": ["F1", "antonelli"],
            },
        )
        cfg = Config(enabled_models=["moonshot_kimi"], daily_ceiling=333, x_monitor_list_id=1234567890)
        p = RunPipeline(cfg, data, db_path=data / "x.db")
        apify = MagicMock()
        # The F1 hijack: a tweet that mentions F1 but no kimi/moonshot.
        # Pre-stamp model_id to bypass the intent-call reclassify.
        apify.run_search.side_effect = [
            [],
            [
                # Tweet mentions BOTH "kimi" (so attribute_to_brand
                # passes) and "F1" (so the relevance filter's
                # must_have_none catches it and soft-drops to review
                # queue). v1.6 reclassify sees the brand match; the
                # filter then sees the banned token.
                {"id": "f1", "text": "kimi is faster than F1 today",
                 "author_handle": "f1fan", "favorite_count": 50,
                 "model_id": "moonshot_kimi", "source_query_id": "Q5"},
            ],
        ]
        review = ReviewQueue(data / "_review_queue.json")
        summary = p.execute(apify, model_filter=["moonshot_kimi"])
        # No posts inserted (the F1 tweet was filtered).
        from x_monitor.store import Store
        store = Store(data / "x.db")
        assert store.get_all_posts("moonshot_kimi") == []
        # The soft-drop landed in the review queue.
        items = review.list()
        assert any(it.get("tweet_id") == "f1" for it in items)
        store.close()
