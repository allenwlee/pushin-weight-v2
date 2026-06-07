# {{AGENT_ATTRIBUTION}}
"""Force-directed account graph (Fruchterman-Reingold, inline SVG, no d3)."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Iterable

from .accounts import Account, Edge


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
