# {{AGENT_ATTRIBUTION}}
"""Force-directed account graph (Fruchterman-Reingold, inline SVG, no d3)."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Iterable, Literal

from pydantic import BaseModel, Field


# Plan 2026-07-11-002 (U4): the Account / StaffAccount / Edge /
# Cluster pydantic models + derive_edges / find_clusters / role_tag
# moved from x_monitor.accounts (deleted) to this module. The
# data/accounts/*.yaml loaders are gone; `brands_accounts` is
# canonical. Models kept here for the in-code edge/cluster
# derivations that read from post body dicts.

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
    multiple_posts_in_thread_with_official: int = 0
    source_query_ids: list[str] = Field(default_factory=list)
    multi_brand_voice: bool = False
    notes: str = ""


class StaffAccount(BaseModel):
    """A staff/employee handle for v1.6 OR-collapse.

    Distinct from `Account`: a staff handle is treated as a brand
    representative but is NOT auto-discovered from posts. The DB
    `brands_accounts WHERE role_id IN (2, 3)` is canonical post-U4.
    """

    handle: str = Field(min_length=1)
    role: Literal["staff", "developer", "employee"] = "staff"


class Edge(BaseModel):
    """A typed edge in the account graph (derived from post SOURCE
    FIELDS, never from text regex)."""

    edge_type: Literal[
        "replied_to", "quoted", "mentioned", "co_appears_in_thread"
    ]
    from_handle: str
    to_handle: str
    weight: int = 1
    post_id: str | None = None
    brand_id: str


class Cluster(BaseModel):
    """A reply-chain cluster: a set of commenters on a set of posts."""

    commenters: list[str]
    post_ids: list[str]
    brand_id: str


def build_force_directed(
    accounts: list[Account],
    edges: list[Edge],
    width: int = 800,
    height: int = 600,
    iterations: int = 80,
    seed: int = 7,
) -> str:
    """Return inline SVG of a force-directed graph.

    Center the 'official' role node(s). Use a simple spring/charge layout
    (Fruchterman-Reingold). Deterministic via `seed`.
    """
    if not accounts:
        return (
            f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'xmlns="http://www.w3.org/2000/svg">'
            f'<text x="50%" y="50%" text-anchor="middle" fill="#8b949e" '
            f'font-size="14">no accounts discovered yet</text></svg>'
        )

    rng = random.Random(seed)
    nodes = {a.handle: a for a in accounts}
    # Initial positions: officials at center, others in a ring.
    handles = list(nodes.keys())
    officials = [h for h, a in nodes.items() if a.role == "official"]
    others = [h for h in handles if h not in officials]
    pos: dict[str, tuple[float, float]] = {}
    for i, h in enumerate(officials):
        pos[h] = (width / 2 + (i - len(officials) / 2) * 30, height / 2)
    for i, h in enumerate(others):
        angle = 2 * math.pi * i / max(len(others), 1)
        pos[h] = (width / 2 + math.cos(angle) * 200, height / 2 + math.sin(angle) * 200)

    # Edge weights
    edge_weight: dict[tuple[str, str], int] = defaultdict(int)
    for e in edges:
        if e.from_handle in nodes and e.to_handle in nodes:
            a, b = sorted([e.from_handle, e.to_handle])
            edge_weight[(a, b)] += e.weight

    k = 50.0  # ideal edge length
    area = width * height
    k = k * math.sqrt(area / max(len(nodes), 1)) / 100

    for _ in range(iterations):
        # Repulsive
        disp: dict[str, list[float]] = {h: [0.0, 0.0] for h in handles}
        for i, h1 in enumerate(handles):
            for h2 in handles[i + 1 :]:
                dx = pos[h1][0] - pos[h2][0]
                dy = pos[h1][1] - pos[h2][1]
                d = math.hypot(dx, dy) + 0.01
                force = (k * k) / d
                disp[h1][0] += (dx / d) * force
                disp[h1][1] += (dy / d) * force
                disp[h2][0] -= (dx / d) * force
                disp[h2][1] -= (dy / d) * force
        # Attractive
        for (a, b), w in edge_weight.items():
            dx = pos[a][0] - pos[b][0]
            dy = pos[a][1] - pos[b][1]
            d = math.hypot(dx, dy) + 0.01
            force = (d * d) / (k * max(w, 1))
            disp[a][0] -= (dx / d) * force
            disp[a][1] -= (dy / d) * force
            disp[b][0] += (dx / d) * force
            disp[b][1] += (dy / d) * force
        # Apply (clamped to canvas)
        max_d = 30.0
        for h in handles:
            dx, dy = disp[h]
            d = math.hypot(dx, dy) + 0.01
            scale = min(d, max_d) / d
            nx = pos[h][0] + dx * scale
            ny = pos[h][1] + dy * scale
            nx = max(20, min(width - 20, nx))
            ny = max(20, min(height - 20, ny))
            pos[h] = (nx, ny)

    # Render SVG
    edge_color = {
        "replied_to": "#3b82f6",
        "quoted": "#a855f7",
        "mentioned": "#10b981",
        "co_appears_in_thread": "#8b949e",
    }
    role_radius = {
        "official": 14,
        "employee": 10,
        "developer": 9,
        "critic": 9,
        "community": 8,
        "suspicious_actor": 8,
        "unknown": 7,
    }
    role_color = {
        "official": "#58a6ff",
        "employee": "#10b981",
        "developer": "#22d3ee",
        "critic": "#ef4444",
        "community": "#a3a3a3",
        "suspicious_actor": "#eab308",
        "unknown": "#6b7280",
    }

    parts: list[str] = [
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg" class="account-graph">'
    ]
    # Edges
    seen_edge_types: dict[tuple[str, str], str] = {}
    for e in edges:
        if e.from_handle in nodes and e.to_handle in nodes:
            a, b = sorted([e.from_handle, e.to_handle])
            key = (a, b)
            if key not in seen_edge_types:
                seen_edge_types[key] = e.edge_type
    for (a, b), etype in seen_edge_types.items():
        x1, y1 = pos[a]
        x2, y2 = pos[b]
        color = edge_color.get(etype, "#9ca3af")
        parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="1" stroke-opacity="0.5"/>'
        )
    # Nodes
    for h, a in nodes.items():
        x, y = pos[h]
        r = role_radius.get(a.role, 7)
        color = role_color.get(a.role, "#9ca3af")
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}" '
            f'stroke="#0b0f14" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{y + r + 10:.1f}" text-anchor="middle" '
            f'fill="#e6edf3" font-size="9">@{h}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


# ----------------------------------------------------------------------
# Plan 2026-07-11-002 (U4): derive_edges / find_clusters / role_tag
# moved here from the deleted `x_monitor.accounts` module. The
# data/accounts/*.yaml loaders (load_accounts, load_staff) are gone
# — `brands_accounts` is canonical. The in-code derivations below
# continue to work against post-fetch posts and account dicts.
# ----------------------------------------------------------------------


def derive_edges(posts: list[dict], brand_id: str) -> list[Edge]:
    """Derive edges from post SOURCE FIELDS only (R11 contract).

    Inputs are dicts with at least: id, author_id, in_reply_to_user_id,
    quoted_status_id, entities (with user_mentions[]), conversation_id.
    """
    edges: list[Edge] = []
    for post in posts:
        author = post.get("author_handle") or post.get("author_id")
        if not author:
            continue
        pid = post.get("id", "")

        # replied_to
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

        # quoted
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

        # mentioned
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

    # co_appears_in_thread — derive from shared conversation_id
    by_conv: dict[str, list[str]] = defaultdict(list)
    for post in posts:
        conv = post.get("conversation_id")
        author = post.get("author_handle") or post.get("author_id")
        if conv and author:
            by_conv[str(conv)].append(str(author))

    for conv, authors in by_conv.items():
        unique = list(dict.fromkeys(authors))
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


def find_clusters(
    posts: list[dict],
    edges: list[Edge],
    min_commenters: int,
    min_posts: int,
) -> list[Cluster]:
    """Find reply-chain clusters (R13): >=min_commenters commenters
    appearing on >=min_posts of the same official's posts."""
    official_to_combos: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for post in posts:
        author = post.get("author_handle") or post.get("author_id")
        in_reply = post.get("in_reply_to_user_id")
        pid = post.get("id")
        if author and in_reply and str(in_reply) != str(author) and pid:
            official_to_combos[str(in_reply)].add((str(author), str(pid)))

    clusters: list[Cluster] = []
    inferred_model = edges[0].brand_id if edges else "unknown"
    for official, combos in official_to_combos.items():
        if len(combos) < min_posts:
            continue
        commenters = sorted({c for c, _ in combos})
        post_ids = sorted({p for _, p in combos})
        covered_posts: set[str] = set()
        for c, p in combos:
            covered_posts.add(p)
        if len(covered_posts) < min_posts:
            continue
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


def role_tag(
    account: Account,
    posts_for_account: list[dict] | None = None,
    brand_terms: list[str] | None = None,
) -> RoleType:
    """Upgrade an account's role based on evidence.

    Starter rules:
      - explicit role: "official" is never overridden
      - verified → employee
      - bio_contains_brand → developer
      - multiple_posts_in_thread_with_official >= 2 → community
      - suspicious_actor heuristic: avg >10 faves, 0 replies, no bio
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
