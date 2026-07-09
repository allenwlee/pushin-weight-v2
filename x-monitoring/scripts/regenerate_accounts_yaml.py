# {{AGENT_ATTRIBUTION}}
"""Regenerate ``data/accounts/<brand>.yaml`` files from the live DB.

Plan: docs/plans/2026-07-09-001-feat-list-yaml-db-sync-plan.md (Unit 1).
The DB is the source of truth for which handles belong to which brand; this
script emits one yaml per brand in ``config.yaml::enabled_models``, preserving
operator-curated fields (``display_name``, ``verified``, ``notes``) from the
existing yaml when present.

Why: brand-account relationships now live in the ``brands_accounts`` table
(introduced in migration 004 and extended by migrations 030-032). The yaml
files were left in place as documentation/operator-curation surfaces, but
they had drifted from the DB (stale placeholders, missing handles after the
list-yaml reconciliation on 2026-07-09). This script closes the drift.

How to apply:

    python3 -m scripts.regenerate_accounts_yaml                # writes to data/accounts/
    python3 -m scripts.regenerate_accounts_yaml --brand doubao # one brand only
    python3 -m scripts.regenerate_accounts_yaml --emit /tmp/y  # custom output dir

Idempotency: re-running on an already-regenerated state produces
byte-identical output (same key order, no trailing whitespace, deterministic
sort).

Multi-brand rows: a handle linked to multiple brands (e.g. ``Kling_ai``
appears on both ``kuaishou`` and ``kwaiyii``) is emitted into the yaml of
the *first* enabled_models match. This keeps each brand yaml self-contained
and avoids cross-references that the smoketest would otherwise have to
resolve.

NOT in scope: this script does not delete yaml files for brands no longer
in enabled_models — that's U4's job. It does not insert into the DB. It
does not modify accounts/roles/brands tables.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

from x_monitor.config import Config, load_config
from x_monitor.store import Store

# Header that all existing yaml files begin with. We emit it verbatim so the
# output matches the committed style and the AGENT_ATTRIBUTION token survives
# round-trips through the regen.
YAML_HEADER = "# {{AGENT_ATTRIBUTION}}\n"

# Footer block copied from the canonical mimo.yaml. Every existing yaml has
# this trailing comment + `staff: []` placeholder. Preserving it keeps
# operators' muscle memory intact (open the file, see the empty staff
# section, know to add to it).
STAFF_FOOTER = (
    "\n"
    "# Manual staff list (you curate). v1.6 OR-collapse: these\n"
    "# handles are folded into the per-brand account call alongside the\n"
    "# official handle. Empty by default — add as you discover PM/dev\n"
    "# accounts that should represent the brand.\n"
    "staff: []\n"
)

# Default location of the live DB relative to the repo root. The Store
# constructor takes a Path; we keep this in one place so tests can override.
DEFAULT_DB_PATH = Path("data/x_monitoring.db")

# Default location of the brand account yamls. We emit here unless --emit
# is given; the test suite uses --emit /tmp/regen-yamls/ to avoid touching
# committed state.
DEFAULT_EMIT_DIR = Path("data/accounts")


def _load_existing_yaml(path: Path) -> dict[str, Any]:
    """Read an existing brand yaml and return its accounts list + staff list.

    Returns ``{"accounts": [...], "staff": [...]}``; missing keys default to
    empty lists. The accounts list preserves operator-curated
    ``display_name`` / ``verified`` / ``notes`` per handle (keyed by handle,
    case-insensitive) so they survive a regen.

    Why a separate parse: PyYAML's default loader round-trips comments fine,
    but we don't try to round-trip them — the canonical header + footer
    pattern is regenerated verbatim and the operator doesn't get to put
    arbitrary content in the middle. This keeps regen idempotent.
    """
    if not path.exists():
        return {"accounts": [], "staff": []}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        "accounts": raw.get("accounts") or [],
        "staff": raw.get("staff") or [],
    }


def _index_existing_fields(
    existing_accounts: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build a handle -> fields map from an existing accounts list.

    Used by ``_merge_row`` to preserve operator-curated fields when the DB
    row's handle matches an existing yaml entry. Handles are lowercased so
    case-insensitive matching mirrors x.com's semantics (X treats handles as
    case-insensitive for lookups but case-preserving in storage).
    """
    idx: dict[str, dict[str, Any]] = {}
    for entry in existing_accounts:
        handle = entry.get("handle")
        if not handle:
            continue
        idx[handle.lower()] = {
            "display_name": entry.get("display_name", ""),
            "verified": bool(entry.get("verified", False)),
            "notes": entry.get("notes", "") or "",
        }
    return idx


def _merge_row(
    db_row: dict[str, Any],
    existing_idx: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Merge a DB row with existing operator-curated fields.

    DB is authoritative for ``handle`` and ``role``; existing yaml is
    authoritative for ``display_name``, ``verified``, and ``notes`` when
    present. New handles (not in existing_idx) get empty defaults so the
    operator can fill them in via the next curation pass.
    """
    handle = db_row["handle"]
    role = db_row["role"]
    key = handle.lower()
    existing = existing_idx.get(key, {})
    return {
        "handle": handle,
        "display_name": existing.get("display_name", ""),
        "role": role,
        "verified": existing.get("verified", False),
        "notes": existing.get("notes", ""),
    }


def _fetch_brand_rows(
    store: Store,
    enabled_brands: list[str],
) -> dict[str, list[dict[str, Any]]]:
    """For each enabled brand, fetch (handle, role) pairs from the DB.

    Sort order is role-then-handle: official (role_id=2) before staff
    (role_id=3), and alphabetical within each role. Multi-brand rows are
    returned once per brand they belong to; the caller (regenerate) picks
    the first enabled match per handle, so the same handle may be missing
    from the secondary brand's yaml. That's deliberate — see module
    docstring "Multi-brand rows".

    Returns a dict keyed by brand nickname; missing brands (no rows in
    brands_accounts) get an empty list.
    """
    rows = store._conn.execute(
        """
        SELECT b.nickname AS brand,
               a.handle   AS handle,
               r.key      AS role
        FROM brands_accounts ba
        JOIN brands  b ON b.id = ba.brand_id
        JOIN accounts a ON a.id = ba.accounts_id
        JOIN roles   r ON r.id = ba.role_id
        WHERE b.nickname IN (SELECT value FROM json_each(?))
        ORDER BY b.nickname, r.id, a.handle COLLATE NOCASE
        """,
        # Pass enabled_brands as a JSON array literal — Store is built on
        # stdlib sqlite3 which has no array binding. json_each + IN is the
        # idiomatic substitute.
        (__import__("json").dumps(enabled_brands),),
    ).fetchall()

    by_brand: dict[str, list[dict[str, Any]]] = {b: [] for b in enabled_brands}
    seen_handles_per_brand: dict[str, set[str]] = {b: set() for b in enabled_brands}
    for r in rows:
        brand = r["brand"]
        handle = r["handle"]
        if not handle:
            continue
        key = handle.lower()
        # Multi-brand dedup: only assign to the first enabled brand we
        # encounter this handle for, in enabled_brands iteration order.
        # Re-iterate the row's brand against enabled_brands to find its
        # priority position.
        already_assigned = any(
            key in seen_handles_per_brand[b] for b in enabled_brands
        )
        if already_assigned:
            continue
        by_brand[brand].append({"handle": handle, "role": r["role"]})
        seen_handles_per_brand[brand].add(key)
    return by_brand


def _render_yaml(
    brand: str,
    rows: list[dict[str, Any]],
    existing: dict[str, Any],
) -> str:
    """Render one brand yaml file.

    Layout (matches mimo.yaml and other committed yamls):

        # {{AGENT_ATTRIBUTION}}
        accounts:
          - handle: Foo
            display_name: ...
            role: official
            verified: true
            notes: ...

        # Manual staff list (you curate). v1.6 OR-collapse: ...
        staff: []
    """
    existing_idx = _index_existing_fields(existing["accounts"])
    merged = [_merge_row(row, existing_idx) for row in rows]

    # PyYAML dumps with default_flow_style=False to get block style and
    # sort_keys=False to preserve our key order. allow_unicode=True keeps
    # non-ASCII display_name values readable (Baidu/SenseTime/Stepfun
    # have CJK display_names set by migration 030-031).
    body = yaml.safe_dump(
        {"accounts": merged},
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=4096,  # one line per value; matches existing yamls
    )

    # Prepend header (PyYAML doesn't preserve leading # comment lines),
    # append footer block. Trailing newline enforced so the file ends in \n
    # the same way all committed yamls do.
    return YAML_HEADER + body + STAFF_FOOTER


def regenerate(
    store: Store,
    config: Config,
    emit_dir: Path,
    *,
    brand_filter: str | None = None,
) -> dict[str, Path]:
    """Regenerate brand yamls. Returns a mapping brand_nickname -> written path.

    ``brand_filter`` is the only-brand mode (--brand CLI flag). When set, only
    that brand is emitted and others are left untouched.

    Why return the path map: callers (the CLI below and tests) want to know
    which files were written so they can run idempotency checks or diff
    against the committed state.
    """
    enabled = list(config.enabled_models)
    if brand_filter:
        if brand_filter not in enabled:
            raise ValueError(
                f"--brand '{brand_filter}' not in enabled_models; "
                f"valid: {enabled}"
            )
        enabled = [brand_filter]

    emit_dir.mkdir(parents=True, exist_ok=True)

    by_brand = _fetch_brand_rows(store, enabled)
    written: dict[str, Path] = {}
    for brand in enabled:
        rows = by_brand.get(brand, [])
        existing_path = DEFAULT_EMIT_DIR / f"{brand}.yaml"
        existing = _load_existing_yaml(existing_path)
        content = _render_yaml(brand, rows, existing)
        out_path = emit_dir / f"{brand}.yaml"
        out_path.write_text(content, encoding="utf-8")
        written[brand] = out_path
    return written


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI arg parser. Three knobs: --emit, --brand, --config, --db."""
    p = argparse.ArgumentParser(
        description="Regenerate data/accounts/<brand>.yaml files from the live DB."
    )
    p.add_argument(
        "--emit",
        type=Path,
        default=DEFAULT_EMIT_DIR,
        help="Output directory (default: data/accounts/).",
    )
    p.add_argument(
        "--brand",
        type=str,
        default=None,
        help="Restrict regen to one brand nickname (must be in enabled_models).",
    )
    p.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to config.yaml (default: config.yaml).",
    )
    p.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to x_monitoring.db (default: data/x_monitoring.db).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 on success, 1 on missing files, 2 on bad input."""
    args = _parse_args(argv)
    if not args.config.exists():
        print(f"config not found: {args.config}", file=sys.stderr)
        return 1
    if not args.db.exists():
        print(f"db not found: {args.db}", file=sys.stderr)
        return 1

    config = load_config(args.config)
    store = Store(args.db, auto_migrate=False)
    try:
        written = regenerate(store, config, args.emit, brand_filter=args.brand)
    finally:
        store.close()

    for brand, path in sorted(written.items()):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())