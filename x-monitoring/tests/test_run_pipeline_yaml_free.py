# {{AGENT_ATTRIBUTION}}
"""Tests for the U3 yaml-free RunPipeline.

Plan: docs/plans/2026-07-11-001-feat-queries-and-filters-retire-and-export-poststep-plan.md
(Unit U3).

Coverage:
- RunPipeline.__init__ does NOT set self.queries_dir.
- _brand_tokens_map, _log_brand_search_terms_drift, load_filter are
  gone (haveattr() == False).
- filter_and_review drops the RelevanceConfig parameter.
- data/queries/ and data/filters/ are deleted (git ls-files empty).
- The LaunchAgent plist WatchPaths no longer references data/queries.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import x_monitor.run as run_mod


REPO_ROOT = Path(__file__).parent.parent
PLIST = REPO_ROOT / "deploy" / "com.fuchitalee.x-monitor.plist"


# ----------------------------------------------------------------------
# 1. RunPipeline.__init__ does not set self.queries_dir.
# ----------------------------------------------------------------------


def test_run_pipeline_init_no_queries_dir(tmp_path: Path) -> None:
    """Constructing RunPipeline does not assign self.queries_dir — the
    data/queries/ runtime read path is retired."""
    from x_monitor.config import Config
    # Minimal config to satisfy RunPipeline.__init__.
    cfg = Config(
        enabled_models=["minimax"],
        daily_ceiling=10,
        x_monitor_list_id=1234567890,
    )
    db_path = tmp_path / "x.db"
    # Use a tmp data dir; RunPipeline doesn't require data/queries to exist.
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pipeline = run_mod.RunPipeline(cfg, data_dir, db_path)
    assert not hasattr(pipeline, "queries_dir"), (
        "self.queries_dir should be removed in U3"
    )


# ----------------------------------------------------------------------
# 2. U3-retired helpers are absent.
# ----------------------------------------------------------------------


def test_retired_u3_helpers_absent() -> None:
    """`_brand_tokens_map`, `_log_brand_search_terms_drift`, and the
    legacy `load_filter` are removed in U3 (R5, R6, R8)."""
    for name in (
        "_brand_tokens_map",
        "_log_brand_search_terms_drift",
    ):
        assert not hasattr(run_mod, name), (
            f"{name!r} should be removed in U3; still present on "
            f"x_monitor.run"
        )
    # `load_filter` lives in x_monitor.relevance.
    import x_monitor.relevance as rel
    assert not hasattr(rel, "load_filter"), (
        "load_filter should be removed in U3 (R8)"
    )


# ----------------------------------------------------------------------
# 3. filter_and_review drops the RelevanceConfig parameter.
# ----------------------------------------------------------------------


def test_filter_and_review_signature_no_cfg() -> None:
    """The relevance-filter step is removed; the cfg parameter is gone
    from filter_and_review (KTD6)."""
    import inspect
    sig = inspect.signature(run_mod.filter_and_review)
    params = list(sig.parameters)
    assert "cfg" not in params, (
        f"filter_and_review still has 'cfg' parameter: {params}"
    )
    # Sanity: brand_id, review, cache are still there.
    assert "brand_id" in params
    assert "review" in params


# ----------------------------------------------------------------------
# 4. data/queries/ and data/filters/ are deleted (git ls-files empty).
# ----------------------------------------------------------------------


def test_data_queries_and_filters_directories_absent() -> None:
    """The two yaml directories are deleted in U3."""
    assert not (REPO_ROOT / "data" / "queries").exists()
    assert not (REPO_ROOT / "data" / "filters").exists()


# ----------------------------------------------------------------------
# 5. LaunchAgent plist WatchPaths no longer references data/queries.
# ----------------------------------------------------------------------


def test_plist_watchpaths_no_data_queries() -> None:
    """The plist's WatchPaths array targets `config.yaml` (the
    operator-edit surface), not `data/queries/` (which is gone)."""
    import re
    text = PLIST.read_text(encoding="utf-8")
    # Pull the WatchPaths block.
    m = re.search(
        r"<key>WatchPaths</key>\s*<array>(.*?)</array>",
        text,
        re.DOTALL,
    )
    assert m is not None, "WatchPaths array not found in plist"
    block = m.group(1)
    # Extract only the <string> elements — comments and metadata
    # outside <string> tags are OK to mention the old path.
    string_entries = re.findall(r"<string>(.*?)</string>", block)
    paths = " ".join(string_entries)
    assert "data/queries" not in paths, (
        f"plist WatchPaths still references data/queries/: {string_entries!r}"
    )
    assert "config.yaml" in paths, (
        f"plist WatchPaths should target config.yaml: {string_entries!r}"
    )


# ----------------------------------------------------------------------
# 6. The body_keyword index is self-brand-only (regression test for
#    the _build_brand_index signature change).
# ----------------------------------------------------------------------


def test_build_brand_index_self_brand_only() -> None:
    """After U3, _build_brand_index(models) takes only `models` and
    returns the self-brand index. It does NOT raise on a missing
    brand_tokens argument (the old positional argument is gone)."""
    index, terms = run_mod._build_brand_index(["minimax", "qwen"])
    assert terms == {"minimax": "minimax", "qwen": "qwen"}
    # The compiled index is a body_keyword index; we just assert it
    # exists and is callable (not None).
    assert index is not None
