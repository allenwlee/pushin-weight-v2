from datetime import UTC, datetime

from core.product_release_milestones import extract_milestones

POSTED = datetime(2026, 10, 18, 2, tzinfo=UTC)


def test_version_digits_do_not_become_a_release_date():
    claims = extract_milestones(
        "DeepSeek-V4.1-Flash-1017 has been released", published_at=POSTED
    )
    assert all(c.effective_date is None and c.effective_at is None for c in claims)


def test_announcement_and_access_are_separate_observed_claims():
    claims = extract_milestones(
        "Today we announce Model A. Weights are now available to download.",
        published_at=POSTED,
    )
    assert {c.kind for c in claims} >= {"announcement", "availability"}
    assert next(c for c in claims if c.kind == "announcement").effective_at == POSTED
    assert (
        next(c for c in claims if c.kind == "availability").access_channel == "weights"
    )


def test_future_and_negated_wording_cannot_establish_availability():
    claims = extract_milestones(
        "We will release A tomorrow. Weights are not available now.",
        published_at=POSTED,
    )
    assert not any(c.kind == "availability" for c in claims)
    assert any(c.kind == "rumor" for c in claims)


def test_explicit_day_keeps_precision_and_relative_day_requires_timezone():
    claims = extract_milestones("We released A on 2026-10-17.", published_at=POSTED)
    c = next(c for c in claims if c.kind == "source_stated_release")
    assert c.precision == "day" and c.effective_date.isoformat() == "2026-10-17"
    assert c.effective_at is None
    unknown = extract_milestones("We released A yesterday.", published_at=POSTED)
    assert unknown[0].precision == "unknown"
    dated = extract_milestones(
        "We released A yesterday.", published_at=POSTED, source_timezone="Asia/Tokyo"
    )
    assert dated[0].effective_date.isoformat() == "2026-10-17"
