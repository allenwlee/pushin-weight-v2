#!/usr/bin/env python3
"""Build the deterministic three-country SVG flag review artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    REPO_ROOT
    / "docs/ideation/assets/2026-08-29-162947-country-flag-pixels.json"
)
SPRITE_PATH = (
    REPO_ROOT
    / "docs/ideation/assets/2026-08-29-162947-country-flag-sprite.svg"
)
EXPECTED_FLAGS = (
    ("CN", "China", "china"),
    ("KR", "South Korea", "south_korea"),
    ("US", "United States", "united_states"),
)
COLOR_PATTERN = re.compile(r"#[0-9A-F]{6}")


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    """Load and validate the committed pixel source."""

    manifest = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict) -> None:
    """Reject inventory, identity, dimension, or color drift."""

    if manifest.get("schema_version") != 1:
        raise ValueError("flag manifest schema_version must be 1")
    if manifest.get("dimensions") != {"width": 16, "height": 9}:
        raise ValueError("flag manifest dimensions must be 16x9")
    source = manifest.get("source")
    if not isinstance(source, dict) or set(source) != {
        "top_gun_commit",
        "r74n_revision",
        "attribution",
        "license_clearance",
    }:
        raise ValueError("flag manifest source metadata is incomplete")

    flags = manifest.get("flags")
    if not isinstance(flags, list):
        raise ValueError("flag manifest flags must be a list")
    identities = tuple(
        (flag.get("code"), flag.get("name"), flag.get("source_name"))
        for flag in flags
        if isinstance(flag, dict)
    )
    if len(identities) != len(flags) or identities != EXPECTED_FLAGS:
        raise ValueError("flag manifest inventory must be exactly CN, KR, and US")

    for flag in flags:
        if set(flag) != {"code", "name", "source_name", "pixels"}:
            raise ValueError(f"{flag['code']} has unexpected manifest fields")
        code = flag["code"]
        if not re.fullmatch(r"[A-Z]{2}", code):
            raise ValueError(f"{code!r} is not an uppercase alpha-2 code")
        pixels = flag["pixels"]
        if not isinstance(pixels, list) or len(pixels) != 9:
            raise ValueError(f"{code} must contain 9 pixel rows")
        for row in pixels:
            if not isinstance(row, list) or len(row) != 16:
                raise ValueError(f"{code} pixel rows must contain 16 cells")
            for cell in row:
                if cell is not None and (
                    not isinstance(cell, str) or not COLOR_PATTERN.fullmatch(cell)
                ):
                    raise ValueError(f"{code} contains invalid pixel color {cell!r}")


def _paths_by_color(pixels: list[list[str | None]]) -> dict[str, list[str]]:
    paths: dict[str, list[str]] = defaultdict(list)
    for y, row in enumerate(pixels):
        x = 0
        while x < 16:
            color = row[x]
            if color is None:
                x += 1
                continue
            right = x + 1
            while right < 16 and row[right] == color:
                right += 1
            paths[color].append(f"M{x} {y}h{right - x}v1H{x}z")
            x = right
    return dict(paths)


def render_sprite(manifest: dict) -> str:
    """Render one path per source color, composed of horizontal pixel runs."""

    validate_manifest(manifest)
    source = manifest["source"]
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">',
        "  <!-- Pixel flags by R74n; source revisions: "
        f"Top Gun {source['top_gun_commit']}, R74n {source['r74n_revision']}. -->",
    ]
    for flag in manifest["flags"]:
        lines.append(
            f'  <symbol id="flag-{flag["code"].lower()}" viewBox="0 0 16 9" '
            'shape-rendering="crispEdges">'
        )
        for color, commands in _paths_by_color(flag["pixels"]).items():
            lines.append(f'    <path fill="{color}" d="{" ".join(commands)}"/>')
        lines.append("  </symbol>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _check_file(path: Path, expected: str) -> bool:
    if not path.exists() or path.read_text(encoding="utf-8") != expected:
        print(f"out of date: {path.relative_to(REPO_ROOT)}", file=sys.stderr)
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    sprite = render_sprite(load_manifest())
    if args.check:
        return 0 if _check_file(SPRITE_PATH, sprite) else 1

    SPRITE_PATH.write_text(sprite, encoding="utf-8")
    print(f"wrote {SPRITE_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
