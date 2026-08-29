#!/usr/bin/env python3
"""Build the deterministic three-country SVG flag review artifacts."""

from __future__ import annotations

import argparse
import html
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
HTML_PATH = (
    REPO_ROOT / "docs/ideation/2026-08-29-162947-country-flag-svg-reference.html"
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


def _embedded_sprite(manifest: dict) -> str:
    sprite = render_sprite(manifest)
    sprite = sprite.removeprefix('<?xml version="1.0" encoding="UTF-8"?>\n')
    return sprite.replace("<svg ", '<svg class="sprite" ', 1).rstrip()


def _flag_svg(code: str, class_name: str, width: str, height: str) -> str:
    return (
        f'<svg class="flag-art {class_name}" width="{width}" height="{height}" '
        'viewBox="0 0 16 9" preserveAspectRatio="xMidYMid meet" '
        'aria-hidden="true" focusable="false">'
        f'<use href="#flag-{code.lower()}"></use></svg>'
    )


def _role_badge() -> str:
    return (
        '<span class="account-role role-official" role="img" '
        'aria-label="Official account">'
        '<svg class="role-badge" width="12" height="12" viewBox="0 0 24 24" '
        'aria-hidden="true" focusable="false">'
        '<path d="M11.83 3.18c1.1-.88 2.2-.83 3.08.18.63.73 1.3 1.01 '
        '2.25.91 1.38-.14 2.19.62 2.2 2.04.01.98.34 1.62 1.12 2.22 '
        '1.13.86 1.2 1.99.22 3.02-.67.7-.89 1.41-.7 2.36.28 1.39-.41 '
        '2.28-1.83 2.43-.96.1-1.58.49-2.1 1.31-.77 1.2-1.88 1.36-3 '
        '.46-.76-.61-1.49-.76-2.42-.48-1.36.41-2.32-.19-2.59-1.59-.19 '
        '-.95-.63-1.53-1.5-1.98-1.27-.66-1.52-1.75-.72-2.91.54-.8.63 '
        '-1.53.27-2.44-.52-1.32 0-2.32 1.37-2.7.94-.27 1.49-.75 '
        '1.86-1.65.53-1.32 1.59-1.65 2.83-1.18Z" fill="none" '
        'stroke="currentColor" stroke-width="1.45" stroke-linejoin="round"></path>'
        '<path d="M15.65 10.72c.08 2.16-1.45 3.8-3.65 3.9-2.18.1-3.81-1.39 '
        '-3.9-3.54-.1-2.21 1.42-3.87 3.66-3.97 2.23-.1 3.8 1.39 '
        '3.89 3.61Z" fill="none" stroke="currentColor" stroke-width="1.35"></path>'
        "</svg></span>"
    )


def _treatment_panel(flag: dict, treatment: str, label: str, note: str) -> str:
    code = flag["code"]
    handle = {
        "CN": "@beijing_signal",
        "KR": "@seoul_signal",
        "US": "@dc_signal",
    }[code]
    return f"""      <section class="treatment treatment--{treatment}" data-treatment="{treatment}">
        <header class="treatment-head">
          <span>{html.escape(label)}</span>
          <small>{html.escape(note)}</small>
        </header>
        <div class="inspection-stage">
          {_flag_svg(code, "flag-inspection", "128", "72")}
        </div>
        <div class="feed-sample">
          <span class="avatar" aria-hidden="true">{code[0]}</span>
          <div class="feed-copy">
            <div class="feed-account">
              <strong>{handle}</strong>
              {_role_badge()}
            </div>
            <span class="feed-meta">account signal · now</span>
          </div>
          <div class="feed-flags" aria-label="Flag size comparison">
            <span class="size-candidate">
              {_flag_svg(code, "flag-native", "16", "9")}
              <small>16</small>
            </span>
            <span class="size-candidate">
              {_flag_svg(code, "flag-compact", "14", "7.875")}
              <small>14</small>
            </span>
          </div>
        </div>
      </section>"""


def _flag_card(flag: dict) -> str:
    return f"""  <article class="flag-card" data-country-code="{flag['code']}">
    <header class="country-head">
      <span class="country-code">{flag['code']}</span>
      <div>
        <h3>{html.escape(flag['name'])}</h3>
        <p>ISO alpha-2 · source key {html.escape(flag['source_name'])}</p>
      </div>
    </header>
    <div class="treatment-grid">
{_treatment_panel(flag, "original", "Original", "Source color, unchanged")}
{_treatment_panel(flag, "recommended", "Recommended", "72% saturation · 90% brightness · 90% opacity")}
{_treatment_panel(flag, "quiet", "Quieter", "52% saturation · 82% brightness · 82% opacity")}
    </div>
  </article>"""


def render_html(manifest: dict) -> str:
    """Render the standalone PushinWeight feed-context review dossier."""

    validate_manifest(manifest)
    source = manifest["source"]
    cards = "\n".join(_flag_card(flag) for flag in manifest["flags"])
    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PushinWeight — Three-country SVG flag trial</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b1220;
      --card: #111827;
      --card-raised: #172033;
      --line: #1f2937;
      --line-strong: #334155;
      --text: #f3f4f6;
      --muted: #94a3b8;
      --faint: #64748b;
      --cyan: #67e8f9;
      --official: #fbbf24;
      --sans: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
    }

    * { box-sizing: border-box; }
    html { background: var(--bg); }
    body {
      margin: 0;
      min-width: 320px;
      color: var(--text);
      background:
        radial-gradient(circle at 80% -10%, rgba(34, 211, 238, .07), transparent 32rem),
        var(--bg);
      font-family: var(--sans);
      line-height: 1.5;
    }
    .sprite { position: absolute; width: 0; height: 0; overflow: hidden; }
    .shell { width: min(1180px, calc(100% - 40px)); margin: 0 auto; }

    .masthead {
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(280px, .65fr);
      gap: 40px;
      padding: 72px 0 48px;
      border-bottom: 1px solid var(--line);
    }
    .eyebrow, .fact-label, .country-code, .treatment-head, .status {
      font-family: var(--mono);
      text-transform: uppercase;
      letter-spacing: .11em;
    }
    .eyebrow { margin: 0 0 18px; color: var(--cyan); font-size: 11px; }
    h1 { max-width: 760px; margin: 0; font-size: clamp(44px, 7vw, 88px); line-height: .93; letter-spacing: -.055em; }
    .lede { max-width: 680px; margin: 26px 0 0; color: var(--muted); font-size: 18px; }
    .status-card { align-self: end; padding: 22px; border: 1px solid var(--line-strong); background: rgba(17, 24, 39, .72); }
    .status { display: block; margin-bottom: 12px; color: var(--official); font-size: 10px; }
    .status-card strong { display: block; margin-bottom: 8px; font-size: 19px; }
    .status-card p { margin: 0; color: var(--muted); font-size: 13px; }

    .facts { display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid var(--line); border-top: 0; }
    .fact { min-width: 0; padding: 18px 20px; border-right: 1px solid var(--line); }
    .fact:last-child { border-right: 0; }
    .fact-label { display: block; margin-bottom: 5px; color: var(--faint); font-size: 9px; }
    .fact strong { font-size: 14px; }

    .decision-note { display: grid; grid-template-columns: 160px 1fr; gap: 24px; margin: 48px 0; padding: 24px; border-left: 2px solid var(--cyan); background: rgba(17, 24, 39, .66); }
    .decision-note h2 { margin: 0; font-family: var(--mono); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }
    .decision-note p { margin: 0; color: var(--muted); }
    .decision-note strong { color: var(--text); }

    .section-head { display: flex; align-items: end; justify-content: space-between; gap: 24px; margin: 0 0 22px; }
    .section-head h2 { margin: 0; font-size: 30px; letter-spacing: -.025em; }
    .section-head p { max-width: 560px; margin: 0; color: var(--muted); font-size: 14px; }

    .flag-card { margin-bottom: 28px; border: 1px solid var(--line); background: var(--card); }
    .country-head { display: flex; align-items: center; gap: 18px; padding: 20px 22px; border-bottom: 1px solid var(--line); }
    .country-code { display: grid; place-items: center; width: 50px; height: 50px; border: 1px solid var(--line-strong); color: var(--cyan); font-size: 12px; }
    .country-head h3 { margin: 0 0 2px; font-size: 21px; }
    .country-head p { margin: 0; color: var(--faint); font-family: var(--mono); font-size: 10px; }

    .treatment-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .treatment { min-width: 0; padding: 20px; border-right: 1px solid var(--line); }
    .treatment:last-child { border-right: 0; }
    .treatment--recommended { background: linear-gradient(rgba(103, 232, 249, .035), rgba(103, 232, 249, .012)); box-shadow: inset 0 2px var(--cyan); }
    .treatment-head { min-height: 45px; font-size: 10px; }
    .treatment-head span { display: block; margin-bottom: 4px; color: var(--text); }
    .treatment-head small { color: var(--faint); font-family: var(--sans); font-size: 10px; letter-spacing: 0; text-transform: none; }

    .inspection-stage { display: grid; min-height: 112px; margin: 12px 0 20px; place-items: center; border: 1px solid var(--line); background: #0d1524; overflow: hidden; }
    .flag-art { display: block; flex: 0 0 auto; overflow: visible; shape-rendering: crispEdges; }
    .treatment--original .flag-art { filter: none; opacity: 1; }
    .treatment--recommended .flag-art {
      filter: saturate(0.72) brightness(0.90);
      opacity: 0.90;
    }
    .treatment--quiet .flag-art {
      filter: saturate(0.52) brightness(0.82);
      opacity: 0.82;
    }

    .feed-sample { display: grid; grid-template-columns: 30px minmax(0, 1fr) auto; align-items: center; gap: 10px; min-width: 0; padding: 11px; border: 1px solid var(--line); background: #0b1220; }
    .avatar { display: grid; place-items: center; width: 30px; height: 30px; border-radius: 50%; color: var(--bg); background: var(--muted); font-size: 11px; font-weight: 800; }
    .feed-copy { min-width: 0; }
    .feed-account { display: flex; align-items: center; min-width: 0; gap: 3px; }
    .feed-account strong { overflow: hidden; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
    .feed-meta { display: block; overflow: hidden; color: var(--faint); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
    .account-role { display: inline-flex; align-items: center; justify-content: center; width: 14px; height: 12px; margin-top: 2px; color: var(--official); flex: 0 0 auto; }
    .role-badge { display: block; }
    .feed-flags { display: flex; align-items: end; gap: 9px; }
    .size-candidate { display: grid; min-width: 18px; justify-items: center; gap: 3px; }
    .size-candidate small { color: var(--faint); font-family: var(--mono); font-size: 7px; line-height: 1; }

    footer { margin-top: 54px; padding: 28px 0 54px; border-top: 1px solid var(--line); color: var(--faint); font-size: 12px; }
    footer strong { color: var(--muted); }
    footer code { font-family: var(--mono); font-size: 10px; }

    @media (max-width: 820px) {
      .shell { width: min(100% - 24px, 620px); }
      .masthead { grid-template-columns: 1fr; gap: 28px; padding-top: 48px; }
      .facts { grid-template-columns: repeat(2, 1fr); }
      .fact:nth-child(2) { border-right: 0; }
      .fact:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
      .decision-note { grid-template-columns: 1fr; gap: 10px; }
      .section-head { align-items: start; flex-direction: column; }
      .treatment-grid { grid-template-columns: 1fr; }
      .treatment { border-right: 0; border-bottom: 1px solid var(--line); }
      .treatment:last-child { border-bottom: 0; }
    }

    @media print {
      :root { color-scheme: light; }
      body { color: #111827; background: #fff; }
      .flag-card, .status-card, .decision-note, .feed-sample, .inspection-stage { background: #fff; break-inside: avoid; }
      .flag-card, .facts, .fact, .country-head, .treatment, footer { border-color: #cbd5e1; }
    }
  </style>
</head>
<body>
{{SPRITE}}
<header class="shell masthead">
  <div>
    <p class="eyebrow">PushinWeight / design trial / 2026-08-29</p>
    <h1>Country flags at feed weight.</h1>
    <p class="lede">Three exact 16×9 pixel flags, converted to reusable SVG symbols. Compare source color against two presentation-only reductions before the remaining 194 flags or any homepage integration.</p>
  </div>
  <aside class="status-card">
    <span class="status">Review boundary</span>
    <strong>3 flags · 0 runtime changes</strong>
    <p>Review artifact only — no live feed integration. The sprite stays under ideation until a size and color treatment are approved.</p>
  </aside>
</header>

<main class="shell">
  <section class="facts" aria-label="Trial facts">
    <div class="fact"><span class="fact-label">Inventory</span><strong>CN · KR · US</strong></div>
    <div class="fact"><span class="fact-label">Source grid</span><strong>16 × 9 pixels</strong></div>
    <div class="fact"><span class="fact-label">Feed peers</span><strong>12 px role badge</strong></div>
    <div class="fact"><span class="fact-label">SVG units</span><strong>3 symbols</strong></div>
  </section>

  <aside class="decision-note">
    <h2>Color approach</h2>
    <p><strong>Keep source fills fixed.</strong> Reduce only the displayed SVG instance with CSS. The recommended starting point uses 72% saturation, 90% brightness, and 90% opacity so flags remain identifiable without competing with role or sentiment accents.</p>
  </aside>

  <div class="section-head">
    <h2>Feed-context comparison</h2>
    <p>Each treatment shows the same source symbol at 8× inspection scale, native 16×9, and 14 px wide at its natural 16:9 height. The official-account badge preserves the current 14×12 slot and 12×12 icon geometry.</p>
  </div>

{{CARDS}}
</main>

<footer class="shell">
  <strong>{{ATTRIBUTION}}</strong> · Top Gun <code>{{TOP_GUN_COMMIT}}</code> · R74n <code>{{R74N_REVISION}}</code>. License clearance confirmed by the owner for this PushinWeight use. SVG path fills remain exact to the vendored matrices; muting is presentation-only.
</footer>
</body>
</html>
"""
    return (
        template.replace("{{SPRITE}}", _embedded_sprite(manifest))
        .replace("{{CARDS}}", cards)
        .replace("{{ATTRIBUTION}}", html.escape(source["attribution"]))
        .replace("{{TOP_GUN_COMMIT}}", source["top_gun_commit"])
        .replace("{{R74N_REVISION}}", source["r74n_revision"])
    )


def _check_file(path: Path, expected: str) -> bool:
    if not path.exists() or path.read_text(encoding="utf-8") != expected:
        display_path = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
        print(f"out of date: {display_path}", file=sys.stderr)
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    manifest = load_manifest()
    sprite = render_sprite(manifest)
    dossier = render_html(manifest)
    if args.check:
        checks = (
            _check_file(SPRITE_PATH, sprite),
            _check_file(HTML_PATH, dossier),
        )
        return 0 if all(checks) else 1

    SPRITE_PATH.write_text(sprite, encoding="utf-8")
    HTML_PATH.write_text(dossier, encoding="utf-8")
    print(f"wrote {SPRITE_PATH.relative_to(REPO_ROOT)}")
    print(f"wrote {HTML_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
