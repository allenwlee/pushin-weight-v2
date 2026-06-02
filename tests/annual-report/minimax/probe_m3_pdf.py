#!/usr/bin/env python3
"""
Probe M3.0 PDF acceptance on MiniMax API.

Tries a series of payload shapes to find what works:
  A) MiniMax-M3 model, PDF as base64 in multimodal content array
  B) MiniMax-M2.7 model, same payload (sanity check, user reports 400 on M2.7)
  C) MiniMax-M3 model, file_id reference (upload PDF via /v1/files/upload first)
  D) MiniMax-M3 model, PDF as base64 wrapped in a file block (alternative shape)

Prints HTTP status + first 500 chars of response body for each attempt.
"""
import base64
import json
import os
import sys

import requests

API_KEY = os.environ.get("MINIMAX_API_TOKEN", "")
API_HOST = "https://api.minimax.io"
PDF_PATH = "/tmp/m3-test-staging/pdf_org_chart/10k.pdf"
PROMPT = "Read pages 21-24 of the attached 10-K filing. Produce an ASCII org chart of the executive officers and directors listed in those pages. Use box-drawing characters. Output ONLY the chart, no commentary."


def must_have_key():
    if not API_KEY:
        print("FATAL: MINIMAX_API_TOKEN not set", file=sys.stderr)
        sys.exit(2)


def b64_pdf():
    with open(PDF_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call(label, payload, headers=None):
    h = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    if headers:
        h.update(headers)
    print(f"\n=== {label} ===", file=sys.stderr)
    print(f"  model: {payload.get('model')}", file=sys.stderr)
    print(f"  msgs[0].content[0].type: {payload['messages'][0]['content'][0].get('type', '?')}", file=sys.stderr)
    r = requests.post(f"{API_HOST}/v1/chat/completions", headers=h, json=payload, timeout=120)
    print(f"  -> HTTP {r.status_code}", file=sys.stderr)
    print(f"  -> body[:500]: {r.text[:500]}", file=sys.stderr)
    return r


def main():
    must_have_key()
    pdf_b64 = b64_pdf()
    print(f"PDF b64 length: {len(pdf_b64)}", file=sys.stderr)

    # Probe A: M3 model, multimodal content array (text + image_url block with PDF data URI)
    payload_a = {
        "model": "MiniMax-M3",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:application/pdf;base64,{pdf_b64}"}},
                ],
            }
        ],
        "stream": False,
    }
    call("A: MiniMax-M3, multimodal content array (image_url with PDF data URI)", payload_a)

    # Probe B: M2.7 model, same payload (user reports 400 — confirm we get the same error)
    payload_b = dict(payload_a, model="MiniMax-M2.7")
    call("B: MiniMax-M2.7, same payload (sanity check — should 400 like user saw)", payload_b)

    # Probe C: M3 model, file block content (alternative OpenAI-compatible shape)
    payload_c = {
        "model": "MiniMax-M3",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "file", "file": {"filename": "10k.pdf", "file_data": f"data:application/pdf;base64,{pdf_b64}"}},
                ],
            }
        ],
        "stream": False,
    }
    call("C: MiniMax-M3, file block content (file_data data URI)", payload_c)

    # Probe D: M3 model, plain string content with PDF base64 (no multimodal structure)
    payload_d = {
        "model": "MiniMax-M3",
        "messages": [
            {"role": "user", "content": f"{PROMPT}\n\n[PDF base64 follows]\n{pdf_b64[:200]}..."}
        ],
        "stream": False,
    }
    call("D: MiniMax-M3, plain text content with truncated b64 in body (control)", payload_d)

    print("\n=== probe done ===", file=sys.stderr)


if __name__ == "__main__":
    main()
