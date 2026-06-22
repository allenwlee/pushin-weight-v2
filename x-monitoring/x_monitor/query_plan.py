# {{AGENT_ATTRIBUTION}}
"""Per-cycle call planning for x-monitor.

v1.7 redesign (2026-06-17):

The v1.6 plan emitted 7-15 calls per cycle (one account call per brand +
3 intent buckets, sometimes split across multiple calls to fit the old
22-OR operator cap). The empirical cap probe on 2026-06-17 confirmed the
real cap is **character length** (~512, per docs.x.com), not operator
count — and that the `list:<id>` operator (~12 chars) returns tweets
from any list (public or private) without scaling the query string.

v1.7 collapses all per-cycle work to **2 calls** by default:

  Call A (account):   (list:<x_monitor_list_id>) min_faves:1
                       — picks up everything from list members,
                         one place to manage brand coverage.
  Call B (brand_wide): ((BrandTok1a OR BrandTok1b) OR
                        (BrandTok2a OR BrandTok2b) OR ... OR
                        (BrandTokNa OR ...)) min_faves:0
                       — paren-grouped brand tokens across all
                         yaml-defined brands, regardless of list
                         membership. Catches the long tail of
                         mentions not from the curated handles.

v1.7.x adds an optional **Call C** — a per-brand brand-wide query with
a co-occurrence constraint — for brands whose tokens collide with
unrelated common nouns. Shape: `(<tokens>) (<co_occurrence>) min_faves:N`
— implicit AND between the two groups, so every result matches BOTH
a brand token AND at least one co-occurrence term. Configured via
`call_c_specs:` in config.yaml; default empty list emits no Call C.

Signal classification is post-fetch in `intent_classifier.classify_signal`
and `attribute_to_brand` (Unit 2). The query shape no longer encodes
signal intent — the structure is one wide net, one targeted net.

Length cap guard: `assert_under_length_cap` is called on every emitted
query so an over-cap query short-circuits to a per-query summary entry
(status: "length_cap_exceeded") and no credits are burned.

The retired v1.6 `INTENT_BUCKETS`, `_split_brands_to_fit_cap`, and
`_compose_intent_query` are gone. Tests assert their absence
(see test_query_plan_v17.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from .queries import X_LENGTH_CAP, assert_under_length_cap


CallKind = Literal["account", "brand_wide"]


@dataclass
class PlannedCall:
    """A single API call to fire this cycle.

    Attributes:
        call_id: human label for the call ("A", "B", "C1", "C2", ...).
            Stable across cycles; useful for logging/dedup/raw-file
            naming alongside brand_id+call_kind.
        call_kind: "account" = list-based fan-in (Call A in v1.7);
            "brand_wide" = paren-grouped brand-token OR-chain (Call B
            or Call C variants).
        brand_id: brand this call is attributed to. For Call A
            (list-based), this is "*" because the list spans all
            brands — post-fetch `attribute_to_brand` reassigns. For
            Call B, this is the FIRST brand in the input order (used
            as a placeholder for `source_query_id`; same reassignment
            applies). For Call C, this is the spec's brand_id (the
            call's primary target).
        bucket: None for both v1.7 call kinds. Retained for schema
            stability with the v1.6 contract.
        query_string: the actual X advanced-search query.
        expected_signal: signal bucket this call primarily targets.
            Call A targets "release" (faved official posts).
            Call B targets "other" (the long tail; classifier may
            upgrade to criticism/praise/etc). Call C defaults to
            "other" per the spec.
        query_length: len(query_string) in characters. Verified under
            `X_LENGTH_CAP` (512) before being returned.
    """

    call_id: str
    call_kind: CallKind
    brand_id: str
    bucket: str | None
    query_string: str
    expected_signal: str
    query_length: int


@dataclass
class CallCBrandSpec:
    """Per-brand spec for an optional Call C co-occurrence-constrained
    brand-wide query.

    Read from config.yaml `call_c_specs:` (not from data/queries/) so
    the spec stays operator-tunable in the same PR-reviewable file as
    other config. Each spec emits one extra API call per cycle.

    Attributes:
        brand_id: the brand this call attributes to. Must match an
            enabled model (Call B's regex post-fetch will only land
            posts here if the brand_id is recognised).
        tokens: list of brand tokens to OR-join in the primary group.
        co_occurrence: list of co-occurrence terms to OR-join in the
            secondary group. Posts must match at least one term from
            each group (implicit AND between the two parenthesised
            groups in X advanced-search syntax).
        expected_signal: signal bucket this call primarily targets.
            "other" by default (long tail; classifier may upgrade).
        min_faves: lower bound on the call's min_faves. 0 by default
            (no lower bound).
    """
    brand_id: str
    tokens: list[str]
    co_occurrence: list[str]
    expected_signal: str = "other"
    min_faves: int = 0


def _build_call_c_query(spec: CallCBrandSpec) -> str:
    """Compose one Call C from a CallCBrandSpec.

    Shape: `(<tokens>) (<co_occurrence>) min_faves:N` — implicit AND
    between the two paren groups. Length-cap assertion is the caller's
    responsibility (mirrors _build_brand_wide_query).
    """
    primary = f"({' OR '.join(spec.tokens)})"
    secondary = f"({' OR '.join(spec.co_occurrence)})"
    return f"{primary} {secondary} min_faves:{spec.min_faves}"


def _load_brand_tokens_per_model(
    enabled_models: list[str], queries_dir: Path
) -> dict[str, list[str]]:
    """For each enabled model, return its brand-token list (deduplicated).

    Brand tokens are read from the Q2 / Q3 / Q5 / Q6 query strings (the
    intent queries carry the brand OR-clause). If a model has none of
    those enabled, or its yaml is missing, the brand-token list falls
    back to [] — the model contributes 0 paren groups to Call B.
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
            inner = entry.get("query_string", "")
            # Pull the first `(...)` group (the brand clause) and split.
            # No re import — we use a tiny inline parser.
            depth = 0
            start = -1
            for i, ch in enumerate(inner):
                if ch == "(":
                    if depth == 0:
                        start = i + 1
                    depth += 1
                elif ch == ")":
                    if depth > 0:
                        depth -= 1
                        if depth == 0 and start != -1:
                            group = inner[start:i]
                            for tok in group.split(" OR "):
                                tok = tok.strip()
                                if tok and tok not in seen:
                                    seen.add(tok)
                                    toks.append(tok)
                            start = -1
                            break
        out[m] = toks
    return out


def _build_brand_wide_query(
    brand_tokens_per_model: dict[str, list[str]],
    enabled_models: list[str],
) -> str:
    """Compose Call B from per-model brand tokens.

    Shape: `((BrandTok1a OR BrandTok1b) OR (BrandTok2a OR ...) OR ...
    OR (BrandTokNa OR ...)) min_faves:0`. The outer paren around the
    whole brand OR chain is required so the trailing `min_faves:0`
    binds to the whole expression. Each per-model group is itself a
    paren to keep its inner ORs together.

    Iteration order follows `enabled_models` (NOT alphabetical) so the
    plan is deterministic and the post-fetch `attribute_to_brand`
    regex can match brand group boundaries in a known order.

    Models with empty token lists contribute 0 paren groups.
    """
    parts: list[str] = []
    for m in enabled_models:
        toks = brand_tokens_per_model.get(m, [])
        if not toks:
            continue
        parts.append(f"({' OR '.join(toks)})")
    if not parts:
        # Defensive — should not happen at the 7-brand baseline, but
        # an all-empty configuration still returns a syntactically
        # valid (if useless) query.
        return "(empty) min_faves:0"
    return f"({' OR '.join(parts)}) min_faves:0"


def plan_calls(
    data_dir: Path,
    enabled_models: list[str],
    *,
    x_monitor_list_id: int | str,
    call_c_specs: list[CallCBrandSpec] | None = None,
) -> list[PlannedCall]:
    """Build the per-cycle call list (v1.7: 2 calls; v1.7.x: 2 + N).

    Call A — `(list:<x_monitor_list_id>) min_faves:1` — fans in all
    curated list members in one go. The list is operator-managed (see
    the v1.7 plan's "Operator manual step"). Length: ~29 chars
    regardless of list size.

    Call B — `((BrandTok_a OR BrandTok_b) OR ... OR (BrandTok_n OR ...))
    min_faves:0` — catches the long tail of brand mentions from
    non-list accounts. ~218 chars at the 7-brand baseline; well under
    the 512-char cap. v1.7 keeps this as a single paren-grouped call
    because we have well under 17 brands (the threshold where Call B
    would need splitting — see queries.py:212 docstring).

    Call C (optional, one per CallCBrandSpec) — `(<tokens>) (<co_occurrence>)
    min_faves:N` — per-brand co-occurrence-constrained brand-wide query
    for brands whose bare tokens collide with unrelated common nouns.

    Args:
        data_dir: project data/ directory (yaml files live under
            data/queries/<model>.yaml).
        enabled_models: brands to include, in the order Call B's paren
            groups are emitted.
        x_monitor_list_id: numeric X list ID for Call A. Required —
            v1.7 does not operate without a list, because Call A is
            the only place we get "faved by official handles" signal
            at scale.
        call_c_specs: optional list of CallCBrandSpec. Each spec emits
            one extra API call per cycle. Default: empty (no Call C;
            v1.7 stays at 2 calls).

    Returns:
        [Call A, Call B, *Call C specs]. Each call has already been
        length-capped.

    Raises:
        TypeError: if x_monitor_list_id is not provided.
        ValueError: if any emitted query exceeds 512 chars
            (propagated from `assert_under_length_cap`).
    """
    if x_monitor_list_id is None:
        raise TypeError(
            "plan_calls() requires x_monitor_list_id (v1.7's Call A is "
            "list-based; no fallback to per-brand account calls)."
        )

    call_a_query = f"(list:{x_monitor_list_id}) min_faves:1"
    assert_under_length_cap(call_a_query)

    brand_tokens = _load_brand_tokens_per_model(
        enabled_models, data_dir / "queries"
    )
    call_b_query = _build_brand_wide_query(brand_tokens, enabled_models)
    assert_under_length_cap(call_b_query)

    result: list[PlannedCall] = [
        PlannedCall(
            call_id="A",
            call_kind="account",
            brand_id="*",
            bucket=None,
            query_string=call_a_query,
            expected_signal="release",
            query_length=len(call_a_query),
        ),
        PlannedCall(
            call_id="B",
            call_kind="brand_wide",
            brand_id=enabled_models[0] if enabled_models else "*",
            bucket=None,
            query_string=call_b_query,
            expected_signal="other",
            query_length=len(call_b_query),
        ),
    ]
    for i, spec in enumerate(call_c_specs or []):
        call_c_query = _build_call_c_query(spec)
        assert_under_length_cap(call_c_query)
        result.append(
            PlannedCall(
                call_id=f"C{i+1}",
                call_kind="brand_wide",
                brand_id=spec.brand_id,
                bucket=None,
                query_string=call_c_query,
                expected_signal=spec.expected_signal,
                query_length=len(call_c_query),
            )
        )
    return result


# Retired v1.6 symbols — referenced in tests as `hasattr() == False`.
# Kept here ONLY as a structural marker; do not uncomment or call.
# def _split_brands_to_fit_cap(...): ...
# INTENT_BUCKETS: dict = {}  # removed in v1.7
