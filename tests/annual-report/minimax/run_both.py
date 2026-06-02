#!/usr/bin/env python3
"""
Run the same org-chart prompt against MiniMax-M3 and Gemini 3.1 Pro.
4 page PNGs (21-24 of a 10-K) + ASCII-chart instruction.
Saves both outputs to out/ for side-by-side.
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
    "Read the four attached pages (21-24) of this 10-K filing. "
    "Produce an ASCII org chart of the executive officers and directors listed on those pages. "
    "Use box-drawing characters. Output ONLY the chart, no commentary, no preamble."
)

OUT_DIR = f"{PAGE_DIR}/out"
os.makedirs(OUT_DIR, exist_ok=True)


def b64_png(page):
    with open(f"{PAGE_DIR}/page-{page}.png", "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_m3(m3_key):
    print("\n=== MiniMax-M3 ===", file=sys.stderr)
    content = [{"type": "text", "text": PROMPT}]
    for p in PAGES:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64_png(p)}"},
        })
    payload = {
        "model": "MiniMax-M3",
        "messages": [{"role": "user", "content": content}],
        "stream": False,
    }
    t0 = time.time()
    r = requests.post(
        "https://api.minimax.io/v1/chat/completions",
        headers={"Authorization": f"Bearer {m3_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=300,
    )
    dt = time.time() - t0
    print(f"  -> HTTP {r.status_code} in {dt:.1f}s", file=sys.stderr)
    if r.status_code != 200:
        print(f"  -> body[:600]: {r.text[:600]}", file=sys.stderr)
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
    print("\n=== Gemini 3.1 Pro ===", file=sys.stderr)
    parts = [{"text": PROMPT}]
    for p in PAGES:
        parts.append({
            "inline_data": {
                "mime_type": "image/png",
                "data": b64_png(p),
            }
        })
    payload = {"contents": [{"role": "user", "parts": parts}]}
    t0 = time.time()
    # Try the standard Gemini 3.1 Pro model name first
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent"
    r = requests.post(
        url,
        headers={"x-goog-api-key": gemini_key, "Content-Type": "application/json"},
        json=payload,
        timeout=300,
    )
    dt = time.time() - t0
    print(f"  -> HTTP {r.status_code} in {dt:.1f}s", file=sys.stderr)
    if r.status_code != 200:
        print(f"  -> body[:600]: {r.text[:600]}", file=sys.stderr)
        return None, dt
    data = r.json()
    # Extract text from first candidate
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        print(f"  -> parse err: {e}", file=sys.stderr)
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
    gemini_key = os.environ.get("GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
    if not m3_key:
        print("FATAL: MINIMAX_API_TOKEN not set", file=sys.stderr)
        sys.exit(2)
    if not gemini_key:
        print("FATAL: GOOGLE_API_KEY / GEMINI_API_KEY not set", file=sys.stderr)
        sys.exit(2)
    m3_text, m3_dt = call_m3(m3_key)
    gem_text, gem_dt = call_gemini(gemini_key)
    print(f"\n=== summary ===", file=sys.stderr)
    print(f"M3 latency: {m3_dt:.1f}s, output: {len(m3_text) if m3_text else 0} chars", file=sys.stderr)
    print(f"Gemini latency: {gem_dt:.1f}s, output: {len(gem_text) if gem_text else 0} chars", file=sys.stderr)


if __name__ == "__main__":
    main()
