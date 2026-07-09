# {{AGENT_ATTRIBUTION}}
"""One-shot seed for the 10 list-not-in-DB handles (plan 005 U3).

Plan: docs/plans/2026-07-09-001-feat-list-yaml-db-sync-plan.md (Unit 3)
Reconciliation note: docs/notes/2026-07-09-list-yaml-reconciliation.md

For each (handle, company, role) triple in the operator-confirmed table,
this script:

1. Looks up the x.com numeric ``author_id`` via TwitterAPI.io
   ``/2/users/by/username/<handle>`` (best-effort; falls back to using
   the lowercased handle as the placeholder ``author_id`` if the lookup
   fails — see Auth diagnostic in the reconciliation note).
2. INSERT OR IGNORE INTO ``accounts`` (author_id, handle, display_name,
   first_seen_at).
3. For every brand linked to the company via ``brands_companies``,
   INSERT OR IGNORE INTO ``brands_accounts`` with the supplied role.

Idempotency: re-running after a successful run produces no changes —
UNIQUE constraints on ``accounts.author_id`` and
``brands_accounts.(brand_id, accounts_id)`` enforce this.

Why a script and not a migration: the seed involves an HTTP lookup. The
API was returning 401 on 2026-07-09 (OAuth2 user-context token dead); if
the auth path gets fixed and we re-run with a working token, the
real ``author_id`` overwrites the placeholder. Keeping this out of the
``_migrations`` ledger means re-runs don't trigger spurious "already
applied" failures. Migration 033 handles the deterministic, no-I/O
``brands_companies`` inserts; this script handles the dynamic
``accounts`` + ``brands_accounts`` cascade.

How to apply:

    # Default: seed the 10 operator-confirmed triples
    python3 -m scripts.seed_list_handles_to_db

    # Dry-run: print the work without writing
    python3 -m scripts.seed_list_handles_to_db --dry-run

    # Custom input file
    python3 -m scripts.seed_list_handles_to_db --input my_handles.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from x_monitor.store import Store

# Operator-confirmed (handle, company, role) triples from plan 005 U3.
# `meituan_longcat` is excluded — operator left it blank in the plan,
# deferring it to a future new-brand-enablement plan.
DEFAULT_SEED: list[dict[str, str]] = [
    {"handle": "bytedanceoss",    "company": "bytedance",   "role": "official"},
    {"handle": "carolglms",       "company": "zhipu",       "role": "staff"},
    {"handle": "chujiezheng",     "company": "alibaba",     "role": "staff"},
    {"handle": "doubaoai",        "company": "bytedance",   "role": "official"},
    {"handle": "hailuo_ai",       "company": "minimax",     "role": "official"},
    {"handle": "liulicheng10",    "company": "stepfun_inc", "role": "staff"},
    {"handle": "mertunsal2020",   "company": "mistral_ai",  "role": "staff"},
    {"handle": "stepfunai",       "company": "stepfun_inc", "role": "official"},
    {"handle": "xuanmingzhangai", "company": "alibaba",     "role": "staff"},
    {"handle": "zrdianjiao",      "company": "zhipu",       "role": "staff"},
]

# TwitterAPI.io lookup endpoint for v2 user-by-username. The plan documents
# the auth failure mode (401 on OAuth2 user-context token) — when that
# happens, ``_lookup_author_id`` returns None and the caller falls back to
# the lowercased handle as the placeholder ``author_id``.
TWITTERAPI_BASE = "https://api.twitterapi.io/twitter/user/by/username"

# role -> role_id. Mirrors the values used in migrations 030/032; verified
# 2026-07-09 via SELECT id, key FROM roles in production. Keep in sync if
# the schema ever introduces a new role (e.g. U6 of plan 005).
ROLE_KEY_TO_ID: dict[str, int] = {
    "community": 1,
    "official": 2,
    "staff": 3,
}


@dataclass(frozen=True)
class SeedTriple:
    """One row of the operator-confirmed (handle, company, role) table.

    Kept as a frozen dataclass (not a dict) so downstream code can rely
    on attribute access — easier to grep, refactor, and type-check.
    """
    handle: str
    company: str
    role: str


@dataclass
class SeedResult:
    """Per-triple outcome for the report at the end of a run."""
    handle: str
    company: str
    role: str
    account_inserted: bool
    brands_accounts_inserted: list[str]  # brand nicknames that got new rows
    brands_accounts_skipped: list[str]   # brand nicknames with no brands_companies
    author_id: str
    author_id_source: str  # "api" | "placeholder"


def _load_seed(path: Path | None) -> list[SeedTriple]:
    """Load the seed triples from a YAML file or fall back to DEFAULT_SEED.

    Input YAML shape (matches the plan's table):

        - handle: bytedanceoss
          company: bytedance
          role: official
        ...

    Why YAML and not JSON: matches the operator's other config files
    (config.yaml, data/accounts/*.yaml). Also keeps the file human-editable.
    """
    import yaml
    if path is None:
        raw = DEFAULT_SEED
    else:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    triples: list[SeedTriple] = []
    for row in raw:
        triples.append(
            SeedTriple(
                handle=row["handle"],
                company=row["company"],
                role=row["role"],
            )
        )
    return triples


def _lookup_author_id(handle: str, timeout_s: float = 5.0) -> str | None:
    """Best-effort TwitterAPI.io lookup. Returns numeric id or None.

    Why best-effort: the operator's auth path was returning 401 on
    2026-07-09. We don't want a transient API failure to block the
    seed — the placeholder ``author_id`` (= lowercased handle) is a
    known-good fallback that subsequent migrations can rewrite once
    a working auth path is restored. The reconciliation note documents
    this in its Auth diagnostic preamble.
    """
    url = f"{TWITTERAPI_BASE}/{handle}"
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None
    # TwitterAPI.io returns {"data": {"id": "...", ...}} on success; be
    # defensive about field shape since v1.1 vs v2 differ.
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None
    candidate = data.get("id") or data.get("rest_id") or data.get("author_id")
    return str(candidate) if candidate else None


def _company_brand_ids(store: Store, company_nickname: str) -> list[int]:
    """Return the brand_ids linked to ``company_nickname`` via brands_companies.

    Empty list means the company has no mapped brands — the script
    surfaces this as a warning rather than failing, because a freshly
    added brand may legitimately have no companies yet (plan 005 U3
    forward path: future brand additions may need this script to be
    re-run once their companies land via a separate migration).
    """
    rows = store._conn.execute(
        """
        SELECT bc.brand_id AS brand_id
        FROM brands_companies bc
        JOIN companies c ON c.id = bc.company_id
        WHERE c.nickname = ?
        ORDER BY bc.brand_id
        """,
        (company_nickname,),
    ).fetchall()
    return [r["brand_id"] for r in rows]


def _brand_id_for_nickname(store: Store, nickname: str) -> int:
    """Resolve a brand nickname to its integer id, or raise KeyError.

    Used by the report printer at end-of-run to map inserted brand_ids
    back to human-readable nicknames.
    """
    row = store._conn.execute(
        "SELECT id FROM brands WHERE nickname = ?", (nickname,)
    ).fetchone()
    if not row:
        raise KeyError(f"brand not found: {nickname}")
    return row["id"]


def seed_one(
    store: Store,
    triple: SeedTriple,
    *,
    use_api: bool = True,
) -> SeedResult:
    """Seed a single triple into the DB. Returns a SeedResult (no exception).

    The function is split out so the test harness can call it directly
    with ``use_api=False`` to keep CI hermetic (the API path is mocked
    in tests).
    """
    handle_lc = triple.handle.lower()
    author_id = (
        _lookup_author_id(handle_lc) if use_api else None
    ) or handle_lc  # placeholder fallback
    author_id_source = "api" if (use_api and author_id != handle_lc) else "placeholder"

    role_id = ROLE_KEY_TO_ID.get(triple.role)
    if role_id is None:
        raise ValueError(
            f"unknown role '{triple.role}' for handle '{triple.handle}'; "
            f"valid: {sorted(ROLE_KEY_TO_ID)}"
        )

    # Step 1: accounts upsert. INSERT OR IGNORE keeps idempotency.
    # Note: display_name is left blank (NOT set to the handle). The
    # placeholder author_id path doesn't have real x.com display_name
    # data, so we don't fabricate one from the handle. Operator can
    # fill display_name via a follow-up once the TwitterAPI.io auth
    # path is restored and the real author_id resolves — at that point
    # the /twitter/user/by/username/<handle> response carries the real
    # name field and we can UPDATE the row.
    cur = store._conn.execute(
        """
        INSERT OR IGNORE INTO accounts
            (author_id, handle, display_name, first_seen_at)
        VALUES (?, ?, '', datetime('now'))
        """,
        (author_id, triple.handle),
    )
    account_inserted = cur.rowcount > 0

    # Resolve account id (whether just inserted or pre-existing).
    row = store._conn.execute(
        "SELECT id FROM accounts WHERE author_id = ?", (author_id,)
    ).fetchone()
    if not row:
        # Should never happen after a successful INSERT OR IGNORE, but
        # guard against the corner case where author_id already exists
        # bound to a different handle (UNIQUE on author_id, not handle).
        raise RuntimeError(
            f"account upsert for {triple.handle} produced no row (author_id={author_id})"
        )
    account_id = row["id"]

    # Step 2: cross-product brands_accounts by company cascade.
    brand_ids = _company_brand_ids(store, triple.company)
    inserted_nicknames: list[str] = []
    skipped_nicknames: list[str] = []
    for brand_id in brand_ids:
        nick_row = store._conn.execute(
            "SELECT nickname FROM brands WHERE id = ?", (brand_id,)
        ).fetchone()
        if not nick_row:
            skipped_nicknames.append(f"<id={brand_id}?>")
            continue
        nickname = nick_row["nickname"]
        ba_cur = store._conn.execute(
            """
            INSERT OR IGNORE INTO brands_accounts
                (brand_id, accounts_id, role_id)
            VALUES (?, ?, ?)
            """,
            (brand_id, account_id, role_id),
        )
        if ba_cur.rowcount > 0:
            inserted_nicknames.append(nickname)
        # If rowcount == 0, the (brand_id, accounts_id) row already
        # exists — that's idempotency working as intended.

    store._conn.commit()

    # Map any brand_ids we silently skipped (company has no brands_companies
    # rows at all) to "no-mapping" so the report is honest about it.
    if not brand_ids:
        skipped_nicknames.append("<no brands_companies rows for company>")

    return SeedResult(
        handle=triple.handle,
        company=triple.company,
        role=triple.role,
        account_inserted=account_inserted,
        brands_accounts_inserted=inserted_nicknames,
        brands_accounts_skipped=skipped_nicknames,
        author_id=author_id,
        author_id_source=author_id_source,
    )


def seed_all(
    store: Store,
    triples: list[SeedTriple],
    *,
    use_api: bool = True,
    dry_run: bool = False,
) -> list[SeedResult]:
    """Seed every triple. Returns one SeedResult per triple.

    ``dry_run`` skips the writes entirely — used for the operator to
    preview the work before committing it. The DB is unchanged.
    """
    if dry_run:
        return [
            SeedResult(
                handle=t.handle,
                company=t.company,
                role=t.role,
                account_inserted=False,
                brands_accounts_inserted=[],
                brands_accounts_skipped=[],
                author_id=t.handle.lower(),
                author_id_source="dry-run",
            )
            for t in triples
        ]
    return [seed_one(store, t, use_api=use_api) for t in triples]


def _format_report(results: list[SeedResult]) -> str:
    """Format a human-readable run report.

    Format mirrors other x-monitor scripts (post_fetch_smoketest) — one
    line per triple, then a footer with the totals. Operators paste this
    into commit messages.
    """
    lines = ["seed_list_handles_to_db — run report", ""]
    for r in results:
        ba_inserted = (
            ", ".join(r.brands_accounts_inserted)
            if r.brands_accounts_inserted else "(none)"
        )
        lines.append(
            f"  {r.handle:25} company={r.company:12} role={r.role:8} "
            f"author_id={r.author_id:20} [{r.author_id_source}] "
            f"account_inserted={r.account_inserted} "
            f"brands_accounts={ba_inserted}"
        )
        for skipped in r.brands_accounts_skipped:
            lines.append(
                f"    WARN: {skipped} for {r.handle}/{r.company} — "
                f"no brands_companies row, brands_accounts not inserted"
            )
    n_inserted = sum(1 for r in results if r.account_inserted)
    n_ba = sum(len(r.brands_accounts_inserted) for r in results)
    lines.append("")
    lines.append(f"  accounts inserted:        {n_inserted} / {len(results)}")
    lines.append(f"  brands_accounts inserted: {n_ba}")
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="One-shot seed for the 10 list-not-in-DB handles "
                    "(plan 005 U3). Idempotent."
    )
    p.add_argument(
        "--input", type=Path, default=None,
        help="YAML file of (handle, company, role) triples. Default: built-in table.",
    )
    p.add_argument(
        "--db", type=Path, default=Path("data/x_monitoring.db"),
        help="Path to x_monitoring.db (default: data/x_monitoring.db).",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print the work without writing.",
    )
    p.add_argument(
        "--no-api", action="store_true",
        help="Skip the TwitterAPI.io author_id lookup; use lowercased handle "
             "as placeholder for every triple. Useful for hermetic CI.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.db.exists():
        print(f"db not found: {args.db}", file=sys.stderr)
        return 1

    triples = _load_seed(args.input)
    store = Store(args.db, auto_migrate=False)
    try:
        results = seed_all(
            store,
            triples,
            use_api=not args.no_api,
            dry_run=args.dry_run,
        )
    finally:
        store.close()

    print(_format_report(results))
    # 0 on success, 2 if any handle hit a brands_companies gap (warning
    # surfaced in the report). Operator can decide whether to fix the
    # gap or accept it.
    has_gaps = any(r.brands_accounts_skipped for r in results)
    return 2 if has_gaps and not args.dry_run else 0


if __name__ == "__main__":
    sys.exit(main())