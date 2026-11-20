"""Connect selected classification history to durable Pulse evidence.

The existing current judgments prove that a complete, possibly empty release
answer was published. Source claims store findings; queue rows only track work.
"""

from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlsplit

from django.db import connection

from core.classification_contract import COMPRESSED_CLASSIFIER_SUPPORTED_REVISIONS
from core.models import (
    Post,
    PostBrand,
    PostBrandClassificationJudgment,
    PostBrandClassificationState,
)
from core.product_release_findings import SCHEMA, finding_identity

OUTPUT_MANIFEST_SCHEMA = "pulse-classified-release-output-v1"


def validate_output_manifest(value):
    """Strict execution metadata; release facts remain in their evidence archives."""
    from x_monitor.compressed_classifier import RELEASE_LIMITS

    if (not isinstance(value, dict)
            or set(value) != {"schema", "finding_keys", "sha256"}
            or value["schema"] != OUTPUT_MANIFEST_SCHEMA):
        raise ValueError("classification_release_manifest_invalid")
    keys = value["finding_keys"]
    if (not isinstance(keys, list) or len(keys) > RELEASE_LIMITS.max_findings
            or any(not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key) for key in keys)
            or keys != sorted(set(keys))
            or not isinstance(value["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])):
        raise ValueError("classification_release_manifest_invalid")
    return value


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _output_manifest(findings):
    # Match the evidence writer's set semantics, including assertion ordering.
    canonical = sorted(
        ({**finding, "assertions": sorted(finding["assertions"], key=_encoded),
          **({"lineage_evidence": sorted(finding["lineage_evidence"], key=_encoded)}
             if "lineage_evidence" in finding else {})} for finding in findings),
        key=lambda finding: finding["finding_key"],
    )
    return validate_output_manifest({
        "schema": OUTPUT_MANIFEST_SCHEMA,
        "finding_keys": [finding["finding_key"] for finding in canonical],
        "sha256": hashlib.sha256(_encoded(canonical).encode()).hexdigest(),
    })


def selected_release_revision(post_id):
    """Return the complete selected producer generation, or pending (None)."""
    publication = _selected_release_publication(post_id)
    return publication[0] if publication is not None else None


def classifier_owns_release_extraction(post_id):
    """A selected combined judgment owns release processing even while its evidence is incomplete."""
    if PostBrandClassificationState.objects.filter(
        post_id=post_id, selected_final_judgment__stage="final",
        selected_final_judgment__validation_state="validated",
        selected_final_judgment__prompt_version__in=[rev[2] for rev in COMPRESSED_CLASSIFIER_SUPPORTED_REVISIONS],
    ).exists():
        return True
    return selected_release_revision(post_id) is not None


def _complete_release_publication(post_id):
    """Return the exact selected generation and its complete-output manifest.

    Only the atomic combined publisher writes this producer revision. An old
    classification, absent judgment or missing brand is never a valid empty
    release answer. A different selected final produces a different key.
    """
    brands = set(PostBrand.objects.filter(post_id=post_id).values_list("brand_id", flat=True))
    states = list(PostBrandClassificationState.objects.filter(post_id=post_id, brand_id__in=brands).select_related(
        "selected_final_judgment__content_judgment",
        "selected_final_judgment__brand_interpretation_judgment",
    ))
    if not brands or {row.brand_id for row in states} != brands:
        return None
    fingerprints = set()
    revisions = []
    manifest = None
    selected_revisions = None
    for row in states:
        final = row.selected_final_judgment
        if final is None:
            return None
        stages = (final.content_judgment, final.brand_interpretation_judgment, final)
        if any(stage is None for stage in stages):
            return None
        stage_revisions = tuple(stage.prompt_version for stage in stages)
        if (stage_revisions not in COMPRESSED_CLASSIFIER_SUPPORTED_REVISIONS
                or row.prompt_version != stage_revisions[2]
                or (selected_revisions is not None and stage_revisions != selected_revisions)):
            return None
        selected_revisions = stage_revisions
        for stage, prompt in zip(stages, stage_revisions):
            if (stage is None or stage.post_id != post_id or stage.brand_id != row.brand_id
                    or stage.prompt_version != prompt or stage.validation_state != "validated"
                    or stage.revision_id != final.revision_id
                    or stage.input_context_fingerprint != row.input_context_fingerprint):
                return None
        changes = final.changes_json
        if not isinstance(changes, dict) or "release_output" not in changes:
            return None
        selected_manifest = validate_output_manifest(changes["release_output"])
        if manifest is not None and selected_manifest != manifest:
            raise ValueError("classification_release_manifest_conflict")
        manifest = selected_manifest
        fingerprints.add(row.input_context_fingerprint)
        revisions.append((row.brand_id, final.revision_id))
    if len(fingerprints) != 1:
        return None
    fingerprint = fingerprints.pop()
    revision = hashlib.sha256(json.dumps(
        {"post_id": post_id, "fingerprint": fingerprint, "finals": sorted(revisions)},
        sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    return {"revision_id": revision, "content_fingerprint": fingerprint}, manifest, selected_revisions


def _selected_release_publication(post_id):
    """Select the latest complete release output, including release-only results."""
    complete = _complete_release_publication(post_id)
    partial = (PostBrandClassificationJudgment.objects.filter(
        post_id=post_id, stage="content", selector_version="pulse-release-only-v1",
        validation_state="release_only",
    ).order_by("-created_at", "-pk").first())
    if partial is None:
        return complete
    if complete is not None:
        complete_times = list(PostBrandClassificationState.objects.filter(post_id=post_id).values_list(
            "selected_final_judgment__created_at", flat=True,
        ))
        if complete_times and all(value is not None and value >= partial.created_at for value in complete_times):
            return complete
    metadata = partial.changes_json
    brands = sorted(PostBrand.objects.filter(post_id=post_id).values_list("brand_id", flat=True))
    revisions = next((row for row in COMPRESSED_CLASSIFIER_SUPPORTED_REVISIONS
                      if row[0] == partial.prompt_version), None)
    fingerprint = partial.input_context_fingerprint
    if (not isinstance(metadata, dict) or set(metadata) != {"release_output", "brand_ids"}
            or metadata["brand_ids"] != brands or partial.brand_id not in brands
            or revisions is None or partial.provider_role != "classifier-release"
            or partial.contract_version != "pulse-release-only-v1"
            or partial.taxonomy_version != "pulse-release-only-v1"
            or partial.canonical_judgment != {} or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)):
        return complete
    expected_revision = hashlib.sha256(_encoded({"post_id": post_id, "fingerprint": fingerprint,
                                                  "producer": "pulse-release-only-v1"}).encode()).hexdigest()
    if partial.revision_id != expected_revision:
        return complete
    manifest = validate_output_manifest(metadata["release_output"])
    return {"revision_id": partial.revision_id, "content_fingerprint": fingerprint}, manifest, revisions


def _saved_locator(post):
    if post is None:
        return None
    for value in (post.tweet_url, post.tweet_twitter_url):
        try:
            url = urlsplit(value or "")
            if url.scheme in {"https", "http"} and url.hostname and not url.username and not url.password:
                return value
        except ValueError:
            continue
    return None


def _source_bound_findings(post, tweet, findings):
    if not findings:
        return []
    from x_monitor.compressed_classifier import sources

    passages = {row["id"]: row["text"] for row in sources({
        "source_text": tweet["text"], "english_translation": tweet.get("english_translation"),
        "context": tweet.get("context") or [],
    })}
    related_ids = {value for value in (post.in_reply_to_id, post.quoted_status_id_id) if value}
    related = {row.pk: row for row in Post.objects.filter(pk__in=related_ids).only("tweet_id", "tweet_url", "tweet_twitter_url")}
    locators = {"post": _saved_locator(post), "translation": _saved_locator(post)}
    context = tweet.get("context") or []
    for index, row in enumerate(context):
        if not isinstance(row, dict):
            continue
        key = post.in_reply_to_id if row.get("provenance") == "local_parent" else (
            post.quoted_status_id_id if row.get("provenance") == "stored_quote" else None
        )
        locators[f"context_{index}"] = _saved_locator(related.get(key))
    bound = []
    for finding in findings:
        assertions = finding["assertions"]
        expected_key = finding_identity({"kind": "post", "id": post.pk}, assertions=assertions,
            **{key: finding[key] for key in ("observed_name", "version", "variant")})
        if finding["finding_key"] != expected_key:
            raise ValueError("classification_release_source_identity_mismatch")
        mapped = []
        for assertion in assertions:
            key = assertion["source_locator"]
            if key not in passages or assertion["source_excerpt"] not in passages[key]:
                raise ValueError("classification_release_evidence_not_supplied")
            mapped.append({**assertion, "source_locator": locators.get(key)})
        profile = finding.get("publisher_profile")
        if profile is not None and profile != tweet.get("author_profile_evidence"):
            raise ValueError("classification_publisher_profile_not_supplied")
        issuer = finding.get("issuer_evidence")
        if issuer is not None:
            key = issuer["source_locator"]
            if key not in passages or issuer["source_excerpt"] not in passages[key]:
                raise ValueError("classification_issuer_evidence_not_supplied")
            issuer = {**issuer, "source_locator": locators.get(key)}
        family = finding.get("family_evidence")
        if family is not None:
            key = family["source_locator"]
            if key not in passages or family["source_excerpt"] not in passages[key]:
                raise ValueError("classification_family_evidence_not_supplied")
            family = {**family, "source_locator": locators.get(key)}
        lineage = []
        for relation in finding.get("lineage_evidence", []):
            key = relation["source_locator"]
            if key not in passages or relation["source_excerpt"] not in passages[key]:
                raise ValueError("classification_lineage_evidence_not_supplied")
            lineage.append({**relation, "source_locator": locators.get(key)})
        output = {key: value for key, value in finding.items() if key not in {"issuer_evidence", "lineage_evidence", "family_evidence"}}
        output["assertions"] = mapped
        if issuer is not None:
            output["issuer_evidence"] = issuer
        if lineage:
            output["lineage_evidence"] = lineage
        if family is not None:
            output["family_evidence"] = family
        bound.append(output)
    return bound


def prepare_publication_findings(*, post, tweet, result):
    """Bind the complete answer once, before its final judgment is persisted."""
    if (result.get("release_findings_version") != SCHEMA
            or not isinstance(result.get("release_findings"), (tuple, list))):
        raise ValueError("classification_release_findings_missing")
    findings = _source_bound_findings(post, tweet, result["release_findings"])
    return findings, _output_manifest(findings)


def persist_publication_findings(*, post, findings):
    """Save all findings and their queue request in the publisher transaction."""
    if not connection.in_atomic_block:
        raise ValueError("classification_release_requires_publication_transaction")
    publication = _selected_release_publication(post.pk)
    if publication is None:
        raise ValueError("classification_release_generation_incomplete")
    revision, manifest, revisions = publication
    if _output_manifest(findings) != manifest:
        raise ValueError("classification_release_output_mismatch")
    from core.product_release_detection_queue import enqueue_saved_post
    from core.product_release_dossiers import persist_classified_release_findings

    outcome = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk}, **revision,
        findings=findings,
        extraction_version=revisions[0],
    )
    enqueue_saved_post(post.pk)
    return outcome


def read_publication_findings(post_id):
    """Read saved findings only; None means pending and an empty tuple is final."""
    publication = _selected_release_publication(post_id)
    if publication is None:
        return None
    revision, manifest, _ = publication
    from core.product_release_dossiers import read_saved_release_findings

    findings = read_saved_release_findings(
        source={"kind": "post", "id": post_id}, revision_id=revision["revision_id"],
    )
    if _output_manifest([row["finding"] for row in findings]) != manifest:
        raise ValueError("classification_release_output_mismatch")
    return findings


def persist_release_only(*, post_id, tweet, result, model, run_id):
    """Save a complete release answer without publishing incomplete sibling axes."""
    from django.db import transaction
    from django.utils import timezone

    from core.classification_contract import COMPRESSED_CLASSIFIER_REVISIONS
    from core.models import PostEnrichmentState
    from core.product_release_detection_queue import enqueue_saved_post
    from core.product_release_dossiers import persist_classified_release_findings
    from x_monitor.attribution import (
        _two_role_fingerprint,
        _validated_tracked_brand_catalog_snapshot,
    )

    if result.get("release_only") is not True or result.get("valid") is not False:
        return False
    with transaction.atomic():
        claim = (PostEnrichmentState.objects.select_for_update().select_related("post")
                 .filter(post_id=post_id).first())
        if (claim is None or claim.claim_run_id != str(run_id)[:128] or claim.claim_expires_at is None
                or claim.claim_expires_at <= timezone.now()):
            return False
        brands = sorted(PostBrand.objects.filter(post_id=post_id).values_list("brand_id", flat=True))
        if not brands or set(brands) != set(tweet.get("brand_ids") or []):
            return False
        catalog_revision = str(tweet.get("_classification_catalog_revision") or "")
        if not catalog_revision:
            return False
        catalog = _validated_tracked_brand_catalog_snapshot({
            "revision": catalog_revision, "brands": tweet.get("tracked_brand_catalog"),
        })
        fingerprint = _two_role_fingerprint(tweet, tracked_catalog=catalog)
        findings, manifest = prepare_publication_findings(post=claim.post, tweet=tweet, result=result)
        revision = hashlib.sha256(_encoded({"post_id": post_id, "fingerprint": fingerprint,
                                           "producer": "pulse-release-only-v1"}).encode()).hexdigest()
        metadata = {"release_output": manifest, "brand_ids": brands}
        judgment, created = PostBrandClassificationJudgment.objects.get_or_create(
            post_id=post_id, brand_id=brands[0], revision_id=revision, stage="content",
            defaults={"canonical_judgment": {}, "contract_version": "pulse-release-only-v1",
                      "taxonomy_version": "pulse-release-only-v1",
                      "prompt_version": COMPRESSED_CLASSIFIER_REVISIONS[0], "model": model,
                      "provider_role": "classifier-release", "input_context_fingerprint": fingerprint,
                      "selector_version": "pulse-release-only-v1", "validation_state": "release_only",
                      "changes_json": metadata},
        )
        if not created and (judgment.changes_json != metadata or judgment.input_context_fingerprint != fingerprint
                            or judgment.validation_state != "release_only" or judgment.provider_role != "classifier-release"
                            or judgment.selector_version != "pulse-release-only-v1"
                            or judgment.prompt_version != COMPRESSED_CLASSIFIER_REVISIONS[0]
                            or judgment.contract_version != "pulse-release-only-v1"
                            or judgment.taxonomy_version != "pulse-release-only-v1" or judgment.canonical_judgment != {}):
            raise ValueError("classification_release_only_generation_conflict")
        persist_classified_release_findings(
            source={"kind": "post", "id": post_id}, revision_id=revision, content_fingerprint=fingerprint,
            findings=findings, extraction_version=COMPRESSED_CLASSIFIER_REVISIONS[0],
        )
        enqueue_saved_post(post_id)
        return True
