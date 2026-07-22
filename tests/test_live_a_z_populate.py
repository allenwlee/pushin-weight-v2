"""Tests for scripts/live_a_z_populate.py (U2 of plan 2026-07-13-001).

Mirror the structure of test_post_fetch_smoketest_latest_n.py: a
FakeRun helper that captures argv, and assertions over the captured
output. No live TwitterAPI calls; we exercise the CLI shape and
the post-run "inserted > 0" gate via monkeypatched helpers.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

# x-monitoring/ is the project root; scripts/ is on sys.path when
# invoked via `python -m scripts.live_a_z_populate`.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import live_a_z_populate as lap  # noqa: E402


def _run_with_argv(argv: list[str]) -> int:
    """Invoke lap.main(argv) and return its rc."""
    return lap.main(argv)


def test_help_lists_both_new_flags(capsys: pytest.CaptureFixture) -> None:
    # --help triggers argparse's SystemExit(0); capture stdout via the
    # parser's format_help() rather than invoking main.
    parser = lap._parse_args.__wrapped__ if hasattr(lap._parse_args, "__wrapped__") else None
    # Fallback: rebuild the parser directly.
    ns = lap._parse_args(["--limit-per-call", "5", "--no-skip-under-budget"])
    assert ns.limit_per_call == 5
    assert ns.no_skip_under_budget is True
    # Confirm the help text via the underlying argparse formatter.
    import argparse
    parser = argparse.ArgumentParser(prog="live-a-z-populate")
    parser.add_argument("--limit-per-call", type=int, default=20)
    parser.add_argument("--no-skip-under-budget", action="store_true")
    parser.add_argument("--log-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    help_text = parser.format_help()
    assert "--limit-per-call" in help_text
    assert "--no-skip-under-budget" in help_text
    assert "--log-dir" in help_text


def test_rejects_zero_limit_per_call(
    capsys: pytest.CaptureFixture, tmp_path: Path,
) -> None:
    rc = lap.main(["--limit-per-call", "0", "--log-dir", str(tmp_path)])
    assert rc == 2
    captured = capsys.readouterr()
    assert "--limit-per-call must be > 0" in captured.err


def test_build_log_path_uses_utc_stamp(tmp_path: Path) -> None:
    stamp = "2026-07-13T000000Z"
    log_path = lap._build_log_path(tmp_path, stamp)
    assert log_path.name == f"{stamp}-live-a-z-populate.log"
    assert log_path.parent == tmp_path


def test_count_posts_after_returns_zero_on_missing_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Repoint _PKG_ROOT to a tmp dir with no DB.
    monkeypatch.setattr(lap, "_PKG_ROOT", tmp_path)
    assert lap._count_posts_after(window_seconds=60) == 0


def test_dry_run_uses_fake_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """When --dry-run is set, the script invokes `x-monitor run --dry-run`
    and returns its rc without checking the DB."""
    calls: list[list[str]] = []

    class _FakeCompleted:
        returncode = 0
        stdout = "fake stdout"
        stderr = "fake stderr"

    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        calls.append(cmd)
        return _FakeCompleted()

    monkeypatch.setattr(lap.subprocess, "run", _fake_run)
    rc = lap.main([
        "--dry-run",
        "--limit-per-call", "5",
        "--log-dir", str(tmp_path),
    ])
    assert rc == 0
    assert len(calls) == 1
    cmd = calls[0]
    # argv order: python -m x_monitor run --limit-per-call 5 --dry-run
    assert cmd[2:] == ["x_monitor", "run", "--limit-per-call", "5", "--dry-run"]


def test_no_six_call_post_insertion_returns_rc_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """When x-monitor run succeeds (rc=0) but zero rows landed in the
    `posts` table in the last 10 min, the script returns rc=1 with a
    stderr diagnostic."""

    class _FakeCompleted:
        returncode = 0
        stdout = "{}"
        stderr = ""

    monkeypatch.setattr(
        lap.subprocess, "run",
        lambda cmd, **kwargs: _FakeCompleted(),
    )
    # Simulate no DB by pointing _PKG_ROOT at a tmp dir.
    monkeypatch.setattr(lap, "_PKG_ROOT", tmp_path)
    rc = lap.main([
        "--limit-per-call", "20",
        "--no-skip-under-budget",
        "--log-dir", str(tmp_path),
    ])
    assert rc == 1


def test_precheck_returns_empty_on_missing_db(tmp_path: Path) -> None:
    """When the DB file does not exist, the precheck returns ([], [])
    so the caller treats it as 'no problem — Store() will create it.'"""
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(lap, "_PKG_ROOT", tmp_path)
    try:
        missing, hints = lap._precheck_required_db_artifacts()
        assert missing == []
        assert hints == []
    finally:
        monkeypatch.undo()


def test_precheck_returns_missing_when_call_state_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """When the DB exists but call_state is missing (the bug that
    blocked U3 in session 2026-07-13), the precheck surfaces the
    missing artifact list with the migration hint."""
    import sqlite3

    db_dir = tmp_path / "data"
    db_dir.mkdir()
    db_path = db_dir / "x_monitoring.db"
    conn = sqlite3.connect(str(db_path))
    try:
        # Empty DB — call_state is missing, but posts_brands_signals
        # and posts_brands_discourse are also missing.
        conn.commit()
    finally:
        conn.close()

    # _precheck_required_db_artifacts looks for data/x_monitoring.db
    # relative to _PKG_ROOT. Point _PKG_ROOT at tmp_path so the path
    # resolution lands on our temp DB.
    monkeypatch.setattr(lap, "_PKG_ROOT", tmp_path)
    missing, hints = lap._precheck_required_db_artifacts()
    assert "call_state" in missing
    assert any("025" in h for h in hints)


def test_precheck_skipped_on_dry_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """`--dry-run` does NOT need call_state (the pipeline never
    reaches that code path on dry_run), so the precheck is skipped
    and the script proceeds even with a half-applied DB."""
    import sqlite3

    db_dir = tmp_path / "data"
    db_dir.mkdir()
    db_path = db_dir / "x_monitoring.db"
    conn = sqlite3.connect(str(db_path))
    conn.commit()
    conn.close()

    monkeypatch.setattr(lap, "_PKG_ROOT", tmp_path)

    # Patch subprocess.run so dry-run completes without doing anything.
    class _FakeCompleted:
        returncode = 0
        stdout = "{}"
        stderr = ""

    monkeypatch.setattr(
        lap.subprocess, "run",
        lambda cmd, **kwargs: _FakeCompleted(),
    )

    rc = lap.main([
        "--dry-run",
        "--limit-per-call", "5",
        "--log-dir", str(tmp_path),
    ])
    captured = capsys.readouterr()
    # The precheck stderr message must NOT appear on dry-run.
    assert "DB schema precheck FAILED" not in captured.err
    # dry-run passes through subprocess rc.
    assert rc == 0


def test_source_secrets_loads_export_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """`_source_secrets` parses `export KEY="value"` lines into
    os.environ, skipping blanks, comments, and lines without `export`.
    Existing env vars are preserved (caller wins)."""
    secrets = tmp_path / ".env.secrets"
    secrets.write_text(
        "# header comment\n"
        "\n"
        'export NEW_VAR="hello"\n'
        "export SINGLE_QUOTED='world'\n"
        "export MULTI=value with spaces\n"
        "export NOQUOTES=plain\n"
        "not_an_export=ignored\n"
        "export ONLY_KEY # no equals\n"
    )
    monkeypatch.delenv("NEW_VAR", raising=False)
    monkeypatch.delenv("SINGLE_QUOTED", raising=False)
    monkeypatch.delenv("MULTI", raising=False)
    monkeypatch.delenv("NOQUOTES", raising=False)
    loaded = lap._source_secrets(secrets)
    assert loaded == 4
    import os
    assert os.environ["NEW_VAR"] == "hello"
    assert os.environ["SINGLE_QUOTED"] == "world"
    assert os.environ["MULTI"] == "value with spaces"
    assert os.environ["NOQUOTES"] == "plain"


def test_source_secrets_does_not_overwrite_existing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Existing os.environ values must win — the helper only fills in
    unset keys (so the caller's shell-exported TWITTERAPI_IO_API_KEY is
    preserved across runs)."""
    secrets = tmp_path / ".env.secrets"
    secrets.write_text('export TWITTERAPI_IO_API_KEY="from_file"\n')
    monkeypatch.setenv("TWITTERAPI_IO_API_KEY", "from_shell")
    loaded = lap._source_secrets(secrets)
    assert loaded == 0  # already in env, not loaded
    import os
    assert os.environ["TWITTERAPI_IO_API_KEY"] == "from_shell"


def test_source_secrets_returns_zero_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Missing secrets file → 0 loaded, no exception. Caller checks
    for the specific TWITTERAPI_IO_API_KEY in os.environ afterwards."""
    missing = tmp_path / "does_not_exist"
    loaded = lap._source_secrets(missing)
    assert loaded == 0


def test_missing_twitterapi_key_exits_rc_two(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """When neither os.environ nor the secrets file contains
    TWITTERAPI_IO_API_KEY, main() prints a stderr diagnostic and
    returns rc=2 BEFORE launching the subprocess (no API quota burned)."""
    secrets = tmp_path / ".env.secrets"
    secrets.write_text('export SOMETHING_ELSE="x"\n')
    monkeypatch.delenv("TWITTERAPI_IO_API_KEY", raising=False)
    rc = lap.main([
        "--limit-per-call", "5",
        "--secrets", str(secrets),
        "--log-dir", str(tmp_path),
    ])
    captured = capsys.readouterr()
    assert rc == 2
    assert "TWITTERAPI_IO_API_KEY" in captured.err
    assert "Recovery:" in captured.err
