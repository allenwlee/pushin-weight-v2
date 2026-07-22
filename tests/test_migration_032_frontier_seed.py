# {{AGENT_ATTRIBUTION}}
"""Migration 032 tests: seed frontier model companies, brands, accounts.

Seed land: 4 companies (openai, anthropic, google, xai); 5 brands
(gpt, claude, gemini, gemma, grok); 5 brands_companies edges;
16 accounts; 9 brands_accounts role=official; 12 brands_accounts role=staff.

These tests verify:
  - 032 applies on a fresh DB and the seed rows are present in expected counts.
  - brand→company edges resolve via the subselect-by-nickname pattern.
  - 032 is re-application-safe (idempotency across the cross-product inserts).
  - role ids 2 (official) and 3 (staff) are the canonical keys asserted by
    the introspection we ran at design time.
"""
from __future__ import annotations

from x_monitor.store import Store


def _open(tmp_path):
    s = Store(tmp_path / "x.db", auto_migrate=True)
    return s


def test_migration_032_seeds_four_companies(tmp_path):
    """The 4 frontier companies are seeded with empty hq_country."""
    s = _open(tmp_path)
    try:
        rows = s._conn.execute(
            "SELECT nickname, display_name, display_name_en, display_name_zh_cn, hq_country "
            "FROM companies "
            "WHERE nickname IN ('openai','anthropic','google','xai') "
            "ORDER BY nickname"
        ).fetchall()
        assert len(rows) == 4
        nicknames = [r["nickname"] for r in rows]
        assert nicknames == ["anthropic", "google", "openai", "xai"]
        # display_name_en and zh_cn should be populated verbatim from the CSV.
        openai = next(r for r in rows if r["nickname"] == "openai")
        assert openai["display_name"] == "OpenAI"
        assert openai["display_name_en"] == "OpenAI"
        assert openai["display_name_zh_cn"] == "OpenAI"
        # hq_country left NULL by design (operator can backfill in a follow-up).
        for r in rows:
            assert r["hq_country"] is None
    finally:
        s.close()


def test_migration_032_seeds_five_brands(tmp_path):
    """GPT, Claude, Gemini, Gemma, Grok brands seeded with accent_color NULL."""
    s = _open(tmp_path)
    try:
        rows = s._conn.execute(
            "SELECT nickname, display_name FROM brands "
            "WHERE nickname IN ('gpt','claude','gemini','gemma','grok') "
            "ORDER BY nickname"
        ).fetchall()
        assert [r["nickname"] for r in rows] == ["claude", "gemini", "gemma", "gpt", "grok"]
        assert [r["display_name"] for r in rows] == ["Claude", "Gemini", "Gemma", "GPT", "Grok"]
        # All frontier brand rows leave accent_color NULL.
        accent = s._conn.execute(
            "SELECT accent_color FROM brands "
            "WHERE nickname IN ('gpt','claude','gemini','gemma','grok')"
        ).fetchall()
        assert all(r["accent_color"] is None for r in accent)
    finally:
        s.close()


def test_migration_032_brands_companies_edges(tmp_path):
    """brands_companies has exactly 5 edges (one per brand→company pair)."""
    s = _open(tmp_path)
    try:
        rows = s._conn.execute(
            "SELECT b.nickname AS brand, c.nickname AS company "
            "FROM brands_companies bc "
            "JOIN brands b    ON bc.brand_id   = b.id "
            "JOIN companies c ON bc.company_id = c.id "
            "WHERE c.nickname IN ('openai','anthropic','google','xai') "
            "ORDER BY b.nickname, c.nickname"
        ).fetchall()
        assert [(r["brand"], r["company"]) for r in rows] == [
            ("claude", "anthropic"),
            ("gemini", "google"),
            ("gemma", "google"),
            ("gpt", "openai"),
            ("grok", "xai"),
        ]
    finally:
        s.close()


def test_migration_032_seeds_sixteen_accounts(tmp_path):
    """All 16 operator-supplied X author_ids are present, no extras."""
    s = _open(tmp_path)
    try:
        expected_author_ids = {
            "4398626122", "1633874951508721686",
            "1605", "162124540", "825088493764407298",
            "1353836358901501952", "1943306828697550848",
            "874126509245476864", "33836629",
            "1806359170830172162", "1908326331609468928",
            "1482581556", "14130366", "284333988",
            "1720665183188922368", "44196397",
        }
        rows = s._conn.execute(
            "SELECT author_id, handle FROM accounts WHERE author_id IN ("
            + ",".join("?" for _ in expected_author_ids) + ")",
            list(expected_author_ids),
        ).fetchall()
        assert len(rows) == 16
        # Spot-check handle mapping for one OpenAI staff and one Google staff.
        by_id = {r["author_id"]: r["handle"] for r in rows}
        assert by_id["1605"] == "sama"
        assert by_id["1482581556"] == "demishassabis"
        assert by_id["4398626122"] == "OpenAI"
    finally:
        s.close()


def test_migration_032_brands_accounts_role_official(tmp_path):
    """9 brands_accounts rows with role_id=2 (official); cross-product per row."""
    s = _open(tmp_path)
    try:
        # Confirm role_id 2 is 'official' (regression: protects against a
        # future roles-table re-numbering silently breaking this migration's
        # semantics — verify the key, not just the count).
        role = s._conn.execute(
            "SELECT key FROM roles WHERE id = 2"
        ).fetchone()
        assert role is not None and role["key"] == "official"

        rows = s._conn.execute(
            "SELECT b.nickname AS brand, c.nickname AS company, "
            "       a.handle AS handle, ba.role_id "
            "FROM brands_accounts ba "
            "JOIN brands b    ON ba.brand_id    = b.id "
            "JOIN accounts a  ON ba.accounts_id = a.id "
            "JOIN brands_companies bc ON bc.brand_id = b.id "
            "JOIN companies c ON bc.company_id  = c.id "
            "WHERE ba.role_id = 2 "
            "  AND c.nickname IN ('openai','anthropic','google','xai') "
            "ORDER BY c.nickname, b.nickname, a.handle"
        ).fetchall()
        expected = [
            ("claude", "anthropic", "AnthropicAI"),
            ("claude", "anthropic", "claudeai"),
            ("gemini", "google",    "GeminiApp"),
            ("gemini", "google",    "googlegemma"),
            ("gemma",  "google",    "GeminiApp"),
            ("gemma",  "google",    "googlegemma"),
            ("gpt",    "openai",    "OpenAI"),
            ("gpt",    "openai",    "OpenAIDevs"),
            ("grok",   "xai",       "grok"),
        ]
        assert [(r["brand"], r["company"], r["handle"]) for r in rows] == expected
        assert all(r["role_id"] == 2 for r in rows)
    finally:
        s.close()


def test_migration_032_brands_accounts_role_staff(tmp_path):
    """12 brands_accounts rows with role_id=3 (staff); cross-product per row."""
    s = _open(tmp_path)
    try:
        role = s._conn.execute("SELECT key FROM roles WHERE id = 3").fetchone()
        assert role is not None and role["key"] == "staff"

        rows = s._conn.execute(
            "SELECT b.nickname AS brand, c.nickname AS company, "
            "       a.handle AS handle, ba.role_id "
            "FROM brands_accounts ba "
            "JOIN brands b    ON ba.brand_id    = b.id "
            "JOIN accounts a  ON ba.accounts_id = a.id "
            "JOIN brands_companies bc ON bc.brand_id = b.id "
            "JOIN companies c ON bc.company_id  = c.id "
            "WHERE ba.role_id = 3 "
            "  AND c.nickname IN ('openai','anthropic','google','xai') "
            "ORDER BY c.nickname, b.nickname, a.handle"
        ).fetchall()
        expected = [
            ("claude", "anthropic", "DarioAmodei"),
            ("claude", "anthropic", "karpathy"),
            ("gemini", "google",    "OfficialLoganK"),
            ("gemini", "google",    "demishassabis"),
            ("gemini", "google",    "sundarpichai"),
            ("gemma",  "google",    "OfficialLoganK"),
            ("gemma",  "google",    "demishassabis"),
            ("gemma",  "google",    "sundarpichai"),
            ("gpt",    "openai",    "gdb"),
            ("gpt",    "openai",    "polynoamial"),
            ("gpt",    "openai",    "sama"),
            ("grok",   "xai",       "elonmusk"),
        ]
        assert [(r["brand"], r["company"], r["handle"]) for r in rows] == expected
        assert all(r["role_id"] == 3 for r in rows)
    finally:
        s.close()


def test_migration_032_idempotent(tmp_path):
    """Re-opening the DB with 032 applied does not duplicate any seed row."""
    s1 = _open(tmp_path)
    s1.close()
    s2 = _open(tmp_path)
    try:
        companies = s2._conn.execute(
            "SELECT COUNT(*) FROM companies WHERE nickname IN "
            "('openai','anthropic','google','xai')"
        ).fetchone()[0]
        brands = s2._conn.execute(
            "SELECT COUNT(*) FROM brands WHERE nickname IN "
            "('gpt','claude','gemini','gemma','grok')"
        ).fetchone()[0]
        bc = s2._conn.execute(
            "SELECT COUNT(*) FROM brands_companies bc "
            "JOIN brands b ON bc.brand_id = b.id "
            "JOIN companies c ON bc.company_id = c.id "
            "WHERE c.nickname IN ('openai','anthropic','google','xai')"
        ).fetchone()[0]
        accounts = s2._conn.execute(
            "SELECT COUNT(*) FROM accounts WHERE author_id IN ("
            "'4398626122','1633874951508721686','1605','162124540','825088493764407298',"
            "'1353836358901501952','1943306828697550848','874126509245476864','33836629',"
            "'1806359170830172162','1908326331609468928','1482581556','14130366','284333988',"
            "'1720665183188922368','44196397')"
        ).fetchone()[0]
        ba_official = s2._conn.execute(
            "SELECT COUNT(*) FROM brands_accounts WHERE role_id = 2"
        ).fetchone()[0]
        ba_staff = s2._conn.execute(
            "SELECT COUNT(*) FROM brands_accounts WHERE role_id = 3"
        ).fetchone()[0]
        assert companies == 4
        assert brands == 5
        assert bc == 5
        assert accounts == 16
        assert ba_official == 9
        assert ba_staff == 12
    finally:
        s2.close()


def test_migration_032_ledger_records_version(tmp_path):
    """The _migrations ledger records version 32 after auto-migrate."""
    s = _open(tmp_path)
    try:
        applied = {r[0] for r in s._conn.execute("SELECT version FROM _migrations").fetchall()}
        assert 32 in applied
    finally:
        s.close()
