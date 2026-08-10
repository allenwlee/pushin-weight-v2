"""Tests for scripts.harvest_cost.pricing (plan 2026-08-10-003 U1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.harvest_cost.pricing import (
    PricingError,
    apply_overrides,
    default_pricing_path,
    load_pricing,
    load_pricing_file,
    parse_pricing_markdown,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_default_pricing_path_points_at_existing_file():
    p = default_pricing_path(REPO_ROOT)
    assert p.is_file(), f"expected pricing doc at {p}"


def test_load_real_pricing_doc_tweet_rate_15():
    rates = load_pricing(repo_root=REPO_ROOT)
    assert rates.tweet_credits == 15
    assert rates.credits_per_usd == 100_000
    assert rates.call_floor_credits == 15
    assert rates.source_path is not None
    assert Path(rates.source_path).is_file()


def test_parse_pricing_markdown_fixture():
    md = """
## Pricing
| **Tweets** | **20 credits / returned tweet** | note |
| **Minimum per call** | 12 credits (waived) |
1 USD = 50,000 credits.
"""
    rates = parse_pricing_markdown(md, source_path="fixture")
    assert rates.tweet_credits == 20
    assert rates.call_floor_credits == 12
    assert rates.credits_per_usd == 50_000


def test_override_tweet_credits_wins():
    rates = load_pricing(repo_root=REPO_ROOT, tweet_credits=20)
    assert rates.tweet_credits == 20
    assert rates.credits_per_usd == 100_000


def test_malformed_file_without_overrides_errors(tmp_path: Path):
    bad = tmp_path / "bad.md"
    bad.write_text("# no rates here\n", encoding="utf-8")
    with pytest.raises(PricingError):
        load_pricing_file(bad)


def test_overrides_only_when_file_missing(tmp_path: Path):
    missing = tmp_path / "nope.md"
    rates = load_pricing(
        pricing_file=missing,
        tweet_credits=9,
        credits_per_usd=1_000,
        call_floor_credits=9,
    )
    assert rates.tweet_credits == 9
    assert rates.credits_per_usd == 1_000


def test_apply_overrides_notes():
    base = parse_pricing_markdown(
        "| **Tweets** | **15 credits / returned tweet** |\n"
        "| **Minimum per call** | 15 credits |\n"
        "1 USD = 100000 credits.\n",
        source_path="x",
    )
    out = apply_overrides(base, tweet_credits=30)
    assert out.tweet_credits == 30
    assert any("override tweet_credits=30" in n for n in out.parse_notes)
