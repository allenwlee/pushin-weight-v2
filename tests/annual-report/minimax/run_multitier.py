#!/usr/bin/env python3
"""
Multi-tier org chart test: M3.0 vs Gemini 3.1 Pro.

Asks both to produce a chart showing the full ownership chain from
beneficial owners down through holding companies to the final reporting
entity, including percentages and share counts.
"""
import base64
import json
import os
import sys
import time

import requests

PAGES = [21, 22, 23, 24]
PAGE_DIR = "/tmp/m3-test-staging/pdf_org_chart"
OUT_DIR = f"{PAGE_DIR}/out_multitier"
os.makedirs(OUT_DIR, exist_ok=True)

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
    print("\n=== MiniMax-M3 (multi-tier) ===", file=sys.stderr)
    content = [{"type": "text", "text": PROMPT}]
    for p in PAGES:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_png(p)}"}})
    payload = {"model": "MiniMax-M3", "messages": [{"role": "user", "content": content}], "stream": False}
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
    print(f"  -> usage: {usage}", file=sys.stderr)
    with open(f"{OUT_DIR}/m3_output.txt", "w") as f:
        f.write(text)
    with open(f"{OUT_DIR}/m3_raw.json", "w") as f:
        json.dump(data, f, indent=2)
    return text, dt


def call_gemini(gemini_key):
    print("\n=== Gemini 3.1 Pro (multi-tier) ===", file=sys.stderr)
    parts = [{"text": PROMPT}]
    for p in PAGES:
        parts.append({"inline_data": {"mime_type": "image/png", "data": b64_png(p)}})
    payload = {"contents": [{"role": "user", "parts": parts}]}
    t0 = time.time()
    r = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent",
        headers={"x-goog-api-key": gemini_key, "Content-Type": "application/json"},
        json=payload,
        timeout=600,
    )
    dt = time.time() - t0
    print(f"  -> HTTP {r.status_code} in {dt:.1f}s", file=sys.stderr)
    if r.status_code != 200:
        print(f"  -> body[:500]: {r.text[:500]}", file=sys.stderr)
        return None, dt
    data = r.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        print(f"  parse err: {e}", file=sys.stderr)
        text = ""
    usage = data.get("usageMetadata", {})
    print(f"  -> usage: {usage}", file=sys.stderr)
    with open(f"{OUT_DIR}/gemini_output.txt", "w") as f:
        f.write(text)
    with open(f"{OUT_DIR}/gemini_raw.json", "w") as f:
        json.dump(data, f, indent=2)
    return text, dt


def main():
    m3_key = os.environ.get("MINIMAX_API_TOKEN", "")
    gemini_key = os.environ.get("GOOGLE_API_KEY", "")
    if not m3_key or not gemini_key:
        print("FATAL: keys not set", file=sys.stderr)
        sys.exit(2)
    m3_text, m3_dt = call_m3(m3_key)
    gem_text, gem_dt = call_gemini(gemini_key)
    print(f"\n=== summary ===", file=sys.stderr)
    print(f"M3: {m3_dt:.1f}s, {len(m3_text) if m3_text else 0} chars", file=sys.stderr)
    print(f"Gemini: {gem_dt:.1f}s, {len(gem_text) if gem_text else 0} chars", file=sys.stderr)


if __name__ == "__main__":
    main()
