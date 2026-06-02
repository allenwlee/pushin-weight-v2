#!/usr/bin/env python3
"""
Control test: did Gemini actually READ the images, or hallucinate names from training data?

Submit the SAME 4 page PNGs but with a question that only has a real answer
on the page. If Gemini returns a real number, the image was read. If it
guesses, the image wasn't fully processed.
"""
import base64
import os
import sys

import requests

API_HOST = "https://api.minimax.io"
GEMINI_HOST = "https://generativelanguage.googleapis.com/v1beta"
PAGES = [21, 22, 23, 24]
PAGE_DIR = "/tmp/m3-test-staging/pdf_org_chart"
PROMPT = (
    "Look at the four attached pages (21-24) of this 10-K filing. "
    "For Dr. Yan Junjie, what is the EXACT number of shares held, as a number? "
    "Reply with ONLY the integer (with commas if relevant), nothing else."
)


def b64_png(p):
    with open(f"{PAGE_DIR}/page-{p}.png", "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_gemini(gemini_key):
    parts = [{"text": PROMPT}]
    for p in PAGES:
        parts.append({"inline_data": {"mime_type": "image/png", "data": b64_png(p)}})
    r = requests.post(
        f"{GEMINI_HOST}/models/gemini-3.1-pro-preview:generateContent",
        headers={"x-goog-api-key": gemini_key, "Content-Type": "application/json"},
        json={"contents": [{"role": "user", "parts": parts}]},
        timeout=180,
    )
    print(f"Gemini: HTTP {r.status_code}", file=sys.stderr)
    if r.status_code != 200:
        print(f"  body: {r.text[:500]}", file=sys.stderr)
        return None
    data = r.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        print(f"  parse err: {e}", file=sys.stderr)
        return None
    return text


def call_m3(m3_key):
    content = [{"type": "text", "text": PROMPT}]
    for p in PAGES:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_png(p)}"}})
    r = requests.post(
        f"{API_HOST}/v1/chat/completions",
        headers={"Authorization": f"Bearer {m3_key}", "Content-Type": "application/json"},
        json={"model": "MiniMax-M3", "messages": [{"role": "user", "content": content}], "stream": False},
        timeout=180,
    )
    print(f"M3: HTTP {r.status_code}", file=sys.stderr)
    if r.status_code != 200:
        print(f"  body: {r.text[:500]}", file=sys.stderr)
        return None
    data = r.json()
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


def main():
    m3_key = os.environ.get("MINIMAX_API_TOKEN", "")
    gemini_key = os.environ.get("GOOGLE_API_KEY", "")
    if not m3_key or not gemini_key:
        print("FATAL: keys not set", file=sys.stderr)
        sys.exit(2)
    print("\n=== control question ===", file=sys.stderr)
    print(f"PROMPT: {PROMPT}\n", file=sys.stderr)
    m3_ans = call_m3(m3_key)
    gem_ans = call_gemini(gemini_key)
    print(f"\nM3 answer:\n  {m3_ans}", file=sys.stderr)
    print(f"\nGemini answer:\n  {gem_ans}", file=sys.stderr)


if __name__ == "__main__":
    main()
