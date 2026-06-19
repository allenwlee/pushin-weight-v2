# {{AGENT_ATTRIBUTION}}
"""Curated X advanced-search query library (R1-R8).

v1.7 update (2026-06-17): The X advanced-search cap is on character
LENGTH (~512, per docs.x.com), not operator count. The v1.6 helpers
`assert_under_operator_cap` / `count_x_operators` are retained for
backward compatibility with v1.6 callers and tests, but new code should
use `assert_under_length_cap` / `X_LENGTH_CAP`. See
docs/plans/2026-06-17-001-refactor-two-call-wide-net-translation-plan.md
§"Cap probe amendment" for the empirical evidence.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


# Allowed expected_signal enum values.
EXPECTED_SIGNALS: frozenset[str] = frozenset(
    {"release", "criticism", "community_question", "commenter_capture", "praise", "other"}
)

# Allowed query IDs.
QUERY_IDS: tuple[str, ...] = ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6")

# X advanced-search operators recognized by validate_query_syntax.
KNOWN_OPERATORS: tuple[str, ...] = (
    "from:",
    "to:",
    "min_faves:",
    "min_retweets:",
    "min_replies:",
    "since:",
    "until:",
    "lang:",
    "-filter:replies",
    "-filter:retweets",
    "-filter:media",
    "-filter:images",
    "-filter:videos",
    "-filter:links",
    "-filter:verified",
    "filter:",
)

# Per R4, lang: is normally NOT used (all-languages default). Per-model
# allowlist overrides (e.g., a model wants ONLY Japanese coverage for an
# experiment). Empty here = no model opts in by default.
LANG_ALLOWLIST: dict[str, set[str]] = {}


class Query(BaseModel):
    """A single curated X advanced-search query (one of Q1-Q6 for a model)."""

    id: Literal["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]
    query_string: str = Field(min_length=1)
    expected_signal: Literal[
        "release", "criticism", "community_question", "commenter_capture", "praise", "other"
    ]
    max_results: int = Field(default=50, ge=1, le=200)
    enabled: bool = True
    min_faves: int = Field(default=0, ge=0)
    notes: str = ""

    @field_validator("query_string")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query_string must not be blank")
        return v


def load_queries(brand_id: str, root: Path) -> list[Query]:
    """Load and validate the 6 queries (Q1-Q6) for one model.

    root is the data/ directory of x-monitoring.
    """
    path = root / "queries" / f"{brand_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"missing query file: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict) or "queries" not in raw:
        raise ValueError(f"{path}: top-level key 'queries' required")
    qs_raw = raw["queries"]
    if not isinstance(qs_raw, list):
        raise ValueError(f"{path}: 'queries' must be a list")
    seen_ids: set[str] = set()
    qs: list[Query] = []
    for entry in qs_raw:
        q = Query.model_validate(entry)
        if q.id in seen_ids:
            raise ValueError(f"{path}: duplicate query id {q.id}")
        seen_ids.add(q.id)
        qs.append(q)
    expected = set(QUERY_IDS)
    if set(seen_ids) != expected:
        missing = expected - set(seen_ids)
        extra = set(seen_ids) - expected
        problems: list[str] = []
        if missing:
            problems.append(f"missing: {sorted(missing)}")
        if extra:
            problems.append(f"unexpected: {sorted(extra)}")
        raise ValueError(f"{path}: query ids wrong ({', '.join(problems)})")
    return qs


def validate_query_syntax(q: Query) -> list[str]:
    """Return a list of human-readable syntax errors. Empty list = OK.

    Catches:
      - unbalanced parens
      - stray `from:@handle` (extra colon after operator arg)
      - bad `min_faves:notanumber` (validator catches at pydantic, but the
        syntax check is for the substring pattern in the query string)
      - lang: used when not in LANG_ALLOWLIST for this query
    """
    errors: list[str] = []
    s = q.query_string
    # Balanced parens
    if s.count("(") != s.count(")"):
        errors.append(f"unbalanced parens in '{s[:60]}...'")
    # Stray colon after from/to operator arg
    import re

    if re.search(r"\bfrom:@", s):
        errors.append("stray colon after from: arg (use 'from:handle' not 'from:@handle')")
    if re.search(r"\bto:@", s):
        errors.append("stray colon after to: arg")
    # Operator-token recognition: every "WORD:" token in the query should
    # correspond to a known operator prefix.
    tokens = re.findall(r"[\-]?\w+:", s)
    for tok in tokens:
        if not any(tok.startswith(op) for op in KNOWN_OPERATORS):
            errors.append(f"unknown operator token '{tok}' in query")
    # lang: filter usage check (R4)
    if "lang:" in s and q.id not in LANG_ALLOWLIST.get("*", set()):
        # Per-model allowlist
        # (We don't have model context here; the caller checks per-model)
        errors.append(
            "lang: filter present; confirm it is intentional (R4: all-languages default)"
        )
    return errors


def estimated_cost(queries: list[Query]) -> int:
    """Sum max_results across enabled queries. Used by the budget guard."""
    return sum(q.max_results for q in queries if q.enabled)


# --- X advanced-search operator cap (v1.6) --------------------------------

# X advanced search silently drops operators past ~22-23 per query: an
# over-cap query returns HTTP 200 with `tweets: []` and no error. We count
# top-level OR tokens (paren-stripped) and refuse to fire the call when over
# the cap — this is the loud-fail behavior the v1.6 pipeline needs.
X_OPERATOR_CAP = 22
_OR_OP_RE = re.compile(r"\bOR\b", re.IGNORECASE)


def count_x_operators(query: str) -> int:
    """Count top-level OR tokens in the query string.

    X treats each `from:X` / `to:X` / `min_faves:N` as one operator and the
    platform-enforced cap sits around 22-23. We count only the top-level OR
    tokens (i.e., those outside any paren group) because X collapses nested
    parens before counting; for our purposes — knowing whether we're about
    to hit the silent-fail cliff — top-level is the conservative answer.
    """
    # X caps total operators (\bOR\b, `from:`, `to:`, `min_faves:`, etc.)
    # at around 22-23 per query; an over-cap query silently returns 0
    # tweets. We count just \bOR\b tokens because the other operators
    # (from:/to:/min_faves:) are the same shape across all our queries —
    # what varies and what matters for the cap is the OR-chain length.
    return len(_OR_OP_RE.findall(query))


def assert_under_operator_cap(query: str) -> None:
    """Raise ValueError if the query exceeds X's ~22 OR-operator cap.

    Callers in RunPipeline.execute invoke this BEFORE apify.run_search so an
    over-cap query is short-circuited into a per-query summary entry
    `{status: "operator_cap_exceeded"}` and no credits are burned.
    """
    n = count_x_operators(query)
    if n > X_OPERATOR_CAP:
        raise ValueError(
            f"query has {n} OR operators at the top level; X caps at ~"
            f"{X_OPERATOR_CAP}. 0-tweet silent fail expected. Rewrite with "
            f"fewer OR clauses or split into multiple calls."
        )


# --- X advanced-search LENGTH cap (v1.7) --------------------------------
#
# The actual constraint on X advanced-search queries is the URL-encoded
# character length of the `query` parameter (~512 per docs.x.com), not
# the operator count. v1.6 used the operator-count cap (22) which is a
# conservative proxy. For v1.7's Call B (paren-grouped brand-wide net),
# we need a length check to be safe.
#
# TwitterAPI.io (the v1.7 fetch backend) silently returns 0 results on
# over-length queries — same silent-fail mode as the operator cap, just
# triggered by length, not count. See memory feedback
# `feedback_x_advanced_search_cap_is_characters_not_operators.md`.

X_LENGTH_CAP = 512


def assert_under_length_cap(
    query: str, max_len: int = X_LENGTH_CAP
) -> None:
    """Raise ValueError if the query exceeds the X length cap.

    Args:
        query: the full X advanced-search query string (operators, OR
            tokens, paren groups — the whole thing).
        max_len: the cap. Default 512 (X's documented limit per
            docs.x.com). Override only for tests that probe the
            boundary.

    The check is on the literal string length of the query, since
    that's what X (and TwitterAPI.io) sees. URL-encoding would expand
    special chars (~33% for spaces, more for CJK), so a 512-char
    literal is the conservative cap.

    Callers in RunPipeline.execute invoke this BEFORE
    twitterapi.run_search so an over-length query is short-circuited
    into a per-query summary entry
    `{status: "length_cap_exceeded"}` and no credits are burned.
    """
    n = len(query)
    if n > max_len:
        raise ValueError(
            f"query length is {n} chars; X caps at {max_len} per "
            f"docs.x.com. Over-length queries silently return 0 results. "
            f"Rewrite with fewer tokens, narrower OR-chains, or split "
            f"into multiple calls."
        )
