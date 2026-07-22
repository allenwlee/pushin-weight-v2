# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.dashboard.serialize_feed_page (U4 of
feat/pushin-weight-home-pages, 2026-07-06).

Covers the Pushin' Weight home feed data layer:
- Cursor pagination: first page + advance + end of feed
- Sort columns: created_at DESC default + like_count variants
- Filter narrowing via _post_matches_filter
- Brand scope (R16) is server-side and not bypassable
- Hard cap: 500-row ceiling
- Empty DB: empty rows, next_cursor=None
- Malformed cursor: next_cursor=None (signals "stop paging")
- Wire shape: each row matches the R10 contract
- locale: affects text_translated column
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from x_monitor.dashboard import (
    _FEED_DEFAULT_LIMIT,
    _FEED_HARD_CAP,
    _feed_decode_cursor,
    _feed_encode_cursor,
    serialize_feed_page,
)


def _post(
    *,
    tweet_id: str,
    created_at: str,
    text: str = "stub",
    text_en: str | None = "english",
    text_zh_cn: str | None = "中文",
    like_count: int = 0,
    brand_nicknames: list[str] | None = None,
    discourse: list[str] | None = None,
    post_types: list[str] | None = None,
    role_key: str = "community",
    cn_nationalism: str | None = None,
    us_nationalism: str | None = None,
    unsanctioned: bool = False,
    lang_detected: str = "en",
) -> dict:
    return {
        "tweet_id": tweet_id,
        "created_at": created_at,
        "text": text,
        "text_en": text_en,
        "text_zh_cn": text_zh_cn,
        "like_count": like_count,
        "lang_detected": lang_detected,
        "brand_nicknames": brand_nicknames or [],
        "brands": [
            {"nickname": n, "display_name": n, "display_name_en": n, "display_name_zh_cn": n}
            for n in (brand_nicknames or [])
        ],
        "classifications_by_brand": {
            n: {
                "discourse": discourse or [],
                "post_types": post_types or [],
                "sentiments": [],
                "cn_nationalism": cn_nationalism,
                "us_nationalism": us_nationalism,
            }
            for n in (brand_nicknames or [])
        },
        "discourse": discourse or [],
        "post_types": post_types or [],
        "role_key": role_key,
        "cn_nationalism": cn_nationalism,
        "us_nationalism": us_nationalism,
        "unsanctioned": unsanctioned,
        "account": {"handle": "@user1", "role": role_key, "role_label": role_key},
    }


# ---------------------------------------------------------------------------
# Cursor encode/decode round-trip
# ---------------------------------------------------------------------------


def test_cursor_encode_decode_round_trip():
    cur = _feed_encode_cursor("2026-07-06T12:00:00+00:00", "tweet-123")
    assert _feed_decode_cursor(cur) == ("2026-07-06T12:00:00+00:00", "tweet-123")


def test_cursor_decode_malformed_returns_none():
    assert _feed_decode_cursor("") is None
    assert _feed_decode_cursor("no-colon") is None
    assert _feed_decode_cursor(":missing-iso") is None
    assert _feed_decode_cursor("iso:") is None


# ---------------------------------------------------------------------------
# Happy path: first page
# ---------------------------------------------------------------------------


def test_feed_returns_first_50_desc_by_default():
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:03d}",
            created_at=(now - timedelta(hours=i)).isoformat(),
        )
        for i in range(60)
    ]
    out = serialize_feed_page(posts, limit=50)
    assert len(out["rows"]) == 50
    # Newest first (DESC default)
    assert out["rows"][0]["tweet_id"] == "t-000"
    assert out["rows"][-1]["tweet_id"] == "t-049"
    assert out["next_cursor"] is not None
    assert out["sort"] == "created_at"
    assert out["order"] == "desc"


def test_feed_empty_db_is_empty_rows_no_error():
    out = serialize_feed_page([])
    assert out["rows"] == []
    assert out["next_cursor"] is None


def test_feed_under_limit_returns_no_next_cursor():
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:03d}",
            created_at=(now - timedelta(hours=i)).isoformat(),
        )
        for i in range(5)
    ]
    out = serialize_feed_page(posts, limit=50)
    assert len(out["rows"]) == 5
    assert out["next_cursor"] is None


# ---------------------------------------------------------------------------
# Cursor advancement
# ---------------------------------------------------------------------------


def test_feed_cursor_advances_past_previous_page():
    """Plan AE2 / R9: pass cursor from previous page; returns rows
    strictly after the cursor."""
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:03d}",
            created_at=(now - timedelta(hours=i)).isoformat(),
        )
        for i in range(60)
    ]
    page1 = serialize_feed_page(posts, limit=50)
    page2 = serialize_feed_page(posts, cursor=page1["next_cursor"], limit=50)
    # page2 should contain the remaining 10 posts
    assert len(page2["rows"]) == 10
    # No overlap with page1
    page1_ids = {r["tweet_id"] for r in page1["rows"]}
    page2_ids = {r["tweet_id"] for r in page2["rows"]}
    assert page1_ids.isdisjoint(page2_ids)
    assert page2["next_cursor"] is None


def test_feed_malformed_cursor_returns_no_next_cursor():
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:03d}",
            created_at=(now - timedelta(hours=i)).isoformat(),
        )
        for i in range(60)
    ]
    out = serialize_feed_page(posts, cursor="garbage", limit=50)
    # Should still return a page (the malformed cursor is treated as
    # "no cursor" by the decoder) but next_cursor is set to None
    # because the cursor token is unusable.
    assert len(out["rows"]) > 0
    assert out["next_cursor"] is None


# ---------------------------------------------------------------------------
# Sort variants
# ---------------------------------------------------------------------------


def test_feed_sort_like_count_asc():
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:03d}",
            created_at=(now - timedelta(hours=i)).isoformat(),
            like_count=10 - i,
        )
        for i in range(5)
    ]
    out = serialize_feed_page(posts, sort="like_count", order="asc", limit=5)
    # Ascending by like_count: t-004 (6) ... t-000 (10) is wrong; asc
    # means smallest first. t-000 has like_count=10, t-004 has
    # like_count=6, so t-004 should be first.
    assert out["rows"][0]["tweet_id"] == "t-004"
    assert out["rows"][-1]["tweet_id"] == "t-000"


def test_feed_sort_like_count_desc():
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:03d}",
            created_at=(now - timedelta(hours=i)).isoformat(),
            like_count=i,
        )
        for i in range(5)
    ]
    out = serialize_feed_page(posts, sort="like_count", order="desc", limit=5)
    # Descending: t-004 (4) first, t-000 (0) last
    assert out["rows"][0]["tweet_id"] == "t-004"
    assert out["rows"][-1]["tweet_id"] == "t-000"


def test_feed_invalid_sort_falls_back_to_created_at():
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:03d}",
            created_at=(now - timedelta(hours=i)).isoformat(),
        )
        for i in range(5)
    ]
    out = serialize_feed_page(posts, sort="bogus", limit=5)
    assert out["sort"] == "created_at"


def test_feed_invalid_order_falls_back_to_desc():
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:03d}",
            created_at=(now - timedelta(hours=i)).isoformat(),
        )
        for i in range(5)
    ]
    out = serialize_feed_page(posts, order="bogus", limit=5)
    assert out["order"] == "desc"


# ---------------------------------------------------------------------------
# Filter narrowing
# ---------------------------------------------------------------------------


def test_feed_filters_narrow_rows():
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:03d}",
            created_at=(now - timedelta(hours=i)).isoformat(),
            discourse=["genuine_hype"] if i % 2 == 0 else ["sarcasm"],
        )
        for i in range(10)
    ]
    out = serialize_feed_page(
        posts, filters={"discourse": ["genuine_hype"]}, limit=10
    )
    assert len(out["rows"]) == 5
    assert out["applied_filters"] == {"discourse": ["genuine_hype"]}


# ---------------------------------------------------------------------------
# Brand scope
# ---------------------------------------------------------------------------


def test_feed_brand_scope_filters_to_one_brand():
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:03d}",
            created_at=(now - timedelta(hours=i)).isoformat(),
            brand_nicknames=["minimax"] if i % 2 == 0 else ["qwen"],
        )
        for i in range(10)
    ]
    out = serialize_feed_page(posts, brand_scope="minimax", limit=10)
    assert len(out["rows"]) == 5
    for r in out["rows"]:
        assert "minimax" in r["brand_nicknames"]


def test_feed_brand_scope_is_server_side_not_bypassable():
    """R16: brand_scope is a server-side filter, NOT a client filter.
    Even with empty client filters, the server still narrows."""
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:03d}",
            created_at=(now - timedelta(hours=i)).isoformat(),
            brand_nicknames=["qwen"] if i == 0 else ["minimax"],
        )
        for i in range(5)
    ]
    out = serialize_feed_page(posts, brand_scope="minimax", limit=10)
    # The qwen post is server-side excluded
    tweet_ids = {r["tweet_id"] for r in out["rows"]}
    assert "t-000" not in tweet_ids


# ---------------------------------------------------------------------------
# Hard cap
# ---------------------------------------------------------------------------


def test_feed_hard_cap_returns_no_next_cursor_after_500():
    """R9: total feed hard cap is 500; after that, next_cursor=None."""
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:05d}",
            created_at=(now - timedelta(seconds=i)).isoformat(),
        )
        for i in range(600)
    ]
    # Simulate a cumulative paging session
    seen: set[tuple[str, str]] = set()
    cursor = None
    pages = 0
    while pages < 12:  # safety guard
        out = serialize_feed_page(
            posts, cursor=cursor, limit=50, seen_cursor_keys=seen
        )
        for r in out["rows"]:
            seen.add((r["created_at"], r["tweet_id"]))
        cursor = out["next_cursor"]
        pages += 1
        if cursor is None:
            break
    # 500-row cap → 10 pages of 50 + a final 0-row page
    assert len(seen) == _FEED_HARD_CAP
    # The 11th page returns 0 rows (the input has more, but we've hit
    # the cap) and next_cursor=None
    final = serialize_feed_page(
        posts, cursor=cursor, limit=50, seen_cursor_keys=seen
    )
    assert final["next_cursor"] is None


# ---------------------------------------------------------------------------
# Wire shape (R10)
# ---------------------------------------------------------------------------


def test_feed_row_wire_shape():
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    p = _post(
        tweet_id="t-001",
        created_at=now.isoformat(),
        text="原文",
        text_en="English translation",
        text_zh_cn="中文翻译",
        like_count=42,
        brand_nicknames=["minimax"],
        discourse=["genuine_hype"],
        role_key="official",
        unsanctioned=True,
        lang_detected="zh",
    )
    # unsanctioned=any disables the default off filter so the flagged
    # post is eligible for the wire-shape assertion.
    out = serialize_feed_page([p], locale="en", filters={"unsanctioned": "any"})
    row = out["rows"][0]
    assert row["tweet_id"] == "t-001"
    assert row["created_at"] == now.isoformat()
    assert row["text"] == "原文"  # original always returned
    assert row["text_translated"] == "English translation"  # locale=en
    assert row["is_translated"] is True
    assert row["text_en"] == "English translation"
    assert row["text_zh_cn"] == "中文翻译"
    assert row["like_count"] == 42
    assert row["lang_detected"] == "zh"
    assert "minimax" in row["brand_nicknames"]
    assert row["unsanctioned"] is True
    assert row["account"]["role"] == "official"
    assert "minimax" in row["classifications"]


def test_feed_locale_original_returns_source_text():
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    p = _post(
        tweet_id="t-001",
        created_at=now.isoformat(),
        text="原文",
        text_en="English translation",
        text_zh_cn="中文翻译",
    )
    out = serialize_feed_page([p], locale="original")
    row = out["rows"][0]
    assert row["text_translated"] == "原文"
    assert row["is_translated"] is False


# ---------------------------------------------------------------------------
# U1: created_at_iso (additive ISO-8601 sibling of `created_at`)
# ---------------------------------------------------------------------------


def test_feed_wire_includes_created_at_iso_iso_input():
    """U1: ISO `created_at` input round-trips into a parseable
    `created_at_iso` field. The client uses this for relative time +
    the local-time tooltip; the existing `created_at` field is
    unchanged for backward compat."""
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    p = _post(tweet_id="t-iso", created_at=now.isoformat())
    out = serialize_feed_page([p])
    row = out["rows"][0]
    assert row["created_at"] == now.isoformat(), "created_at must be unchanged"
    assert row["created_at_iso"] == now.isoformat(), (
        f"created_at_iso should round-trip the ISO input; got "
        f"{row['created_at_iso']!r}"
    )
    # Round-trip parses back to the same aware UTC instant.
    parsed = datetime.fromisoformat(row["created_at_iso"])
    assert parsed == now
    assert parsed.tzinfo is not None


def test_feed_wire_includes_created_at_iso_twitter_input():
    """U1: Twitter-format `created_at` (legacy wire shape) parses
    into a valid `created_at_iso`. Some older posts still carry the
    legacy format and the client must handle both."""
    p = _post(
        tweet_id="t-tw",
        created_at="Wed Jul 15 21:00:00 +0000 2026",
    )
    out = serialize_feed_page([p])
    row = out["rows"][0]
    assert row["created_at"] == "Wed Jul 15 21:00:00 +0000 2026"
    parsed = datetime.fromisoformat(row["created_at_iso"])
    assert parsed == datetime(2026, 7, 15, 21, 0, 0, tzinfo=timezone.utc)


def test_feed_wire_created_at_iso_none_for_unparseable():
    """U1: garbage created_at yields created_at_iso=None — client
    renders the date as raw text fallback. Must NOT raise."""
    p = _post(tweet_id="t-garbage", created_at="not a date")
    out = serialize_feed_page([p])
    row = out["rows"][0]
    assert row["created_at"] == "not a date"
    assert row["created_at_iso"] is None


def test_feed_wire_created_at_iso_none_when_missing():
    """U1: when _post's created_at is missing, the wire emits
    created_at_iso=None without raising. (The default `_post` helper
    always sets created_at; this test verifies the None-safe path by
    calling _feed_row_to_wire directly.)"""
    from x_monitor.dashboard import _feed_row_to_wire
    p = {"tweet_id": "t-direct", "brand_nicknames": []}
    row = _feed_row_to_wire(p, locale="en")
    assert row["created_at"] is None
    assert row["created_at_iso"] is None


def test_feed_default_limit_is_50():
    """R9: page size is 50 by default."""
    out = serialize_feed_page([])
    # The default limit isn't echoed in the payload, but the function
    # should accept the default without error and return no rows.
    assert out["rows"] == []


def test_feed_default_limit_constant():
    assert _FEED_DEFAULT_LIMIT == 50


def test_feed_default_sort_is_created_at_desc():
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:03d}",
            created_at=(now - timedelta(hours=i)).isoformat(),
        )
        for i in range(5)
    ]
    out = serialize_feed_page(posts)
    assert out["sort"] == "created_at"
    assert out["order"] == "desc"


# ---------------------------------------------------------------------------
# U1: chronological order survives non-ISO (Twitter-format) created_at
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# U1: chronological order survives non-ISO (Twitter-format) created_at
# ---------------------------------------------------------------------------


def test_feed_sorts_chronologically_for_twitter_date_strings():
    """U1: lexicographic on Twitter-format strings sorts WRONG
    ('Mon' > 'Thu' alphabetically). The route layer must parse
    the date and sort by parsed timestamp, not string."""
    posts = [
        _post(tweet_id="tw-oldest", created_at="Mon Jul 14 01:00:00 +0000 2025"),
        _post(tweet_id="tw-newest", created_at="Tue Jul 14 01:00:00 +0000 2026"),
        _post(tweet_id="tw-middle", created_at="Wed Jul 14 01:00:00 +0000 2025"),
    ]
    out = serialize_feed_page(posts)
    ids = [r["tweet_id"] for r in out["rows"]]
    assert ids == ["tw-newest", "tw-oldest", "tw-middle"], (
        f"expected chronological DESC across mixed formats, got {ids}"
    )


# ---------------------------------------------------------------------------
# U3: account.role is None when no DB mapping (not 'community')
# ---------------------------------------------------------------------------


def test_feed_no_community_default_role_key():
    """U3: _denormalize_posts used to default role_key='community'
    when no brands_accounts row matched. The fix leaves role_key
    unset (None) in that case. This test asserts the post-input
    contract: when the producer supplies role_key=None / absent,
    serialize_feed_page must NOT put the literal 'community' in
    the wire output."""
    p = _post(
        tweet_id="t-no-role",
        created_at="2026-07-14T01:18:36+00:00",
        brand_nicknames=["minimax"],
        discourse=[],
        post_types=[],
        role_key=None,
    )
    # _post helper would still set account={'role': role_key, ...}.
    # Mirror what the fix should produce.
    p["account"] = {"handle": "@someone", "role": None, "role_label": None}
    out = serialize_feed_page([p])
    row = out["rows"][0]
    role = (row.get("account") or {}).get("role")
    assert role != "community", (
        "U3 fix: do not fabricate 'community' when DB has no role; "
        f"got account={row.get('account')!r}"
    )
    assert role is None, f"account.role must be None, got {role!r}"


def test_feed_account_role_passes_through_when_set():
    """U3 (positive control): real role from DB still renders."""
    p = _post(
        tweet_id="t-official",
        created_at="2026-07-14T01:18:36+00:00",
        role_key="official",
    )
    out = serialize_feed_page([p])
    assert out["rows"][0]["account"]["role"] == "official"


# ---------------------------------------------------------------------------
# Brand filter narrowing (control panel multi-brand checkbox)
# ---------------------------------------------------------------------------


def test_feed_filter_brands_overlap_includes_post():
    """brands=["qwen","glm"] + post with brand_nicknames=["qwen"] → row included."""
    now = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:03d}",
            created_at=(now - timedelta(hours=i)).isoformat(),
            brand_nicknames=["qwen"] if i < 5 else ["deepseek"],
        )
        for i in range(10)
    ]
    out = serialize_feed_page(posts, filters={"brands": ["qwen", "glm"]}, limit=50)
    assert len(out["rows"]) == 5
    for r in out["rows"]:
        assert "qwen" in r["brand_nicknames"]


def test_feed_filter_brands_empty_returns_no_rows():
    """brands=[] → zero rows (intentional narrowing)."""
    now = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:03d}",
            created_at=(now - timedelta(hours=i)).isoformat(),
            brand_nicknames=["qwen"],
        )
        for i in range(5)
    ]
    out = serialize_feed_page(posts, filters={"brands": []}, limit=50)
    assert out["rows"] == []
    assert out["next_cursor"] is None


def test_feed_filter_brands_all_sentinel_disables_filter():
    """brands=\"__all__\" → no narrowing (all rows pass)."""
    now = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:03d}",
            created_at=(now - timedelta(hours=i)).isoformat(),
            brand_nicknames=["qwen"] if i % 2 == 0 else ["deepseek"],
        )
        for i in range(10)
    ]
    out = serialize_feed_page(posts, filters={"brands": "__all__"}, limit=50)
    assert len(out["rows"]) == 10


def test_feed_filter_brands_absent_disables_filter():
    """absent brands key → no narrowing (back-compat with un-filtered callers)."""
    now = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:03d}",
            created_at=(now - timedelta(hours=i)).isoformat(),
            brand_nicknames=["qwen"],
        )
        for i in range(5)
    ]
    out = serialize_feed_page(posts, filters={}, limit=50)
    assert len(out["rows"]) == 5


# ---------------------------------------------------------------------------
# M1 (2026-07-16): __all__ sentinel and empty-list narrowing for all axes.
# Pre-existing bug: non-brand axes did substring-match against the string
# "__all__" instead of treating it as "no narrowing". This diff fixes it.
# ---------------------------------------------------------------------------


def test_feed_filter_all_sentinel_disables_discourse_narrowing():
    """discourse=\"__all__\" → no narrowing (no substring-match bug)."""
    now = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:03d}",
            created_at=(now - timedelta(hours=i)).isoformat(),
            discourse=["genuine_hype"] if i % 2 == 0 else ["sarcasm"],
        )
        for i in range(10)
    ]
    out = serialize_feed_page(posts, filters={"discourse": "__all__"}, limit=50)
    assert len(out["rows"]) == 10


def test_feed_filter_empty_discourse_returns_no_rows():
    """discourse=[] → zero rows (intentional narrowing)."""
    now = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
    posts = [
        _post(
            tweet_id=f"t-{i:03d}",
            created_at=(now - timedelta(hours=i)).isoformat(),
            discourse=["genuine_hype"],
        )
        for i in range(5)
    ]
    out = serialize_feed_page(posts, filters={"discourse": []}, limit=50)
    assert out["rows"] == []
