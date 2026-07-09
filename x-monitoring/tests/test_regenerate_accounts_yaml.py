# {{AGENT_ATTRIBUTION}}
"""Tests for scripts.regenerate_accounts_yaml (plan 005 U1).

The regen script's job is to keep ``data/accounts/<brand>.yaml`` in sync with
the live ``brands_accounts`` table while preserving operator-curated fields
(``display_name``, ``verified``, ``notes``) per handle. These tests pin the
five behaviors called out in the plan's U1 test scenarios:

    1. Happy path: 3-brand DB -> 3 yamls emitted with correct shape.
    2. Idempotency: run twice, byte-identical output.
    3. Multi-brand row assignment: handle in brands_accounts for both
       enabled and non-enabled brand goes to enabled brand's yaml only.
    4. Existing-yaml preservation: pre-existing ``display_name`` on a
       handle survives a regen.
    5. New-handle insertion: a DB handle with no existing yaml entry
       gets ``display_name=""``, ``verified=false``, ``notes=""``.

Each test seeds a fresh in-memory SQLite DB via Store (the same class the
script uses in production), populates the minimum table set the script
reads from, runs regen, and asserts against the output dir. We don't
touch the on-disk committed state — the script's --emit flag is the
escape hatch.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.regenerate_accounts_yaml import (
    STAFF_FOOTER,
    YAML_HEADER,
    _load_existing_yaml,
    _merge_row,
    regenerate,
)
from x_monitor.config import Config
from x_monitor.store import Store


# ----------------------------------------------------------------------
# Fixtures and helpers
# ----------------------------------------------------------------------


@pytest.fixture
def tmp_emit_dir(tmp_path: Path) -> Path:
    """Fresh output dir for each test. The script must create it if absent."""
    return tmp_path / "emit"


def _fresh_db(db_path: Path) -> None:
    """Materialize the schema on a fresh DB.

    Store with auto_migrate=True runs every migration in order. For the
    regen tests we don't care about post-migration data — we only need
    the brands / accounts / brands_accounts / roles tables to exist so
    INSERT statements can run. The test then closes the store and reopens
    with auto_migrate=False to do its own seed inserts.
    """
    s = Store(db_path, auto_migrate=True)
    s.close()


def _seed_db_for_three_brands(db_path: Path) -> None:
    """Seed a 3-brand DB for happy-path tests.

    Brands already exist in the schema (minimax=7, deepseek=2, qwen=10 from
    migration 030/032) so we don't re-insert them — we only add the test
    accounts and brands_accounts rows. Role ids: official=2, staff=3.
    """
    _fresh_db(db_path)
    store = Store(db_path, auto_migrate=False)
    try:
        # minimax brand_id=7: 1 official + 1 staff
        store._conn.execute(
            "INSERT INTO accounts (author_id, handle) VALUES ('a1', 'MiniMax_AI')"
        )
        store._conn.execute(
            "INSERT INTO accounts (author_id, handle) VALUES ('a2', 'SkylerMiao7')"
        )
        # deepseek brand_id=2: 1 official + 1 staff
        store._conn.execute(
            "INSERT INTO accounts (author_id, handle) VALUES ('b1', 'deepseek_ai')"
        )
        store._conn.execute(
            "INSERT INTO accounts (author_id, handle) VALUES ('b2', '_LuoFuli')"
        )
        # qwen brand_id=10: 1 official only
        store._conn.execute(
            "INSERT INTO accounts (author_id, handle) VALUES ('c1', 'Alibaba_Qwen')"
        )
        store._conn.commit()
        # Pull the auto-assigned account ids and insert brands_accounts rows
        acc_ids = {
            r['handle']: r['id']
            for r in store._conn.execute(
                "SELECT id, handle FROM accounts WHERE handle IN "
                "('MiniMax_AI','SkylerMiao7','deepseek_ai','_LuoFuli','Alibaba_Qwen')"
            ).fetchall()
        }
        store._conn.execute(
            "INSERT INTO brands_accounts (brand_id, accounts_id, role_id) "
            "VALUES (7, ?, 2)", (acc_ids['MiniMax_AI'],)
        )
        store._conn.execute(
            "INSERT INTO brands_accounts (brand_id, accounts_id, role_id) "
            "VALUES (7, ?, 3)", (acc_ids['SkylerMiao7'],)
        )
        store._conn.execute(
            "INSERT INTO brands_accounts (brand_id, accounts_id, role_id) "
            "VALUES (2, ?, 2)", (acc_ids['deepseek_ai'],)
        )
        store._conn.execute(
            "INSERT INTO brands_accounts (brand_id, accounts_id, role_id) "
            "VALUES (2, ?, 3)", (acc_ids['_LuoFuli'],)
        )
        store._conn.execute(
            "INSERT INTO brands_accounts (brand_id, accounts_id, role_id) "
            "VALUES (10, ?, 2)", (acc_ids['Alibaba_Qwen'],)
        )
        store._conn.commit()
    finally:
        store.close()


def _seed_db_for_multi_brand(db_path: Path) -> None:
    """Seed a DB where one handle appears on two brands.

    Mirrors the production case after migration 030's brand split:
    ``Kling_ai`` belongs to both ``kuaishou`` (brand_id=19) and
    ``kwaiyii`` (brand_id=25). The regen picks the first enabled_models
    match (kuaishou, since kwaiyii is not in enabled_models).
    """
    _fresh_db(db_path)
    store = Store(db_path, auto_migrate=False)
    try:
        store._conn.execute(
            "INSERT INTO accounts (author_id, handle) VALUES ('a1', 'Kling_ai')"
        )
        store._conn.commit()
        kid = store._conn.execute(
            "SELECT id FROM accounts WHERE handle='Kling_ai'"
        ).fetchone()['id']
        store._conn.execute(
            "INSERT INTO brands_accounts (brand_id, accounts_id, role_id) "
            "VALUES (19, ?, 2)", (kid,)
        )
        store._conn.execute(
            "INSERT INTO brands_accounts (brand_id, accounts_id, role_id) "
            "VALUES (25, ?, 2)", (kid,)
        )
        store._conn.commit()
    finally:
        store.close()


def _three_brand_config() -> Config:
    return Config.model_validate(
        {"enabled_models": ["minimax", "deepseek", "qwen"], "daily_ceiling": 1}
    )


def _yaml_hashes(emit_dir: Path) -> dict[str, str]:
    """sha256 of every yaml file in ``emit_dir``, sorted by name."""
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(emit_dir.glob("*.yaml"))
    }


def _seed_existing_yaml(
    existing_dir: Path,
    name: str,
    body: str,
) -> None:
    """Write a fully-formed existing yaml at ``existing_dir / <name>.yaml``.

    The script reads existing yamls from ``DEFAULT_EMIT_DIR`` regardless
    of ``--emit``, so to inject fixtures the test patches
    ``DEFAULT_EMIT_DIR`` to a temp dir before running regen. This helper
    keeps the format boilerplate in one place.
    """
    existing_dir.mkdir(parents=True, exist_ok=True)
    (existing_dir / name).write_text(
        YAML_HEADER + body + STAFF_FOOTER,
        encoding="utf-8",
    )


# ----------------------------------------------------------------------
# 1. Happy path
# ----------------------------------------------------------------------


def test_regen_emits_one_yaml_per_enabled_brand(
    tmp_path: Path, tmp_emit_dir: Path
) -> None:
    """3 enabled brands + 3-brand DB -> 3 yamls emitted with correct shape."""
    db_path = tmp_path / "x_monitoring.db"
    _seed_db_for_three_brands(db_path)

    store = Store(db_path, auto_migrate=False)
    try:
        written = regenerate(store, _three_brand_config(), tmp_emit_dir)
    finally:
        store.close()

    assert set(written.keys()) == {"minimax", "deepseek", "qwen"}
    assert tmp_emit_dir.is_dir()
    for brand in ("minimax", "deepseek", "qwen"):
        assert (tmp_emit_dir / f"{brand}.yaml").exists()


def test_regen_yaml_shape_matches_canonical(
    tmp_path: Path, tmp_emit_dir: Path
) -> None:
    """Emitted yaml has header + accounts list + staff footer, sorted role-first."""
    db_path = tmp_path / "x_monitoring.db"
    _seed_db_for_three_brands(db_path)

    store = Store(db_path, auto_migrate=False)
    try:
        regenerate(store, _three_brand_config(), tmp_emit_dir)
    finally:
        store.close()

    content = (tmp_emit_dir / "minimax.yaml").read_text(encoding="utf-8")
    assert content.startswith(YAML_HEADER)
    assert content.endswith(STAFF_FOOTER)

    yaml_lines = content[len(YAML_HEADER):-len(STAFF_FOOTER)]
    assert "MiniMax_AI" in yaml_lines and "SkylerMiao7" in yaml_lines
    assert yaml_lines.index("MiniMax_AI") < yaml_lines.index("SkylerMiao7"), (
        "official role must sort before staff role"
    )


# ----------------------------------------------------------------------
# 2. Idempotency
# ----------------------------------------------------------------------


def test_regen_is_idempotent(tmp_path: Path, tmp_emit_dir: Path) -> None:
    """Re-running regen on an already-emitted dir produces byte-identical output."""
    db_path = tmp_path / "x_monitoring.db"
    _seed_db_for_three_brands(db_path)
    config = _three_brand_config()

    store = Store(db_path, auto_migrate=False)
    try:
        regenerate(store, config, tmp_emit_dir)
    finally:
        store.close()
    hashes_1 = _yaml_hashes(tmp_emit_dir)

    store = Store(db_path, auto_migrate=False)
    try:
        regenerate(store, config, tmp_emit_dir)
    finally:
        store.close()
    hashes_2 = _yaml_hashes(tmp_emit_dir)

    assert hashes_1 == hashes_2, f"non-idempotent output: {hashes_1} vs {hashes_2}"


# ----------------------------------------------------------------------
# 3. Multi-brand row assignment
# ----------------------------------------------------------------------


def test_multi_brand_row_goes_to_first_enabled_match(
    tmp_path: Path, tmp_emit_dir: Path
) -> None:
    """Handle in brands_accounts for both kuaishou (enabled) and kwaiyii (NOT
    enabled) ends up in kuaishou.yaml only.

    The regen script picks the first enabled_models match for multi-brand
    rows. Since kwaiyii is not in enabled_models, the handle surfaces only
    in kuaishou.yaml — kwaiyii.yaml isn't even emitted (because kwaiyii
    isn't in enabled_models).
    """
    db_path = tmp_path / "x_monitoring.db"
    _seed_db_for_multi_brand(db_path)

    config = Config.model_validate(
        {"enabled_models": ["kuaishou"], "daily_ceiling": 1}
    )

    store = Store(db_path, auto_migrate=False)
    try:
        regenerate(store, config, tmp_emit_dir)
    finally:
        store.close()

    kuaishou_yaml = tmp_emit_dir / "kuaishou.yaml"
    assert kuaishou_yaml.exists()
    assert "Kling_ai" in kuaishou_yaml.read_text(encoding="utf-8")
    assert not (tmp_emit_dir / "kwaiyii.yaml").exists()


# ----------------------------------------------------------------------
# 4. Existing-yaml preservation
# ----------------------------------------------------------------------


def test_existing_display_name_survives_regen(
    tmp_path: Path, tmp_emit_dir: Path
) -> None:
    """Pre-existing ``display_name`` and ``notes`` survive a regen.

    We seed an existing yaml that hand-curates MiniMax_AI.display_name
    and notes, then regen, then assert the curated fields are intact.
    DB is authoritative for handle/role; existing yaml is authoritative
    for display_name / verified / notes.
    """
    db_path = tmp_path / "x_monitoring.db"
    _seed_db_for_three_brands(db_path)

    import scripts.regenerate_accounts_yaml as regen_mod

    fake_existing_dir = tmp_path / "existing"
    _seed_existing_yaml(
        fake_existing_dir,
        "minimax.yaml",
        "accounts:\n"
        "- handle: MiniMax_AI\n"
        "  display_name: 'MiniMax AI (curated)'\n"
        "  role: official\n"
        "  verified: true\n"
        "  notes: 'curated note preserved'\n",
    )

    original_default = regen_mod.DEFAULT_EMIT_DIR
    regen_mod.DEFAULT_EMIT_DIR = fake_existing_dir
    try:
        store = Store(db_path, auto_migrate=False)
        try:
            regenerate(store, _three_brand_config(), tmp_emit_dir)
        finally:
            store.close()
    finally:
        regen_mod.DEFAULT_EMIT_DIR = original_default

    new_yaml = tmp_emit_dir / "minimax.yaml"
    assert new_yaml.exists()
    text = new_yaml.read_text(encoding="utf-8")
    assert "MiniMax AI (curated)" in text, "operator-curated display_name lost"
    assert "curated note preserved" in text, "operator-curated notes lost"


# ----------------------------------------------------------------------
# 5. New-handle insertion (brand-new yaml from scratch)
# ----------------------------------------------------------------------


def test_new_handle_gets_empty_defaults(
    tmp_path: Path, tmp_emit_dir: Path
) -> None:
    """A handle that exists in the DB but not in the existing yaml gets
    emitted with display_name='', verified=false, notes=''.

    Only minimax.yaml exists in the seed; deepseek.yaml and qwen.yaml are
    brand-new, so every handle in those brands gets empty defaults.
    """
    db_path = tmp_path / "x_monitoring.db"
    _seed_db_for_three_brands(db_path)

    import scripts.regenerate_accounts_yaml as regen_mod

    fake_existing_dir = tmp_path / "existing"
    _seed_existing_yaml(
        fake_existing_dir,
        "minimax.yaml",
        "accounts:\n"
        "- handle: MiniMax_AI\n"
        "  display_name: 'MiniMax AI'\n"
        "  role: official\n"
        "  verified: true\n"
        "  notes: 'curated'\n",
    )

    original_default = regen_mod.DEFAULT_EMIT_DIR
    regen_mod.DEFAULT_EMIT_DIR = fake_existing_dir
    try:
        store = Store(db_path, auto_migrate=False)
        try:
            regenerate(store, _three_brand_config(), tmp_emit_dir)
        finally:
            store.close()
    finally:
        regen_mod.DEFAULT_EMIT_DIR = original_default

    deepseek_text = (tmp_emit_dir / "deepseek.yaml").read_text(encoding="utf-8")
    assert "- handle: deepseek_ai\n" in deepseek_text

    lines = deepseek_text.splitlines()
    handle_idx = lines.index("- handle: deepseek_ai")
    assert lines[handle_idx + 1] == "  display_name: ''", (
        f"expected empty display_name for brand-new handle, "
        f"got: {lines[handle_idx + 1]!r}"
    )
    assert lines[handle_idx + 2] == "  role: official"
    assert lines[handle_idx + 3] == "  verified: false"
    assert lines[handle_idx + 4] == "  notes: ''"


# ----------------------------------------------------------------------
# Helper unit tests (lower-stakes; pin contract for refactors)
# ----------------------------------------------------------------------


def test_load_existing_yaml_returns_empty_when_missing(tmp_path: Path) -> None:
    """Missing yaml -> empty dict (no exception).

    The script relies on this for the brand-new-yaml case.
    """
    assert _load_existing_yaml(tmp_path / "nope.yaml") == {"accounts": [], "staff": []}


def test_merge_row_uses_db_for_handle_and_role() -> None:
    """When no existing fields are present, merge returns DB-authoritative
    handle/role plus empty defaults. Pins the contract that DB wins on
    identity fields even when the operator hasn't curated anything yet.
    """
    row = {"handle": "Foo_Bar", "role": "official"}
    merged = _merge_row(row, {})
    assert merged["handle"] == "Foo_Bar"
    assert merged["role"] == "official"
    assert merged["display_name"] == ""
    assert merged["verified"] is False
    assert merged["notes"] == ""