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
ALTERNATE_SOURCE = REPO_ROOT / "docs/ideation/2026-08-29-161106-cyber-quan-icon-alts.html"
ALTERNATE_SOURCE_SHA256 = "dae29084a247656169dd3e076f0d616390c4fe6f791c697a38a7f8076ad55d81"
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
    "a-opportunity",
    "a-jobs",
    "a-personnel",
    "a-opinions",
    "a-research",
    "a-finance",
    "a-other",
    "icon-caret",
    "icon-sunrise",
    "icon-day",
    "icon-dusk",
    "icon-night",
)

APPROVED_ALTERNATE_SYMBOLS = {
    "icon-rise": "alt-rise",
    "icon-fall": "alt-fall",
    "icon-followers-1": "alt-followers-1",
    "icon-followers-3": "alt-followers-3",
    "icon-sentiment-neutral": "alt-neutral",
    "icon-hands-on-hammer": "alt-hand-point-up-right",
    "icon-california": "alt-california-badge",
}

LOCKED_COLUMN_A_SYMBOLS = {
    "a-opportunity": '<path d="M7.02 4.78c3.22-.23 6.49-.25 9.81-.05l-.23 3.75c-.24 3.87-1.78 5.92-4.65 6.03-2.88.1-4.52-1.86-4.72-5.75l-.21-3.98Z" fill="none" stroke="currentColor" stroke-width="1.55" stroke-linejoin="round"/><path d="M7.15 6.62 4.2 6.7c.13 3.25 1.22 4.92 3.61 5.37m8.9-5.58 3.06-.04c-.02 3.26-1.05 4.98-3.41 5.51m-4.42 2.73.05 2.42m-3.33 2.14c2.23-.17 4.48-.2 6.75-.08m-5.12-2.02 3.37-.06" fill="none" stroke="currentColor" stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round"/>',
    "a-jobs": '<path d="M3.56 8.45c5.54-.35 11.13-.38 16.78-.08l.18 10.5c-5.63.31-11.23.34-16.82.09l-.14-10.51Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M8.46 8.18c.05-2.16 1.13-3.32 3.38-3.39 2.28-.07 3.46 1.04 3.56 3.3M3.78 12.04c5.41 1.18 10.94 1.14 16.58-.13m-9.9.85.03 1.47 2.97-.03-.02-1.5" fill="none" stroke="currentColor" stroke-width="1.55" stroke-linecap="round" stroke-linejoin="round"/>',
    "a-personnel": '<circle cx="7.08" cy="7.2" r="2.58" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M2.95 18.75c.28-4.1 1.65-6.06 4.18-6.13 2.48-.08 3.85 1.7 4.22 5.54" fill="none" stroke="currentColor" stroke-width="1.55" stroke-linecap="round"/><circle cx="17.63" cy="8.07" r="2.08" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M14.2 18.29c.24-3.43 1.37-5.02 3.48-5.09 2.1-.06 3.25 1.45 3.55 4.8M10.2 9.52l3.62-.04m-1.2-1.35 1.28 1.34-1.22 1.45" fill="none" stroke="currentColor" stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round"/>',
    "a-opinions": '<path d="M4.73 17.67c-1.03-1.18-1.56-2.65-1.47-4.32.2-3.84 3.28-6.52 7.39-6.51 4.16.01 7.09 2.51 7.19 6.17.1 3.52-3.01 6.09-7.14 6.04-1.08-.01-2.07-.19-2.98-.53l-3.61 1.52.62-2.37Z" fill="none" stroke="currentColor" stroke-width="1.55" stroke-linecap="round" stroke-linejoin="round"/><path d="m8.04 13.36 1.69-2.06 1.64 2.02 1.74-2.2 1.75 1.87M18.03 7.14l1.19-1.3m-3.28-.05.34-1.74m3.4 4.84 1.77-.08" fill="none" stroke="currentColor" stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round"/>',
    "a-research": '<path d="M3.45 6.57c3.26-.29 6.07.38 8.38 2.01 2.23-1.71 5.14-2.45 8.69-2.21l-.08 12.46c-3.42-.21-6.27.53-8.57 2.03-2.41-1.48-5.17-2.14-8.3-1.98L3.45 6.57Z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="m11.83 8.62.04 12.02M6.33 10.27c1.05-.02 2.01.17 2.91.57m-2.86 2.2c1-.01 1.95.17 2.84.55m5.47-3.38c1.02-.28 1.98-.35 2.91-.24m-2.86 2.99c1-.27 1.96-.35 2.89-.23" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round"/>',
    "a-finance": '<path d="M10.2 6.8c-.8-.61-1.79-.88-2.98-.8-1.57.1-2.57.89-2.49 2.02.09 1.2 1.04 1.61 2.91 2.06 1.84.45 2.76.99 2.85 2.29.09 1.33-.95 2.25-2.69 2.35-1.33.08-2.48-.24-3.43-.96M7.08 4.12l.82 12.53" fill="none" stroke="currentColor" stroke-width="1.45" stroke-linecap="round"/><path d="m14.03 5.34 3.05 4.07 2.48-4.2m-5.18 5.23c1.79-.15 3.53-.17 5.24-.06m-4.97 2.42c1.59-.12 3.15-.13 4.68-.04m-2.18-3.1.18 6.74" fill="none" stroke="currentColor" stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round"/>',
    "a-other": '<path d="M20.06 11.74c.1 4.43-3.18 7.78-7.84 7.95-4.6.17-8.03-2.88-8.15-7.29-.12-4.51 3.1-7.97 7.81-8.15 4.75-.18 8.06 2.95 8.18 7.49Z" fill="none" stroke="currentColor" stroke-width="1.55" stroke-dasharray="1.1 2.1" stroke-linecap="round"/><path d="M7.82 12.1h.01m4.1-.13h.01m4.09-.12h.01" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>',
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
    alternate_source = ALTERNATE_SOURCE.read_text(encoding="utf-8")
    assert hashlib.sha256(alternate_source.encode()).hexdigest() == ALTERNATE_SOURCE_SHA256
    alternate_symbols = {
        symbol_id: re.sub(r"\s+", "", body)
        for symbol_id, _, body in _symbols(alternate_source)
    }
    view_boxes = {symbol_id: view_box for symbol_id, view_box, _ in symbols}

    assert tuple(symbol_id for symbol_id, _, _ in symbols) == RUNTIME_SYMBOLS
    assert len(set(RUNTIME_SYMBOLS)) == 40
    assert view_boxes["mark-quiet"] == "4.24 2.3494 15.55 19.2724"
    assert all(
        view_box == "0 0 24 24"
        for symbol_id, view_box, _ in symbols
        if symbol_id != "mark-quiet"
    )
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
        symbol_id
        for symbol_id in RUNTIME_SYMBOLS
        if symbol_id != "icon-role-badge" and symbol_id not in LOCKED_COLUMN_A_SYMBOLS
    )
    expected_runtime_symbols = {
        symbol_id: re.sub(
            r"\s+",
            "",
            alternate_symbols[APPROVED_ALTERNATE_SYMBOLS[symbol_id]]
            if symbol_id in APPROVED_ALTERNATE_SYMBOLS
            else dossier_symbols[symbol_id],
        )
        for symbol_id in dossier_runtime_symbols
    }
    assert {
        symbol_id: re.sub(r"\s+", "", body)
        for symbol_id, _, body in symbols
        if symbol_id != "icon-role-badge" and symbol_id not in LOCKED_COLUMN_A_SYMBOLS
    } == expected_runtime_symbols
    runtime_bodies = {
        symbol_id: re.sub(r"\s+", "", body) for symbol_id, _, body in symbols
    }
    assert {
        symbol_id: runtime_bodies[symbol_id] for symbol_id in LOCKED_COLUMN_A_SYMBOLS
    } == {
        symbol_id: re.sub(r"\s+", "", body)
        for symbol_id, body in LOCKED_COLUMN_A_SYMBOLS.items()
    }
    assert not any(symbol_id.startswith("b-") for symbol_id in runtime_bodies)
    assert set(APPROVED_ALTERNATE_SYMBOLS) == {
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
