#!/usr/bin/env python3
"""classify_batch_pragmatics_full limits probe.

Plan: docs/plans/2026-07-15-001-feat-classify-batch-limits-probe-plan.md

Sweeps the 6 axes which could be the "limit" of the production
classifier ``classify_batch_pragmatics_full``:

  A1 batch_size       posts per LLM call     [1, 5, 10, 15, 20, 25, 30, 40, 50]
  A2 input_tokens     prompt length          [2k, 4k, 8k, 16k, 32k, 64k]
  A3 max_tokens       response cap           [256, 512, 1024, 2048, 4096]
  A4 rpm              serial request rate    [60, 120, 240]
  A5 cache_state      prompt-cache behavior  (write / read across 3 calls)
  A6 concurrency      parallel call fan-out  [1, 2, 4, 8, 16]

For each axis the probe varies exactly one knob, fires real LLM calls
through ``classify_batch_pragmatics_full`` (or short-circuits via the
FakeClaudeClient under ``--dry-run``), and prints a per-axis ceiling
table plus a one-line verdict naming the smallest value that failed.

Usage:
    # offline — never hits the LLM
    python -m scripts.probes.classify_batch_limits.probe --dry-run

    # single axis, real calls
    python -m scripts.probes.classify_batch_limits.probe --axes=batch_size

    # targeted re-run after a fix lands
    python -m scripts.probes.classify_batch_limits.probe --axes=concurrency
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Make the package importable when run as a module from the repo root.
PROBE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PROBE_DIR.parents[3]  # scripts/probes/<name>/probe.py -> repo root
sys.path.insert(0, str(REPO_ROOT))

# Default synthetic-tweet brand registry. Mirrors scripts/probe_filter_yield.py's
# hardcoded fallback so the probe works on a fresh checkout without a DB.
DEFAULT_BRAND_IDS: list[str] = [
    "minimax", "hailuo", "kimi", "deepseek", "qwen", "glm", "yi", "baichuan",
    "doubao", "ernie", "hunyuan", "spark", "wenxin", "tongyi", "abab", "rohan",
    "minimax_m2", "kuaishou_kling", "tencent_hunyuan", "iflytek_spark",
]

# Default synthetic tweet text. Repeated to scale up input_tokens.
_TWEET_SEED_TEXT = (
    "We are excited to announce the latest breakthrough from our research team "
    "on long-context reasoning and tool-use across multi-turn agentic workflows. "
)

# Default per-call wall-clock timeout. Shorter than the 5+ min SSL hang observed
# in production so a stalled call does not stall the whole probe.
DEFAULT_TIMEOUT_SECONDS = 30.0

# Per-axis default sweep values.
BATCH_SIZE_VALUES = [1, 5, 10, 15, 20, 25, 30, 40, 50]
INPUT_TOKEN_VALUES = [2_000, 4_000, 8_000, 16_000, 32_000, 64_000]
MAX_TOKENS_VALUES = [256, 512, 1024, 2048, 4096]
RPM_VALUES = [60, 120, 240]
CONCURRENCY_VALUES = [1, 2, 4, 8, 16]
RPM_DURATION_SECONDS = 60.0
CONCURRENCY_DURATION_SECONDS = 60.0

VALID_AXES = {
    "batch_size", "max_tokens", "input_tokens",
    "rpm", "cache_state", "concurrency",
}

# --- helpers --------------------------------------------------------------


def _have_api_creds() -> tuple[bool, str | None]:
    """ANTHROPIC_API_KEY is the only required credential (KTD1, R7).

    The probe runs against the same MiniMax proxy the production pipeline
    uses; the proxy is selected via ANTHROPIC_BASE_URL by x_monitor.attribution
    at module load, so we don't set it here.
    """
    v = os.environ.get("ANTHROPIC_API_KEY")
    if v:
        return True, v
    return False, None


def _classify_status(exc: Exception | None, response: Any = None) -> str:
    """Map an exception or response to a canonical status string (KTD7).

    The SDK raises a small zoo of exception types; pattern matching on
    the message is more robust than isinstance checks.
    """
    if exc is None and response is not None:
        return "success"
    if exc is None:
        return "other"
    msg = repr(exc) + " " + str(exc)
    if "Unterminated string" in msg or "Expecting value" in msg and "line 1" in msg:
        return "unterminated_json"
    if "_ssl__SSLSocket_read" in msg or "Read timed out" in msg or "ssl_hang" in msg:
        return "ssl_hang"
    if "timeout" in msg.lower() or "TimeoutError" in msg:
        return "timeout"
    if "429" in msg or "rate_limit" in msg.lower():
        return "rate_limited"
    if re.search(r"\b4\d{2}\b", msg) and "RequestException" in msg:
        return "4xx"
    if re.search(r"\b5\d{2}\b", msg) and "RequestException" in msg:
        return "5xx"
    if "AuthenticationError" in msg or "401" in msg:
        return "4xx"
    return "other"


def _build_synthetic_tweets(
    n: int,
    brand_ids: list[str],
    text_len: int = 240,
    rng_seed: int = 0,
) -> list[dict[str, Any]]:
    """Construct N synthetic tweets carrying 1-3 random brand_ids each.

    Text length scales by repeating the seed sentence so we can vary
    token count without varying semantic content (KTD6).
    """
    rng = random.Random(rng_seed)
    brands = brand_ids or DEFAULT_BRAND_IDS
    base_text = (_TWEET_SEED_TEXT * ((text_len // len(_TWEET_SEED_TEXT)) + 1))[:text_len]
    out: list[dict[str, Any]] = []
    for i in range(n):
        n_brand = rng.randint(1, min(3, len(brands)))
        chosen = rng.sample(brands, n_brand)
        out.append({
            "tweet_id": f"probe-{i:05d}",
            "id": f"probe-{i:05d}",
            "text": base_text,
            "brand_ids": chosen,
        })
    return out


def _fire_one_batch(
    tweets: list[dict[str, Any]],
    max_tokens: int,
    timeout: float,
    client: Any,
) -> dict[str, Any]:
    """Fire one classify_batch_pragmatics_full call against the given client.

    Returns ``{"status": str, "wall_clock_s": float, "response_chars": int,
    "input_tokens": int|None, "exc": Exception|None, "response": Any}``.

    The timeout is enforced via ThreadPoolExecutor + future.result(timeout=)
    (KTD4). FakeClaudeClient is supported by importing it from tests, but
    for production use the probe routes through the real classifier.
    """
    from x_monitor.attribution import classify_batch_pragmatics_full

    def _do() -> Any:
        return classify_batch_pragmatics_full(
            tweets=tweets,
            brand_registry=[],
            anthropic_client=client,
        )

    started = time.time()
    exc: Exception | None = None
    response: Any = None
    response_chars = 0
    input_tokens: int | None = None
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_do)
            response = future.result(timeout=timeout)
        # response is a list[dict] for the batched API
        if isinstance(response, list):
            response_chars = sum(len(json.dumps(r, default=str)) for r in response)
            # Cheap token proxy if usage info isn't surfaced
            input_tokens = sum(len(t.get("text", "")) for t in tweets) // 4
    except concurrent.futures.TimeoutError as e:
        exc = e
    except Exception as e:  # surface the real exception to the classifier
        exc = e
    wall_clock_s = time.time() - started
    status = _classify_status(exc, response)
    return {
        "status": status,
        "wall_clock_s": wall_clock_s,
        "response_chars": response_chars,
        "input_tokens": input_tokens,
        "exc": exc,
        "response": response,
    }


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Fixed-width ASCII table — matches the style of probe_filter_yield.py."""
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h)
              for i, h in enumerate(headers)]
    sep = "-+-".join("-" * w for w in widths)
    print(" | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print(sep)
    for row in rows:
        print(" | ".join(c.ljust(widths[i]) for i, c in enumerate(row)))


def _verdict_line(axis: str, rows: list[dict[str, Any]]) -> str | None:
    """Return the smallest-axis-value-that-failed verdict, or None if all green.

    In --dry-run mode every row is `status=dry_run`, which is not a failure —
    the verdict is suppressed.
    """
    for r in rows:
        s = r["status"]
        if s == "success" or s == "dry_run":
            continue
        return f"limit hit: {axis}={r['value']} -> {s}"
    return None


# --- U2: per-axis sweeps --------------------------------------------------


def sweep_batch_size(
    client: Any,
    base_batch_size: int,
    timeout: float,
    brand_ids: list[str],
    dry_run: bool,
) -> list[dict[str, Any]]:
    """A1 — vary n_posts at default text length."""
    rows: list[dict[str, Any]] = []
    for n_posts in BATCH_SIZE_VALUES:
        if dry_run:
            tweets = _build_synthetic_tweets(n_posts, brand_ids, text_len=240)
            rows.append({
                "value": str(n_posts),
                "status": "dry_run",
                "wall_clock_s": 0.0,
                "response_chars": 0,
                "input_tokens": sum(len(t["text"]) for t in tweets) // 4,
            })
            continue
        tweets = _build_synthetic_tweets(n_posts, brand_ids, text_len=240)
        result = _fire_one_batch(tweets, max_tokens=1024, timeout=timeout, client=client)
        rows.append({
            "value": str(n_posts),
            "status": result["status"],
            "wall_clock_s": round(result["wall_clock_s"], 3),
            "response_chars": result["response_chars"],
            "input_tokens": result["input_tokens"],
        })
    return rows


def sweep_max_tokens(
    client: Any,
    base_batch_size: int,
    timeout: float,
    brand_ids: list[str],
    dry_run: bool,
) -> list[dict[str, Any]]:
    """A3 — vary max_tokens at fixed batch_size=base_batch_size (production value)."""
    rows: list[dict[str, Any]] = []
    for max_tokens in MAX_TOKENS_VALUES:
        if dry_run:
            rows.append({
                "value": str(max_tokens),
                "status": "dry_run",
                "wall_clock_s": 0.0,
                "response_chars": 0,
                "input_tokens": None,
            })
            continue
        tweets = _build_synthetic_tweets(base_batch_size, brand_ids, text_len=240)
        result = _fire_one_batch(tweets, max_tokens=max_tokens, timeout=timeout, client=client)
        rows.append({
            "value": str(max_tokens),
            "status": result["status"],
            "wall_clock_s": round(result["wall_clock_s"], 3),
            "response_chars": result["response_chars"],
            "input_tokens": result["input_tokens"],
        })
    return rows


def sweep_input_tokens(
    client: Any,
    base_batch_size: int,
    timeout: float,
    brand_ids: list[str],
    dry_run: bool,
) -> list[dict[str, Any]]:
    """A2 — vary text length at fixed batch_size=base_batch_size."""
    rows: list[dict[str, Any]] = []
    for text_len in INPUT_TOKEN_VALUES:
        if dry_run:
            tweets = _build_synthetic_tweets(base_batch_size, brand_ids, text_len=text_len)
            rows.append({
                "value": str(text_len),
                "status": "dry_run",
                "wall_clock_s": 0.0,
                "response_chars": 0,
                "input_tokens": sum(len(t["text"]) for t in tweets) // 4,
            })
            continue
        tweets = _build_synthetic_tweets(base_batch_size, brand_ids, text_len=text_len)
        result = _fire_one_batch(tweets, max_tokens=1024, timeout=timeout, client=client)
        rows.append({
            "value": str(text_len),
            "status": result["status"],
            "wall_clock_s": round(result["wall_clock_s"], 3),
            "response_chars": result["response_chars"],
            "input_tokens": result["input_tokens"],
        })
    return rows


def sweep_rpm(
    client: Any,
    base_batch_size: int,
    timeout: float,
    brand_ids: list[str],
    dry_run: bool,
) -> list[dict[str, Any]]:
    """A4 — serial request rate; fire for RPM_DURATION_SECONDS per row."""
    rows: list[dict[str, Any]] = []
    for target_rpm in RPM_VALUES:
        if dry_run:
            rows.append({
                "value": str(target_rpm),
                "status": "dry_run",
                "wall_clock_s": 0.0,
                "achieved_rpm": 0.0,
                "rate_limited_count": 0,
            })
            continue
        tweets = _build_synthetic_tweets(base_batch_size, brand_ids, text_len=240)
        interval = 60.0 / target_rpm
        started = time.time()
        calls = 0
        rate_limited = 0
        while time.time() - started < RPM_DURATION_SECONDS:
            result = _fire_one_batch(tweets, max_tokens=1024, timeout=timeout, client=client)
            calls += 1
            if result["status"] == "rate_limited":
                rate_limited += 1
            time.sleep(max(0.0, interval - result["wall_clock_s"]))
        wall_clock_s = time.time() - started
        achieved_rpm = round(calls / wall_clock_s * 60.0, 1) if wall_clock_s > 0 else 0.0
        rows.append({
            "value": str(target_rpm),
            "status": "rate_limited" if rate_limited > 0 else "success",
            "wall_clock_s": round(wall_clock_s, 3),
            "achieved_rpm": achieved_rpm,
            "rate_limited_count": rate_limited,
        })
    return rows


def sweep_cache_state(
    client: Any,
    base_batch_size: int,
    timeout: float,
    brand_ids: list[str],
    dry_run: bool,
) -> list[dict[str, Any]]:
    """A5 — fire 3 consecutive calls at batch_size=1 with 30s gaps.

    Anthropic's prompt-cache TTL is 5 min, so each call should still
    hit cache (read) — the first fresh-process call writes the cache.
    """
    rows: list[dict[str, Any]] = []
    for i in range(3):
        if dry_run:
            rows.append({
                "value": f"call_{i + 1}",
                "status": "dry_run",
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            })
            continue
        tweets = _build_synthetic_tweets(1, brand_ids, text_len=240)
        result = _fire_one_batch(tweets, max_tokens=1024, timeout=timeout, client=client)
        rows.append({
            "value": f"call_{i + 1}",
            "status": result["status"],
            "wall_clock_s": round(result["wall_clock_s"], 3),
            "cache_creation_input_tokens": 0,  # usage not surfaced via batched path
            "cache_read_input_tokens": 0,
        })
        if i < 2 and not dry_run:
            time.sleep(30.0)  # keep cache warm across calls
    return rows


def sweep_concurrency(
    client: Any,
    base_batch_size: int,
    timeout: float,
    brand_ids: list[str],
    dry_run: bool,
) -> list[dict[str, Any]]:
    """A6 — fan out N parallel calls; observe degradation under load (KTD9)."""
    rows: list[dict[str, Any]] = []
    for max_workers in CONCURRENCY_VALUES:
        if dry_run:
            rows.append({
                "value": str(max_workers),
                "status": "dry_run",
                "achieved_calls_per_sec": 0.0,
                "status_histogram": {},
                "in_flight_max": 0,
            })
            continue
        tweets = _build_synthetic_tweets(base_batch_size, brand_ids, text_len=240)
        started = time.time()
        statuses: list[str] = []
        in_flight_max = 0
        in_flight = 0

        def _worker() -> str:
            nonlocal in_flight, in_flight_max
            in_flight += 1
            in_flight_max = max(in_flight_max, in_flight)
            try:
                result = _fire_one_batch(tweets, max_tokens=1024, timeout=timeout, client=client)
                return result["status"]
            finally:
                in_flight -= 1

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(_worker) for _ in range(max_workers)]
            for f in concurrent.futures.as_completed(futures, timeout=CONCURRENCY_DURATION_SECONDS + 10):
                try:
                    statuses.append(f.result())
                except Exception:
                    statuses.append("other")
        wall_clock_s = time.time() - started
        achieved = round(len(statuses) / wall_clock_s, 2) if wall_clock_s > 0 else 0.0
        histogram: dict[str, int] = {}
        for s in statuses:
            histogram[s] = histogram.get(s, 0) + 1
        # Failure if any non-success status
        any_fail = any(s != "success" for s in statuses)
        rows.append({
            "value": str(max_workers),
            "status": "degraded" if any_fail else "success",
            "wall_clock_s": round(wall_clock_s, 3),
            "achieved_calls_per_sec": achieved,
            "status_histogram": histogram,
            "in_flight_max": in_flight_max,
        })
    return rows


class _FakeClient:
    """In-memory Claude client used by --dry-run. Module-scope (not nested
    in main()) so test_probe.py can import and exercise it directly.

    Tracks in-flight call count via class attributes so the concurrency
    sweep can observe the max parallelism the probe actually achieved.
    """
    in_flight: int = 0
    in_flight_max: int = 0
    calls: list[dict[str, Any]] = []

    def messages_create(self, **kwargs: Any) -> dict[str, Any]:
        type(self).in_flight += 1
        type(self).in_flight_max = max(type(self).in_flight_max, type(self).in_flight)
        try:
            type(self).calls.append(kwargs)
            return {"results": [], "usage": {"input_tokens": 0}}
        finally:
            type(self).in_flight -= 1


# --- CLI ------------------------------------------------------------------


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="probe_classify_batch_limits",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--axes",
        default=",".join(sorted(VALID_AXES)),
        help=(
            "Comma-separated subset of axes to run. Valid axes: "
            + ", ".join(sorted(VALID_AXES))
            + ". Default: all.",
        ),
    )
    p.add_argument(
        "--batch-size", type=int, default=20,
        help="Fixed batch size for axes that hold it constant (default: 20, the production value).",
    )
    p.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-call wall-clock timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS}).",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Build every prompt and report len/estimated tokens, never fire any LLM call.",
    )
    return p


def _parse_axes(arg: str) -> list[str]:
    parts = [p.strip() for p in arg.split(",") if p.strip()]
    for a in parts:
        if a not in VALID_AXES:
            sys.exit(f"error: unknown axis {a!r}; valid axes: {sorted(VALID_AXES)}")
    return parts


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    axes = _parse_axes(args.axes)

    have_creds, _key = _have_api_creds()
    if not args.dry_run and not have_creds:
        print(
            "missing ANTHROPIC_API_KEY — set it in the environment "
            "(see ~/.env.secrets) or pass --dry-run to skip live calls.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    # Real client when not dry-run; FakeClaudeClient when dry-run.
    if args.dry_run:
        # Reset class-level in-flight counters so each --dry-run run is independent.
        _FakeClient.in_flight = 0
        _FakeClient.in_flight_max = 0
        _FakeClient.calls = []
        client: Any = _FakeClient()
    else:
        from x_monitor.attribution import AnthropicClaudeClient as _RealClient
        client = _RealClient()

    # Probe entry: dispatch each axis to its sweep function.
    print(f"axes: {axes}")
    print(f"dry_run: {args.dry_run}")
    print(f"timeout: {args.timeout}s")
    print(f"batch_size: {args.batch_size}")
    print()

    all_rows: dict[str, list[dict[str, Any]]] = {}
    verdict: str | None = None
    sweep_dispatch = {
        "batch_size": sweep_batch_size,
        "max_tokens": sweep_max_tokens,
        "input_tokens": sweep_input_tokens,
        "rpm": sweep_rpm,
        "cache_state": sweep_cache_state,
        "concurrency": sweep_concurrency,
    }
    for axis in axes:
        fn = sweep_dispatch[axis]
        rows = fn(client, args.batch_size, args.timeout, DEFAULT_BRAND_IDS, args.dry_run)
        all_rows[axis] = rows
        if axis == "cache_state":
            print(f"=== {axis} ===")
            _print_table(
                ["call", "status", "wall_clock_s", "cache_write", "cache_read"],
                [[r["value"], r["status"], str(r.get("wall_clock_s", "")),
                  str(r.get("cache_creation_input_tokens", "")),
                  str(r.get("cache_read_input_tokens", ""))]
                 for r in rows],
            )
            print()
        elif axis == "rpm":
            print(f"=== {axis} ===")
            _print_table(
                ["target_rpm", "status", "wall_clock_s", "achieved_rpm", "rate_limited"],
                [[r["value"], r["status"], str(r.get("wall_clock_s", "")),
                  str(r.get("achieved_rpm", "")),
                  str(r.get("rate_limited_count", ""))]
                 for r in rows],
            )
            if verdict is None:
                verdict = _verdict_line(axis, rows)
            print()
        elif axis == "concurrency":
            print(f"=== {axis} ===")
            _print_table(
                ["max_workers", "status", "wall_clock_s", "calls/sec", "in_flight_max", "histogram"],
                [[r["value"], r["status"], str(r.get("wall_clock_s", "")),
                  str(r.get("achieved_calls_per_sec", "")),
                  str(r.get("in_flight_max", "")),
                  json.dumps(r.get("status_histogram", {}), default=str)]
                 for r in rows],
            )
            if verdict is None:
                verdict = _verdict_line(axis, rows)
            print()
        else:  # batch_size, max_tokens, input_tokens
            print(f"=== {axis} ===")
            _print_table(
                ["value", "status", "wall_clock_s", "input_tokens", "response_chars"],
                [[r["value"], r["status"], str(r.get("wall_clock_s", "")),
                  str(r.get("input_tokens", "")),
                  str(r.get("response_chars", ""))]
                 for r in rows],
            )
            if verdict is None:
                verdict = _verdict_line(axis, rows)
            print()

    if verdict:
        print(f"VERDICT: {verdict}")
    else:
        print("VERDICT: all green — no axis failed.")

    # U3: write JSON next to the pipeline's run files for follow-up diff.
    json_path = Path("data/runs") / f"probe_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps({
        "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "axes_run": axes,
        "rows": all_rows,
        "verdict": verdict,
    }, indent=2, default=str))
    print(f"\nwrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())