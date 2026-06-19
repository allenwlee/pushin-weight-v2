# {{AGENT_ATTRIBUTION}}
"""
Per-model relevance post-filter (v1.2).

Loads a RelevanceConfig from data/filters/<brand_id>.yaml and applies
filter_posts() to a list of normalized tweet dicts (the shape produced
by x_monitor.apify._normalize_tweet, with brand_id and source_query_id
stamped by the run loop). Returns the kept set + per-reason drop counts.

Token matching rules:
- ASCII tokens use word-boundary regex on casefold()ed text.
- CJK tokens use plain `in` on casefold()ed text (no word boundaries in CJK).
- casefold() (not lower()) — correct for German ß, Turkish dotless i, etc.

Filter decision tree (per item):
1. Author is canonical_handle        -> KEEP, count canonical_bypass.
2. text is URL-only and not dropping -> KEEP, count url_only_kept
                                        (downstream headline pass will fill).
3. has_must and not banned-only      -> KEEP.
4. banned and no must                -> SOFT-DROP (caller routes to review queue).
5. no must, no banned                -> HARD-DROP (count hard_drop_no_signal).
6. drop_url_only and URL-only        -> HARD-DROP (count hard_drop_url_only).

Soft-drop vs hard-drop distinction lets the user recover via
`x-monitor review resolve` if a real post gets soft-dropped.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


# --- Pydantic model ------------------------------------------------------


class RelevanceConfig(BaseModel):
    """Per-model filter config. Loaded from data/filters/<brand_id>.yaml."""

    canonical_handles: list[str] = Field(
        default_factory=list,
        description=(
            "Author handles that bypass token gates (case-insensitive). "
            "Official brand accounts and known AI press/devtool accounts."
        ),
    )
    must_have_any: list[str] = Field(
        default_factory=list,
        description=(
            "At least one ASCII token (word-boundary regex) or CJK token "
            "(plain `in`) must appear in text. Empty = no token gate."
        ),
    )
    cjk_tokens: list[str] = Field(
        default_factory=list,
        description=(
            "CJK tokens matched with plain `in` on casefold()ed text. "
            "Listed separately from must_have_any for clarity in the YAML."
        ),
    )
    must_have_none: list[str] = Field(
        default_factory=list,
        description=(
            "Banned tokens. If any match AND no must_have token also "
            "matched, the post is SOFT-DROPPED to the review queue."
        ),
    )
    drop_url_only: bool = Field(
        default=False,
        description=(
            "If True, URL-only posts are HARD-DROPPED (instead of kept for "
            "the downstream headline enrichment pass)."
        ),
    )
    verified_at: str = Field(
        default="",
        description="ISO date when canonical_handles was last audited.",
    )
    notes: str = Field(default="", description="Free-form reviewer notes.")

    @field_validator("canonical_handles", "must_have_any", "must_have_none", "cjk_tokens")
    @classmethod
    def _strip_blanks(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if s and s.strip()]

    @field_validator("cjk_tokens")
    @classmethod
    def _warn_short_cjk(cls, v: list[str]) -> list[str]:
        for tok in v:
            if len(tok) < 2:
                raise ValueError(
                    f"CJK token {tok!r} is too short (1 char) — would match "
                    "too much. Use at least 2 characters."
                )
        return v


# --- Token matching ------------------------------------------------------


# URLs that look like text content (not just bare t.co).
# We treat a post as "URL-only" if stripping all t.co and http(s) URLs
# leaves no other content.
_TCO_RE = re.compile(r"https?://t\.co/\w+", re.IGNORECASE)
_HTTP_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def _strip_urls(text: str) -> str:
    return _TCO_RE.sub("", _HTTP_RE.sub("", text)).strip()


def is_url_only(text: str | None) -> bool:
    """True if the post is essentially just one or more URLs."""
    if not text:
        return False
    return _strip_urls(text) == ""


def _has_cjk(token: str) -> bool:
    """A token is CJK if it contains any CJK Unified Ideograph."""
    return any("一" <= ch <= "鿿" for ch in token)


def _match_token(token: str, text_cf: str) -> bool:
    """Match one token against casefold()ed text.

    CJK tokens use `in` (no word boundaries in CJK).
    ASCII tokens use word-boundary regex (so "F1" doesn't match "F12"
    and "kimi" doesn't match "kimiko").
    """
    if _has_cjk(token):
        return token.casefold() in text_cf
    # ASCII: word boundary. casefold the token too.
    pattern = r"\b" + re.escape(token.casefold()) + r"\b"
    return re.search(pattern, text_cf) is not None


def _has_any(tokens: list[str], text_cf: str) -> bool:
    return any(_match_token(t, text_cf) for t in tokens)


# --- filter_posts --------------------------------------------------------


# Drop-reason keys — also documented in tests/test_relevance.py.
REASON_CANONICAL_BYPASS = "canonical_bypass"
REASON_URL_ONLY_KEPT = "url_only_kept"
REASON_HARD_DROP_NO_SIGNAL = "hard_drop_no_signal"
REASON_SOFT_DROP_BANNED = "soft_drop_banned"
REASON_HARD_DROP_URL_ONLY = "hard_drop_url_only"
REASON_KEPT = "kept"


def _is_canonical_author(author_handle: str | None, cfg: RelevanceConfig) -> bool:
    if not author_handle:
        return False
    h = author_handle.casefold()
    return any(casefold_eq(h, c) for c in cfg.canonical_handles)


def casefold_eq(a: str, b: str) -> bool:
    """Case-insensitive equality using casefold() (correct for non-ASCII)."""
    return a.casefold() == b.casefold()


def filter_posts(
    items: list[dict[str, Any]],
    cfg: RelevanceConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Apply the per-model relevance filter.

    Args:
        items: list of normalized post dicts (must have `text` and
            `author_handle`; other fields passed through).
        cfg: the per-model config.

    Returns:
        (kept, stats, soft_dropped)
        - kept: list of items that should be inserted into the DB.
        - stats: dict with keys
            - "n_dropped": int (hard + soft)
            - "n_kept": int
            - "n_soft_dropped": int
            - "reasons": Counter of reason -> count
        - soft_dropped: list of {tweet_id, brand_id, text_excerpt, reason}
            items for the caller to route to the review queue.
    """
    kept: list[dict[str, Any]] = []
    soft_dropped: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    n_soft = 0

    # Precompute the union of must tokens (ASCII + CJK) for the decision tree.
    must_tokens = list(cfg.must_have_any) + list(cfg.cjk_tokens)
    banned_tokens = list(cfg.must_have_none)

    for item in items:
        text = item.get("text") or ""
        author = item.get("author_handle")
        text_cf = unicodedata.normalize("NFC", text).casefold()
        url_only = is_url_only(text)

        # 1. Canonical author bypasses everything.
        if _is_canonical_author(author, cfg):
            kept.append(item)
            reasons[REASON_CANONICAL_BYPASS] += 1
            continue

        # 6. Explicit drop_url_only overrides URL-only keep.
        if cfg.drop_url_only and url_only:
            reasons[REASON_HARD_DROP_URL_ONLY] += 1
            continue

        # 2. URL-only posts pass through (downstream headline pass fills them).
        if url_only:
            kept.append(item)
            reasons[REASON_URL_ONLY_KEPT] += 1
            continue

        # Token decisions.
        has_must = _has_any(must_tokens, text_cf) if must_tokens else False
        has_banned = _has_any(banned_tokens, text_cf) if banned_tokens else False

        # 3. Has must and (no banned, or banned is overridden by must).
        if has_must:
            kept.append(item)
            reasons[REASON_KEPT] += 1
            continue

        # No must tokens configured AND no banned tokens configured ->
        # this model has no relevance filter. Keep everything.
        if not must_tokens and not banned_tokens:
            kept.append(item)
            reasons[REASON_KEPT] += 1
            continue

        # 4. Banned with no must -> soft-drop to review queue.
        if has_banned:
            reasons[REASON_SOFT_DROP_BANNED] += 1
            n_soft += 1
            soft_dropped.append(
                {
                    "tweet_id": item.get("tweet_id") or item.get("id") or "",
                    "brand_id": item.get("brand_id", ""),
                    "text_excerpt": text[:200],
                    "reason": "banned_token",
                }
            )
            continue

        # 5. No must, no banned -> hard-drop.
        reasons[REASON_HARD_DROP_NO_SIGNAL] += 1

    n_dropped = sum(v for k, v in reasons.items() if k != REASON_KEPT
                    and k != REASON_CANONICAL_BYPASS
                    and k != REASON_URL_ONLY_KEPT)
    n_kept = len(kept)

    stats = {
        "n_dropped": n_dropped,
        "n_kept": n_kept,
        "n_soft_dropped": n_soft,
        "reasons": dict(reasons),
    }
    return kept, stats, soft_dropped


# --- YAML loader ---------------------------------------------------------


def load_filter(brand_id: str, root: Path) -> RelevanceConfig:
    """Load data/filters/<brand_id>.yaml, return RelevanceConfig.

    If the file is missing, returns an empty config (no filter applied).
    This is intentional: legacy models can be added without a filter,
    and the user can drop in a YAML later to enable one.
    """
    path = root / "filters" / f"{brand_id}.yaml"
    if not path.exists():
        return RelevanceConfig()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    # Allow either a top-level dict or a wrapped {"filter": {...}} for
    # future expansion (mirrors the queries.py loader shape).
    if isinstance(raw, dict) and "filter" in raw and isinstance(raw["filter"], dict):
        raw = raw["filter"]
    return RelevanceConfig.model_validate(raw)


# --- Audit helper --------------------------------------------------------


def looks_like_ai_account(
    user_info: dict[str, Any],
    brand_tokens: list[str],
) -> tuple[bool, str]:
    """Heuristic: does this user_info look like the brand's official account?

    Returns (is_likely, reason_string).

    Heuristic, in order of priority:
    1. If the user's name or description contains any brand token -> likely.
    2. If the user is verified and has > 1000 followers -> likely.
    3. Otherwise -> unlikely.
    """
    name = (user_info.get("name") or "").casefold()
    desc = (user_info.get("description") or "").casefold()
    followers = int(user_info.get("followersCount") or user_info.get("followers_count") or 0)
    verified = bool(user_info.get("isBlueVerified") or user_info.get("verified"))

    for tok in brand_tokens:
        t = tok.casefold()
        if t in name or t in desc:
            return True, f"name/desc contains {tok!r}"
    if verified and followers > 1000:
        return True, f"verified with {followers} followers"
    return False, f"name={name[:30]!r} verified={verified} followers={followers}"
