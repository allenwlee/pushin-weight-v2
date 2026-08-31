# {{AGENT_ATTRIBUTION}}
"""U2 (plan 2026-07-13-001): one-shot live A→Z DB populate.

Drives `x-monitor run` with all six v1.7 calls (A + B1/B2/B3 +
C1/C2), each capped at 20 posts, and persists every result into
`data/x_monitoring.db`. The smoketest was read-only — this is the
bridge that writes real TwitterAPI.io-fetched posts through the live
translate + classify path.

Logs to `tests/classifier_tests/<UTC>-live-a-z-populate.log` and
exits 0 when at least one post was inserted.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from x_monitor.twitterapi_credentials import (
    TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV,
)

_PKG_ROOT = Path(__file__).resolve().parent.parent


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="live-a-z-populate",
        description=(
            "Live end-to-end DB populate: A + B1/B2/B3 + C1/C2, "
            "20 posts per call, persisted to data/x_monitoring.db."
        ),
    )
    p.add_argument(
        "--limit-per-call", type=int, default=20,
        help="Per-call result cap forwarded to `x-monitor run` "
             "(default: 20 — same as the prior 6-call smoketest).",
    )
    p.add_argument(
        "--no-skip-under-budget", action="store_true",
        help="Forward --no-skip-under-budget to `x-monitor run`. "
             "In v1.7 the per-model skip-order loop is a no-op, but "
             "the flag keeps the operator intent explicit.",
    )
    p.add_argument(
        "--log-dir", type=Path,
        default=_PKG_ROOT / "tests" / "classifier_tests",
        help="Where to write the run log (default: "
             "tests/classifier_tests).",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Forward --dry-run to `x-monitor run` (no DB writes, "
             "no API quota).",
    )
    p.add_argument(
        "--secrets", type=Path, default=_DEFAULT_SECRETS_PATH,
        help="Path to the dotenv-style secrets file to source before "
             "launching the subprocess (default: ~/.env.secrets). "
             "Existing env vars are preserved; only unset keys are "
             "loaded from the file.",
    )
    return p.parse_args(argv)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


_DEFAULT_SECRETS_PATH = Path.home() / ".env.secrets"


def _source_secrets(path: Path = _DEFAULT_SECRETS_PATH) -> int:
    """Source a dotenv-style `export KEY="value"` file into os.environ.

    Lines starting with `#` or blank are skipped. Each `export KEY="VALUE"`
    line strips the `export ` prefix and the surrounding quotes, then sets
    `os.environ[KEY] = VALUE`. Single-quoted values are stripped the same
    way. Existing os.environ values are not overwritten (caller wins).

    Returns the number of vars loaded (0 if path missing / no parsable lines).
    Used by main() before launching the x-monitor subprocess so the
    subprocess inherits the operator's on-demand TwitterAPI key without
    requiring the caller to source the file in their shell.

    Plan 2026-07-13-001 R1 mitigation: caller (main) checks
    `TWITTERAPI_IO_ON_DEMAND_API_KEY in os.environ` after this returns and prints
    a stderr diagnostic + exits rc=2 if absent.
    """
    if not path.exists():
        return 0
    loaded = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not line.startswith("export "):
            continue
        line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip surrounding quotes (single or double).
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded


def _build_log_path(log_dir: Path, stamp: str) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{stamp}-live-a-z-populate.log"


def _count_posts_after(window_seconds: int = 600) -> int:
    """Count posts inserted in the last `window_seconds` (default 10 min).

    Used as a cheap post-run sanity check that the DB write path fired.
    """
    db_path = _PKG_ROOT / "data" / "x_monitoring.db"
    if not db_path.exists():
        return 0
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM posts "
            "WHERE datetime(fetched_at) >= datetime('now', ?)",
            (f"-{window_seconds} seconds",),
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


# Code review 2026-07-13-001 (#2): cheap schema precheck before
# launching the x-monitor subprocess. If the migration ledger says
# v37 is applied but `call_state` is missing, the pipeline aborts
# 5-10s into the subprocess with an opaque OperationalError. This
# probe catches the same gap in <50ms and prints the recovery
# command.
#
# Each entry: (table_or_index_name, migrator_recovery_hint).
_REQUIRED_DB_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("call_state", "migration 025"),
    ("posts_brands_discourse", "migration 026"),
    ("posts_brands_signals", "migration 028"),
)


def _precheck_required_db_artifacts() -> tuple[list[str], list[str]]:
    """Verify the schema artifacts the pipeline needs exist.

    Returns (missing_artifacts, migration_hints). Empty missing list
    means the pipeline can run. Caller surfaces the hints to stderr.
    """
    db_path = _PKG_ROOT / "data" / "x_monitoring.db"
    if not db_path.exists():
        # No DB at all — Store(auto_migrate=True) will build it.
        return ([], [])
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    try:
        names = [n for (n, _hint) in _REQUIRED_DB_ARTIFACTS]
        placeholders = ",".join("?" * len(names))
        rows = conn.execute(
            f"SELECT name FROM sqlite_master WHERE type IN "
            f"('table', 'index') AND name IN ({placeholders})",
            tuple(names),
        ).fetchall()
        present = {r[0] for r in rows}
        missing = [n for n in names if n not in present]
        hints = [
            hint
            for (n, hint) in _REQUIRED_DB_ARTIFACTS
            if n in missing
        ]
        return (missing, hints)
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.limit_per_call <= 0:
        print(
            f"--limit-per-call must be > 0 (got {args.limit_per_call})",
            file=sys.stderr,
        )
        return 2

    # Plan 2026-07-13-001 R1: source ~/.env.secrets before launching the
    # subprocess so the on-demand key reaches TwitterApiClient.from_env()
    # without the caller needing to `source ~/.env.secrets` themselves.
    loaded = _source_secrets(args.secrets)
    if loaded:
        print(
            f"_source_secrets: loaded {loaded} vars from {args.secrets}",
            file=sys.stderr,
        )
    if not args.dry_run and TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV not in os.environ:
        print(
            f"{TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV} not in environment and "
            f"not found in {args.secrets}. TwitterApiClient.from_env() will "
            "raise at subprocess start. Recovery: add "
            f"`export {TWITTERAPI_IO_ON_DEMAND_API_KEY_ENV}=\"...\"` "
            "to your secrets file or pass --secrets <path>.",
            file=sys.stderr,
        )
        return 2

    # Code review 2026-07-13-001 (#2): precheck the DB has the
    # artifacts the pipeline needs. Skip on --dry-run (which never
    # touches call_state anyway).
    if not args.dry_run:
        missing, hints = _precheck_required_db_artifacts()
        if missing:
            print(
                f"DB schema precheck FAILED — the pipeline cannot run "
                f"until the following artifacts are present in "
                f"data/x_monitoring.db:",
                file=sys.stderr,
            )
            for name, hint in zip(missing, hints):
                print(f"  - {name} (added by {hint})", file=sys.stderr)
            print(
                "Recovery: run `python -m x_monitor migrate` to apply "
                "pending migrations, or restore the DB from a known-good "
                "backup. If the migration is marked applied in "
                "`_migrations` but the artifact is missing, the next "
                "Store() open will detect the gap via "
                "`expected_artifacts:` headers and roll back the "
                "ledger entry.",
                file=sys.stderr,
            )
            return 1

    stamp = _utc_stamp()
    log_path = _build_log_path(args.log_dir, stamp)

    # Build the `x-monitor run` argv from the project's package root.
    cmd = [
        sys.executable, "-m", "x_monitor", "run",
        "--limit-per-call", str(args.limit_per_call),
    ]
    if args.no_skip_under_budget:
        cmd.append("--no-skip-under-budget")
    if args.dry_run:
        cmd.append("--dry-run")

    # Pre-run snapshot for the post-run "did anything insert?" check.
    pre_run_count = 0 if args.dry_run else _count_posts_after(window_seconds=1)

    header = (
        f"# live_a_z_populate\n"
        f"# started_at={stamp}\n"
        f"# cmd={' '.join(cmd)}\n"
        f"# log_path={log_path}\n"
    )

    print(header)
    t0 = time.monotonic()
    # Code review 2026-07-13-001 (#6): open the log in mode "w" first
    # and write the header immediately so a timeout leaves a complete
    # record. The post-run footer is then appended (mode "a").
    with log_path.open("w", encoding="utf-8") as f:
        f.write(header)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(_PKG_ROOT),
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        msg = f"x-monitor run exceeded 600s timeout"
        print(msg, file=sys.stderr)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"\n=== TIMEOUT ===\n{msg}\n")
        return 1

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    footer = (
        f"\n# rc={proc.returncode} elapsed_ms={elapsed_ms}\n"
    )

    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n=== STDOUT ===\n")
        f.write(proc.stdout)
        f.write("\n=== STDERR ===\n")
        f.write(proc.stderr)
        f.write(footer)

    print(f"log: {log_path}")
    print(f"rc={proc.returncode} elapsed_ms={elapsed_ms}")

    if args.dry_run:
        # Code review 2026-07-13-001 (#10): emit a single JSON line
        # so a future cron / CI wrapper can consume the result
        # without re-reading the log file.
        print(json.dumps({
            "rc": proc.returncode,
            "elapsed_ms": elapsed_ms,
            "log_path": str(log_path),
            "dry_run": True,
        }))
        # In dry-run there are no DB inserts; rc=0 from x-monitor is
        # the success signal.
        return proc.returncode

    if proc.returncode != 0:
        print(
            f"x-monitor run exited rc={proc.returncode}; "
            f"see {log_path}",
            file=sys.stderr,
        )
        return 1

    post_run_count = _count_posts_after(window_seconds=600)
    inserted = post_run_count - pre_run_count
    summary_line = (
        f"inserted={inserted} posts in last 10 min "
        f"(pre={pre_run_count}, post={post_run_count}); "
        f"see {log_path}"
    )
    print(summary_line)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n# {summary_line}\n")

    if inserted <= 0:
        print(
            "no posts inserted in the last 10 min — pipeline ran "
            "without DB writes; check the log",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
