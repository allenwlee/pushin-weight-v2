# {{AGENT_ATTRIBUTION}}
"""Account graph: YAML nodes, on-demand edges from post source fields (R9-R15)."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from .config import KNOWN_MODELS


# --- Data models ----------------------------------------------------------

RoleType = Literal[
    "official",
    "developer",
    "employee",
    "critic",
    "community",
    "suspicious_actor",
    "unknown",
]


class Account(BaseModel):
    """A node in the account graph."""

    handle: str = Field(min_length=1)
    display_name: str = ""
    role: RoleType = "unknown"
    verified: bool = False
    bio_contains_brand: bool = False
    multiple_posts_in_thread_with_official: int = 0  # count
    source_query_ids: list[str] = Field(default_factory=list)
    multi_brand_voice: bool = False
    notes: str = ""


class StaffAccount(BaseModel):
    """A staff/employee handle for v1.6 OR-collapse (manually curated).

    Distinct from `Account`: a staff handle is treated as a brand
    representative but is NOT auto-discovered from posts. The
    `data/accounts/<brand>.yaml::staff: []` list is the source of
    truth — the operator adds handles by hand.
    """

    handle: str = Field(min_length=1)
    role: Literal["staff", "developer", "employee"] = "staff"


class Edge(BaseModel):
    """A typed edge in the account graph.

    R11: derived from post SOURCE FIELDS, never from text regex.
    """

    edge_type: Literal[
        "replied_to", "quoted", "mentioned", "co_appears_in_thread"
    ]
    from_handle: str
    to_handle: str
    weight: int = 1
    post_id: str | None = None
    brand_id: str


class Cluster(BaseModel):
    """A reply-chain cluster: a set of commenters on a set of posts (R13)."""

    commenters: list[str]
    post_ids: list[str]
    brand_id: str


# --- YAML load ------------------------------------------------------------


def load_accounts(brand_id: str, root: Path) -> list[Account]:
    """Load seeded accounts for one model.

    root is the data/ directory of x-monitoring.
    """
    if brand_id not in KNOWN_MODELS:
        raise ValueError(f"unknown brand_id '{brand_id}'")
    path = root / "accounts" / f"{brand_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"missing account file: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict) or "accounts" not in raw:
        raise ValueError(f"{path}: top-level key 'accounts' required")
    accounts_raw = raw["accounts"]
    if not isinstance(accounts_raw, list):
        raise ValueError(f"{path}: 'accounts' must be a list")
    accounts = [Account.model_validate(a) for a in accounts_raw]
    # Enforce uniqueness of handle within file
    seen = {a.handle for a in accounts}
    if len(seen) != len(accounts):
        raise ValueError(f"{path}: duplicate handle in seed YAML")
    return accounts


def load_staff(brand_id: str, root: Path) -> list[StaffAccount]:
    """Load the manually-curated staff list for a model (v1.6).

    root is the data/ directory. The list lives under the `staff:` key
    in data/accounts/<brand_id>.yaml; if the key is missing, an empty
    list is returned. The list is never derived from posts — only the
    operator (or a future v1.7 audit) adds entries here.
    """
    if brand_id not in KNOWN_MODELS:
        raise ValueError(f"unknown brand_id '{brand_id}'")
    path = root / "accounts" / f"{brand_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"missing account file: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return []
    staff_raw = raw.get("staff") or []
    if not isinstance(staff_raw, list):
        raise ValueError(f"{path}: 'staff' must be a list")
    return [StaffAccount.model_validate(s) for s in staff_raw]


# --- Edge derivation (R11) -------------------------------------------------


def derive_edges(posts: list[dict], brand_id: str) -> list[Edge]:
    """Derive edges from post SOURCE FIELDS only (R11 contract).

    Inputs are dicts with at least: id, author_id, in_reply_to_user_id,
    quoted_status_id, entities (with user_mentions[]), conversation_id.
    """
    if brand_id not in KNOWN_MODELS:
        raise ValueError(f"unknown brand_id '{brand_id}'")
    edges: list[Edge] = []

    for post in posts:
        author = post.get("author_handle") or post.get("author_id")
        if not author:
            continue
        pid = post.get("id", "")

        # 1. replied_to — from in_reply_to_user_id
        in_reply = post.get("in_reply_to_user_id")
        if in_reply:
            edges.append(
                Edge(
                    edge_type="replied_to",
                    from_handle=str(author),
                    to_handle=str(in_reply),
                    post_id=str(pid) if pid else None,
                    brand_id=brand_id,
                )
            )

        # 2. quoted — from quoted_status_id (we don't have the quoted author
        #    inline, so we record the quoted author handle if the scraper
        #    provided it via quoted_status_author_handle; otherwise skip)
        quoted = post.get("quoted_status_id")
        quoted_author = post.get("quoted_status_author_handle")
        if quoted and quoted_author:
            edges.append(
                Edge(
                    edge_type="quoted",
                    from_handle=str(author),
                    to_handle=str(quoted_author),
                    post_id=str(pid) if pid else None,
                    brand_id=brand_id,
                )
            )

        # 3. mentioned — from entities.user_mentions[].id
        entities = post.get("entities") or {}
        mentions = entities.get("user_mentions") or []
        for m in mentions:
            mid = m.get("id") if isinstance(m, dict) else None
            if mid:
                edges.append(
                    Edge(
                        edge_type="mentioned",
                        from_handle=str(author),
                        to_handle=str(mid),
                        post_id=str(pid) if pid else None,
                        brand_id=brand_id,
                    )
                )

    # 4. co_appears_in_thread — derive from shared conversation_id
    by_conv: dict[str, list[str]] = defaultdict(list)
    for post in posts:
        conv = post.get("conversation_id")
        author = post.get("author_handle") or post.get("author_id")
        if conv and author:
            by_conv[str(conv)].append(str(author))

    for conv, authors in by_conv.items():
        unique = list(dict.fromkeys(authors))  # preserve order, dedupe
        # Only emit edges when at least 2 unique authors share a thread
        if len(unique) < 2:
            continue
        for i, a in enumerate(unique):
            for b in unique[i + 1 :]:
                edges.append(
                    Edge(
                        edge_type="co_appears_in_thread",
                        from_handle=a,
                        to_handle=b,
                        brand_id=brand_id,
                    )
                )

    return edges


# --- Cluster detection (R13) ----------------------------------------------


def find_clusters(
    posts: list[dict],
    edges: list[Edge],
    min_commenters: int,
    min_posts: int,
) -> list[Cluster]:
    """Find reply-chain clusters (R13): >=min_commenters commenters appearing
    on >=min_posts of the same official's posts.

    Implementation:
      - Group posts by official (the to_handle of a replied_to edge from this
        model — i.e., posts by community authors replying to the official).
      - For each official, count distinct commenters and the post_ids they
        appear on.
      - Emit a cluster when an official has >=min_posts of its posts covered
        by a group of >=min_commenters commenters.
    """
    # Map: official_handle -> set of (commenter_handle, post_id)
    official_to_combos: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for post in posts:
        author = post.get("author_handle") or post.get("author_id")
        in_reply = post.get("in_reply_to_user_id")
        pid = post.get("id")
        if author and in_reply and str(in_reply) != str(author) and pid:
            official_to_combos[str(in_reply)].add((str(author), str(pid)))

    clusters: list[Cluster] = []
    # We don't have brand_id on posts here; caller passes it via edges[0] if
    # any. We use "unknown" as a fallback; callers can rewrite.
    inferred_model = edges[0].brand_id if edges else "unknown"
    for official, combos in official_to_combos.items():
        if len(combos) < min_posts:
            continue
        commenters = sorted({c for c, _ in combos})
        post_ids = sorted({p for _, p in combos})
        # Count how many distinct posts each commenter appears on
        covered_posts: set[str] = set()
        for c, p in combos:
            covered_posts.add(p)
        if len(covered_posts) < min_posts:
            continue
        # Commenters who appear on >=1 of the covered posts
        # (i.e., all of them, since combos are already filtered)
        if len(commenters) < min_commenters:
            continue
        clusters.append(
            Cluster(
                commenters=commenters,
                post_ids=post_ids,
                brand_id=inferred_model,
            )
        )
    return clusters


# --- Role tagging (Q5 starter rules) --------------------------------------


# Per R10 + the May 30 bot-detection heuristic (avg >10 faves/post, 0 replies,
# no bio → suspicious_actor). v1.1 will move this to LLM; Q5 says keep it
# rule-based in v1.
def role_tag(
    account: Account,
    posts_for_account: list[dict] | None = None,
    brand_terms: list[str] | None = None,
) -> RoleType:
    """Upgrade an account's role based on evidence.

    Starter rules:
      - bio_contains_brand (set by Q4 ingestion) → developer
      - verified_handle (set by Q1 ingestion) → employee
      - suspicious_actor — avg >10 faves/post, 0 replies, no bio → suspicious
      - multiple_posts_in_thread_with_official >= 2 → community
      - explicit role: "official" is never overridden
    """
    if account.role == "official":
        return "official"
    if account.verified:
        return "employee"
    if account.bio_contains_brand:
        return "developer"
    if account.multiple_posts_in_thread_with_official >= 2:
        return "community"
    if posts_for_account:
        n = len(posts_for_account)
        if n >= 3:
            avg_likes = sum(p.get("like_count", 0) for p in posts_for_account) / n
            n_replies = sum(1 for p in posts_for_account if p.get("in_reply_to_user_id"))
            bio = (posts_for_account[0].get("author_bio") or "").strip()
            if avg_likes > 10 and n_replies == 0 and not bio:
                return "suspicious_actor"
    return "unknown"
