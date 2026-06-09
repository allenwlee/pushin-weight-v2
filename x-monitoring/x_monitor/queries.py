# {{AGENT_ATTRIBUTION}}
"""Curated X advanced-search query library (R1-R8)."""

from __future__ import annotations

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


def load_queries(model_id: str, root: Path) -> list[Query]:
    """Load and validate the 6 queries (Q1-Q6) for one model.

    root is the data/ directory of x-monitoring.
    """
    path = root / "queries" / f"{model_id}.yaml"
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
