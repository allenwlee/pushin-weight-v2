# {{AGENT_ATTRIBUTION}}
"""Build the per-cycle call list from accounts + intent buckets (v1.6).

In the v1.5 architecture, the pipeline ran 6 queries per model
(7 brands × 6 = 42 calls/cycle) and the per-tweet `source_query_id`
attribution came for free. The v1.6 architecture collapses:

  - Account coverage: 1 OR-chain per brand, e.g.
      (from:MiniMaxAI OR to:MiniMaxAI OR from:STAFF1 OR to:STAFF1
       OR ... OR from:STAFF10 OR to:STAFF10) min_faves:1
    = 22 operators at 1 official + 10 staff, under X's ~22-cap.
  - Intent coverage: 1-3 OR-chains per intent bucket, e.g.
      ((MiMo OR 小米) OR (DeepSeek OR 深度求索) OR ...)
      (how OR 怎么 OR 教程 OR ...) min_faves:0
    = N brand-terms + M intent-terms, split when over the cap.

The per-tweet brand + signal attribution is recovered post-fetch by
`x_monitor.intent_classifier`. The filter pipeline (relevance, review
queue) runs unchanged after the post-fetch classify step.

This module is the source of truth for which calls fire in a cycle.
`RunPipeline.execute` iterates the PlannedCall list it returns; tests
target the helpers directly to lock the call-shape invariants.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from .accounts import load_accounts, load_staff
from .queries import (
    X_OPERATOR_CAP,
    assert_under_operator_cap,
    count_x_operators,
)


# Intent bucket definitions. The post-fetch classifier (intent_classifier.py)
# must agree on which tokens map to which signal — keep these in sync.
INTENT_BUCKETS: dict[str, dict[str, object]] = {
    # Token lists are ORed at the top level of the intent clause.
    # CJK terms are matched by substring (no \\b), ASCII by word boundary
    # in the post-fetch classifier.
    "howto_criticism": {
        "tokens": [
            "how", "tutorial", "怎么", "教程", "guide", "如何",
            "broken", "fails", "bad", "翻车", "不行",
        ],
        "expected_signal": "criticism",  # post-fetch bias; classifier may override
    },
    "benchmark_tech": {
        "tokens": [
            "benchmark", "eval", "paper", "github", "code", "开源",
        ],
        "expected_signal": "other",
    },
    "praise_other": {
        "tokens": [
            "amazing", "incredible", "best", "love", "mind blowing",
            "🤯", "卧槽", "太强了",
        ],
        "expected_signal": "praise",
    },
}


@dataclass
class PlannedCall:
    """A single API call to fire this cycle.

    Attributes:
        call_kind: "account" = per-brand from/to chain; "intent" =
            cross-brand intent bucket.
        model_id: brand this call maps to. For intent calls, this is
            the FIRST brand in the included split (used as a placeholder
            for `source_query_id`; the post-fetch classifier reassigns
            the real model_id from the tweet content).
        bucket: None for account calls; intent bucket name for intent calls.
        query_string: the actual X advanced-search query (operator cap
            already asserted).
        expected_signal: signal bucket this call primarily targets.
            Account calls target "release"; intent calls target the
            bucket's expected_signal.
        n_operators: top-level OR token count in query_string.
    """

    call_kind: Literal["account", "intent"]
    model_id: str
    bucket: str | None
    query_string: str
    expected_signal: str
    n_operators: int


def _bucket_to_signal(bucket_name: str) -> str:
    """Map an intent bucket name to its primary expected_signal."""
    info = INTENT_BUCKETS.get(bucket_name)
    if not info:
        return "other"
    return str(info["expected_signal"])


def _extract_brand_tokens(query_string: str) -> list[str]:
    """Pull the brand-term list from the first `(...)` group of a query.

    The Q2-Q6 query yaml pattern is `(Brand1 OR Brand2 OR ...) (intent ...)
    min_faves:N`. We parse the first paren group, split on ` OR `, and
    return the stripped token list. Quoted tokens (e.g., "love it") are
    preserved as-is so the post-fetch classifier sees them literally.
    """
    m = re.search(r"\(([^()]*)\)", query_string)
    if not m:
        return []
    inner = m.group(1)
    return [tok.strip() for tok in inner.split(" OR ") if tok.strip()]


def _load_brand_tokens_per_model(
    enabled_models: list[str], queries_dir: Path
) -> dict[str, list[str]]:
    """For each enabled model, return its brand-token list (deduplicated).

    Brand tokens are read from the Q2 / Q3 / Q5 / Q6 query strings (the
    intent queries carry the brand OR-clause). If a model has none of
    those enabled, the brand-token list falls back to [].
    """
    out: dict[str, list[str]] = {}
    for m in enabled_models:
        path = queries_dir / f"{m}.yaml"
        if not path.exists():
            out[m] = []
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        seen: set[str] = set()
        toks: list[str] = []
        for entry in raw.get("queries", []):
            if entry.get("id") not in {"Q2", "Q3", "Q5", "Q6"}:
                continue
            for tok in _extract_brand_tokens(entry.get("query_string", "")):
                if tok not in seen:
                    seen.add(tok)
                    toks.append(tok)
        out[m] = toks
    return out


def _split_brands_to_fit_cap(
    brand_tokens: dict[str, list[str]],
    intent_tokens: list[str],
    operator_cap: int,
) -> list[dict[str, list[str]]]:
    """Split the brand-token map into 1+ chunks, each within the operator cap.

    For a single bucket, the operator count is approximately
        len(brand_tokens) + len(intent_tokens) + 1
    (the +1 covers the OR between the brands clause and the intent clause;
    intra-clause ORs are counted separately as N-1 and M-1 respectively,
    so the formula above is the count of `OR` tokens at the top level).

    If a single chunk over-shoots the cap, we halve the brand list and
    emit two chunks; if either half still over-shoots, we halve again.
    The intent-token list is NOT split (one bucket, one intent OR list).
    """
    if not brand_tokens:
        return []
    single_count = count_x_operators(_compose_intent_query(brand_tokens, intent_tokens))
    if single_count <= operator_cap:
        return [brand_tokens]
    # Halve the brand list. Recurse if needed.
    items = list(brand_tokens.items())
    mid = max(1, len(items) // 2)
    left = dict(items[:mid])
    right = dict(items[mid:])
    out: list[dict[str, list[str]]] = []
    for half in (left, right):
        if not half:
            continue
        out.extend(_split_brands_to_fit_cap(half, intent_tokens, operator_cap))
    return out


def _compose_intent_query(
    brand_tokens: dict[str, list[str]], intent_tokens: list[str]
) -> str:
    """Build the cross-brand intent query string (no cap check here).

    Shape: `((BrandA OR A2) OR (BrandB OR B2) OR ...) intent1 OR intent2
    OR ... min_faves:0`. The outer paren around brands is required to
    keep the brand clause as a single token against the intent OR-list.
    The intent clause is NOT wrapped in extra parens — it is already
    a flat OR list of tokens at the top level.
    """
    brands_part = " OR ".join(
        f"({' OR '.join(toks)})" for toks in brand_tokens.values() if toks
    )
    intent_part = " OR ".join(intent_tokens)
    return f"({brands_part}) {intent_part} min_faves:0"


def plan_calls(
    data_dir: Path,
    enabled_models: list[str],
    *,
    operator_cap: int = X_OPERATOR_CAP,
) -> list[PlannedCall]:
    """Build the per-cycle call list.

    Returns one PlannedCall per (brand, kind) and 1-3 per intent bucket
    bucketed across all brands. Order: account calls first (release +
    mention capture), then intent calls.

    Raises:
        ValueError: if any emitted query exceeds operator_cap (propagated
            from `assert_under_operator_cap`). The pipeline treats this as
            a per-query summary entry and skips the call.
    """
    calls: list[PlannedCall] = []
    # Account calls: per-brand, from:OFFICIAL + to:OFFICIAL + from:STAFF +
    # to:STAFF for each staff handle in the brand's staff list. Each
    # handle contributes 2 ORs (from:H, to:H) — at 1 official + 10 staff
    # we get 22 ORs, exactly at the cap.
    for m in enabled_models:
        try:
            accts = load_accounts(m, data_dir)
        except (FileNotFoundError, ValueError):
            continue
        handles = [a.handle for a in accts if a.role == "official"]
        try:
            staff = load_staff(m, data_dir)
        except (FileNotFoundError, ValueError):
            staff = []
        all_handles = handles + [s.handle for s in staff]
        if not all_handles:
            continue
        from_to = " OR ".join(f"from:{h} OR to:{h}" for h in all_handles)
        q = f"({from_to}) min_faves:1"
        assert_under_operator_cap(q)
        calls.append(
            PlannedCall(
                call_kind="account",
                model_id=m,
                bucket=None,
                query_string=q,
                expected_signal="release",
                n_operators=count_x_operators(q),
            )
        )
    # Intent calls: bucket each brand's brand-terms with intent tokens.
    brand_tokens_per_model = _load_brand_tokens_per_model(
        enabled_models, data_dir / "queries"
    )
    for bucket_name, info in INTENT_BUCKETS.items():
        intent_tokens = list(info["tokens"])  # type: ignore[arg-type]
        splits = _split_brands_to_fit_cap(
            brand_tokens_per_model, intent_tokens, operator_cap
        )
        for split in splits:
            if not split:
                continue
            q = _compose_intent_query(split, intent_tokens)
            assert_under_operator_cap(q)
            first_brand = next(iter(split))
            calls.append(
                PlannedCall(
                    call_kind="intent",
                    model_id=first_brand,
                    bucket=bucket_name,
                    query_string=q,
                    expected_signal=_bucket_to_signal(bucket_name),
                    n_operators=count_x_operators(q),
                )
            )
    return calls
