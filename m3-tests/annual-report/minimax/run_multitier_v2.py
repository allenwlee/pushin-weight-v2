#!/usr/bin/env python3
"""
Multi-tier org chart test v2: M3.0 with thinking DISABLED.

Same 4 page PNGs and same prompt as run_multitier.py, but with
`thinking: {"type": "disabled"}` in the payload (the only parameter
that actually suppresses M3.0's <think>...</think> block — confirmed
via probe_m3_thinking.py).

Saves outputs to m3_multi_v2.txt (locally) and the same path on fuchitalee.
"""
import base64
import json
import os
import sys
import time

import requests

PAGES = [21, 22, 23, 24]
PAGE_DIR = "/tmp/m3-test-staging/pdf_org_chart"

PROMPT = (
    "Read pages 21-24 of this 10-K filing. Produce a multi-tier ASCII org chart showing the ownership structure. "
    "At the TOP: the beneficial owners and individuals (people + holding companies with direct shareholdings). "
    "In the MIDDLE: the intermediary holding companies, controlled corporations, and trusts that connect them. "
    "At the BOTTOM: the final reporting company (the issuer of the 10-K). "
    "For each ownership chain, show the percentage of Class A shares and the number of shares. "
    "Use box-drawing characters. Output ONLY the chart, no commentary, no preamble."
)


def b64_png(p):
    with open(f"{PAGE_DIR}/page-{p}.png", "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_m3(m3_key):
    print("\n=== MiniMax-M3 (multi-tier v2, thinking disabled) ===", file=sys.stderr)
    content = [{"type": "text", "text": PROMPT}]
    for p in PAGES:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_png(p)}"}})
    payload = {
        "model": "MiniMax-M3",
        "messages": [{"role": "user", "content": content}],
        "stream": False,
        "thinking": {"type": "disabled"},
    }
    t0 = time.time()
    r = requests.post(
        "https://api.minimax.io/v1/chat/completions",
        headers={"Authorization": f"Bearer {m3_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=600,
    )
    dt = time.time() - t0
    print(f"  -> HTTP {r.status_code} in {dt:.1f}s", file=sys.stderr)
    if r.status_code != 200:
        print(f"  -> body[:500]: {r.text[:500]}", file=sys.stderr)
        return None, dt
    data = r.json()
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = data.get("usage", {})
    has_think = "<think>" in text
    print(f"  -> usage: {usage}", file=sys.stderr)
    print(f"  -> has_think={has_think}, len={len(text)}", file=sys.stderr)
    with open(f"{PAGE_DIR}/m3_multi_v2.txt", "w") as f:
        f.write(text)
    with open(f"{PAGE_DIR}/m3_multi_v2_raw.json", "w") as f:
        json.dump(data, f, indent=2)
    return text, dt


def main():
    m3_key = os.environ.get("MINIMAX_API_TOKEN", "")
    if not m3_key:
        print("FATAL: MINIMAX_API_TOKEN not set", file=sys.stderr)
        sys.exit(2)
    text, dt = call_m3(m3_key)
    print(f"\n=== summary ===", file=sys.stderr)
    print(f"M3 v2: {dt:.1f}s, {len(text) if text else 0} chars", file=sys.stderr)


if __name__ == "__main__":
    main()
