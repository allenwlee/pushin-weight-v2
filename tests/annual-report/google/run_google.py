#!/usr/bin/env python3
"""
Google proxy A/B test: M3.0 (thinking disabled) vs Gemini 3.1 Pro.

Input: 2 page PNGs of the "Common Stock Ownership of Certain Beneficial Owners
and Management" section from Alphabet's 2026 DEF 14A
(goog-20260424.htm, period ending 2026-04-06).

Output: m3_google.txt and gemini_google.txt with ASCII org chart attempts.
"""
import base64
import json
import os
import sys
import time

import requests

PAGES = [1, 2]
PAGE_DIR = "/tmp/m3-test-staging/pdf_org_chart"
OUT_DIR = "/tmp/m3-test-staging/pdf_org_chart"

PROMPT = (
    "Read the attached pages from Alphabet's 2026 DEF 14A proxy statement. "
    "They show the 'Common Stock Ownership of Certain Beneficial Owners and Management' table. "
    "Produce a multi-tier ASCII org chart showing the ownership structure. "
    "At the TOP: the beneficial owners (Larry Page, Sergey Brin, Sundar Pichai, "
    "the other named executive officers and directors, and the 5%+ holders like BlackRock). "
    "In the MIDDLE: any intermediary holding vehicles mentioned in the footnotes "
    "(trusts, foundations, charitable remainder unitrusts, etc.). "
    "At the BOTTOM: Alphabet Inc. as the reporting issuer. "
    "For each ownership chain, show the percentage of Class A and Class B common stock, "
    "the number of shares, and the total voting power percentage. "
    "Use box-drawing characters. Output ONLY the chart, no commentary, no preamble."
)


def b64_png(p):
    with open(f"{PAGE_DIR}/google_page-{p}.png", "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_m3(m3_key):
    print("\n=== MiniMax-M3 (Google, thinking disabled) ===", file=sys.stderr)
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
    with open(f"{OUT_DIR}/m3_google.txt", "w") as f:
        f.write(text)
    with open(f"{OUT_DIR}/m3_google_raw.json", "w") as f:
        json.dump(data, f, indent=2)
    return text, dt


def call_gemini(gemini_key):
    print("\n=== Gemini 3.1 Pro (Google) ===", file=sys.stderr)
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
    with open(f"{OUT_DIR}/gemini_google.txt", "w") as f:
        f.write(text)
    with open(f"{OUT_DIR}/gemini_google_raw.json", "w") as f:
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
