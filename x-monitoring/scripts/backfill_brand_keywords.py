# {{AGENT_ATTRIBUTION}}
"""One-shot backfill for the brand_keywords table (plan 2026-07-10-001).

Plan: docs/plans/2026-07-10-001-feat-brand-keywords-backfill-plan.md

The ``probe_filter_yield`` probe (and any production code that uses the
same index) reads brand tokens from the live ``brand_keywords`` table
via ``store.read_brand_keywords()``. The table covers 8 of 20+ brands;
13 brands in ``enabled_models`` have zero entries, which makes the
``_kept_after_filter`` count return 0 for posts mentioning those brands
even when the post text clearly contains a brand token like ``NeMo``
or ``Upstage``.

This script closes that gap by parsing ``data/queries/<brand>.yaml`` Q2
paren groups (the operator-curated source of truth for brand tokens)
and INSERT-OR-IGNORE-ing every (brand, token) pair into the table.
Same parser as the runtime Call B construction uses
(``x_monitor.query_plan.parse_brand_tokens``).

Idempotent: re-running after a successful run produces no changes —
the (brand_id, pattern) UNIQUE on brand_keywords enforces this.

Why a script and not a migration: the source is a yaml file the
operator curates, not a deterministic snapshot. Re-running shouldn't
require touching the migration ledger. The migration 034 in this plan
is a static fallback for hermetic apply paths (fresh DBs, CI seeding);
this script is the dynamic source going forward — operators who add a
new brand's yaml just rerun the script.

How to apply:

    # Default: backfill from data/queries/ to data/x_monitoring.db
    python3 -m scripts.backfill_brand_keywords

    # Dry-run: print the work without writing
    python3 -m scripts.backfill_brand_keywords --dry-run

    # Custom DB / queries dir
    python3 -m scripts.backfill_brand_keywords --db path/to.db --queries-dir path/to/queries
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

from x_monitor.config import load_config
from x_monitor.query_plan import parse_brand_tokens
from x_monitor.store import Store


def _load_enabled_models(config_path: Path) -> list[str]:
    """Return enabled_models from config.yaml. Used as the brand universe."""
    cfg = load_config(config_path)
    return list(cfg.enabled_models)


def _existing_pairs(store: Store) -> set[tuple[str, str]]:
    """Snapshot of (brand_id, pattern) pairs already in brand_keywords.

    Used for the per-row skipped-vs-inserted accounting in the run report.
    """
    rows = store._conn.execute(
        "SELECT brand_id, pattern FROM brand_keywords"
    ).fetchall()
    return {(r["brand_id"], r["pattern"]) for r in rows}


def _insert_pairs(
    store: Store,
    pairs: Iterable[tuple[str, str]],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """INSERT OR IGNORE every (brand_id, pattern) into brand_keywords.

    Returns (inserted, skipped) — ``skipped`` means the pair already
    existed at the time of the call. Operator sees the split in the
    run report so a re-run prints all-skipped and confirms idempotency.
    """
    inserted: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []
    for brand_id, pattern in pairs:
        cur = store._conn.execute(
            """
            INSERT OR IGNORE INTO brand_keywords
                (brand_id, pattern, is_regex, added_at)
            VALUES (?, ?, 0, datetime('now'))
            """,
            (brand_id, pattern),
        )
        if cur.rowcount > 0:
            inserted.append((brand_id, pattern))
        else:
            skipped.append((brand_id, pattern))
    store._conn.commit()
    return inserted, skipped


def _enumerate_pairs(
    enabled_models: list[str], queries_dir: Path
) -> tuple[list[tuple[str, str]], list[str]]:
    """Build the full (brand, token) pair list from yaml Q2 paren groups.

    Returns (pairs, empty_brands). ``empty_brands`` are brands whose yaml
    is missing or whose Q2/Q3/Q5/Q6 have no parseable paren group — the
    caller surfaces these as warnings (rc=2 if any).
    """
    tokens = parse_brand_tokens(enabled_models, queries_dir)
    pairs: list[tuple[str, str]] = []
    empty_brands: list[str] = []
    for brand in enabled_models:
        toks = tokens.get(brand, [])
        if not toks:
            empty_brands.append(brand)
            continue
        for tok in toks:
            pairs.append((brand, tok))
    return pairs, empty_brands


def _format_report(
    enabled_models: list[str],
    pairs: list[tuple[str, str]],
    inserted: list[tuple[str, str]],
    skipped: list[tuple[str, str]],
    empty_brands: list[str],
    dry_run: bool,
) -> str:
    """Human-readable run report. Operators paste this into commit msgs."""
    lines = ["backfill_brand_keywords — run report", ""]
    lines.append(f"  enabled brands:    {len(enabled_models)}")
    lines.append(f"  (brand, token) pairs parsed: {len(pairs)}")
    lines.append(f"  inserted:          {len(inserted)}")
    lines.append(f"  skipped (existed): {len(skipped)}")
    if empty_brands:
        lines.append("")
        lines.append("  WARN: enabled brands with zero parsed tokens:")
        for b in empty_brands:
            lines.append(f"    - {b}")
    if dry_run:
        lines.append("")
        lines.append("  (dry-run; no rows were written)")
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill brand_keywords from data/queries/<brand>.yaml "
                    "Q2 paren groups. Idempotent."
    )
    p.add_argument(
        "--config", type=Path, default=Path("config.yaml"),
        help="Path to config.yaml (default: config.yaml).",
    )
    p.add_argument(
        "--db", type=Path, default=Path("data/x_monitoring.db"),
        help="Path to x_monitoring.db (default: data/x_monitoring.db).",
    )
    p.add_argument(
        "--queries-dir", type=Path, default=Path("data/queries"),
        help="Directory holding <brand>.yaml query files (default: data/queries).",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print the work without writing.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.db.exists():
        print(f"db not found: {args.db}", file=sys.stderr)
        return 1
    if not args.config.exists():
        print(f"config not found: {args.config}", file=sys.stderr)
        return 1
    if not args.queries_dir.exists():
        print(f"queries dir not found: {args.queries_dir}", file=sys.stderr)
        return 1

    enabled_models = _load_enabled_models(args.config)
    pairs, empty_brands = _enumerate_pairs(enabled_models, args.queries_dir)

    if args.dry_run:
        print(_format_report(
            enabled_models, pairs, [], [], empty_brands, dry_run=True,
        ))
        return 0

    store = Store(args.db, auto_migrate=False)
    try:
        # Snapshot existing pairs BEFORE the insert so we can compute
        # inserted vs skipped in one pass without re-querying the DB
        # after each row.
        existing_before = _existing_pairs(store)
        to_insert = [
            (b, p) for (b, p) in pairs
            if (b, p) not in existing_before
        ]
        to_skip_report = [
            (b, p) for (b, p) in pairs
            if (b, p) in existing_before
        ]
        inserted, _skipped = _insert_pairs(store, to_insert)
    finally:
        store.close()

    print(_format_report(
        enabled_models, pairs, inserted, to_skip_report, empty_brands,
        dry_run=False,
    ))
    # rc=2 surfaces the warning visibly (operator can grep for WARN)
    # but doesn't fail CI; the script always completes its inserts.
    return 2 if empty_brands else 0


if __name__ == "__main__":
    sys.exit(main())