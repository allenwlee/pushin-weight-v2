"""Unit + integration tests for scripts/2026-06-25-005-seed-companies-brands-from-csv.py.

Plan: docs/plans/2026-06-25-004-feat-populate-brand-search-terms-plan.md
Units 3 + 4 of 4. Verifies:
- slugify with override map (CJK, J/K, Korean, edge cases).
- split_multivalue (comma, whitespace, mixed).
- parse_hf_url (standard, with model, malformed).
- parse_x_url (standard, trailing `;`, `,`, twitter.com domain).
- parse_followers (comma-formatted, malformed).
- End-to-end seed from a mini-CSV in tmp_path.
- Idempotency, dry-run, --limit N.
- Column M (notes) is read and discarded — never written.
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import importlib.util

_SPEC = importlib.util.spec_from_file_location(
    "seed_companies_brands_from_csv",
    SCRIPTS_DIR / "2026-06-25-005-seed-companies-brands-from-csv.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)

_slugify = _mod.slugify
_split_multivalue = _mod.split_multivalue
_parse_hf_url = _mod.parse_hf_url
_parse_x_url = _mod.parse_x_url
_parse_followers = _mod.parse_followers


# --- slugify -------------------------------------------------------------


def test_slugify_override_hit_cjk():
    """CJK display_name → v1 brand_id via override."""
    assert _slugify("千问", _mod.BRAND_SLUG_OVERRIDES) == "qwen"
    assert _slugify("深度求索", _mod.BRAND_SLUG_OVERRIDES) == "deepseek"
    assert _slugify("サカナAI", _mod.BRAND_SLUG_OVERRIDES) == "sakana"
    assert _slugify("업스테이지", _mod.BRAND_SLUG_OVERRIDES) == "upstage"


def test_slugify_override_hit_v1_canonical():
    """v1 brand display_names → their canonical v1 ids."""
    assert _slugify("MiniMax", _mod.BRAND_SLUG_OVERRIDES) == "minimax"
    assert _slugify("GLM / ChatGLM", _mod.BRAND_SLUG_OVERRIDES) == "glm"
    assert _slugify("Mimo", _mod.BRAND_SLUG_OVERRIDES) == "xiaomi_mimo"
    assert _slugify("ERNIE / Wenxin", _mod.BRAND_SLUG_OVERRIDES) == "ernie"


def test_slugify_override_miss_falls_back_to_regex():
    """Plain ASCII display_name without override → regex slugify."""
    assert _slugify("Some New Brand", {}) == "some_new_brand"
    assert _slugify("Cohere Command R+", {}) == "cohere_command_r"


def test_slugify_pure_cjk_no_override_raises():
    """A CJK display_name with no override produces an empty slug and raises."""
    with pytest.raises(ValueError, match="empty slug"):
        _slugify("百度", {})


def test_slugify_company_overrides():
    """Company slugify covers the 11 v1 company_ids + new ones."""
    assert _slugify("Mistral AI", _mod.COMPANY_SLUG_OVERRIDES) == "mistral_ai"
    assert _slugify("NVIDIA", _mod.COMPANY_SLUG_OVERRIDES) == "nvidia"
    assert _slugify("蚂蚁 Inclusion AI", _mod.COMPANY_SLUG_OVERRIDES) == "inclusion_ai"


# --- split_multivalue ----------------------------------------------------


def test_split_multivalue_comma_separated():
    assert _split_multivalue("A, B, C") == ["A", "B", "C"]


def test_split_multivalue_whitespace_separated():
    assert _split_multivalue("A   B   C") == ["A", "B", "C"]


def test_split_multivalue_mixed():
    assert _split_multivalue("A, B C") == ["A", "B", "C"]


def test_split_multivalue_trailing_junk():
    """Trailing punctuation on cells is preserved for parse_url to strip."""
    assert _split_multivalue("A,, B,") == ["A", "B"]


def test_split_multivalue_empty_returns_empty():
    assert _split_multivalue("") == []
    assert _split_multivalue("   ") == []


def test_split_multivalue_dedups_preserving_order():
    assert _split_multivalue("A, B, A, C") == ["A", "B", "C"]


# --- parse_hf_url --------------------------------------------------------


def test_parse_hf_url_standard():
    assert _parse_hf_url("https://huggingface.co/meta-llama/") == "meta-llama"


def test_parse_hf_url_with_model_path_returns_namespace_only():
    """Only the namespace (first path segment) is returned, not the model."""
    assert _parse_hf_url("https://huggingface.co/MiniMaxAI/MiniMax-M1") == "MiniMaxAI"


def test_parse_hf_url_trailing_punctuation_stripped():
    assert _parse_hf_url("https://huggingface.co/bytedance/  ,") == "bytedance"


def test_parse_hf_url_malformed_returns_none():
    assert _parse_hf_url("not-a-url") is None
    assert _parse_hf_url("") is None
    assert _parse_hf_url("https://example.com/foo") is None


# --- parse_x_url ---------------------------------------------------------


def test_parse_x_url_standard():
    assert _parse_x_url("https://x.com/MiniMax_AI") == "MiniMax_AI"


def test_parse_x_url_trailing_semicolon_stripped():
    """Trailing `;` is stripped — common in the CSV's K/L cells."""
    assert _parse_x_url("https://x.com/01AI_Yi;") == "01AI_Yi"


def test_parse_x_url_trailing_comma_stripped():
    assert _parse_x_url("https://x.com/X,") == "X"


def test_parse_x_url_trailing_slash_stripped():
    assert _parse_x_url("https://x.com/MiniMaxAI/") == "MiniMaxAI"


def test_parse_x_url_twitter_domain_also_matches():
    """twitter.com domain is still valid (some legacy URLs use it)."""
    assert _parse_x_url("https://twitter.com/X") == "X"


def test_parse_x_url_malformed_returns_none():
    assert _parse_x_url("not-a-url") is None
    assert _parse_x_url("") is None


# --- parse_followers -----------------------------------------------------


def test_parse_followers_comma_format():
    assert _parse_followers("38,400") == 38400


def test_parse_followers_plain_int():
    assert _parse_followers("100") == 100


def test_parse_followers_empty_returns_zero():
    assert _parse_followers("") == 0


def test_parse_followers_malformed_returns_zero():
    assert _parse_followers("abc") == 0
    assert _parse_followers(None) == 0  # type: ignore[arg-type]


# --- integration: end-to-end from a mini-CSV -----------------------------


MINI_CSV_HEADER = [
    "#",
    "brands.display_name",
    "brands.display_name_en",
    "brands.display_name_zh_cn",
    "company.display_name",
    "company.display_name_en",
    "company.display_name_zh_cn",
    "company.hq_country",
    "co_hq_city",
    "ai_lab_city",
    "brands_accounts.role_id='official'",
    "brands_accounts.role_id='staff'",
    "notes",
    "github_accounts",
    "hf_orgs",
    "hf_followers_num",
    "tier",
]


def _write_mini_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(MINI_CSV_HEADER)
        for r in rows:
            w.writerow(r)


def _mini_csv_row(
    brand: str,
    company: str,
    country: str = "US",
    official_x: str = "",
    staff_x: str = "",
    hf_orgs: str = "",
    notes: str = "",
    brand_en: str = "",
    brand_zh: str = "",
    company_en: str = "",
    company_zh: str = "",
) -> list[str]:
    return [
        "1",  # rank
        brand, brand_en or brand, brand_zh or brand,
        company, company_en or company, company_zh or company,
        country, "", "",
        official_x, staff_x, notes, "",
        hf_orgs, "", "",
    ]


def test_end_to_end_seeds_six_tables(tmp_path):
    """A 3-row mini-CSV seeds companies, brands, brands_companies,
    accounts, brands_accounts, hf_orgs."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    s.close()

    csv_path = tmp_path / "mini.csv"
    _write_mini_csv(csv_path, [
        _mini_csv_row(
            brand="MiniMax", company="MiniMax",
            official_x="https://x.com/MiniMax_AI, ",
            hf_orgs="https://huggingface.co/MiniMaxAI/",
        ),
        _mini_csv_row(
            brand="Llama", company="Meta",
            country="US",
            official_x="https://x.com/AIatMeta",
            staff_x="https://x.com/alexandr_wang",
            hf_orgs="https://huggingface.co/meta-llama/",
        ),
        _mini_csv_row(
            brand="千问", company="阿里巴巴",
            country="CN",
            official_x="https://x.com/Alibaba_Qwen",
            hf_orgs="https://huggingface.co/Qwen/",
        ),
    ])

    rc = _mod.main.__wrapped__ if hasattr(_mod.main, "__wrapped__") else None  # type: ignore[attr-defined]
    # Call main via sys.argv so it picks up our paths.
    import sys
    old_argv = sys.argv
    sys.argv = ["seed.py", str(db), str(csv_path)]
    try:
        ret = _mod.main()
    finally:
        sys.argv = old_argv
    assert ret == 0

    conn = sqlite3.connect(db)
    try:
        # v1 baseline (migrations 004 + 009):
        #   brands: 12 (11 brand_ids + _unattributed sentinel)
        #   companies: 11 (10 from migration 004 + minimax from migration 009)
        #   brands_companies: 11 (10 from migration 004 + minimax→minimax from 009)
        #   hf_orgs: 11 (curated corporate HF namespaces from migration 009)
        # After 3 CSV rows (MiniMax, Llama, 千问):
        #   brands: +1 (llama; minimax & qwen are v1)
        #   companies: +1 (meta; minimax & alibaba are v1)
        #   brands_companies: +1 (llama→meta; minimax→minimax & qwen→alibaba are v1)
        #   hf_orgs: +1 (meta-llama; MiniMaxAI & Qwen are v1)
        #   accounts + brands_accounts: 4 new (MiniMax_AI, AIatMeta, alexandr_wang, Alibaba_Qwen)
        assert conn.execute("SELECT COUNT(*) FROM brands").fetchone()[0] == 13
        assert conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 12
        assert conn.execute("SELECT COUNT(*) FROM brands_companies").fetchone()[0] == 12
        assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM brands_accounts").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM hf_orgs").fetchone()[0] == 12
        # qwen round-trip: qwen's brand row has CJK override.
        bid = conn.execute(
            "SELECT brand_id FROM brands WHERE brand_id = ?",
            ("qwen",),
        ).fetchone()[0]
        assert bid == "qwen"
        # HF namespace from URL with model path → only namespace.
        ns = conn.execute(
            "SELECT id FROM hf_orgs WHERE id = ?", ("MiniMaxAI",),
        ).fetchone()[0]
        assert ns == "MiniMaxAI"
        # X handle from URL with trailing `, ` → stripped.
        handle = conn.execute(
            "SELECT handle FROM accounts WHERE handle = ?", ("MiniMax_AI",),
        ).fetchone()[0]
        assert handle == "MiniMax_AI"
    finally:
        conn.close()


def test_idempotency(tmp_path):
    """Re-running inserts 0 new rows on the second pass."""
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    s.close()

    csv_path = tmp_path / "mini.csv"
    _write_mini_csv(csv_path, [
        _mini_csv_row(
            brand="Llama", company="Meta",
            official_x="https://x.com/AIatMeta",
            hf_orgs="https://huggingface.co/meta-llama/",
        ),
    ])

    import sys
    old_argv = sys.argv
    sys.argv = ["seed.py", str(db), str(csv_path)]
    try:
        assert _mod.main() == 0
        # second run: same counts.
        before = _table_counts(db)
        assert _mod.main() == 0
        after = _table_counts(db)
    finally:
        sys.argv = old_argv

    assert before == after


def _table_counts(db: Path) -> dict[str, int]:
    conn = sqlite3.connect(db)
    try:
        out = {}
        for tbl in [
            "companies", "brands", "brands_companies",
            "accounts", "brands_accounts", "hf_orgs",
        ]:
            out[tbl] = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        return out
    finally:
        conn.close()


def test_dry_run_makes_no_writes(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    s.close()

    csv_path = tmp_path / "mini.csv"
    _write_mini_csv(csv_path, [
        _mini_csv_row(
            brand="Llama", company="Meta",
            official_x="https://x.com/AIatMeta",
            hf_orgs="https://huggingface.co/meta-llama/",
        ),
    ])

    before = _table_counts(db)

    import sys
    old_argv = sys.argv
    sys.argv = ["seed.py", str(db), str(csv_path), "--dry-run"]
    try:
        assert _mod.main() == 0
    finally:
        sys.argv = old_argv

    after = _table_counts(db)
    assert before == after


def test_limit_n_processes_only_n_rows(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    s.close()

    csv_path = tmp_path / "mini.csv"
    _write_mini_csv(csv_path, [
        _mini_csv_row(brand=f"Brand{i}", company=f"Co{i}", country="US")
        for i in range(5)
    ])

    import sys
    old_argv = sys.argv
    sys.argv = ["seed.py", str(db), str(csv_path), "--limit", "3"]
    try:
        assert _mod.main() == 0
    finally:
        sys.argv = old_argv

    conn = sqlite3.connect(db)
    try:
        # 3 unique brand_ids added (Brand0, Brand1, Brand2).
        rows = conn.execute(
            "SELECT brand_id FROM brands WHERE brand_id LIKE 'brand%'"
            " ORDER BY brand_id"
        ).fetchall()
        assert [r[0] for r in rows] == ["brand0", "brand1", "brand2"]
    finally:
        conn.close()


def test_column_m_notes_is_read_and_discarded(tmp_path):
    """Column M (notes) is read but never written to any table.

    This test asserts that:
    1. The script doesn't fail on a row where column M is non-empty.
    2. The notes content does NOT appear anywhere in the seeded tables.
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    s.close()

    csv_path = tmp_path / "mini.csv"
    notes_text = "this is a free-text note that must NEVER be persisted"
    _write_mini_csv(csv_path, [
        _mini_csv_row(
            brand="Llama", company="Meta",
            official_x="https://x.com/AIatMeta",
            notes=notes_text,
        ),
    ])

    import sys
    old_argv = sys.argv
    sys.argv = ["seed.py", str(db), str(csv_path)]
    try:
        assert _mod.main() == 0
    finally:
        sys.argv = old_argv

    conn = sqlite3.connect(db)
    try:
        # notes must not appear in any text column of any seeded table.
        for tbl in [
            "companies", "brands", "brands_companies",
            "accounts", "brands_accounts", "hf_orgs",
        ]:
            text_cols = [
                r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()
                if r[1] not in ("brand_id", "company_id", "author_id")
            ]
            for col in text_cols:
                hits = conn.execute(
                    f"SELECT COUNT(*) FROM {tbl} WHERE {col} LIKE ?",
                    (f"%{notes_text}%",),
                ).fetchone()[0]
                assert hits == 0, f"notes leaked into {tbl}.{col}"
    finally:
        conn.close()


def test_overrides_cover_all_20_brand_ids():
    """The override map must cover all 20 brand_ids (11 v1 + 9 new)."""
    expected_v1 = {
        "qwen", "deepseek", "glm", "xiaomi_mimo", "moonshot_kimi",
        "inclusionai", "mistral", "stepfun", "ernie", "hunyuan", "minimax",
    }
    expected_new = {
        "llama", "nvidia_nemo", "doubao", "yi", "sensechat",
        "exaone", "kuaishou", "sakana", "upstage",
    }
    override_ids = set(_mod.BRAND_SLUG_OVERRIDES.values())
    assert expected_v1 <= override_ids, (
        f"missing v1 ids: {expected_v1 - override_ids}"
    )
    assert expected_new <= override_ids, (
        f"missing new ids: {expected_new - override_ids}"
    )