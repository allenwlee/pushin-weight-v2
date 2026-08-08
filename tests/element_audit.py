"""
Element Audit — Chrome DevTools MCP-driven visual drift detector.

Per plan § "Visual-drift detection: Element Audit + Chrome DevTools MCP
(added 2026-08-08)": reads pinned computed-style values from
`tests/visual_tokens.py`, then via Chrome DevTools MCP captures the live
page's getComputedStyle() for each region and diffs against the pin.

This is the **visual layer** of the regression net. Pairs with
`tests/regression_net.py` (structural layer).

Usage:
    # Pre-req: Django dev server on fuchitalee:5050 reachable via SSH tunnel
    #   ssh -o NoMosH=1 -f -N -L 5050:127.0.0.1:5000 fuchitalee
    .venv/bin/python tests/element_audit.py [--live-url URL] [--mockup-url URL]

Defaults:
    --live-url    http://127.0.0.1:5050/?locale=en
    --mockup-url  http://127.0.0.1:8001/06-tier1-composed.v22-master.html

Exit code 0 on all-pinned-values-match, 1 on any drift.

NOTE: This script is INTENTIONALLY a CLI that does NOT import chrome-devtools
SDK directly — the agent that runs the audit uses the Chrome DevTools MCP
tools (mcp__chrome-devtools__*) to navigate + evaluate_script, then writes
the captured live values to /tmp/element_audit_live.json; this script reads
that JSON. This separation keeps the audit reproducible without requiring
the agent's MCP session in the test runner.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from visual_tokens import VISUAL_TOKENS, regions, pinned  # noqa: E402


def audit(live_values: dict, mockup_values: dict | None = None) -> tuple[int, list[str]]:
    """Diff live values against pinned values. Return (fail_count, messages)."""
    fails: list[str] = []
    passes: list[str] = []
    skipped: list[str] = []

    for selector in regions():
        live = live_values.get(selector)
        mockup = (mockup_values or {}).get(selector)
        pin = pinned(selector)

        if live is None or live == "NOT FOUND":
            # Tolerate absence for data-dependent regions (e.g. .delta.up when no up-trending brands)
            if selector == ".delta.up::before":
                skipped.append(f"SKIP {selector} — data-dependent absence (no up-trending brands in current window)")
                continue
            fails.append(f"FAIL {selector} — element not found on live page (P0 element missing)")
            continue

        for prop, expected in pin.items():
            actual = live.get(prop)
            if actual is None:
                fails.append(f"FAIL {selector} {prop} — property missing in live capture")
                continue
            if actual != expected:
                mock_str = f" (mockup: {mockup.get(prop, 'n/a')})" if mockup else ""
                fails.append(
                    f"FAIL {selector} {prop} — pinned {expected!r}, live {actual!r}{mock_str}"
                )
            else:
                passes.append(f"PASS {selector} {prop} = {actual}")

    return len(fails), passes + skipped + fails


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-json", default="/tmp/element_audit_live.json",
                        help="Path to live-values JSON (written by Chrome DevTools MCP run)")
    parser.add_argument("--mockup-json", default=None,
                        help="Path to mockup-values JSON (optional)")
    args = parser.parse_args()

    live_path = Path(args.live_json)
    if not live_path.exists():
        print(f"ERROR: {live_path} not found. Run the Chrome DevTools MCP audit first.", file=sys.stderr)
        print("  1. mcp__chrome-devtools__navigate_page to the live URL", file=sys.stderr)
        print("  2. mcp__chrome-devtools__evaluate_script for getComputedStyle() across regions", file=sys.stderr)
        print("  3. Save result to /tmp/element_audit_live.json", file=sys.stderr)
        sys.exit(2)

    live_values = json.loads(live_path.read_text())
    mockup_values = json.loads(Path(args.mockup_json).read_text()) if args.mockup_json else None

    fail_count, messages = audit(live_values, mockup_values)
    for m in messages:
        print(m)
    print()
    print(f"FAIL: {fail_count}")
    print(f"Total messages: {len(messages)}")
    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
