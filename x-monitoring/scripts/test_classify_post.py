#!/usr/bin/env python3
"""Smoke-test the post-fetch (post_type, sentiment) classifier.

Runs ``classify_post(text, brand_ids, brand_registry, anthropic_client)``
in ``x_monitor.attribution`` against a curated set of post texts that
exercises all 4 post_types × 4 sentiments. Talks to the real LLM (default
``MiniMax-M3.0`` via api.minimax.io if ``ANTHROPIC_BASE_URL`` is set,
otherwise ``claude-haiku-4-5``).

Usage:
    scripts/test_classify_post.py                 # default 9-sample sweep
    scripts/test_classify_post.py --out FILE.json # also persist results
    scripts/test_classify_post.py --text my.txt   # read texts one per line
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Make x_monitor importable when invoked from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from x_monitor.attribution import (  # noqa: E402
    AnthropicClaudeClient,
    BrandRow,
    classify_post,
)


# Curated samples — each (text, brands, expected_post_type, expected_sentiment).
# Expected values are what a competent human labeler would pick; the run
# prints actual vs expected so we can spot drifts.
DEFAULT_SAMPLES: list[dict] = [
    {
        "text": "🚀 GLM-5.2 just dropped with 1M context and MIT license. Huge for open-source AI.",
        "brands": ["glm"],
        "expect_post_type": "buzz_releases",
        "expect_sentiment": "positive",
        "note": "release announcement, explicit hype",
    },
    {
        "text": "Qwen3-Max release notes: 480B params, native tool-calling support.",
        "brands": ["qwen"],
        "expect_post_type": "buzz_releases",
        "expect_sentiment": "neutral",
        "note": "release note, no hype or criticism",
    },
    {
        "text": "I've been running DeepSeek-V3 in production for 2 weeks. Saved $40k/mo vs Anthropic.",
        "brands": ["deepseek"],
        "expect_post_type": "hands_on_usage",
        "expect_sentiment": "positive",
        "note": "first-person production story, positive",
    },
    {
        "text": "GLM-5.2 in Cline feels good in theory but the tool-call formatting is fragile.",
        "brands": ["glm"],
        "expect_post_type": "hands_on_usage",
        "expect_sentiment": "mixed",
        "note": "qualified hands-on review",
    },
    {
        "text": "Qwen3-Coder keeps inventing tool calls that don't exist. Frustrating.",
        "brands": ["qwen"],
        "expect_post_type": "hands_on_usage",
        "expect_sentiment": "negative",
        "note": "frustration with tool calls",
    },
    {
        "text": "GLM-5.2 hit 88 on SWE-bench Verified, matching Opus. OSS is catching up.",
        "brands": ["glm"],
        "expect_post_type": "performance_comparisons",
        "expect_sentiment": "positive",
        "note": "benchmark with comparison",
    },
    {
        "text": "MiniMax M3 benchmarks fast but I've seen hallucinations in long-context that GPT-5 handles fine.",
        "brands": ["minimax"],
        "expect_post_type": "performance_comparisons",
        "expect_sentiment": "mixed",
        "note": "bench positive + caveat",
    },
    {
        "text": "Zhipu's free tier pricing has gotten predatory. Personal users getting squeezed out.",
        "brands": ["glm"],
        "expect_post_type": "feedback_questions",
        "expect_sentiment": "negative",
        "note": "pricing complaint",
    },
    {
        "text": "How do I configure the Kimi K2 Thinking API endpoint with LangChain?",
        "brands": ["moonshot_kimi"],
        "expect_post_type": "feedback_questions",
        "expect_sentiment": "neutral",
        "note": "how-to question",
    },
]


def make_registry(brands: list[str]) -> list[BrandRow]:
    """Construct a stub BrandRow list covering the brands in our samples.

    classify_post validates every returned brand_id against this list
    (R8 hallucination drop). We hand-construct the rows so the test does
    not depend on a live DB.
    """
    out: list[BrandRow] = []
    for b in brands:
        out.append(BrandRow(
            brand_id=b,
            display_name=b,
            accent_color="#888888",
            is_sentinel=False,
        ))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--text", help="file with one tweet text per line (overrides samples)"
    )
    parser.add_argument(
        "--out", help="also persist run results to this JSON file"
    )
    parser.add_argument(
        "--brands",
        default=None,
        help="comma-separated brands to register (default: union of sample brands)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not in environment", file=sys.stderr)
        return 1

    if args.text:
        # One tweet per line; brand defaults to first sample's brand.
        with open(args.text) as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        samples = []
        for ln in lines:
            samples.append({
                "text": ln,
                "brands": (args.brands or "").split(",") if args.brands else ["minimax"],
                "expect_post_type": "?",
                "expect_sentiment": "?",
                "note": "from file",
            })
    else:
        samples = list(DEFAULT_SAMPLES)

    all_brands = sorted({b for s in samples for b in s["brands"]})
    if args.brands:
        all_brands = sorted(set(args.brands.split(",")))
    registry = make_registry(all_brands)

    base_url = os.environ.get("ANTHROPIC_BASE_URL") or None
    client = AnthropicClaudeClient(api_key=api_key, base_url=base_url)

    print(f"# classify_post smoke test")
    print(f"# model:        {os.environ.get('ANTHROPIC_MODEL', '(auto)')}")
    print(f"# base_url:     {base_url or '(default anthropic)'}")
    print(f"# registry:     {all_brands}")
    print(f"# samples:      {len(samples)}")
    print()

    results: list[dict] = []
    n_correct_pt = 0
    n_correct_sent = 0
    for i, s in enumerate(samples, 1):
        t0 = time.monotonic()
        out = classify_post(
            text=s["text"],
            brand_ids=s["brands"],
            brand_registry=registry,
            anthropic_client=client,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        for b in s["brands"]:
            got = out.get(b)
            if got is None:
                actual_pt, actual_sent = "—", "—"
            else:
                actual_pt, actual_sent = got

            exp_pt = s["expect_post_type"]
            exp_sent = s["expect_sentiment"]
            ok_pt = "✓" if actual_pt == exp_pt or exp_pt == "?" else "✗"
            ok_sent = "✓" if actual_sent == exp_sent or exp_sent == "?" else "✗"
            if exp_pt != "?" and actual_pt == exp_pt:
                n_correct_pt += 1
            if exp_sent != "?" and actual_sent == exp_sent:
                n_correct_sent += 1

            # Truncate text for display.
            text_preview = s["text"][:65] + ("…" if len(s["text"]) > 65 else "")
            note = s.get("note", "")
            print(
                f"  [{i:2d}] {b:<14}  pt={actual_pt:<22}  sent={actual_sent:<8}  "
                f"dur={elapsed_ms:>5d}ms  "
                f"pt_ok={ok_pt} sent_ok={ok_sent}  "
                f'"{text_preview}"'
            )

        results.append({
            "text": s["text"],
            "brands": s["brands"],
            "expect_post_type": s["expect_post_type"],
            "expect_sentiment": s["expect_sentiment"],
            "note": s.get("note", ""),
            "actual": {b: list(out[b]) if b in out else None for b in s["brands"]},
            "duration_ms": elapsed_ms,
        })

    n_judged = sum(1 for s in samples for b in s["brands"] if s["expect_post_type"] != "?")
    n_judged_sent = sum(1 for s in samples for b in s["brands"] if s["expect_sentiment"] != "?")
    print()
    print(
        f"# post_type accuracy: {n_correct_pt}/{n_judged}  "
        f"sentiment accuracy: {n_correct_sent}/{n_judged_sent}"
    )

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({
            "model": os.environ.get("ANTHROPIC_MODEL"),
            "base_url": base_url,
            "registry": all_brands,
            "results": results,
            "accuracy": {
                "post_type": f"{n_correct_pt}/{n_judged}",
                "sentiment": f"{n_correct_sent}/{n_judged_sent}",
            },
        }, indent=2, ensure_ascii=False))
        print(f"# wrote {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
