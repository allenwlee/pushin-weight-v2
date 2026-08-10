"""TwitterAPI.io rate defaults for harvester cost reports.

Loads tweet-unit credits, per-call floor, and credits-per-USD from the
in-repo pricing index markdown. CLI overrides replace individual fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

# Prefer renamed layout; fall back to pre-rename path on older checkouts.
_DEFAULT_REL_CANDIDATES = (
    Path("docs/external_vendors/twitterapi/twitterapi_index.md"),
    Path("docs/external_vendors/twitterapi_docs/twitterapi_index.md"),
)

_TWEET_RATE_RE = re.compile(
    r"\*\*Tweets\*\*\s*\|\s*\*\*(\d+(?:\.\d+)?)\s*credits?\s*/\s*returned\s+tweet",
    re.IGNORECASE,
)
# Also accept simpler "15 credits / returned tweet" near Tweets
_TWEET_RATE_LOOSE_RE = re.compile(
    r"Tweets[^\n]*?(\d+(?:\.\d+)?)\s*credits?\s*/\s*returned\s+tweet",
    re.IGNORECASE,
)
_FLOOR_RE = re.compile(
    r"\*\*Minimum per call\*\*\s*\|\s*(\d+(?:\.\d+)?)\s*credits?",
    re.IGNORECASE,
)
_FLOOR_LOOSE_RE = re.compile(
    r"Minimum per call[^\n]*?(\d+(?:\.\d+)?)\s*credits?",
    re.IGNORECASE,
)
_USD_RE = re.compile(
    r"1\s*USD\s*=\s*([\d_,]+(?:\.\d+)?)\s*credits?",
    re.IGNORECASE,
)


class PricingError(ValueError):
    """Raised when rates cannot be resolved from doc or overrides."""


@dataclass(frozen=True)
class PricingRates:
    tweet_credits: float
    call_floor_credits: float
    credits_per_usd: float
    source_path: str | None = None
    parse_notes: tuple[str, ...] = ()

    def usd(self, credits: float) -> float:
        if self.credits_per_usd <= 0:
            return 0.0
        return float(credits) / float(self.credits_per_usd)


def default_pricing_path(repo_root: Path | None = None) -> Path:
    """Return the first existing default pricing markdown path."""
    root = repo_root if repo_root is not None else Path.cwd()
    for rel in _DEFAULT_REL_CANDIDATES:
        p = root / rel
        if p.is_file():
            return p
    # Prefer the modern relative path for error messages even if missing.
    return root / _DEFAULT_REL_CANDIDATES[0]


def parse_pricing_markdown(text: str, *, source_path: str | None = None) -> PricingRates:
    """Extract rates from pricing markdown body."""
    notes: list[str] = []
    tweet: float | None = None
    m = _TWEET_RATE_RE.search(text) or _TWEET_RATE_LOOSE_RE.search(text)
    if m:
        tweet = float(m.group(1))
        notes.append(f"tweet_credits={tweet} from Tweets row")
    floor: float | None = None
    mf = _FLOOR_RE.search(text) or _FLOOR_LOOSE_RE.search(text)
    if mf:
        floor = float(mf.group(1))
        notes.append(f"call_floor_credits={floor} from Minimum per call")
    usd: float | None = None
    mu = _USD_RE.search(text)
    if mu:
        usd = float(mu.group(1).replace(",", "").replace("_", ""))
        notes.append(f"credits_per_usd={usd} from Currency")

    missing = [
        name
        for name, val in (
            ("tweet_credits", tweet),
            ("call_floor_credits", floor),
            ("credits_per_usd", usd),
        )
        if val is None
    ]
    if missing:
        raise PricingError(
            f"could not parse pricing fields {missing} from {source_path or 'markdown'}"
        )
    assert tweet is not None and floor is not None and usd is not None
    return PricingRates(
        tweet_credits=tweet,
        call_floor_credits=floor,
        credits_per_usd=usd,
        source_path=source_path,
        parse_notes=tuple(notes),
    )


def load_pricing_file(path: Path) -> PricingRates:
    if not path.is_file():
        raise PricingError(f"pricing file not found: {path}")
    text = path.read_text(encoding="utf-8")
    return parse_pricing_markdown(text, source_path=str(path))


def apply_overrides(
    rates: PricingRates | None,
    *,
    tweet_credits: float | None = None,
    call_floor_credits: float | None = None,
    credits_per_usd: float | None = None,
) -> PricingRates:
    """Merge optional overrides onto parsed rates (or build from overrides alone)."""
    if rates is None:
        if tweet_credits is None or credits_per_usd is None:
            raise PricingError(
                "tweet_credits and credits_per_usd required when pricing file is unavailable"
            )
        base = PricingRates(
            tweet_credits=float(tweet_credits),
            call_floor_credits=float(
                call_floor_credits if call_floor_credits is not None else 15.0
            ),
            credits_per_usd=float(credits_per_usd),
            source_path=None,
            parse_notes=("from CLI overrides only",),
        )
        return base
    out = rates
    notes = list(rates.parse_notes)
    if tweet_credits is not None:
        out = replace(out, tweet_credits=float(tweet_credits))
        notes.append(f"override tweet_credits={tweet_credits}")
    if call_floor_credits is not None:
        out = replace(out, call_floor_credits=float(call_floor_credits))
        notes.append(f"override call_floor_credits={call_floor_credits}")
    if credits_per_usd is not None:
        out = replace(out, credits_per_usd=float(credits_per_usd))
        notes.append(f"override credits_per_usd={credits_per_usd}")
    return replace(out, parse_notes=tuple(notes))


def load_pricing(
    *,
    pricing_file: Path | None = None,
    repo_root: Path | None = None,
    tweet_credits: float | None = None,
    call_floor_credits: float | None = None,
    credits_per_usd: float | None = None,
) -> PricingRates:
    """Load defaults from pricing doc (if available) then apply overrides."""
    rates: PricingRates | None = None
    path = pricing_file
    if path is None:
        path = default_pricing_path(repo_root)
    try:
        rates = load_pricing_file(path)
    except PricingError:
        if (
            tweet_credits is None
            or credits_per_usd is None
        ):
            raise
        rates = None
    return apply_overrides(
        rates,
        tweet_credits=tweet_credits,
        call_floor_credits=call_floor_credits,
        credits_per_usd=credits_per_usd,
    )


def rates_to_dict(rates: PricingRates) -> dict[str, Any]:
    return {
        "tweet_credits": rates.tweet_credits,
        "call_floor_credits": rates.call_floor_credits,
        "credits_per_usd": rates.credits_per_usd,
        "source_path": rates.source_path,
        "parse_notes": list(rates.parse_notes),
    }
