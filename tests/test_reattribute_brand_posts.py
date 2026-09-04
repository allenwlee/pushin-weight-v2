from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from core.models import (
    Account,
    Brand,
    BrandAccount,
    Post,
    PostBrand,
    PostBrandMention,
    PostEnrichmentState,
    Role,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def _post(tweet_id: str, text: str, *, author: Account | None = None) -> Post:
    return Post.objects.create(
        tweet_id=tweet_id,
        author=author,
        author_handle=author.handle if author else "observer",
        text=text,
        created_at=timezone.now() - timedelta(days=1),
    )


def _run(*args: str) -> dict[str, object]:
    stdout = StringIO()
    call_command("reattribute_brand_posts", *args, stdout=stdout)
    return json.loads(stdout.getvalue().strip().splitlines()[-1])


def test_requires_brand_and_since():
    with pytest.raises(CommandError, match="--brand"):
        call_command("reattribute_brand_posts", "--since", "2026-08-01")
    with pytest.raises(CommandError, match="--since"):
        call_command("reattribute_brand_posts", "--brand", "dots")


def test_dry_run_apply_and_idempotency_reuse_live_attribution(
    seeded_policy_keywords,
):
    dots = Brand.objects.get(nickname="dots")
    other = Brand.objects.create(nickname="other", display_name="Other")
    Role.objects.get_or_create(key="official")
    Role.objects.get_or_create(key="staff")
    official = Account.objects.create(author_id="dots-official", handle="dotsstudioai")
    staff = Account.objects.create(author_id="dots-staff", handle="ChaoQiao42")
    BrandAccount.objects.create(brand=dots, account=official, role_id="official")
    BrandAccount.objects.create(brand=dots, account=staff, role_id="staff")

    spaced = _post("stored-spaced", "Dots 3 Note Preview is out")
    _post("stored-dotted", "Try Dots.3-Note today")
    _post("stored-repo", "See dots-studio/dots-3-note-preview")
    _post("stored-official", "A new release", author=official)
    _post("stored-staff", "A new release", author=staff)
    _post("stored-unrelated", "No relevant model here")
    PostBrand.objects.create(post=spaced, brand=other)
    enrichment = PostEnrichmentState.objects.create(
        post=spaced,
        translation_status=PostEnrichmentState.Status.SUCCEEDED,
        classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )
    old_enrichment_created_at = timezone.now() - timedelta(days=30)
    PostEnrichmentState.objects.filter(pk=enrichment.pk).update(
        created_at=old_enrichment_created_at
    )

    dry = _run("--brand", "dots", "--since", "2026-08-01")

    assert dry == {
        "active_claim_skips": 0,
        "apply": False,
        "brand": "dots",
        "links_created": 0,
        "links_needed": 4,
        "matched": 4,
        "mentions_created": 0,
        "mentions_needed": 4,
        "scanned": 6,
    }
    assert not PostBrand.objects.filter(brand=dots).exists()

    first = _run("--brand", "dots", "--since", "2026-08-01", "--apply")

    assert first["links_created"] == 4
    assert first["mentions_created"] == 4
    assert set(
        PostBrand.objects.filter(brand=dots).values_list("post_id", flat=True)
    ) == {
        "stored-spaced",
        "stored-dotted",
        "stored-repo",
        "stored-official",
    }
    assert PostBrand.objects.filter(post=spaced, brand=other).exists()
    assert PostBrandMention.objects.filter(
        post_id="stored-official",
        brand=dots,
        source="author_account",
    ).exists()
    assert not PostBrand.objects.filter(post_id="stored-staff", brand=dots).exists()
    spaced.enrichment_state.refresh_from_db()
    assert (
        spaced.enrichment_state.classification_status
        == PostEnrichmentState.Status.PENDING
    )
    assert spaced.enrichment_state.translation_status == (
        PostEnrichmentState.Status.SUCCEEDED
    )
    assert spaced.enrichment_state.created_at > old_enrichment_created_at

    second = _run("--brand", "dots", "--since", "2026-08-01", "--apply")

    assert second["links_needed"] == 0
    assert second["links_created"] == 0
    assert second["mentions_needed"] == 0
    assert second["mentions_created"] == 0


def test_missing_state_preserves_complete_translation(seeded_policy_keywords):
    dots = Brand.objects.get(nickname="dots")
    post = _post("stored-complete-no-state", "Dots 3 Note Preview is out")
    post.lang_detected = "en"
    post.text_en = "Dots 3 Note Preview is out"
    post.text_zh_cn = "Dots 3 Note 预览版已发布。"
    post.commentary_en = "The release expands the Dots model family."
    post.commentary_zh_cn = "这次发布扩展了 Dots 模型系列。"
    post.save(
        update_fields=(
            "lang_detected",
            "text_en",
            "text_zh_cn",
            "commentary_en",
            "commentary_zh_cn",
        )
    )

    result = _run("--brand", "dots", "--since", "2026-08-01", "--apply")

    assert result["links_created"] == 1
    assert PostBrand.objects.filter(post=post, brand=dots).exists()
    state = PostEnrichmentState.objects.get(post=post)
    assert state.translation_status == PostEnrichmentState.Status.SUCCEEDED
    assert state.classification_status == PostEnrichmentState.Status.PENDING
    assert state.classification_next_attempt_at is not None


def test_active_claim_skips_without_mutation(seeded_policy_keywords):
    dots = Brand.objects.get(nickname="dots")
    post = _post("stored-active-claim", "Dots.3-Note is out")
    state = PostEnrichmentState.objects.create(
        post=post,
        claim_owner="harvester:active",
        claim_run_id="active-run",
        claimed_at=timezone.now(),
        claim_expires_at=timezone.now() + timedelta(minutes=5),
    )
    before = {
        "created_at": state.created_at,
        "classification_status": state.classification_status,
        "claim_owner": state.claim_owner,
        "claim_expires_at": state.claim_expires_at,
    }

    result = _run("--brand", "dots", "--since", "2026-08-01", "--apply")

    assert result["active_claim_skips"] == 1
    assert not PostBrand.objects.filter(post=post, brand=dots).exists()
    assert not PostBrandMention.objects.filter(post=post, brand=dots).exists()
    state.refresh_from_db()
    assert {
        "created_at": state.created_at,
        "classification_status": state.classification_status,
        "claim_owner": state.claim_owner,
        "claim_expires_at": state.claim_expires_at,
    } == before
