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

import yaml

from x_monitor.config import load_config


def _parse_first_paren_group(query_string: str) -> list[str]:
    """Extract tokens from the first balanced `(...)` group.

    Inlined here (rather than imported from `x_monitor.query_plan`)
    because the plan 2026-07-11-001 retires the public surface — the
    runtime no longer reads `data/queries/<brand>.yaml`. This script
    is the only remaining parser call, so it owns its own copy.
    """
    depth = 0
    start = -1
    for i, ch in enumerate(query_string):
        if ch == "(":
            if depth == 0:
                start = i + 1
            depth += 1
        elif ch == ")":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    group = query_string[start:i]
                    seen: set[str] = set()
                    out: list[str] = []
                    for tok in group.split(" OR "):
                        tok = tok.strip()
                        if tok and tok not in seen:
                            seen.add(tok)
                            out.append(tok)
                    return out
    return []


def _parse_brand_tokens(
    enabled_models: list[str], queries_dir: Path
) -> dict[str, list[str]]:
    """Per-brand deduplicated token list from Q2/Q3/Q5/Q6 paren groups.

    Inlined (see `_parse_first_paren_group` for why). Mirrors the
    legacy `x_monitor.query_plan.parse_brand_tokens` byte-for-byte
    so the U1 test fixtures still parse identically.
    """
    out: dict[str, list[str]] = {}
    for m in enabled_models:
        path = queries_dir / f"{m}.yaml"
        if not path.exists():
            out[m] = []
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        seen: set[str] = set()
        toks: list[str] = []
        for entry in raw.get("queries", []):
            if entry.get("id") not in {"Q2", "Q3", "Q5", "Q6"}:
                continue
            inner = entry.get("query_string", "")
            for tok in _parse_first_paren_group(inner):
                if tok not in seen:
                    seen.add(tok)
                    toks.append(tok)
        out[m] = toks
    return out


def _emit_sql(
    enabled_models: list[str], queries_dir: Path
) -> str:
    """Return the static SQL body — pre-computed INSERTs that match
    the current ``data/queries/*.yaml`` state.
    """
    tokens = _parse_brand_tokens(enabled_models, queries_dir)
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