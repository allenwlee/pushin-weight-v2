from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from core import models

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_same_inputs_reuse_snapshot_and_correction_keeps_old_numbers():
    from core.discussion_windows import capture_window, read_window

    brand = models.Brand.objects.create(nickname="study-brand")
    account = models.Account.objects.create(author_id="same-author")
    now = timezone.now()
    for n in range(3):
        post = models.Post.objects.create(
            tweet_id=f"window-{n}",
            text="model",
            lang="en",
            author=account,
            created_at=now + timedelta(minutes=n),
        )
        models.PostBrand.objects.create(post=post, brand=brand)
    first, created = capture_window(brand.pk, now, now + timedelta(minutes=15))
    assert created and first.post_count == 3 and first.account_count == 1
    repeated, created = capture_window(brand.pk, now, now + timedelta(minutes=15))
    assert not created and repeated.pk == first.pk
    models.Post.objects.filter(pk="window-1").update(lang="zh")
    corrected, created = capture_window(brand.pk, now, now + timedelta(minutes=15))
    assert created and corrected.pk != first.pk
    old = read_window(first.pk)
    assert (
        next(
            c["count"]
            for c in old["counts"]
            if c["dimension"] == "language" and c["category"] == "en"
        )
        == 3
    )
    assert not models.EventDossierSource.objects.exists()


def test_arbitrary_boundaries_are_exact_and_no_activity_is_not_complete_coverage():
    from core.discussion_windows import capture_window

    brand = models.Brand.objects.create(nickname="bounds-brand")
    now = timezone.now()
    for n in (0, 5, 15, 20):
        post = models.Post.objects.create(
            tweet_id=f"bounds-{n}", created_at=now + timedelta(minutes=n)
        )
        models.PostBrand.objects.create(post=post, brand=brand)
    snapshot, _ = capture_window(
        brand.pk, now + timedelta(minutes=5), now + timedelta(minutes=20)
    )
    assert snapshot.post_count == 2
    empty, _ = capture_window(brand.pk, now - timedelta(days=1), now)
    assert empty.post_count == 0 and empty.coverage == "no_stored_posts"


def test_as_known_history_is_not_fabricated_from_current_classification():
    from core.discussion_windows import capture_window

    brand = models.Brand.objects.create(nickname="asof-brand")
    now = timezone.now()
    with pytest.raises(ValueError, match="history_policy"):
        capture_window(
            brand.pk, now - timedelta(days=1), now, history_policy="as_known"
        )


def test_published_snapshot_rejects_late_count_insertions():
    from core.discussion_windows import capture_window

    brand = models.Brand.objects.create(nickname="sealed-brand")
    now = timezone.now()
    snapshot, _ = capture_window(brand.pk, now - timedelta(days=1), now)
    with pytest.raises(IntegrityError), transaction.atomic():
        models.DiscussionWindowCount.objects.create(
            snapshot=snapshot,
            population="all",
            dimension="volume",
            definition="invented",
            category="posts",
            count=0,
            denominator=0,
        )


def test_many_early_languages_do_not_hide_the_middle_of_the_window():
    from core.discussion_windows import capture_window, discussion_packet

    brand = models.Brand.objects.create(nickname="quartile-brand")
    now = timezone.now()
    for n in range(15):
        minute = 1 if n < 12 else (n - 11) * 15 + 1
        post = models.Post.objects.create(
            tweet_id=f"quartile-{n}",
            created_at=now + timedelta(minutes=minute),
            lang=f"lang-{n}" if n < 12 else "en",
            text=f"Observation {n}",
        )
        models.PostBrand.objects.create(post=post, brand=brand)
    snapshot, _ = capture_window(brand.pk, now, now + timedelta(hours=1))
    result = discussion_packet(snapshot.pk, source_limit=4)
    assert {p["post_id"] for p in result["sources"]} == {
        "quartile-0",
        "quartile-12",
        "quartile-13",
        "quartile-14",
    }
