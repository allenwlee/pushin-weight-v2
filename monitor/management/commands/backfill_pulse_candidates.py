"""Revisit recent staging Pulse candidate posts through the ordinary classifier."""

import hashlib
import json
import os
import uuid
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from core.classified_product_releases import read_publication_findings
from core.models import EventDossierSource, Post, PostEnrichmentState
from core.product_release_detection_queue import drain_posts
from core.product_release_dossiers import read_saved_release_findings
from monitor.cycle import CycleRunner
from monitor.management.commands.reattribute_brand_posts import _reopen_classification
from monitor.management.commands.reclassify_posts import _require_staging_target
from monitor.pulse_processing import identity_application
from monitor.run_lock import harvest_writer_lock
from x_monitor.config import load_config
from x_monitor.reattribute import build_classifier_client_from_env


def saved_result(post_id):
    selected = read_publication_findings(post_id)
    if selected is not None:
        return "selected", selected
    # The historical trial predates selected-output manifests. Its separately
    # archived finding can be reused without treating absent output as empty.
    revision = hashlib.sha256(f"saved-p1-86:{post_id}".encode()).hexdigest()
    trial = read_saved_release_findings(
        source={"kind": "post", "id": post_id}, revision_id=revision
    )
    return ("saved_trial", trial) if trial else ("missing", ())


class Command(BaseCommand):
    help = "Preview or process the last 30 days of staging release candidates by post publication time."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **opts):
        _require_staging_target(
            os.getenv("DATABASE_URL"), os.getenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT")
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            if cursor.fetchone()[0] != "pushinweight_staging":
                raise CommandError("Expected staging database")
        end = timezone.now()
        start = end - timedelta(days=30)
        ids = list(
            EventDossierSource.objects.filter(
                event_dossier__event_kind_reference__code="product_release",
                post__created_at__gte=start,
                post__created_at__lt=end,
            )
            .order_by("post_id")
            .values_list("post_id", flat=True)
            .distinct()
        )
        self.stdout.write(
            json.dumps(
                {"start": start.isoformat(), "end": end.isoformat(), "posts": len(ids)}
            )
        )
        if not opts["apply"]:
            for post_id in ids:
                self.stdout.write(
                    json.dumps({"post": post_id, "decision": saved_result(post_id)[0]})
                )
            return
        cfg = load_config(Path("config.yaml"))
        with harvest_writer_lock(
            execution_mode="repair",
            entrypoint="management.backfill_pulse_candidates",
            environment="staging",
        ) as lease:
            if not lease.acquired:
                raise CommandError("Staging writer is busy")
            failed = []
            for post_id in ids:
                source, findings = saved_result(post_id)
                calls = 0
                if source == "missing":
                    if cfg.llm.classifier_pipeline != "compressed8_pulse_v1":
                        raise CommandError("Pulse classifier required to classify missing findings")
                    client = build_classifier_client_from_env(
                        cfg, deepinfra_key_env="DEEPINFRA_ON_DEMAND"
                    )
                    if client is None:
                        raise CommandError(
                            "Staging backfill classifier credentials unavailable"
                        )
                    runner = CycleRunner(
                        cfg=cfg,
                        cycle_kind="backfill",
                        _max_llm_calls=8,
                        _post_fetch_clients={
                            "classification": client,
                            "translation": None,
                        },
                    )
                    with transaction.atomic():
                        post = Post.objects.select_for_update().get(pk=post_id)
                        state = (
                            PostEnrichmentState.objects.select_for_update()
                            .filter(post=post)
                            .first()
                        )
                        if state and (
                            state.source_collection_job_id
                            or (
                                state.claim_expires_at
                                and state.claim_expires_at > timezone.now()
                            )
                        ):
                            raise CommandError(
                                f"Post already owned by another job: {post_id}"
                            )
                        _reopen_classification(
                            post=post, state=state, now=timezone.now()
                        )
                    runner._process_enrichment_claim_batch(
                        [],
                        post_ids={post_id},
                        run_id=f"pulse-history-{uuid.uuid4().hex}",
                        pulse_backfill=True,
                    )
                    calls = runner._llm_call_count
                    findings = read_publication_findings(post_id)
                    if findings is None:
                        failed.append(post_id)
                        self.stdout.write(
                            json.dumps(
                                {
                                    "post": post_id,
                                    "status": "incomplete",
                                    "calls": calls,
                                    "errors": runner._errors,
                                }
                            )
                        )
                        continue
                identity = {}
                if source != "saved_trial":
                    with identity_application() as boundary:
                        if not boundary.allowed():
                            raise CommandError(f"Pulse control: {boundary.status}")
                        identity = drain_posts(
                            limit=1,
                            post_ids=[post_id],
                            classified_only=True,
                            before_post=boundary.allowed,
                        )
                        if identity["failed"] or identity["busy"]:
                            failed.append(post_id)
                self.stdout.write(
                    json.dumps(
                        {
                            "post": post_id,
                            "decision": source if source != "missing" else "classified",
                            "calls": calls,
                            "names": [
                                item["finding"]["observed_name"] for item in findings
                            ],
                            "identity": identity,
                        }
                    )
                )
            if failed:
                raise CommandError(f"Incomplete posts: {failed}")
