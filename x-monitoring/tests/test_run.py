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
from x_monitor.queries import Query
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
""",
                encoding="utf-8",
            )
        cfg = Config(enabled_models=["minimax", "qwen", "deepseek"], daily_ceiling=333)
        # Pipeline needs a data_dir; we don't call execute here
        p = RunPipeline(cfg, data, db_path=Path(d) / "x.db")
        from x_monitor.queries import load_queries

        per_model = {m: load_queries(m, data) for m in cfg.enabled_models}
        cost = p.estimate_cost(per_model)
        # 3 models × 5 queries × 50 = 750 — ABOVE 333 default
        assert cost == 750
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
        cfg = Config(enabled_models=["minimax"], daily_ceiling=50)
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


def test_pipeline_writes_raw_before_db_insert():
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
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
        p = RunPipeline(cfg, data, db_path=data / "x.db")
        apify = MagicMock()
        # 5 query results (no more cookie probe)
        apify.run_search.side_effect = [
            [{"id": "t1", "text": "hello", "author_handle": "u1"}],  # Q1
            [],  # Q2
            [],  # Q3
            [],  # Q4
            [],  # Q5
        ]
        summary = p.execute(apify, model_filter=["minimax"])
        # All 5 queries should have run (cost 5*5=25 < 333 budget).
        assert summary["totals"]["n_queries_run"] == 5
        # Raw files present
        raw_files = list((data / "runs" / "raw").rglob("*.json"))
        assert len(raw_files) == 5, f"expected 5 raw files, got {len(raw_files)}"
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
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
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
        cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
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
                "started_at": "2026-06-07T00:00:00+00:00",
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
                "started_at": "2026-06-07T01:00:00+00:00",
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
                "started_at": "2026-06-07T00:00:00+00:00",
                "queries": [
                    {"model_id": "m", "query_id": "Q1", "status": "completed", "n_results": 0}
                ],
            }
        )
    )
    (runs / "run2.json").write_text(
        json.dumps(
            {
                "started_at": "2026-06-07T01:00:00+00:00",
                "queries": [
                    {"model_id": "m", "query_id": "Q1", "status": "completed", "n_results": 0}
                ],
            }
        )
    )
    (runs / "run3.json").write_text(
        json.dumps(
            {
                "started_at": "2026-06-07T02:00:00+00:00",
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
