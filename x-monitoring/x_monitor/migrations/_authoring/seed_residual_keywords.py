# {{AGENT_ATTRIBUTION}}
"""One-shot authoring tool: dump residual-seed INSERT lines for
brand_keywords as SQL.

Plan: docs/plans/2026-07-11-001-feat-queries-and-filters-retire-and-export-poststep-plan.md
(Unit U1).

This script is **authoring-time only**: it parses
``data/queries/<brand>.yaml`` Q2/Q3/Q5/Q6 paren groups via
``x_monitor.query_plan.parse_brand_tokens`` and emits SQL ``INSERT OR
IGNORE`` lines that get pasted into
``x_monitor/migrations/035_rename_call_c_specs_and_residual_seed.sql``.

It does NOT run at apply-time. The migration runner
(``Store.apply_migrations``) only picks up files directly under
``x_monitor/migrations/``; this file lives in ``_authoring/`` so it
will never be executed by the runner.

Why static SQL instead of a Python hook in the runner:
  - U1's brief is to make the migration pure SQL (the runner is
    ``executescript``-only; adding a hook would couple apply-time to
    Python and break hermetic seed paths).
  - The set of brands/tokens is bounded and operator-curated; the
    cost of regenerating the static SQL on every yaml change is the
    same as the cost of running this script once on a brand-add.

Output format:
  INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex,
    added_at) VALUES
      ('<brand>', '<token>', 0, datetime('now')),
      ...;

Each brand emits one multi-row INSERT statement (preserves
readability for reviewers).

Usage:
  # Dry-run (prints SQL to stdout):
  python3 -m x_monitor.migrations._authoring.seed_residual_keywords

  # Write to migration file (overwrites -- check the diff before
  # committing):
  python3 -m x_monitor.migrations._authoring.seed_residual_keywords \\
    --out x_monitor/migrations/035_rename_call_c_specs_and_residual_seed.sql

Re-running is idempotent because the output uses INSERT OR IGNORE.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from x_monitor.config import load_config
from x_monitor.query_plan import parse_brand_tokens


def _emit_sql(
    enabled_models: list[str], queries_dir: Path
) -> str:
    """Return the static SQL body — pre-computed INSERTs that match
    the current ``data/queries/*.yaml`` state.
    """
    tokens = parse_brand_tokens(enabled_models, queries_dir)
    blocks: list[str] = []
    for brand in enabled_models:
        toks = tokens.get(brand, [])
        if not toks:
            blocks.append(f"-- {brand}: (no Q2/Q3/Q5/Q6 paren groups; nothing to seed)")
            continue
        rows = ",\n    ".join(
            f"('{brand}', {tok!r}, 0, datetime('now'))" for tok in toks
        )
        blocks.append(
            f"-- {brand}\nINSERT OR IGNORE INTO brand_keywords "
            f"(brand_id, pattern, is_regex, added_at) VALUES\n    {rows};"
        )
    return "\n\n".join(blocks)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Dump residual-seed SQL for brand_keywords (authoring-time)."
    )
    p.add_argument(
        "--config", type=Path, default=Path("config.yaml"),
    )
    p.add_argument(
        "--queries-dir", type=Path, default=Path("data/queries"),
    )
    p.add_argument(
        "--out", type=Path, default=None,
        help="If set, write SQL to this file (overwrites). Otherwise print to stdout.",
    )
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    body = _emit_sql(cfg.enabled_models, args.queries_dir)

    if args.out is None:
        print(body)
    else:
        args.out.write_text(body + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())