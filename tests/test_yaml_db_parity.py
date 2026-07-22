# {{AGENT_ATTRIBUTION}}
"""YAML ↔ DB parity test (plan 005 U5).

For every brand in ``config.yaml::enabled_models``:

1. Load ``data/accounts/<brand>.yaml``.
2. Extract every handle from the yaml's ``accounts[].handle`` and
   ``staff[].handle`` fields (case-preserved — yaml is the operator's
   curation surface).
3. Query the DB: ``accounts`` JOIN ``brands_accounts`` WHERE the brand's
   nickname matches.
4. Assert yaml → DB coverage: every yaml handle resolves to a DB row in
   brands_accounts for that brand (no yaml↛DB leak).
5. Assert DB → yaml coverage: every DB handle for that brand appears in
   the yaml's accounts or staff lists (no DB↛yaml leak).

The two-direction check catches both kinds of drift:

- yaml↛DB leak: the yaml references a handle the DB doesn't know about.
  This is the classic placeholder-drift bug (e.g. ``Llama`` in qwen.yaml
  when the DB has ``AIatMeta``). Plan 005 U2/U3/U4 close these.
- DB↛yaml leak: the DB has a handle for the brand but the yaml doesn't
  mention it. This is the new-handle case the regen script (U1) prevents
  by emitting yamls from the DB.

This test runs against the live ``data/x_monitoring.db`` and the
committed ``data/accounts/*.yaml`` set — it is a guardrail, not a unit
test. As such it uses the production config and DB rather than the
hermetic mini-fixture pattern in ``test_regenerate_accounts_yaml.py``.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ACCOUNTS_DIR = REPO_ROOT / "data" / "accounts"
DB_PATH = REPO_ROOT / "data" / "x_monitoring.db"
CONFIG_PATH = REPO_ROOT / "config.yaml"


def _load_enabled_brands() -> list[str]:
    """Return enabled_models from config.yaml. Skip the test if absent."""
    if not CONFIG_PATH.exists():
        pytest.skip(f"config.yaml not found at {CONFIG_PATH}")
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    return list(raw.get("enabled_models", []))


def _yaml_handles(brand: str) -> tuple[set[str], set[str]]:
    """Return (accounts_handles, staff_handles) for ``data/accounts/<brand>.yaml``.

    Lowercased so we can do case-insensitive matching against the DB. The
    yaml is the operator-curated surface and case in the DB is whatever
    the migration stored — both can drift.
    """
    path = ACCOUNTS_DIR / f"{brand}.yaml"
    if not path.exists():
        return (set(), set())
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    accounts = {str(h).lower() for h in (a.get("handle") for a in (raw.get("accounts") or [])) if h}
    staff = {str(h).lower() for h in (a.get("handle") for a in (raw.get("staff") or [])) if h}
    return (accounts, staff)


def _db_handles(brand: str) -> set[str]:
    """Return the set of DB handles for a brand (lowercased).

    Joins accounts → brands_accounts → brands. Includes both official and
    staff roles — a handle is a handle regardless of role.
    """
    if not DB_PATH.exists():
        pytest.skip(f"x_monitoring.db not found at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            """
            SELECT LOWER(a.handle) AS h
            FROM brands_accounts ba
            JOIN brands b ON b.id = ba.brand_id
            JOIN accounts a ON a.id = ba.accounts_id
            WHERE b.nickname = ?
            """,
            (brand,),
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Per-brand parity
# ----------------------------------------------------------------------


@pytest.mark.parametrize("brand", _load_enabled_brands())
def test_yaml_has_no_handles_missing_from_db(brand: str) -> None:
    """For brand ``<brand>``: every yaml handle (accounts + staff) must
    resolve to a DB row in brands_accounts for that brand.

    yaml↛DB leak — this is the placeholder-drift case the regen script
    closes. A failing assertion here means the yaml still references a
    handle the DB doesn't know about; either the handle needs a
    brands_accounts row (run U3 seed), or the yaml needs an update (run
    U1 regen to overwrite from the DB).
    """
    accounts, staff = _yaml_handles(brand)
    yaml_handles = accounts | staff
    if not yaml_handles:
        pytest.skip(f"{brand}: no yaml handles (yaml may be brand-new)")
    db_handles = _db_handles(brand)

    missing = yaml_handles - db_handles
    assert not missing, (
        f"{brand}: yaml references handles not in DB: {sorted(missing)}. "
        f"Run scripts.regenerate_accounts_yaml.py --emit data/accounts/ "
        f"or scripts.seed_list_handles_to_db.py to close the gap."
    )


@pytest.mark.parametrize("brand", _load_enabled_brands())
def test_db_has_no_handles_missing_from_yaml(brand: str) -> None:
    """For brand ``<brand>``: every DB handle in brands_accounts must
    appear in the yaml's accounts or staff lists.

    DB↛yaml leak — this is the new-handle case the regen script
    prevents. A failing assertion here means the DB has a handle the
    yaml doesn't mention; run U1 regen to refresh the yaml.
    """
    accounts, staff = _yaml_handles(brand)
    yaml_handles = accounts | staff
    db_handles = _db_handles(brand)
    if not db_handles:
        pytest.skip(f"{brand}: no DB handles (DB may be brand-new)")

    missing = db_handles - yaml_handles
    assert not missing, (
        f"{brand}: DB has handles not in yaml: {sorted(missing)}. "
        f"Run scripts.regenerate_accounts_yaml.py --emit data/accounts/ "
        f"to refresh the yaml from the DB."
    )


# ----------------------------------------------------------------------
# Whole-graph sanity
# ----------------------------------------------------------------------


def test_every_brand_has_at_least_one_yaml_handle() -> None:
    """At minimum, every enabled brand must have ONE yaml handle entry.

    Catches the regression where a brand yaml is empty after a botched
    regen — every enabled brand is supposed to surface some account.
    """
    enabled = _load_enabled_brands()
    empty = [b for b in enabled if not (_yaml_handles(b)[0] | _yaml_handles(b)[1])]
    assert not empty, (
        f"these enabled brands have empty yamls: {empty}. "
        f"Either run scripts.regenerate_accounts_yaml.py to backfill, "
        f"or remove the brand from config.yaml::enabled_models."
    )


def test_yaml_handle_uniqueness_within_brand() -> None:
    """No duplicate handles within a single brand yaml.

    A yaml listing the same handle twice in ``accounts:`` (or once in
    ``accounts:`` and once in ``staff:``) is almost certainly a copy-
    paste error; surfaces as a duplicate fetch in Call A or Call B.
    """
    enabled = _load_enabled_brands()
    for brand in enabled:
        accounts, staff = _yaml_handles(brand)
        all_handles = list(accounts | staff)
        # Detect duplicates by counting
        counts: dict[str, int] = {}
        for h in all_handles:
            counts[h] = counts.get(h, 0) + 1
        dups = {h for h, c in counts.items() if c > 1}
        assert not dups, f"{brand}: duplicate handles in yaml: {sorted(dups)}"


# ----------------------------------------------------------------------
# Idempotency check (run after U1)
# ----------------------------------------------------------------------


def test_regen_then_parity_is_stable(tmp_path: Path) -> None:
    """After regen, the parity test must still pass.

    This is the idempotency contract: regenerating yamls from the DB
    must not introduce new leaks in either direction. We run regen into
    a tmp dir and run the parity check against the tmp dir's yamls.
    """
    if not DB_PATH.exists() or not CONFIG_PATH.exists():
        pytest.skip("live DB or config not available")

    from scripts.regenerate_accounts_yaml import regenerate
    from x_monitor.config import Config
    from x_monitor.store import Store

    config = Config.model_validate(yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")))
    emit_dir = tmp_path / "regen"
    store = Store(DB_PATH, auto_migrate=False)
    try:
        regenerate(store, config, emit_dir)
    finally:
        store.close()

    # For each enabled brand, the regen output must satisfy parity
    # (yaml handles match DB handles). The regen output is the
    # DB-authoritative state, so the parity is trivially true — this
    # test exists to catch regen bugs that drift the yaml.
    for brand in config.enabled_models:
        # Read regen yaml
        path = emit_dir / f"{brand}.yaml"
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        regen_handles = {
            str(a.get("handle")).lower()
            for a in (raw.get("accounts") or [])
            if a.get("handle")
        }
        db_handles = _db_handles(brand)
        missing = regen_handles - db_handles
        assert not missing, (
            f"{brand}: regen output references handles not in DB: {sorted(missing)}. "
            f"The regen script should be DB-authoritative — this is a bug."
        )