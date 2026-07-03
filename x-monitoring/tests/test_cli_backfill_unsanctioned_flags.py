"""U8b: x-monitor backfill unsanctioned-flags CLI.

Plan: docs/plans/2026-07-03-003-feat-post-fetch-taxonomy-and-multi-discourse-plan.md
Unit U8b.

Verifies (via parser-level smoke tests + unit-level checks):
- Parser entry exists under `backfill unsanctioned-flags`.
- `--limit > 500` without `--yes` returns exit 1.
- `--limit > 500` with `--yes` proceeds.
- `--dry-run` skips the LLM calls.
- Empty DB returns 0 (no posts to process).
"""

from __future__ import annotations

import pytest


# --- parser-level checks (no LLM, no DB writes) ------------------------


def test_u8b_parser_entry_exists():
    """The `backfill unsanctioned-flags` subcommand is registered."""
    from x_monitor.__main__ import build_parser
    parser = build_parser()
    # Verify we can parse the args without error.
    args = parser.parse_args(["backfill", "unsanctioned-flags", "--limit", "10"])
    assert args.limit == 10
    assert args.dry_run is False
    assert args.yes is False
    assert args.func.__name__ == "cmd_backfill_unsanctioned_flags"


def test_u8b_parser_dry_run_flag():
    from x_monitor.__main__ import build_parser
    parser = build_parser()
    args = parser.parse_args(
        ["backfill", "unsanctioned-flags", "--dry-run"]
    )
    assert args.dry_run is True


def test_u8b_parser_yes_flag():
    from x_monitor.__main__ import build_parser
    parser = build_parser()
    args = parser.parse_args(
        ["backfill", "unsanctioned-flags", "--limit", "1000", "--yes"]
    )
    assert args.yes is True
    assert args.limit == 1000


# --- unit-level checks --------------------------------------------------


def test_u8b_refuses_limit_over_500_without_yes(monkeypatch, tmp_path):
    """--limit > 500 without --yes → returns exit 1."""
    from x_monitor import __main__ as cli
    from argparse import Namespace

    # Build the args namespace the way the parser would.
    args = Namespace(
        limit=501, dry_run=False, yes=False,
        func=cli.cmd_backfill_unsanctioned_flags,
    )
    paths = {"db": tmp_path / "x.db"}  # DB doesn't even need to exist

    rc = cli.cmd_backfill_unsanctioned_flags(args, paths)
    assert rc == 1


def test_u8b_empty_db_returns_zero(monkeypatch, tmp_path):
    """No posts missing flags → returns 0 (no work)."""
    from x_monitor import __main__ as cli
    from argparse import Namespace
    from x_monitor.store import Store

    # Create an empty DB.
    db = tmp_path / "x.db"
    Store(db, auto_migrate=True).close()

    args = Namespace(
        limit=200, dry_run=True, yes=False,
        func=cli.cmd_backfill_unsanctioned_flags,
    )
    paths = {"db": db}

    rc = cli.cmd_backfill_unsanctioned_flags(args, paths)
    assert rc == 0


def test_u8b_missing_db_returns_two(monkeypatch, tmp_path):
    """DB path doesn't exist → returns 2."""
    from x_monitor import __main__ as cli
    from argparse import Namespace

    args = Namespace(
        limit=200, dry_run=False, yes=False,
        func=cli.cmd_backfill_unsanctioned_flags,
    )
    paths = {"db": tmp_path / "nonexistent.db"}

    rc = cli.cmd_backfill_unsanctioned_flags(args, paths)
    assert rc == 2


# --- integration: dry-run with seeded posts ---------------------------


def test_u8b_dry_run_with_seeded_posts(monkeypatch, tmp_path):
    """--dry-run with seeded posts prints post_ids without LLM calls."""
    from x_monitor import __main__ as cli
    from argparse import Namespace
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    # Seed posts (no unsanctioned_flags rows yet).
    for i in range(3):
        s._conn.execute(
            "INSERT INTO posts (tweet_id, text, fetched_at) "
            "VALUES (?, ?, ?)",
            (f"test_post_{i}", f"text {i}", "2026-07-03T00:00:00+00:00"),
        )
    s._conn.commit()
    s.close()

    args = Namespace(
        limit=200, dry_run=True, yes=False,
        func=cli.cmd_backfill_unsanctioned_flags,
    )
    paths = {"db": db}

    rc = cli.cmd_backfill_unsanctioned_flags(args, paths)
    assert rc == 0
    # No rows written.
    s = Store(db, auto_migrate=True)
    count = s._conn.execute(
        "SELECT COUNT(*) FROM posts_unsanctioned_flags"
    ).fetchone()[0]
    assert count == 0, "dry-run should not write any rows"
    s.close()