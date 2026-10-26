"""Read-only acceptance of historical X posts against current harvest storage.

The operator embeds this module in a pinned Render one-off. It does not fetch,
enrich, repair or register anything. Canonical parsers and application readers
remain the source of truth; this checks their persisted inputs and projections.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter

from django.db import connection, transaction
from django.db.models import Exists, OuterRef

from core.classification_contract import CONTRACT_VERSION, TAXONOMY_VERSION
from core.models import (
    AccountProfileSnapshot,
    CollectionJob,
    CollectionObservation,
    Post,
    RareTypeSearchHit,
)
from monitor.backfill_enrichment import completion_facts
from monitor.cycle import _parse_published_classifications
from monitor.post_artifacts import read_post_content_many
from scripts.backfill_targeted import incomplete_roles


def _present(value):
    return isinstance(value, str) and bool(value.strip())


def verify_posts(ids, *, cfg, since_epoch=None, until_epoch=None, collection_only=False):
    """Check a bounded page; return reasons rather than hide a failed row."""
    if not 0 < len(ids) <= 100 or len(set(ids)) != len(ids):
        raise ValueError("verification_requires_1_to_100_distinct_ids")
    facts = {} if collection_only else completion_facts(ids)
    posts_query = (
        Post.objects.filter(pk__in=ids)
        .annotate(
            profile_snapshot_present=Exists(
                AccountProfileSnapshot.objects.filter(account_id=OuterRef("author_id"))
            )
        )
        .select_related("author")
        .prefetch_related("brands__brand", "mentions")
    )
    if not collection_only:
        posts_query = posts_query.select_related("enrichment_state").prefetch_related(
            "signals", "product_label_edges",
            "classification_states__selected_final_judgment",
            "audience_topic_assignments__concept", "geopolitical_mode_assignments",
            "translation_artifacts__texts",
        )
    posts = list(posts_query)
    projections = {} if collection_only else read_post_content_many(posts)
    present_ids = {str(post.pk) for post in posts}
    errors = {str(i): ["post_missing"] for i in ids if str(i) not in present_ids}
    for post in posts:
        reasons = []
        if not _present(post.text):
            reasons.append("source_text_missing")
        if post.created_at is None:
            reasons.append("publication_time_missing")
        elif (
            post.created_at_epoch is not None
            and int(post.created_at.timestamp()) != post.created_at_epoch
        ):
            reasons.append("publication_time_inconsistent")
        elif (
            since_epoch is not None
            and not since_epoch <= int(post.created_at.timestamp()) < until_epoch
        ):
            reasons.append("outside_frozen_window")
        if post.author_id is None or post.author.data_source_id != "x":
            reasons.append("x_author_missing")
        elif not post.profile_snapshot_present:
            reasons.append("author_profile_snapshot_missing")
        brands = {row.brand_id for row in post.brands.all()}
        if not brands:
            reasons.append("brand_attribution_missing")
        # Sentinel attribution records the absence of a matched brand; it is
        # never a claim that the Post mentioned that sentinel's name.
        evidence_brands = {row.brand_id for row in post.brands.all() if not row.brand.is_sentinel}
        if not evidence_brands <= {row.brand_id for row in post.mentions.all()}:
            reasons.append("brand_mention_missing")
        if collection_only:
            if reasons:
                errors[str(post.pk)] = sorted(set(reasons))
            continue
        state = getattr(post, "enrichment_state", None)
        if (
            state is None
            or state.translation_status != "succeeded"
            or state.classification_status != "succeeded"
        ):
            reasons.append("durable_enrichment_incomplete")
        if not facts[str(post.pk)]["translation"]:
            reasons.append("canonical_translation_invalid")
        if not facts[str(post.pk)]["classification"]:
            reasons.append("canonical_classification_invalid")
        projection = projections[str(post.pk)]
        if projection.literal_source != "normalized" or set(projection.literal) != {
            "en",
            "zh-cn",
            "ja",
        }:
            reasons.append("application_literal_projection_incomplete")
        if not _present(post.lang_detected):
            reasons.append("detected_language_missing")
        if not _present(post.text_en) or not _present(post.text_zh_cn):
            reasons.append("legacy_literal_projection_incomplete")
        artifacts = [
            a
            for a in post.translation_artifacts.all()
            if a.is_current and a.state == "succeeded"
        ]
        if len(artifacts) != 1 or artifacts[0].model != cfg.llm.translator_model:
            reasons.append("translation_model_or_current_identity_mismatch")
        states = {row.brand_id: row for row in post.classification_states.all()}
        canonical = (
            _parse_published_classifications(
                {
                    brand: row.selected_final_judgment.canonical_judgment
                    for brand, row in states.items()
                    if row.selected_final_judgment is not None
                },
                brands,
            )
            if brands
            else None
        )
        for brand, row in states.items():
            if row.model != cfg.llm.classifier_model:
                reasons.append("classification_model_mismatch")
            if (
                row.contract_version != CONTRACT_VERSION
                or row.taxonomy_version != TAXONOMY_VERSION
            ):
                reasons.append("classification_contract_mismatch")
            selected = row.selected_final_judgment
            if canonical is None or selected is None:
                continue
            expected = canonical[brand]
            # Read the same published v4 contract as the normal harvester.
            if "audience_topics" not in expected:
                reasons.append("current_classification_contract_missing")
                continue
            topics = [
                a for a in post.audience_topic_assignments.all() if a.brand_id == brand
            ]
            modes = [
                a
                for a in post.geopolitical_mode_assignments.all()
                if a.brand_id == brand
            ]
            if {a.concept.key for a in topics} != set(expected["audience_topics"]):
                reasons.append("audience_topic_projection_mismatch")
            if {a.geopolitical_mode_id for a in modes} != set(
                expected["geopolitical_modes"]
            ):
                reasons.append("geopolitical_projection_mismatch")
            for a in [*topics, *modes]:
                if a.final_judgment_id != selected.pk or a.model != row.model:
                    reasons.append("derived_judgment_provenance_mismatch")
            for country in ("china", "us"):
                expected_stance = expected[f"{country}_national_stance"]
                if (
                    getattr(row, f"{country}_national_stance_id") != expected_stance
                    or getattr(row, f"{country}_nationalism_id") != expected_stance
                ):
                    reasons.append("national_stance_projection_mismatch")
            if any(
                s.brand_id == brand and s.sentiment_id != expected["sentiment"]
                for s in post.signals.all()
            ):
                reasons.append("signal_sentiment_projection_mismatch")
        if incomplete_roles(post, cfg):
            reasons.append("targeted_extraction_incomplete")
        if reasons:
            errors[str(post.pk)] = sorted(set(reasons))
    return {"checked": len(ids), "valid": len(ids) - len(errors), "errors": errors}


def verify_collection_window(job_id, *, cfg):
    """Accept durable collection without requiring later enrichment."""
    return verify_window(job_id, cfg=cfg, collection_only=True)


def verify_window(job_id, *, cfg, collection_only=False):
    """Verify every member, collection checkpoint and consumer output, read-only."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            cursor.execute("SET LOCAL statement_timeout='60s'")
        job = CollectionJob.objects.select_related("last_success").get(pk=job_id)
        if (
            job.state != "completed"
            or job.last_success is None
            or job.last_success.status != "success"
        ):
            raise ValueError("collection_not_successful")
        from core.collection_pages import page_receipts

        scopes = list(job.last_success.scopes.filter(scope_kind="x_query"))
        receipts = {scope.pk: page_receipts(scope) for scope in scopes}
        if (
            {(s.scope_kind, s.scope_key) for s in scopes}
            != {(u.get("scope_kind", "x_query"), u["scope_key"]) for u in job.scope["units"]}
            or len(scopes) != len(job.scope["units"])
            or not scopes
            or any(
                not s.enumeration_complete or s.outcome != "complete" for s in scopes
            )
        ):
            raise ValueError("collection_scope_not_drained")
        for scope in scopes:
            if not any(e.get("collection_drained") for e in receipts[scope.pk]):
                raise ValueError("collection_terminal_receipt_missing")
            for envelope in receipts[scope.pk]:
                if "received_post_ids" not in envelope:
                    continue  # Publication-only envelope; source page is separate.
                received = envelope["received_post_ids"]
                exclusions = envelope.get("exclusions", [])
                excluded = {row["appearance"] for row in exclusions}
                retained = set(envelope.get("post_ids", [])) | set(envelope.get("inbox_post_ids", []))
                if (
                    len(received) != envelope.get("raw_count")
                    or len(excluded) != len(exclusions)
                    or any(not isinstance(i, int) or not 0 <= i < len(received) for i in excluded)
                    or any(not row.get("reason") or row.get("post_id") != received[row["appearance"]]
                           for row in exclusions)
                    or any(i not in excluded and identifier not in retained
                           for i, identifier in enumerate(received))
                ):
                    raise ValueError("collection_page_accounting_mismatch")
        checkpoint_ids = {
            str(i) for s in scopes for e in receipts[s.pk] for i in e.get("post_ids", [])
        }
        # Gate outcomes are durable source facts, independent of model enrichment.
        hit_ids = {hit for scope in scopes for envelope in receipts[scope.pk]
                   for hit in envelope.get("rare_hit_ids", [])}
        hits = list(RareTypeSearchHit.objects.filter(pk__in=hit_ids)
                    .values("pk", "gate_state", "post_id")) if hit_ids else []
        if len(hits) != len(hit_ids) or any(
            hit["gate_state"] not in {"junk", "review_needed"}
            and not (hit["gate_state"] == "kept" and str(hit["post_id"]) in checkpoint_ids)
            for hit in hits
        ):
            raise ValueError("collection_rare_gate_pending")
        observations = CollectionObservation.objects.filter(
            run__job=job, source_subject_kind="post"
        )
        count = observations.values("post_id").distinct().count()
        if count != len(checkpoint_ids):
            raise ValueError("collection_membership_count_mismatch")
        after, checked, failures, samples = "", 0, Counter(), {}
        digest = hashlib.sha256()
        bounds = job.scope
        while True:
            ids = list(
                observations.filter(post_id__gt=after)
                .order_by("post_id")
                .values_list("post_id", flat=True)
                .distinct()[:100]
            )
            if not ids:
                break
            if not set(ids) <= checkpoint_ids:
                raise ValueError("collection_membership_identity_mismatch")
            after = ids[-1]
            result = verify_posts(
                ids,
                cfg=cfg,
                since_epoch=bounds["since_epoch"],
                until_epoch=bounds["until_epoch"],
                collection_only=collection_only,
            )
            checked += result["checked"]
            for identifier in ids:
                digest.update((str(identifier) + "\n").encode())
            for identifier, reasons in result["errors"].items():
                failures.update(reasons)
                if len(samples) < 50:
                    samples[identifier] = reasons
        if checked != count:
            raise ValueError("collection_verification_count_mismatch")
        return {
            "schema_version": 1,
            "status": "verified" if not failures else "failed",
            "source_collection_job": str(job.pk),
            "checked_posts": checked,
            "zero_results": checked == 0,
            "phase": "collection" if collection_only else "enrichment",
            "scopes_complete": len(scopes),
            "member_ids_sha256": digest.hexdigest(),
            "failure_counts": dict(failures),
            "failure_samples": samples,
            "twitterapi_requests": 0,
            "model_requests": 0,
        }


def semantic_snapshot(post_id):
    """Comparable fixture output; execution identity/times remain separately stored."""
    post = Post.objects.get(pk=post_id)
    excluded = {
        "fetched_at",
        "source_query_id",
        "metrics_refreshed_at",
        "last_quote_fetched_at",
    }
    snapshot = {
        "post": {
            field.attname: getattr(post, field.attname)
            for field in Post._meta.concrete_fields
            if field.name not in excluded
        },
    }
    for relation, excluded_fields in {
        "brands": set(),
        "mentions": {"mentioned_at"},
        "signals": set(),
        "product_label_edges": set(),
        "classification_states": {"classified_at", "selected_final_judgment_id"},
        "audience_topic_assignments": {"assigned_at", "final_judgment_id"},
        "geopolitical_mode_assignments": {"assigned_at", "final_judgment_id"},
    }.items():
        rows = getattr(post, relation).all()
        snapshot[relation] = sorted(
            [
                {k: v for k, v in row.items() if k not in excluded_fields}
                for row in rows.values()
            ],
            key=lambda row: json.dumps(row, sort_keys=True, default=str),
        )
    projection = read_post_content_many([post])[str(post.pk)]
    snapshot["literal"] = dict(projection.literal)
    return snapshot
