"""Regression contract for the owner-approved Cyber-Quan icon family."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOSSIER_ROOT = REPO_ROOT / "docs/ideation/mockups/qin-quan"
SOURCE_FILES = (
    DOSSIER_ROOT / "2026-08-28-134649-cyber-quan-svg-system-en.html",
    DOSSIER_ROOT / "2026-08-28-134649-cyber-quan-svg-system-zh-cn.html",
)
SOURCE_CSS = "2026-08-28-134649-cyber-quan-svg-system.css"
FULL_SPRITE_SHA256 = "9a5fd90add8e5d60baf87796054b0211fbb94d9ad92e952fc5133465eb9da658"
SPRITE = REPO_ROOT / "monitor/templates/monitor/_cyber_quan_sprite.html"
HELPER = REPO_ROOT / "monitor/static/pw-icons.js"
HOME_CSS = REPO_ROOT / "monitor/static/home-v20.css"

SOURCE_SYMBOLS = (
    "mark-quiet",
    "mark-cast",
    "mark-bulbous",
    "mark-bulbous-dome",
    "mark-bulbous-orb",
    "icon-heart",
    "icon-reply",
    "icon-repost",
    "icon-rise",
    "icon-flat",
    "icon-fall",
    "icon-followers-1",
    "icon-followers-2",
    "icon-followers-3",
    "icon-followers-4",
    "icon-sentiment-neutral",
    "icon-sentiment-negative",
    "icon-sentiment-mixed",
    "icon-hands-on-hammer",
    "icon-hands-on-chisel",
    "icon-compare",
    "icon-question",
    "icon-marketing",
    "icon-event",
    "icon-discourse",
    "icon-nationalism",
    "icon-unsanctioned",
    "icon-california",
    "icon-beijing",
    "icon-sentiment",
    "icon-announce",
    "icon-moderation",
    "icon-star",
    "icon-caret",
    "icon-sunrise",
    "icon-day",
    "icon-dusk",
    "icon-night",
)

RUNTIME_SYMBOLS = (
    "mark-quiet",
    "icon-heart",
    "icon-reply",
    "icon-repost",
    "icon-rise",
    "icon-flat",
    "icon-fall",
    "icon-followers-1",
    "icon-followers-2",
    "icon-followers-3",
    "icon-followers-4",
    "icon-role-badge",
    "icon-sentiment-neutral",
    "icon-sentiment-negative",
    "icon-sentiment-mixed",
    "icon-hands-on-hammer",
    "icon-compare",
    "icon-question",
    "icon-marketing",
    "icon-event",
    "icon-discourse",
    "icon-nationalism",
    "icon-unsanctioned",
    "icon-california",
    "icon-beijing",
    "icon-sentiment",
    "icon-announce",
    "icon-star",
    "icon-caret",
    "icon-sunrise",
    "icon-day",
    "icon-dusk",
    "icon-night",
)

APPROVED_RUNTIME_OVERRIDES = {
    "icon-rise": '<path fill="currentColor" d="M12.15 6.05 2.85 17.35l18.45-.4Z"/>',
    "icon-fall": '<path fill="currentColor" d="M12.1 17.95 2.8 6.7l18.5.35Z"/>',
    "icon-followers-1": """
      <circle cx="11.78" cy="6.7" r="2.82" fill="none" stroke="currentColor" stroke-width="1.55"/>
      <path d="M6.53 19.65c.32-4.72 2.05-6.9 5.22-7.01 3.15-.11 4.84 2.02 5.25 6.73" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"/>
    """,
    "icon-followers-3": """
      <circle cx="5.12" cy="7.85" r="1.72" fill="none" stroke="currentColor" stroke-width="1.28"/>
      <circle cx="11.94" cy="6.45" r="2.02" fill="none" stroke="currentColor" stroke-width="1.32"/>
      <circle cx="18.88" cy="7.55" r="1.74" fill="none" stroke="currentColor" stroke-width="1.28"/>
      <path d="M1.48 19.12c.23-3.36 1.43-4.95 3.65-5.02 2.13-.07 3.28 1.31 3.6 4.43M7.96 18.5c.27-4.05 1.64-5.91 4.15-6 2.5-.08 3.84 1.72 4.17 5.74m-.07-.04c.28-3.41 1.45-4.97 3.62-5.05 2.21-.07 3.41 1.49 3.69 4.85" fill="none" stroke="currentColor" stroke-width="1.36" stroke-linecap="round"/>
    """,
    "icon-sentiment-neutral": """
      <path d="M20.24 11.88c.12 4.57-3.27 8.01-8.08 8.18-4.74.18-8.28-2.97-8.4-7.52-.13-4.66 3.19-8.23 8.05-8.42 4.9-.19 8.31 3.04 8.43 7.76Z" fill="none" stroke="currentColor" stroke-width="1.6"/>
      <path d="M8.75 10.02h.01m6.46-.19h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
    """,
    "icon-hands-on-hammer": """
      <g transform="rotate(45 12 12)" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10.16 21.72 5.72 15.5c-.72-1-.48-2.38.52-3.08.98-.68 2.3-.45 3.02.5l1.06 1.42V4.38c0-1.38 1.1-2.48 2.47-2.48 1.34 0 2.44 1.1 2.44 2.48v5.74c.37-.76 1.14-1.28 2.04-1.28 1.18 0 2.14.9 2.25 2.04.38-.43.94-.7 1.56-.7 1.16 0 2.1.95 2.1 2.11v3.25c0 3.88-2.66 6.34-6.52 6.34h-5.64c-.34 0-.65-.05-.86-.16Z" stroke-width="1.55"/>
        <path d="M15.2 10.1v3.18m4.3-2.42v2.98" stroke-width="1.15"/>
      </g>
    """,
    "icon-california": '<path d="M5.08 1.88 12.72 2l-.08 5.18 2.4 3.26 2.52 2.55 3.76 3.72-.82 3.7-3.26 1.46-1.96-2.28-2.72-1.3-1.83-2.38-1.83-1.02-.72-2.18-1.4-1.22.72-.86-.94-.68-.4-2.16-1.25-2.57-.13-2.48-1.1-1.54Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
}


def _symbols(source: str) -> list[tuple[str, str, str]]:
    return re.findall(
        r'<symbol id="([^"]+)" viewBox="([^"]+)">(.*?)</symbol>',
        source,
        flags=re.DOTALL,
    )


def test_bilingual_dossier_has_the_same_complete_source_inventory() -> None:
    inventories = []
    for source_path in SOURCE_FILES:
        source = source_path.read_text(encoding="utf-8")
        symbols = _symbols(source)
        inventories.append(tuple(symbol_id for symbol_id, _, _ in symbols))
        assert SOURCE_CSS in source
        assert len(symbols) == len(SOURCE_SYMBOLS)
        assert all(view_box == "0 0 24 24" for _, view_box, _ in symbols)
        assert all(re.search(r"<(?:path|circle|line|polyline|polygon|rect)\b", body) for _, _, body in symbols)
        sprite = re.search(
            r'  <svg class="sprite".*?^  </svg>\n',
            source,
            flags=re.DOTALL | re.MULTILINE,
        )
        assert sprite
        assert hashlib.sha256(sprite.group(0).encode()).hexdigest() == FULL_SPRITE_SHA256

    assert inventories == [SOURCE_SYMBOLS, SOURCE_SYMBOLS]


def test_runtime_sprite_is_the_exact_approved_subset() -> None:
    source = SPRITE.read_text(encoding="utf-8")
    symbols = _symbols(source)

    assert tuple(symbol_id for symbol_id, _, _ in symbols) == RUNTIME_SYMBOLS
    assert len(set(RUNTIME_SYMBOLS)) == 33
    assert all(view_box == "0 0 24 24" for _, view_box, _ in symbols)
    assert all(re.search(r"<(?:path|circle|line|polyline|polygon|rect)\b", body) for _, _, body in symbols)
    assert set(SOURCE_SYMBOLS) - set(RUNTIME_SYMBOLS) == {
        "mark-cast",
        "mark-bulbous",
        "mark-bulbous-dome",
        "mark-bulbous-orb",
        "icon-hands-on-chisel",
        "icon-moderation",
    }

    dossier_symbols = {
        symbol_id: re.sub(r"\s+", "", body)
        for symbol_id, _, body in _symbols(SOURCE_FILES[0].read_text(encoding="utf-8"))
    }
    dossier_runtime_symbols = tuple(
        symbol_id for symbol_id in RUNTIME_SYMBOLS if symbol_id != "icon-role-badge"
    )
    expected_runtime_symbols = {
        symbol_id: re.sub(
            r"\s+",
            "",
            APPROVED_RUNTIME_OVERRIDES.get(symbol_id, dossier_symbols[symbol_id]),
        )
        for symbol_id in dossier_runtime_symbols
    }
    assert {
        symbol_id: re.sub(r"\s+", "", body)
        for symbol_id, _, body in symbols
        if symbol_id != "icon-role-badge"
    } == expected_runtime_symbols
    assert set(APPROVED_RUNTIME_OVERRIDES) == {
        "icon-rise",
        "icon-fall",
        "icon-followers-1",
        "icon-followers-3",
        "icon-sentiment-neutral",
        "icon-hands-on-hammer",
        "icon-california",
    }
    assert "icon-role-badge" not in SOURCE_SYMBOLS


def test_client_helper_is_constant_only_and_fail_closed() -> None:
    source = HELPER.read_text(encoding="utf-8")

    assert "global.pwIcon = api;" in source
    assert "ALLOWED_SYMBOLS" in source
    assert "if (!ALLOWED_SYMBOLS[symbolId]) return '';" in source
    assert "aria-hidden=\"true\"" in source
    for symbol_id in RUNTIME_SYMBOLS:
        assert f"'{symbol_id}': true" in source


def test_follower_magnitude_and_sentiment_keep_the_approved_semantic_colors() -> None:
    source = HOME_CSS.read_text(encoding="utf-8")

    follower_colors = {
        "follower-lead": "#64748b",
        "follower-bin-1k-10k": "#8492a6",
        "follower-bin-10k-50k": "#cbd5e1",
        "follower-bin-50k-plus": "#f8fafc",
    }
    for selector, color in follower_colors.items():
        block = re.search(rf"\.{selector}\s*\{{(?P<body>.*?)\}}", source, flags=re.DOTALL)
        assert block
        assert f"--follower-color: {color};" in block.group("body")

    assert ".feed-signals .tone-positive { color: var(--up); }" in source
    assert ".feed-signals .tone-neutral { color: var(--muted); }" in source
    assert ".feed-signals .tone-negative { color: var(--down); }" in source
    assert ".feed-signals .tone-mixed { color: #fbbf24; }" in source
