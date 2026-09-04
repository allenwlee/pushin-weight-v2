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
    assert len(set(RUNTIME_SYMBOLS)) == 33
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
        symbol_id for symbol_id in RUNTIME_SYMBOLS if symbol_id != "icon-role-badge"
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
        if symbol_id != "icon-role-badge"
    } == expected_runtime_symbols
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
