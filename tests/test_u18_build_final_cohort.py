"""Evaluation-cohort selection preserves source evidence and deterministic identity."""

from __future__ import annotations

import hashlib
import json

from scripts import u18_build_final_cohort as cohort


def _row(tweet_id: str = "post-1") -> tuple[object, ...]:
    return (
        tweet_id,
        "llama",
        "handle",
        "Author",
        "ja",
        "source text",
        "quoted text",
        "parent text",
        "staff",
    )


def _row_for_brand(tweet_id: str, brand_id: str) -> tuple[object, ...]:
    row = list(_row(tweet_id))
    row[1] = brand_id
    return tuple(row)


def test_source_row_keeps_selection_metadata_outside_classifier_input():
    row = cohort._source_row(
        _row(), stratum="rare_positive", source_hint="job_listing_terms"
    )

    assert row["source_language"] == "ja"
    assert row["source_role"] == "staff"
    assert row["source_hint"] == "job_listing_terms"
    assert row["input"] == {
        "brand_ids": ["llama"],
        "context": [
            {"provenance": "stored_quote", "text": "quoted text"},
            {"provenance": "local_parent", "text": "parent text"},
        ],
        "text": "source text",
        "tweet_id": "post-1",
    }
    assert "source_hint" not in row["input"]
    canonical = json.dumps(
        row["input"], ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    assert row["input_context_fingerprint"] == hashlib.sha256(canonical).hexdigest()


def test_take_is_deterministic_and_excludes_development_posts():
    candidates = [_row("post-3"), _row("post-1"), _row("post-2")]
    excluded = {"post-2"}

    first = cohort._take(
        candidates,
        category="jobs:ja",
        quota=2,
        chosen=set(),
        excluded=excluded,
    )
    second = cohort._take(
        reversed(candidates),
        category="jobs:ja",
        quota=2,
        chosen=set(),
        excluded=excluded,
    )

    assert first == second
    assert {row[0] for row in first} == {"post-1", "post-3"}


def test_take_keeps_only_one_brand_attribution_per_post():
    candidates = [
        _row("post-1"),
        _row_for_brand("post-1", "other-brand"),
        _row("post-2"),
    ]

    selected = cohort._take(
        candidates,
        category="prevalence:ja",
        quota=2,
        chosen=set(),
        excluded=set(),
    )

    assert len({row[0] for row in selected}) == 2
