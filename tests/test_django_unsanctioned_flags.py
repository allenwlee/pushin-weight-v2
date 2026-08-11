from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def _post(tweet_id: str):
    from core.models import Post

    return Post.objects.create(tweet_id=tweet_id, text="fixture text")


def _seed_existing(post, flags: list[str]):
    from core.models import PostUnsanctionedFlag

    return PostUnsanctionedFlag.objects.create(
        post=post,
        flags=json.dumps(flags),
        flag_set=flags,
    )


def test_valid_flags_create_and_update_the_one_to_one_row():
    from core.models import PostUnsanctionedFlag
    from monitor.unsanctioned_flags import persist_classifier_flags

    post = _post("flags-valid")
    first = persist_classifier_flags(
        post_id=post.pk,
        classifier_result={"unsanctioned_flags": ["scam", "crypto"]},
        run_id="run-1",
    )
    second = persist_classifier_flags(
        post_id=post.pk,
        classifier_result={"unsanctioned_flags": ["unauthorized"]},
        run_id="run-2",
    )

    row = PostUnsanctionedFlag.objects.get(post=post)
    assert first.outcome == "persisted"
    assert second.outcome == "persisted"
    assert json.loads(row.flags) == ["unauthorized"]
    assert row.flag_set == ["unauthorized"]
    assert PostUnsanctionedFlag.objects.filter(post=post).count() == 1


def test_successful_explicit_empty_deletes_existing_row():
    from core.models import PostUnsanctionedFlag
    from monitor.unsanctioned_flags import persist_classifier_flags

    post = _post("flags-empty")
    _seed_existing(post, ["scam"])

    result = persist_classifier_flags(
        post_id=post.pk,
        classifier_result={"unsanctioned_flags": []},
        run_id="run-empty",
    )

    assert result.outcome == "cleared"
    assert not PostUnsanctionedFlag.objects.filter(post=post).exists()


@pytest.mark.parametrize(
    "classifier_result",
    [None, {}, {"unsanctioned_flags": "scam"}, {"unsanctioned_flags": [None]}],
)
def test_failed_malformed_or_partial_result_preserves_prior_row(classifier_result):
    from core.models import PostUnsanctionedFlag
    from monitor.unsanctioned_flags import persist_classifier_flags

    post = _post(f"flags-malformed-{abs(hash(repr(classifier_result)))}")
    _seed_existing(post, ["scam"])

    result = persist_classifier_flags(
        post_id=post.pk,
        classifier_result=classifier_result,
        run_id="run-malformed",
    )

    assert result.outcome == "preserved"
    assert json.loads(PostUnsanctionedFlag.objects.get(post=post).flags) == ["scam"]


def test_unknown_only_preserves_prior_and_dead_letter_is_minimized():
    from core.models import PostUnsanctionedFlag
    from monitor.unsanctioned_flags import persist_classifier_flags

    post = _post("flags-unknown")
    _seed_existing(post, ["scam"])
    secret = "DATABASE_URL=postgresql://user:password@example/db\nraw body"

    result = persist_classifier_flags(
        post_id=post.pk,
        classifier_result={"unsanctioned_flags": [secret]},
        run_id="run-unknown",
    )

    assert result.outcome == "preserved"
    assert result.degraded is True
    assert json.loads(PostUnsanctionedFlag.objects.get(post=post).flags) == ["scam"]
    encoded = json.dumps(result.dead_letter, sort_keys=True)
    assert "password" not in encoded
    assert "raw body" not in encoded
    assert len(encoded) < 512
    assert set(result.dead_letter) == {
        "run_id",
        "tweet_id",
        "stage",
        "known_keys",
        "rejected_keys",
        "reason_code",
    }


def test_mixed_known_unknown_persists_known_and_dead_letters_unknown():
    from core.models import PostUnsanctionedFlag
    from monitor.unsanctioned_flags import persist_classifier_flags

    post = _post("flags-mixed")
    result = persist_classifier_flags(
        post_id=post.pk,
        classifier_result={
            "unsanctioned_flags": ["scam", "future_flag", "crypto"]
        },
        run_id="run-mixed",
    )

    row = PostUnsanctionedFlag.objects.get(post=post)
    assert result.outcome == "persisted"
    assert result.degraded is True
    assert json.loads(row.flags) == ["scam", "crypto"]
    assert result.dead_letter["known_keys"] == ["scam", "crypto"]
    assert result.dead_letter["rejected_keys"] == ["future_flag"]
