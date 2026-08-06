#!/usr/bin/env python3
"""Translator batch-limits probe (x_monitor.translator.translate_batch_pragmatics).

Trigger: 2026-08-06 08:47:02 UTC cron run -- translator returned
`translator_batch_failed` after an 11,108-byte response was truncated
mid-JSON at DeepSeek V4 Pro. The translator cap was raised to
65,536 tokens in commit c09a291 (2026-08-05) after a live probe of
the same 20 prod-failing posts measured 19,554 output tokens
(stop_reason=end_turn). Today's 11k-byte truncation **contradicts**
that measurement.

This probe rules out the two remaining hypotheses:
  1. DS V4 has a per-request token limit that varies.
  2. DS V4's `thinking` budget leaks into `max_tokens` when the
     Anthropic-compatible shim's `thinking={"type": "disabled"}`
     is not honored on every request.
(OpenAI shim is RULED OUT -- no provider change in recent commits;
we are still on api.deepseek.com/anthropic.)

Axes swept:
  A1 max_tokens      [4096, 8192, 16384, 20000, 32768, 65536]
  A2 batch_size      [1, 5, 10, 15, 20, 25, 30]
  A3 input_tokens    [200, 500, 1000, 2000, 4000, 8000]  (per-tweet chars)
  A4 thinking        [disabled, omitted, enabled]

Usage:
    # offline -- never hits the LLM
    python -m scripts.probes.translator_batch_limits.probe --dry-run

    # single axis, real calls
    python -m scripts.probes.translator_batch_limits.probe --axes=max_tokens

    # targeted re-run after a fix
    python -m scripts.probes.translator_batch_limits.probe --axes=thinking
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# --- path setup ------------------------------------------------------------

PROBE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PROBE_DIR.parents[3]  # scripts/probes/<name>/probe.py -> repo root
sys.path.insert(0, str(REPO_ROOT))


# --- defaults --------------------------------------------------------------

# Synthetic-tweet registry. Mirrors classify_batch_limits/probe.py's
# DEFAULT_BRAND_IDS so the probe works on a fresh checkout without a DB.
DEFAULT_BRAND_IDS: list[str] = [
    "minimax", "hailuo", "kimi", "deepseek", "qwen", "glm", "yi", "baichuan",
    "doubao", "ernie", "hunyuan", "spark", "wenxin", "tongyi", "abab", "rohan",
    "minimax_m2", "kuaishou_kling", "tencent_hunyuan", "iflytek_spark",
]

# Default synthetic tweet text. Repeated to scale up input_tokens. The
# per-tweet text length is the input-tokens axis.
_TWEET_SEED_TEXT = (
    "We are excited to announce the latest breakthrough from our research team "
    "on long-context reasoning and tool-use across multi-turn agentic workflows. "
)

# Per-call wall-clock timeout. Shorter than the 5+ min SSL hang observed
# in production so a stalled call does not stall the whole probe.
DEFAULT_TIMEOUT_SECONDS = 30.0

# Per-axis default sweep values.
BATCH_SIZE_VALUES: list[int] = [1, 5, 10, 15, 20, 25, 30]
INPUT_TOKEN_VALUES: list[int] = [200, 500, 1_000, 2_000, 4_000, 8_000]
MAX_TOKENS_VALUES: list[int] = [4_096, 8_192, 16_384, 20_000, 32_768, 65_536]
THINKING_VALUES: list = [{"type": "disabled"}, None, {"type": "enabled"}]

VALID_AXES: set[str] = {"batch_size", "max_tokens", "input_tokens", "thinking"}


# --- helpers ----------------------------------------------------------------


def _build_tweets(n: int, text_len_chars: int) -> list:
    """Build n synthetic tweets of text_len_chars each, with brand_ids."""
    out = []
    base_text = (_TWEET_SEED_TEXT * ((text_len_chars // len(_TWEET_SEED_TEXT)) + 1))[:text_len_chars]
    for i in range(n):
        out.append({
            "tweet_id": f"probe_{i}_{text_len_chars}",
            "text": base_text,
            "brand_id": DEFAULT_BRAND_IDS[i % len(DEFAULT_BRAND_IDS)],
        })
    return out


def _build_client():
    """Mirror cycle.py: load config, pass cfg through the canonical factory.

    build_translator_client_from_env reads `cfg.llm.translator_base_url`
    first, falling back to ANTHROPIC_BASE_URL. The factory internally
    resolves the right API key based on the base URL substring (MiniMax
    proxy vs DeepSeek vs direct Anthropic). Callers do not touch
    credentials directly -- they reuse the production translation
    client and inherit the same key switch the cron uses.

    Returns None when no credential is available; callers should treat
    None as a stop signal (not an error).
    """
    from x_monitor.config import load_config
    from x_monitor.reattribute import build_translator_client_from_env

    cfg = load_config(Path("config.yaml"))
    return build_translator_client_from_env(cfg=cfg)


def _fire_one_translation(
    client,
    tweets: list,
    max_tokens: int,
    thinking,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Fire one translation call. Returns a structured row of metrics."""
    from x_monitor.translator import build_pragmatics_translation_prompt
    from x_monitor.attribution import _resolve_translator_model

    prompt = build_pragmatics_translation_prompt(
        tweets, target_locales=["en", "zh_cn"], brand_names=DEFAULT_BRAND_IDS[:5],
    )
    model = _resolve_translator_model()
    t0 = time.monotonic()
    row = {
        "n_tweets": len(tweets),
        "max_tokens": max_tokens,
        "thinking": thinking,
        "model": model,
        "status": "init",
    }
    try:
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "timeout": timeout,
        }
        if thinking is not None:
            kwargs["thinking"] = thinking
        resp = client.messages_create(**kwargs)
        wall = time.monotonic() - t0
        row.update({
            "status": "ok",
            "wall_clock_s": round(wall, 3),
            "stop_reason": getattr(resp, "stop_reason", None),
            "input_tokens": getattr(resp.usage, "input_tokens", None) if getattr(resp, "usage", None) else None,
            "output_tokens": getattr(resp.usage, "output_tokens", None) if getattr(resp, "usage", None) else None,
            "response_chars": len(resp.content[0].text) if resp.content else 0,
        })
        try:
            parsed = json.loads(resp.content[0].text)
            results = parsed.get("results", []) if isinstance(parsed, dict) else []
            row["len_results"] = len(results) if isinstance(results, list) else 0
        except (json.JSONDecodeError, AttributeError, IndexError) as exc:
            row["parse_error"] = f"{type(exc).__name__}: {exc}"
            row["len_results"] = 0
        return row
    except Exception as exc:
        wall = time.monotonic() - t0
        row.update({
            "status": "error",
            "wall_clock_s": round(wall, 3),
            "error_type": type(exc).__name__,
            "error_msg": str(exc)[:200],
        })
        return row


# --- sweeps -----------------------------------------------------------------


def sweep_max_tokens(client, base_n: int = 20, base_text_len: int = 1_000,
                     base_thinking={"type": "disabled"}) -> list:
    """A1: max_tokens varies at fixed batch_size."""
    tweets = _build_tweets(base_n, base_text_len)
    return [_fire_one_translation(client, tweets, max_tokens=mt, thinking=base_thinking)
            for mt in MAX_TOKENS_VALUES]


def sweep_batch_size(client, base_text_len: int = 1_000,
                     base_max_tokens: int = 65_536,
                     base_thinking={"type": "disabled"}) -> list:
    """A2: batch_size varies at fixed max_tokens."""
    return [_fire_one_translation(client, _build_tweets(n, base_text_len),
                                  max_tokens=base_max_tokens, thinking=base_thinking)
            for n in BATCH_SIZE_VALUES]


def sweep_input_tokens(client, base_n: int = 20,
                       base_max_tokens: int = 65_536,
                       base_thinking={"type": "disabled"}) -> list:
    """A3: per-tweet text length varies at fixed batch_size."""
    return [_fire_one_translation(client, _build_tweets(base_n, tl),
                                  max_tokens=base_max_tokens, thinking=base_thinking)
            for tl in INPUT_TOKEN_VALUES]


def sweep_thinking(client, base_n: int = 20, base_text_len: int = 1_000,
                   base_max_tokens: int = 65_536) -> list:
    """A4: thinking kwarg varies."""
    return [_fire_one_translation(client, _build_tweets(base_n, base_text_len),
                                  max_tokens=base_max_tokens, thinking=th)
            for th in THINKING_VALUES]


# --- output formatting ------------------------------------------------------


def _print_table(title: str, rows: list, cols: list) -> None:
    print(f"\n=== {title} ===")
    widths = [max(len(c[0]), max((len(str(r.get(c[1], ""))) for r in rows), default=0)) for c in cols]
    print(" | ".join(c[0].ljust(w) for c, w in zip(cols, widths)))
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(" | ".join(str(r.get(c[1], "")).ljust(w) for c, w in zip(cols, widths)))


def _verdict(axis: str, rows: list, failure_signal: str = "stop_reason") -> str:
    """Find the smallest axis value that hit the failure signal."""
    for r in rows:
        if r.get(failure_signal) == "max_tokens" or r.get("status") == "error":
            axis_val = r.get(axis, "?")
            return f"limit hit: {axis}={axis_val} -> stop_reason={r.get('stop_reason')}"
    return f"no {failure_signal} hit; all rows ok"


# --- dry-run ----------------------------------------------------------------


def _dry_run_row(thinking, max_tokens: int, n: int, text_len: int) -> dict:
    return {
        "n_tweets": n, "max_tokens": max_tokens, "thinking": thinking,
        "status": "dry_run", "response_chars": 0, "output_tokens": 0, "len_results": 0,
    }


# --- entry point ------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="translator_batch_limits.probe",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--axes", type=str, default="",
        help="Comma-separated subset of {batch_size,max_tokens,input_tokens,thinking}. Default: all.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Skip real LLM calls; print synthetic rows that would have been fetched.",
    )
    parser.add_argument(
        "--output-json", type=str, default=None,
        help="Path to write the result rows as JSON (default: data/runs/probe_translator_<UTC>.json).",
    )
    parser.add_argument(
        "--batch-size", type=int, default=20,
        help="Production batch size (default 20, the live operator value).",
    )
    args = parser.parse_args(argv)

    axes = set(a for a in args.axes.split(",") if a) if args.axes else VALID_AXES
    unknown = axes - VALID_AXES
    if unknown:
        print(f"unknown axes: {unknown}; valid: {sorted(VALID_AXES)}")
        return 2

    print(f"# translator_batch_limits.probe axes={sorted(axes)} dry_run={args.dry_run}")

    if args.dry_run:
        sweep_results = {}
        if "max_tokens" in axes:
            sweep_results["max_tokens"] = [
                _dry_run_row({"type": "disabled"}, mt, args.batch_size, 1_000)
                for mt in MAX_TOKENS_VALUES
            ]
        if "batch_size" in axes:
            sweep_results["batch_size"] = [
                _dry_run_row({"type": "disabled"}, 65_536, n, 1_000)
                for n in BATCH_SIZE_VALUES
            ]
        if "input_tokens" in axes:
            sweep_results["input_tokens"] = [
                _dry_run_row({"type": "disabled"}, 65_536, args.batch_size, tl)
                for tl in INPUT_TOKEN_VALUES
            ]
        if "thinking" in axes:
            sweep_results["thinking"] = [
                _dry_run_row(th, 65_536, args.batch_size, 1_000) for th in THINKING_VALUES
            ]
    else:
        client = _build_client()
        if client is None:
            print("build_translator_client_from_env returned None; check env + config.yaml.")
            return 2

        sweep_results = {}
        if "max_tokens" in axes:
            print("running A1 max_tokens sweep...")
            sweep_results["max_tokens"] = sweep_max_tokens(client, base_n=args.batch_size)
        if "batch_size" in axes:
            print("running A2 batch_size sweep...")
            sweep_results["batch_size"] = sweep_batch_size(client)
        if "input_tokens" in axes:
            print("running A3 input_tokens sweep...")
            sweep_results["input_tokens"] = sweep_input_tokens(client, base_n=args.batch_size)
        if "thinking" in axes:
            print("running A4 thinking sweep...")
            sweep_results["thinking"] = sweep_thinking(client, base_n=args.batch_size)

    cols = [
        ("n_tweets", "n_tweets"),
        ("max_tokens", "max_tokens"),
        ("thinking", "thinking"),
        ("status", "status"),
        ("response_chars", "resp_chars"),
        ("output_tokens", "out_tokens"),
        ("stop_reason", "stop_reason"),
        ("len_results", "n_results"),
    ]

    for axis, rows in sweep_results.items():
        _print_table(f"{axis}", rows, cols)
        print(_verdict("max_tokens" if axis != "thinking" else "thinking", rows))

    out_path = args.output_json or f"data/runs/probe_translator_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_payload = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "axes_run": sorted(axes),
        "dry_run": args.dry_run,
        "results": {axis: rows for axis, rows in sweep_results.items()},
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(out_payload, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
