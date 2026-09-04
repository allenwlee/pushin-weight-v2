"""Re-run the live brand matcher against a bounded set of stored posts."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (
    Brand,
    BrandAccount,
    Post,
    PostBrand,
    PostBrandMention,
    PostEnrichmentState,
)
from monitor.cycle import CycleRunner, _build_brand_index, _persist_attribution
from monitor.post_enrichment import post_persisted_output_complete


def _parse_bound(value: str, *, option: str) -> datetime:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise CommandError(f"{option} must be YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS (UTC)")


def _reopen_classification(
    *,
    post: Post,
    state: PostEnrichmentState | None,
    now: datetime,
) -> None:
    """Make a newly attributed historical post eligible for classification."""
    if state is None:
        translation_status = (
            PostEnrichmentState.Status.SUCCEEDED
            if post_persisted_output_complete(post)
            else PostEnrichmentState.Status.PENDING
        )
        PostEnrichmentState.objects.create(
            post=post,
            translation_status=translation_status,
            classification_status=PostEnrichmentState.Status.PENDING,
            classification_next_attempt_at=now,
        )
        return

    # Queue age is measured from created_at. Refresh it deliberately so
    # historical posts are not quarantined immediately as old debt.
    state.created_at = now
    state.classification_status = PostEnrichmentState.Status.PENDING
    state.classification_attempts = 0
    state.classification_first_attempt_at = None
    state.classification_last_attempt_at = None
    state.classification_next_attempt_at = now
    state.classification_error_code = ""
    state.claim_owner = ""
    state.claim_run_id = ""
    state.claimed_at = None
    state.claim_expires_at = None
    state.save(
        update_fields=(
            "created_at",
            "classification_status",
            "classification_attempts",
            "classification_first_attempt_at",
            "classification_last_attempt_at",
            "classification_next_attempt_at",
            "classification_error_code",
            "claim_owner",
            "claim_run_id",
            "claimed_at",
            "claim_expires_at",
            "updated_at",
        )
    )


class Command(BaseCommand):
    help = (
        "Re-run the live brand matcher against stored posts. "
        "Dry-run by default; pass --apply to add missing links and mentions."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--brand", type=str)
        parser.add_argument("--since", type=str)
        parser.add_argument("--until", type=str)
        parser.add_argument(
            "--limit",
            type=int,
            default=100_000,
            help="Maximum posts to scan (default: 100000).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Database iterator chunk size (default: 500).",
        )
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--apply", action="store_true")
        mode.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options) -> None:
        brand_id = str(options.get("brand") or "").strip()
        since_raw = str(options.get("since") or "").strip()
        until_raw = str(options.get("until") or "").strip()
        if not brand_id:
            raise CommandError("--brand is required")
        if not since_raw:
            raise CommandError("--since is required")
        if options["limit"] <= 0:
            raise CommandError("--limit must be positive")
        if options["batch_size"] <= 0:
            raise CommandError("--batch-size must be positive")

        since = _parse_bound(since_raw, option="--since")
        until = (
            _parse_bound(until_raw, option="--until") if until_raw else timezone.now()
        )
        if until <= since:
            raise CommandError("--until must be later than --since")
        if not Brand.objects.filter(
            nickname=brand_id,
            is_sentinel=False,
        ).exists():
            raise CommandError(f"unknown or sentinel brand {brand_id!r}")

        # These are the same index and item attribution path used by a live
        # CycleRunner. Limiting the index to one brand keeps this repair from
        # changing unrelated links.
        try:
            index = _build_brand_index([brand_id])
        except (RuntimeError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        runner = CycleRunner(cycle_kind="manual", dry_run=True)
        official_author_ids = set(
            BrandAccount.objects.filter(
                brand_id=brand_id,
                role_id="official",
            ).values_list("account_id", flat=True)
        )

        posts = (
            Post.objects.filter(created_at__gte=since, created_at__lt=until)
            .only(
                "tweet_id",
                "text",
                "quoted_text",
                "created_at",
                "entities",
                "author_id",
            )
            .order_by("created_at", "tweet_id")[: options["limit"]]
        )
        summary: dict[str, object] = {
            "active_claim_skips": 0,
            "apply": bool(options["apply"]),
            "brand": brand_id,
            "links_created": 0,
            "links_needed": 0,
            "matched": 0,
            "mentions_created": 0,
            "mentions_needed": 0,
            "scanned": 0,
        }

        for post in posts.iterator(chunk_size=options["batch_size"]):
            summary["scanned"] += 1
            item = {
                "tweet_id": str(post.pk),
                "text": post.text or "",
                "quoted_text": post.quoted_text or "",
                "created_at": (
                    post.created_at.isoformat()
                    if post.created_at is not None
                    else since.isoformat()
                ),
                "entities": post.entities or {},
            }
            if post.author_id in official_author_ids:
                item["_author_seed_brands"] = [brand_id]
                item["_author_membership_source"] = "brand_account"
                item["_author_membership_run_id"] = "reattribute_brand_posts"

            runner._attribute_items([item], index, {})
            target_mentions = [
                mention
                for mention in item.get("mentions", [])
                if mention.brand_id == brand_id
            ]
            if not target_mentions:
                continue
            summary["matched"] += 1

            needed_sources = {mention.source for mention in target_mentions}
            if not options["apply"]:
                existing_link = PostBrand.objects.filter(
                    post_id=post.pk,
                    brand_id=brand_id,
                ).exists()
                existing_sources = set(
                    PostBrandMention.objects.filter(
                        post_id=post.pk,
                        brand_id=brand_id,
                    ).values_list("source", flat=True)
                )
                if not existing_link:
                    summary["links_needed"] += 1
                summary["mentions_needed"] += len(
                    needed_sources - existing_sources
                )
                continue

            with transaction.atomic():
                locked_post = Post.objects.select_for_update().get(pk=post.pk)
                state = (
                    PostEnrichmentState.objects.select_for_update()
                    .filter(post=locked_post)
                    .first()
                )
                now = timezone.now()
                if (
                    state is not None
                    and state.claim_owner
                    and state.claim_expires_at is not None
                    and state.claim_expires_at > now
                ):
                    summary["active_claim_skips"] += 1
                    continue

                link_existed = PostBrand.objects.filter(
                    post=locked_post,
                    brand_id=brand_id,
                ).exists()
                sources_before = set(
                    PostBrandMention.objects.filter(
                        post=locked_post,
                        brand_id=brand_id,
                    ).values_list("source", flat=True)
                )
                if not link_existed:
                    summary["links_needed"] += 1
                summary["mentions_needed"] += len(
                    needed_sources - sources_before
                )
                _persist_attribution(
                    locked_post,
                    [],
                    target_mentions,
                    classifications=None,
                )
                if not link_existed:
                    summary["links_created"] += 1
                summary["mentions_created"] += len(
                    {mention.source for mention in target_mentions} - sources_before
                )

                # A newly attached brand changes the classifier input. Reopen
                # classification so the normal enrichment worker creates the
                # missing per-brand signals; leave translation state intact.
                if not link_existed:
                    _reopen_classification(
                        post=locked_post,
                        state=state,
                        now=now,
                    )

        self.stdout.write(json.dumps(summary, sort_keys=True))
