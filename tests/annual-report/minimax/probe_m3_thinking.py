#!/usr/bin/env python3
"""
Probe M3.0 chat completions API to find the parameter that disables thinking.

Tries several common patterns and reports which (if any) removes the <think> block.
"""
import base64
import json
import os
import sys
import time

import requests

API_HOST = "https://api.minimax.io"
MODEL = "MiniMax-M3"
PAGE_DIR = "/tmp/m3-test-staging/pdf_org_chart"
PROMPT = "Reply with one word: OK"


def b64_png(p):
    with open(f"{PAGE_DIR}/page-{p}.png", "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call(payload_extra, label):
    content = [
        {"type": "text", "text": PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_png(21)}"}},
    ]
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "stream": False,
    }
    payload.update(payload_extra)
    t0 = time.time()
    r = requests.post(
        f"{API_HOST}/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['MINIMAX_API_TOKEN']}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    dt = time.time() - t0
    if r.status_code != 200:
        return label, r.status_code, dt, None, r.text[:200]
    data = r.json()
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    has_think = "<think>" in text
    return label, r.status_code, dt, len(text), f"has_think={has_think} content={text[:120]!r}"


def main():
    probes = [
        ("baseline (no extra)", {}),
        ('thinking=false', {"thinking": False}),
        ('thinking={"type":"disabled"}', {"thinking": {"type": "disabled"}}),
        ('enable_thinking=false', {"enable_thinking": False}),
        ('reasoning_effort="none"', {"reasoning_effort": "none"}),
        ('reasoning_effort="low"', {"reasoning_effort": "low"}),
        ('reasoning_effort="minimal"', {"reasoning_effort": "minimal"}),
        ('thinking_budget=0', {"thinking_budget": 0}),
        ('model="MiniMax-M3-nothink"', {"model": "MiniMax-M3-nothink"}),
        ('temperature=0', {"temperature": 0}),
    ]
    print(f"{'label':40s} {'http':>4s} {'dt':>6s} {'len':>6s}  result")
    print("-" * 100)
    for label, extra in probes:
        try:
            l, code, dt, length, detail = call(extra, label)
            length_str = f"{length}" if length is not None else "—"
            print(f"{l:40s} {code:>4d} {dt:>5.1f}s {length_str:>6s}  {detail}")
        except Exception as e:
            print(f"{label:40s} ERR  {e}")


if __name__ == "__main__":
    main()
