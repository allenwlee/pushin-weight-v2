"""Translator extension for registry rows (Unit 4).

Plan: docs/plans/2026-06-23-001-feat-i18n-locale-columns-plan.md (Unit 4).

Verifies:
- `Store.get_registry_missing_translations` finds rows where the target
  column is NULL and respects limit + closed-set validation.
- `Store.bulk_update_registry_translations` writes back en/zh_cn columns
  via closed-set table/column interpolation; raises on invalid combos.
- `translate_registry_rows` returns one result per input row in order,
  with proper-noun preservation prompt (rule 7), batch_size honored.
- Dry-run returns stub rows without calling the LLM.
- 5xx retry exhausts → `translation_failed: True` per row, batch continues.
- End-to-end with FakeClaudeClient populates the DB.
"""

import json
from typing import Any

import pytest


# --- Fake client ---------------------------------------------------------


class FakeClaudeClient:
    """Captures all LLM calls and returns scripted responses.

    `responses`: list of dicts to return in order. Each call consumes
    the next entry. If the list is exhausted, raises IndexError (tests
    use this to assert "no more calls expected").
    """

    def __init__(self, responses: list[dict[str, Any]] | None = None,
                 raise_after: int | None = None):
        self.responses = list(responses or [])
        self.raise_after = raise_after
        self.calls: list[dict[str, Any]] = []
        self._n_calls = 0

    def messages_create(self, **kwargs) -> dict[str, Any]:
        self.calls.append(kwargs)
        self._n_calls += 1
        if self.raise_after is not None and self._n_calls > self.raise_after:
            raise RuntimeError("fake: simulated 5xx")
        if not self.responses:
            raise IndexError(
                f"FakeClaudeClient: no scripted response for call #{self._n_calls}"
            )
        return self.responses.pop(0)


# --- get_registry_missing_translations ----------------------------------


def test_get_registry_missing_translations_brands_display_name_en(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # brands are seeded by migration 004 — display_name_en is NULL
        # for all of them at this point (no translator has run).
        rows = s.get_registry_missing_translations(
            "brands", "display_name", "en",
        )
        assert len(rows) >= 1
        for r in rows:
            assert "pk" in r
            assert r["source"] is not None
            assert r["col_en"] is None  # missing
    finally:
        s.close()


def test_get_registry_missing_translations_respects_limit(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows = s.get_registry_missing_translations(
            "brands", "display_name", "en", limit=2,
        )
        assert len(rows) == 2
    finally:
        s.close()


def test_get_registry_missing_translations_rejects_invalid_table(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        with pytest.raises(ValueError, match="table must be one of"):
            s.get_registry_missing_translations(
                "not_a_table", "display_name", "en",
            )
    finally:
        s.close()


def test_get_registry_missing_translations_rejects_invalid_column(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        with pytest.raises(ValueError, match="column must be one of"):
            s.get_registry_missing_translations(
                "brands", "not_a_column", "en",
            )
    finally:
        s.close()


def test_get_registry_missing_translations_rejects_invalid_locale(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        with pytest.raises(ValueError, match="locale must be one of"):
            s.get_registry_missing_translations(
                "brands", "display_name", "fr",
            )
    finally:
        s.close()


def test_get_registry_missing_translations_rejects_bio_on_non_accounts(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        with pytest.raises(ValueError, match="'bio' is only valid for"):
            s.get_registry_missing_translations(
                "brands", "bio", "en",
            )
    finally:
        s.close()


def test_get_registry_missing_translations_excludes_null_source(tmp_path):
    """If the source column is NULL, the row is not included even if
    the locale column is also NULL — there's nothing to translate.

    brands.display_name is NOT NULL by schema, so we test this via the
    `accounts.bio` path (bio is nullable).
    """
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # Insert an account with NULL bio (no bio yet).
        s._conn.execute(
            "INSERT INTO accounts (author_id, handle) VALUES (?, ?)",
            ("ghost_acct", "u_ghost"),
        )
        rows = s.get_registry_missing_translations(
            "accounts", "bio", "en",
        )
        pks = [r["pk"] for r in rows]
        assert "ghost_acct" not in pks
    finally:
        s.close()


# --- bulk_update_registry_translations ----------------------------------


def test_bulk_update_registry_translations_writes_back(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        n = s.bulk_update_registry_translations(
            "brands", "display_name",
            [
                {"pk": "minimax", "col_en": "MiniMax AI Co.",
                 "col_zh_cn": "MiniMax AI 公司"},
            ],
        )
        assert n == 1
        row = s._conn.execute(
            "SELECT display_name_en, display_name_zh_cn FROM brands "
            "WHERE brand_id = ?",
            ("minimax",),
        ).fetchone()
        assert row["display_name_en"] == "MiniMax AI Co."
        assert row["display_name_zh_cn"] == "MiniMax AI 公司"
    finally:
        s.close()


def test_bulk_update_registry_translations_empty_input_is_noop(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        assert s.bulk_update_registry_translations("brands", "display_name", []) == 0
    finally:
        s.close()


def test_bulk_update_registry_translations_missing_pk_raises(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        with pytest.raises(KeyError, match="row missing 'pk'"):
            s.bulk_update_registry_translations(
                "brands", "display_name",
                [{"col_en": "x"}],  # no pk
            )
    finally:
        s.close()


def test_bulk_update_registry_translations_rejects_bio_on_non_accounts(tmp_path):
    from x_monitor.store import Store

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        with pytest.raises(ValueError, match="'bio' is only valid for"):
            s.bulk_update_registry_translations(
                "brands", "bio", [{"pk": "minimax"}],
            )
    finally:
        s.close()


# --- translate_registry_rows: prompt + dry-run + retry ------------------


def test_translate_registry_rows_dry_run_returns_stubs(tmp_path):
    from x_monitor.translator import translate_registry_rows

    client = FakeClaudeClient()  # no responses; should not be called
    rows = [
        {"pk": "minimax", "source": "MiniMax AI"},
        {"pk": "qwen", "source": "Qwen"},
    ]
    result = translate_registry_rows(
        rows, ["en", "zh_cn"], client,
        column_label="brand display name", dry_run=True,
    )
    assert len(result) == 2
    for r in result:
        assert r["dry_run"] is True
        assert r["col_en"] is None
        assert r["col_zh_cn"] is None
    # No LLM calls made.
    assert client.calls == []


def test_translate_registry_rows_happy_path(tmp_path):
    """One batch of 2 rows, single LLM call returns valid response."""
    from x_monitor.translator import translate_registry_rows

    response = {
        "results": [
            {"pk": "minimax", "col_en": "MiniMax AI",
             "col_zh_cn": "MiniMax AI 公司", "noop_en": False, "noop_zh": False},
            {"pk": "qwen", "col_en": "Qwen",
             "col_zh_cn": "通义千问", "noop_en": False, "noop_zh": False},
        ],
    }
    client = FakeClaudeClient([response])
    rows = [
        {"pk": "minimax", "source": "MiniMax AI"},
        {"pk": "qwen", "source": "Qwen"},
    ]
    result = translate_registry_rows(
        rows, ["en", "zh_cn"], client,
        column_label="brand display name",
    )
    assert len(result) == 2
    assert result[0]["col_zh_cn"] == "MiniMax AI 公司"
    assert result[1]["col_zh_cn"] == "通义千问"
    # Exactly one LLM call.
    assert len(client.calls) == 1


def test_translate_registry_rows_noop_on_english_source(tmp_path):
    """When the source is already English, the LLM is expected to set
    col_en == source and noop_en=true."""
    from x_monitor.translator import translate_registry_rows

    response = {
        "results": [
            {"pk": "minimax", "col_en": "MiniMax AI",
             "col_zh_cn": "MiniMax AI 公司", "noop_en": True, "noop_zh": False},
        ],
    }
    client = FakeClaudeClient([response])
    rows = [{"pk": "minimax", "source": "MiniMax AI"}]
    result = translate_registry_rows(
        rows, ["en", "zh_cn"], client,
        column_label="brand display name",
    )
    assert result[0]["noop_en"] is True


def test_translate_registry_rows_respects_batch_size(tmp_path):
    """batch_size=2 + 5 rows = 3 LLM calls (2, 2, 1)."""
    from x_monitor.translator import translate_registry_rows

    def _make_response(pks):
        return {
            "results": [
                {"pk": pk, "col_en": f"en_{pk}", "col_zh_cn": f"zh_{pk}",
                 "noop_en": False, "noop_zh": False}
                for pk in pks
            ],
        }

    responses = [
        _make_response(["a", "b"]),
        _make_response(["c", "d"]),
        _make_response(["e"]),
    ]
    client = FakeClaudeClient(responses)
    rows = [{"pk": p, "source": p} for p in ["a", "b", "c", "d", "e"]]
    result = translate_registry_rows(
        rows, ["en", "zh_cn"], client,
        column_label="brand display name", batch_size=2,
    )
    assert len(result) == 5
    assert len(client.calls) == 3
    # First call's prompt should reference only a, b; not c, d, e.
    first_prompt = client.calls[0]["messages"][0]["content"]
    assert '"pk": "a"' in first_prompt
    assert '"pk": "c"' not in first_prompt


def test_translate_registry_rows_empty_input_is_noop(tmp_path):
    from x_monitor.translator import translate_registry_rows

    client = FakeClaudeClient()
    assert translate_registry_rows(
        [], ["en", "zh_cn"], client,
        column_label="x",
    ) == []
    assert client.calls == []


def test_translate_registry_rows_5xx_exhausts_to_failed(tmp_path):
    """When the LLM raises on every retry, the row is marked failed and
    the batch continues."""
    from x_monitor.translator import translate_registry_rows

    client = FakeClaudeClient(raise_after=0)  # always raise
    rows = [
        {"pk": "minimax", "source": "MiniMax AI"},
        {"pk": "qwen", "source": "Qwen"},
    ]
    result = translate_registry_rows(
        rows, ["en", "zh_cn"], client,
        column_label="brand display name",
    )
    assert len(result) == 2
    for r in result:
        assert r["translation_failed"] is True
        assert r["col_en"] is None
        assert r["col_zh_cn"] is None


def test_translate_registry_rows_malformed_response_marks_failed(tmp_path):
    """When the LLM returns a response that doesn't match the schema,
    the rows are marked failed and the batch continues."""
    from x_monitor.translator import translate_registry_rows

    client = FakeClaudeClient([{"results": "not a list"}])
    rows = [{"pk": "minimax", "source": "MiniMax AI"}]
    result = translate_registry_rows(
        rows, ["en", "zh_cn"], client,
        column_label="brand display name",
    )
    assert result[0]["translation_failed"] is True


def test_translate_registry_rows_prompt_includes_rule_7_proper_nouns(tmp_path):
    """The prompt should include rule 7 about preserving proper nouns."""
    from x_monitor.translator import (
        build_registry_translation_prompt, translate_registry_rows,
    )

    # Sanity check the standalone prompt builder.
    prompt = build_registry_translation_prompt(
        [{"pk": "minimax", "source": "MiniMax AI"}],
        ["en", "zh_cn"],
        "brand display name",
    )
    assert "proper nouns" in prompt.lower() or "VERBATIM" in prompt
    assert "MiniMax AI" in prompt
    assert "brand display name" in prompt

    # Also verify rule 7 appears in the actual translator call.
    response = {
        "results": [
            {"pk": "minimax", "col_en": "x", "col_zh_cn": "y",
             "noop_en": False, "noop_zh": False},
        ],
    }
    client = FakeClaudeClient([response])
    translate_registry_rows(
        [{"pk": "minimax", "source": "MiniMax AI"}],
        ["en", "zh_cn"], client,
        column_label="brand display name",
        brand_names=["MiniMax AI", "Haiku 4.5"],
    )
    sent_prompt = client.calls[0]["messages"][0]["content"]
    assert "VERBATIM" in sent_prompt
    assert "MiniMax AI" in sent_prompt  # in brand_names block


# --- end-to-end with Store ----------------------------------------------


def test_end_to_end_brands_display_name_translated_to_db(tmp_path):
    """Populate 2 brands via the translator; verify the DB rows updated."""
    from x_monitor.store import Store
    from x_monitor.translator import translate_registry_rows

    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        rows_missing = s.get_registry_missing_translations(
            "brands", "display_name", "en", limit=2,
        )
        # Build the translator input.
        translator_rows = [
            {"pk": str(r["pk"]), "source": r["source"]}
            for r in rows_missing
        ]
        response = {
            "results": [
                {"pk": r["pk"], "col_en": f"EN_{r['pk']}",
                 "col_zh_cn": f"ZH_{r['pk']}",
                 "noop_en": False, "noop_zh": False}
                for r in translator_rows
            ],
        }
        client = FakeClaudeClient([response])
        results = translate_registry_rows(
            translator_rows, ["en", "zh_cn"], client,
            column_label="brand display name",
        )
        # Write back.
        update_rows = [
            {"pk": r["pk"], "col_en": r["col_en"], "col_zh_cn": r["col_zh_cn"]}
            for r in results
        ]
        n = s.bulk_update_registry_translations(
            "brands", "display_name", update_rows,
        )
        assert n == 2

        # Re-query missing → should be 0 for the first 2 brands.
        rows_after = s.get_registry_missing_translations(
            "brands", "display_name", "en", limit=2,
        )
        assert len(rows_after) == 0 or all(
            r["pk"] not in {tr["pk"] for tr in translator_rows}
            for r in rows_after
        )
    finally:
        s.close()