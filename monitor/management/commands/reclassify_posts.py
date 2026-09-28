"""Preview or safely reclassify a reviewed exact-ID Stage 1 cohort."""

from __future__ import annotations

import json
import os
import uuid
from contextlib import ExitStack
from pathlib import Path
from urllib.parse import urlsplit

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import Post, PostBrand, PostBrandClassificationState, PostEnrichmentState
from monitor.cycle import CycleRunner, _parse_published_classifications
from monitor.run_lock import harvest_writer_lock
from scripts.database_lock import DatabaseLockError, acquire_harvest_coordination_lock
from x_monitor.attribution import _two_role_revisions


_QUEUE_FIELDS = (
    "created_at", "classification_status", "classification_attempts",
    "classification_first_attempt_at", "classification_last_attempt_at",
    "classification_next_attempt_at", "classification_error_code",
    "claim_owner", "claim_run_id", "claimed_at", "claim_expires_at",
)


def _restore_unpublished_queue_states(snapshots: dict[str, dict]) -> None:
    """Keep a rejected repair out of the ordinary unguarded retry queue."""
    with transaction.atomic():
        states = PostEnrichmentState.objects.select_for_update().filter(post_id__in=snapshots)
        for state in states:
            if state.classification_status == PostEnrichmentState.Status.SUCCEEDED:
                continue
            for field, value in snapshots[str(state.post_id)].items():
                setattr(state, field, value)
            state.save(update_fields=(*_QUEUE_FIELDS, "updated_at"))


def _require_staging_target(database_url: str | None, environment: str | None) -> None:
    if not database_url or environment != "staging":
        raise CommandError("repair_requires_staging_environment")
    try:
        target = urlsplit(database_url)
    except ValueError as exc:
        raise CommandError("repair_requires_staging_database") from exc
    if (
        target.scheme not in {"postgres", "postgresql"}
        or target.path != "/pushinweight_staging"
    ):
        raise CommandError("repair_requires_staging_database")


def _load_manifest(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CommandError("repair_manifest_unreadable") from exc
    content_revision, brand_revision, merge_revision = _two_role_revisions("deepseek_0731")
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or payload.get("selected_content_revision") != content_revision
        or payload.get("selected_brand_revision") != brand_revision
        or payload.get("selected_merge_revision") != merge_revision
        or not isinstance(payload.get("posts"), dict)
    ):
        raise CommandError("repair_manifest_invalid")
    for post_id, row in payload["posts"].items():
        if (
            not isinstance(post_id, str)
            or not post_id.isdecimal()
            or not isinstance(row, dict)
            or not isinstance(row.get("input_context_fingerprint"), str)
            or len(row["input_context_fingerprint"]) != 64
            or not isinstance(row.get("by_brand"), dict)
            or not row["by_brand"]
            or not isinstance(row.get("untracked_brand_promotions"), list)
            or not isinstance(row.get("promoted_subjects"), list)
        ):
            raise CommandError(f"repair_manifest_invalid_row:{post_id}")
        if _parse_published_classifications(row["by_brand"], set(row["by_brand"])) != row["by_brand"]:
            raise CommandError(f"repair_manifest_invalid_judgment:{post_id}")
        promotions = row["untracked_brand_promotions"]
        if (
            any(not isinstance(key, str) for key in promotions)
            or
            len(promotions) != len(set(promotions))
            or any(key not in {"general", "spam", "scam", "crypto", "unauthorized"} for key in promotions)
            or bool(promotions) != bool(row["promoted_subjects"])
            or any(
                not isinstance(subject, dict)
                or set(subject) != {"name", "handle", "domain", "account_handle", "evidence"}
                or not isinstance(subject["name"], str)
                or not subject["name"].strip()
                or not isinstance(subject["evidence"], str)
                or not subject["evidence"].strip()
                for subject in row["promoted_subjects"]
            )
        ):
            raise CommandError(f"repair_manifest_invalid_promotion:{post_id}")
    return payload


def _preflight(post_ids: list[str], posts: dict[str, dict]) -> None:
    now = timezone.now()
    from monitor.post_artifacts import literal_translation_artifact_complete
    for post_id in post_ids:
        expected = posts[post_id]
        post = Post.objects.filter(pk=post_id).first()
        if post is None:
            raise CommandError(f"repair_unknown_post:{post_id}")
        state = PostEnrichmentState.objects.filter(post_id=post_id).first()
        if state is None or state.translation_status != PostEnrichmentState.Status.SUCCEEDED:
            raise CommandError(f"repair_translation_incomplete:{post_id}")
        if state.classification_status != PostEnrichmentState.Status.SUCCEEDED:
            raise CommandError(f"repair_requires_completed_classification:{post_id}")
        if not literal_translation_artifact_complete(post):
            raise CommandError(f"repair_source_incomplete:{post_id}")
        visible = "\n".join(filter(None, (post.text, post.text_en, post.quoted_text))).casefold()
        if any(
            subject["evidence"].casefold() not in visible
            for subject in expected["promoted_subjects"]
        ):
            raise CommandError(f"repair_subject_evidence_not_visible:{post_id}")
        if state.claim_expires_at and state.claim_expires_at > now:
            raise CommandError(f"repair_active_claim:{post_id}")
        actual_brands = set(PostBrand.objects.filter(post_id=post_id).values_list("brand_id", flat=True))
        if actual_brands != set(expected["by_brand"]):
            raise CommandError(f"repair_brand_set_changed:{post_id}")
        current_lineage = set(
            PostBrandClassificationState.objects.filter(post_id=post_id).values_list(
                "input_context_fingerprint", "prompt_version",
            )
        )
        if current_lineage != {(
            expected["input_context_fingerprint"], "stage1-two-role-merge-0731-v5",
        )}:
            raise CommandError(f"repair_input_fingerprint_changed:{post_id}")


class Command(BaseCommand):
    help = "Preview exact post IDs; --apply republishes only a reviewed complete Stage 1 manifest."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--post-id", action="append", required=True)
        parser.add_argument("--manifest", type=Path, required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options) -> None:
        post_ids = options["post_id"]
        if not 1 <= len(post_ids) <= 20 or len(set(post_ids)) != len(post_ids):
            raise CommandError("repair_requires_1_to_20_unique_post_ids")
        if any(not post_id.isdecimal() for post_id in post_ids):
            raise CommandError("repair_post_ids_must_be_numeric")
        manifest = _load_manifest(options["manifest"])
        posts = manifest["posts"]
        if set(post_ids) != set(posts):
            raise CommandError("repair_ids_must_match_manifest_exactly")
        from x_monitor.config import load_config

        cfg = load_config(Path("config.yaml"))
        if not cfg.llm.literal_translation_v2_enabled:
            raise CommandError("repair_requires_literal_translation_v2")
        _preflight(post_ids, posts)
        if not options["apply"]:
            self.stdout.write(json.dumps({"status": "preview", "post_ids": sorted(post_ids)}))
            return

        database_url = os.environ.get("DATABASE_URL")
        environment = os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT")
        _require_staging_target(database_url, environment)
        try:
            with ExitStack() as stack:
                stack.enter_context(acquire_harvest_coordination_lock(database_url, environment=environment))
                lease = stack.enter_context(harvest_writer_lock(
                    execution_mode="repair", entrypoint="management.reclassify_posts",
                    environment=environment,
                ))
                if not lease.acquired:
                    raise CommandError("repair_writer_lock_unavailable")
                # Recheck under both locks; preview is intentionally read-only.
                _preflight(post_ids, posts)
                from monitor.management.commands.reattribute_brand_posts import _reopen_classification

                snapshots = {}
                with transaction.atomic():
                    for post_id in post_ids:
                        state = PostEnrichmentState.objects.select_for_update().get(post_id=post_id)
                        snapshots[post_id] = {field: getattr(state, field) for field in _QUEUE_FIELDS}
                        _reopen_classification(
                            post=Post.objects.get(pk=post_id),
                            state=state,
                            now=timezone.now(),
                        )
                run_id = f"repair-{uuid.uuid4().hex}"
                # The selected two-role caller reserves three transport slots
                # per role. The repair delegate permits only the first two,
                # so no more than four provider requests can be sent.
                try:
                    runner = CycleRunner(cfg=cfg, cycle_kind="manual", _max_llm_calls=6)
                    counters = runner._run_post_fetch(
                        [], run_id=run_id, post_ids=set(post_ids), repair_manifest=posts,
                    )
                finally:
                    _restore_unpublished_queue_states(snapshots)
                published = int(counters.get("n_classifications_published") or 0)
                status = "published" if published == len(post_ids) else "incomplete"
                self.stdout.write(json.dumps({
                    "status": status, "post_ids": sorted(post_ids),
                    "published": published, "errors": runner._errors,
                }, sort_keys=True))
                if status != "published":
                    raise CommandError("repair_incomplete")
        except DatabaseLockError as exc:
            raise CommandError(str(exc)) from exc
