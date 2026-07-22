"""U5 tests for the posts_brands_discourse partial-row write path.

Plan 2026-07-13-002 U5: when the LLM emits a discourse_key value
not in the discourse_keys lookup table (KTD5 dead-letter), the
china_nationalism / us_nationalism pair the LLM also emitted
should still land in the DB as a partial row (discourse_key=NULL,
act_id=0, nationalism pair populated). The dead-letter JSONL still
captures the failed key for human review.

The migration 038 changes posts_brands_discourse to allow NULL
discourse_key and act_id in 0..99 (0 = KTD5 partial sentinel).

These tests pin the partial-row write behavior so the KTD5
recovery doesn't regress back to "drop the whole row."
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from x_monitor.store import Store


@pytest.fixture
def store_with_brands(tmp_path: Path) -> Store:
    """Create a fresh Store against an empty tmp DB. Migration 004
    seeds the brands table (including `minimax` and `glm`); the
    fixture relies on those seeds and does NOT re-insert them."""
    db = tmp_path / "test.db"
    s = Store(db)
    return s


def test_ktd5_dead_letter_still_writes_partial_row_with_nationalism(
    store_with_brands: Store,
    tmp_path: Path,
) -> None:
    """When the LLM emits an unknown discourse_key, the partial
    row should persist with discourse_key=NULL, act_id=0, and the
    nationalism pair populated."""
    s = store_with_brands
    # Insert a post so post_id resolves.
    s._conn.execute(
        "INSERT INTO posts (tweet_id, text, lang) VALUES (?, ?, ?)",
        ("t1", "China is moving to wall off its top open source AI models", "en"),
    )
    s._conn.commit()

    # LLM output: unknown discourse_key + valid nationalism pair.
    # Migration 038 must have been applied for the partial-row write
    # to succeed (discourse_key NULLable, act_id=0 valid).
    rows = [{
        "tweet_id": "t1",
        "brand_id": "minimax",
        "discourse_key": "some_future_key_not_in_lookup",  # KTD5 trigger
        "act_id": 1,  # ignored for partial-row path (overridden to 0)
        "china_nationalism": "none",
        "us_nationalism": "none",
    }]
    n = s.bulk_insert_post_brand_discourse(rows)
    assert n == 1, f"partial-row write should count as 1 row, got {n}"

    # Verify the partial row landed.
    persisted = s._conn.execute(
        """
        SELECT pbd.discourse_key, pbd.act_id, pbd.china_nationalism,
               pbd.us_nationalism
        FROM posts_brands_discourse pbd
        JOIN posts p ON p.id = pbd.post_id
        WHERE p.tweet_id = ?
        """,
        ("t1",),
    ).fetchall()
    assert len(persisted) == 1
    discourse_key, act_id, cn, un = persisted[0]
    assert discourse_key is None, (
        f"KTD5 partial row must have discourse_key=NULL, got {discourse_key}"
    )
    assert act_id == 0, (
        f"KTD5 partial row must have act_id=0 (sentinel), got {act_id}"
    )
    assert cn is not None and un is not None, (
        f"nationalism pair must persist on partial row, got "
        f"china={cn} us={un}"
    )


def test_ktd5_dead_letter_uncategorized_key_writes_partial_row(
    store_with_brands: Store,
) -> None:
    """The `uncategorized` sentinel value (KTD5's primary trigger)
    should also take the partial-row path — the LLM emitting
    `uncategorized` is the most common KTD5 case in the U3 run."""
    s = store_with_brands
    s._conn.execute(
        "INSERT INTO posts (tweet_id, text, lang) VALUES (?, ?, ?)",
        ("t2", "policy discussion of open source AI", "en"),
    )
    s._conn.commit()
    rows = [{
        "tweet_id": "t2",
        "brand_id": "glm",
        "discourse_key": "uncategorized",  # the canonical KTD5 trigger
        "act_id": 1,
        "china_nationalism": "none",
        "us_nationalism": "none",
    }]
    n = s.bulk_insert_post_brand_discourse(rows)
    assert n == 1, "uncategorized should still take partial-row path"

    persisted = s._conn.execute(
        "SELECT discourse_key, act_id FROM posts_brands_discourse pbd "
        "JOIN posts p ON p.id = pbd.post_id WHERE p.tweet_id = ?",
        ("t2",),
    ).fetchall()
    assert persisted[0][0] is None
    assert persisted[0][1] == 0


def test_valid_discourse_key_still_takes_full_row_path(
    store_with_brands: Store,
) -> None:
    """Regression guard: a valid discourse_key (one that IS in
    discourse_keys) must still take the original full-row write
    path, NOT the partial-row path."""
    s = store_with_brands
    # `dunk_yingyang` (id=3) is already seeded by migration 026.
    # No manual insert needed; the fixture relies on the seed.
    s._conn.execute(
        "INSERT INTO posts (tweet_id, text, lang) VALUES (?, ?, ?)",
        ("t3", "dunk on the model", "en"),
    )
    s._conn.commit()
    rows = [{
        "tweet_id": "t3",
        "brand_id": "minimax",
        "discourse_key": "dunk_yingyang",  # valid FK target
        "act_id": 1,
        "china_nationalism": "none",
        "us_nationalism": "none",
    }]
    n = s.bulk_insert_post_brand_discourse(rows)
    assert n == 1

    persisted = s._conn.execute(
        "SELECT discourse_key, act_id FROM posts_brands_discourse pbd "
        "JOIN posts p ON p.id = pbd.post_id WHERE p.tweet_id = ?",
        ("t3",),
    ).fetchall()
    assert persisted[0][0] == 3, (
        f"valid discourse_key must write the FK id (dunk_yingyang=3), "
        f"not NULL; got {persisted[0][0]}"
    )
    assert persisted[0][1] == 1, (
        f"valid discourse_key must use the caller's act_id, not "
        f"the KTD5 sentinel 0; got {persisted[0][1]}"
    )


def test_ktd5_dead_letter_still_emits_to_jsonl(
    store_with_brands: Store,
    tmp_path: Path,
) -> None:
    """The dead-letter JSONL must STILL receive the failed key —
    partial-row write is additive, not a replacement for human-
    visible dead-letter capture."""
    s = store_with_brands
    # Dead-letter path is <db_path.parent>/runs/<YYYY-MM-DD>/enum_dead_letter.jsonl
    runs_dir = tmp_path / "runs"
    day = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).strftime("%Y-%m-%d")
    dead_letter = runs_dir / day / "enum_dead_letter.jsonl"

    s._conn.execute(
        "INSERT INTO posts (tweet_id, text, lang) VALUES (?, ?, ?)",
        ("t4", "policy", "en"),
    )
    s._conn.commit()
    rows = [{
        "tweet_id": "t4",
        "brand_id": "minimax",
        "discourse_key": "some_future_key",
        "act_id": 1,
        "china_nationalism": "none",
        "us_nationalism": "none",
    }]
    s.bulk_insert_post_brand_discourse(rows)
    # Dead-letter file must have a record for the failed key.
    assert dead_letter.exists(), (
        f"dead-letter JSONL must still be written for human review; "
        f"looked for {dead_letter}"
    )
    content = dead_letter.read_text().strip()
    assert content, "dead-letter JSONL is empty"
    rec = json.loads(content.splitlines()[-1])
    assert rec.get("value") == "some_future_key"
    assert rec.get("family") == "discourse"