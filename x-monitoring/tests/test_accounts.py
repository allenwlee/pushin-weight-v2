# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.accounts."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from x_monitor.accounts import (
    Account,
    Cluster,
    Edge,
    derive_edges,
    find_clusters,
    load_accounts,
    role_tag,
)


# --- derive_edges ---------------------------------------------------------


def test_derive_replied_to_from_in_reply_to_user_id():
    posts = [
        {
            "id": "1",
            "author_handle": "alice",
            "in_reply_to_user_id": "official",
        }
    ]
    edges = derive_edges(posts, model_id="minimax")
    assert any(
        e.edge_type == "replied_to" and e.from_handle == "alice" and e.to_handle == "official"
        for e in edges
    )


def test_derive_quoted_from_quoted_status_id_and_author():
    posts = [
        {
            "id": "2",
            "author_handle": "bob",
            "quoted_status_id": "999",
            "quoted_status_author_handle": "carol",
        }
    ]
    edges = derive_edges(posts, model_id="minimax")
    assert any(
        e.edge_type == "quoted" and e.from_handle == "bob" and e.to_handle == "carol"
        for e in edges
    )


def test_derive_mentioned_from_entities_user_mentions():
    posts = [
        {
            "id": "3",
            "author_handle": "dave",
            "entities": {"user_mentions": [{"id": "official", "screen_name": "MiniMaxAI"}]},
        }
    ]
    edges = derive_edges(posts, model_id="minimax")
    assert any(
        e.edge_type == "mentioned" and e.from_handle == "dave" and e.to_handle == "official"
        for e in edges
    )


def test_derive_co_appears_in_thread_from_conversation_id():
    posts = [
        {"id": "a", "author_handle": "u1", "conversation_id": "C1"},
        {"id": "b", "author_handle": "u2", "conversation_id": "C1"},
        {"id": "c", "author_handle": "u3", "conversation_id": "C1"},
    ]
    edges = derive_edges(posts, model_id="minimax")
    co = [e for e in edges if e.edge_type == "co_appears_in_thread"]
    # 3 unique authors → 3 choose 2 = 3 co-appearing edges
    assert len(co) == 3


def test_no_replied_to_edge_when_field_missing():
    # Text starts with @user but in_reply_to_user_id is None — must NOT
    # produce an edge. This is the R11 contract.
    posts = [
        {
            "id": "x",
            "author_handle": "eve",
            "text": "@official hello",
            "in_reply_to_user_id": None,
        }
    ]
    edges = derive_edges(posts, model_id="minimax")
    assert not any(e.edge_type == "replied_to" for e in edges)


# --- find_clusters --------------------------------------------------------


def test_find_clusters_flags_threshold_met():
    # 3 commenters x 2 posts on the same official
    posts = [
        {"id": "p1", "author_handle": "c1", "in_reply_to_user_id": "official"},
        {"id": "p1", "author_handle": "c2", "in_reply_to_user_id": "official"},
        {"id": "p1", "author_handle": "c3", "in_reply_to_user_id": "official"},
        {"id": "p2", "author_handle": "c1", "in_reply_to_user_id": "official"},
        {"id": "p2", "author_handle": "c2", "in_reply_to_user_id": "official"},
        {"id": "p2", "author_handle": "c3", "in_reply_to_user_id": "official"},
    ]
    edges: list[Edge] = []
    clusters = find_clusters(posts, edges, min_commenters=3, min_posts=2)
    assert len(clusters) == 1
    assert set(clusters[0].commenters) == {"c1", "c2", "c3"}
    assert set(clusters[0].post_ids) == {"p1", "p2"}


def test_find_clusters_does_not_flag_single_commenter():
    posts = [
        {"id": "p1", "author_handle": "c1", "in_reply_to_user_id": "official"},
        {"id": "p2", "author_handle": "c1", "in_reply_to_user_id": "official"},
    ]
    edges = []
    clusters = find_clusters(posts, edges, min_commenters=3, min_posts=2)
    assert clusters == []


# --- role_tag (Q5 starter rules) -----------------------------------------


def test_role_tag_official_is_never_overridden():
    a = Account(handle="x", role="official")
    assert role_tag(a) == "official"


def test_role_tag_verified_becomes_employee():
    a = Account(handle="x", verified=True)
    assert role_tag(a) == "employee"


def test_role_tag_bio_contains_brand_becomes_developer():
    a = Account(handle="x", bio_contains_brand=True)
    assert role_tag(a) == "developer"


def test_role_tag_multi_thread_becomes_community():
    a = Account(handle="x", multiple_posts_in_thread_with_official=3)
    assert role_tag(a) == "community"


def test_role_tag_suspicious_actor():
    a = Account(handle="bot")
    posts = [
        {"favorite_count": 20, "in_reply_to_user_id": None, "author_bio": ""},
        {"favorite_count": 15, "in_reply_to_user_id": None, "author_bio": ""},
        {"favorite_count": 30, "in_reply_to_user_id": None, "author_bio": ""},
    ]
    assert role_tag(a, posts_for_account=posts) == "suspicious_actor"


def test_role_tag_unknown_when_no_signals():
    a = Account(handle="x")
    assert role_tag(a) == "unknown"


# --- load_accounts --------------------------------------------------------


def test_load_accounts_reads_seed_yaml():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "accounts").mkdir()
        (root / "accounts" / "minimax.yaml").write_text(
            """
accounts:
  - handle: MiniMaxAI
    display_name: "MiniMax AI"
    role: official
    verified: true
    notes: Official company handle.
""",
            encoding="utf-8",
        )
        accts = load_accounts("minimax", root)
        assert len(accts) == 1
        assert accts[0].handle == "MiniMaxAI"
        assert accts[0].role == "official"


def test_load_accounts_rejects_unknown_model():
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(ValueError, match="unknown model_id"):
            load_accounts("bogus", Path(d))


def test_load_accounts_rejects_duplicate_handles():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "accounts").mkdir()
        (root / "accounts" / "minimax.yaml").write_text(
            """
accounts:
  - handle: dup
    role: unknown
  - handle: dup
    role: official
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="duplicate"):
            load_accounts("minimax", root)
