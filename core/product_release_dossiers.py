"""Persist fresh product-release reports as typed EventDossier claims.

The immutable intake packet preserves source wording for audit and correction.
This module makes no provider or model calls.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date

from django.db import transaction
from django.utils import timezone

from core.collection_capture import archive_document
from core.event_dossiers import identity_key
from core.models import (
    EventClaimKind,
    EventDossier,
    EventDossierClaim,
    EventDossierSource,
    EventKind,
    ReleaseMaturity,
)

CLAIM_FIELDS = frozenset(
    {
        "organization_name",
        "organization_handle",
        "release_precision",
        "brand_id",
        "source_url",
        "version",
        "release_value",
        "model_name",
        "candidate_repo_id",
        "categories",
        "confidence",
        "release_channel",
    }
)


def _validate_record(record):
    if not isinstance(record, dict) or not record.keys() <= CLAIM_FIELDS:
        raise ValueError("Unreviewed product-release extraction keys")
    if (
        not isinstance(record.get("model_name"), str)
        or not record["model_name"].strip()
    ):
        raise ValueError("Product-release extraction needs a model name")
    for name in (
        "organization_name",
        "organization_handle",
        "brand_id",
        "source_url",
        "version",
        "release_value",
        "candidate_repo_id",
        "release_channel",
        "release_precision",
    ):
        if (
            name in record
            and record[name] is not None
            and not isinstance(record[name], str)
        ):
            raise ValueError(f"Invalid product-release extraction {name}")
    if "categories" in record and (
        not isinstance(record["categories"], list)
        or any(not isinstance(value, str) for value in record["categories"])
    ):
        raise ValueError("Invalid product-release categories")
    if "confidence" in record and record["confidence"] is not None:
        if isinstance(record["confidence"], bool):
            raise ValueError("Invalid product-release confidence")
        qualitative = isinstance(record["confidence"], str) and record[
            "confidence"
        ] in {"low", "medium", "high"}
        if not qualitative:
            try:
                confidence = float(record["confidence"])
            except (TypeError, ValueError) as error:
                raise ValueError("Invalid product-release confidence") from error
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("Invalid product-release confidence")
    return record


def _effective_fields(value, precision):
    fields = {"effective_precision": precision}
    if precision == "unknown":
        if value is not None:
            raise ValueError("Unknown release date must have no value")
    elif precision == "day":
        fields["effective_date"] = date.fromisoformat(value)
    elif precision == "month":
        year, month = value.split("-")
        fields.update(effective_year=int(year), effective_month=int(month))
    elif precision == "year":
        fields["effective_year"] = int(value)
    else:
        raise ValueError(f"Unsupported release date precision: {precision}")
    return fields


@transaction.atomic
def record_release_report(
    *,
    post,
    record,
    release_identity,
    observed_name,
    source_url,
    brand=None,
    candidate=None,
    maturity_code,
    release_value,
    release_precision,
    extraction_version,
    queue_acquisition=False,
):
    """Save one fresh source claim without writing the retired prototype tables."""
    if brand is not None and candidate is not None:
        raise ValueError("Release report cannot name two original owners")
    _validate_record(record)
    packet = {
        "schema": "product-release-intake-v1",
        "record": record,
        "source_post_id": post.pk,
        "release_identity": release_identity,
        "extraction_version": extraction_version,
    }
    body = json.dumps(
        packet, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    archive = archive_document(
        body,
        encoding="selected-json-canonical-v1",
        capture_kind="product_release_intake",
    )
    kind = EventKind.objects.get(code="product_release")
    key = identity_key("product-release-v1", release_identity)
    now = timezone.now()
    first_seen_at = post.fetched_at
    last_seen_at = post.fetched_at
    dossier, created = EventDossier.objects.get_or_create(
        identity_key=key,
        defaults={
            "event_kind_reference": kind,
            "first_seen_at": first_seen_at,
            "last_seen_at": last_seen_at,
            "created_at": now,
        },
    )
    dossier = EventDossier.objects.select_for_update().get(pk=dossier.pk)
    if dossier.event_kind_reference_id != kind.pk:
        raise ValueError("Release report identity belongs to another kind")
    source, _ = EventDossierSource.objects.get_or_create(
        event_dossier=dossier, post=post, defaults={"linked_at": now}
    )
    excerpt = post.text or observed_name
    if not excerpt.strip():
        raise ValueError("Release report has no source excerpt")
    claim_hash = hashlib.sha256(
        f"product-release-intake-v1:{post.pk}:{archive.content_sha256}".encode()
    ).hexdigest()
    claim, claim_created = EventDossierClaim.objects.get_or_create(
        claim_hash=claim_hash,
        defaults={
            "event_dossier_source": source,
            "claim_kind_reference": EventClaimKind.objects.get(code="release_report"),
            "source_archive": archive,
            "reported_brand": brand,
            "reported_brand_discovery_candidate": candidate,
            "release_maturity_reference": ReleaseMaturity.objects.get(
                code=maturity_code
            ),
            "scope_key": release_identity,
            "extraction_version": extraction_version,
            "recorded_at": now,
            "assertion_text": observed_name,
            "source_excerpt": excerpt,
            "source_locator": source_url,
            "source_hash": hashlib.sha256(excerpt.encode()).hexdigest(),
            **_effective_fields(release_value, release_precision),
        },
    )
    if (
        claim.event_dossier_source_id != source.pk
        or claim.source_archive_id != archive.pk
    ):
        raise ValueError("Release report claim identity collision")
    if dossier.last_seen_at < post.fetched_at:
        EventDossier.objects.filter(pk=dossier.pk).update(last_seen_at=post.fetched_at)
    if queue_acquisition:
        from core.product_release_acquisition import queue_after_commit

        queue_after_commit(claim.pk)
    return dossier, created, claim_created


# Classifier findings are evidence packets, not canonical Product identities.
_PULSE_FINDING_FIELDS = frozenset(
    {
        "finding_key",
        "observed_name",
        "version",
        "variant",
        "novelty",
        "category",
        "brand_id",
        "brand_candidate_id",
        "candidate_repo_id",
        "assertions",
    }
)
_PULSE_ASSERTION_FIELDS = frozenset(
    {
        "claim_kind",
        "assertion_text",
        "source_excerpt",
        "source_locator",
        "access_channel",
        "effective_precision",
        "event_timezone",
        "effective_at",
        "effective_date",
        "effective_year",
        "effective_month",
        "not_before",
        "not_after",
    }
)


def _pulse_source(source):
    from core.models import CollectionObservation, Post

    if not isinstance(source, dict) or set(source) != {"kind", "id"}:
        raise ValueError("Invalid finding source")
    if source["kind"] == "post" and isinstance(source["id"], str) and source["id"]:
        post = Post.objects.get(pk=source["id"])
        return {"kind": "post", "id": post.pk}, post.fetched_at
    if (
        source["kind"] == "observation"
        and type(source["id"]) is int
        and source["id"] > 0
    ):
        observation = CollectionObservation.objects.get(pk=source["id"])
        if observation.post_id:
            return {
                "kind": "post",
                "id": observation.post_id,
            }, observation.post.fetched_at
        return {"kind": "observation", "id": observation.pk}, observation.observed_at
    raise ValueError("Invalid finding source")


def _pulse_assertion(value):
    from datetime import datetime

    if not isinstance(value, dict) or set(value) != _PULSE_ASSERTION_FIELDS:
        raise ValueError("Invalid finding assertion")
    result = dict(value)
    if result["claim_kind"] not in {
        "announcement",
        "availability",
        "repository_created",
        "release_report",
        "release_signal",
        "source_stated_release",
        "first_observed_usage",
        "rumor",
        "release_context",
    }:
        raise ValueError("Invalid finding claim kind")
    for field in ("assertion_text", "source_excerpt"):
        if not isinstance(result[field], str) or not result[field].strip():
            raise ValueError("Finding assertion needs source text")
    for field in ("effective_at", "not_before", "not_after"):
        if result[field] is not None:
            result[field] = datetime.fromisoformat(result[field])
    if result["effective_date"] is not None:
        result["effective_date"] = date.fromisoformat(result["effective_date"])
    return result


def _pulse_revision(value):
    import re

    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Invalid finding revision")
    return value


@transaction.atomic
def persist_classified_release_findings(
    *, source, revision_id, content_fingerprint, findings, extraction_version
):
    """Persist validated findings atomically without detection or provider work."""
    from core.event_dossiers import add_claim, attach_source, create_dossier
    from core.official_company_offerings import TYPES

    revision_id = _pulse_revision(revision_id)
    _pulse_revision(content_fingerprint)
    if not isinstance(extraction_version, str) or not extraction_version.strip():
        raise ValueError("Invalid extraction version")
    if not isinstance(findings, (tuple, list)):
        raise TypeError("Invalid findings")
    source, first_seen = _pulse_source(source)
    keys = set()
    saved = []
    revision = f"pulse-classified-findings-v1:{revision_id}"
    for finding in findings:
        if (
            not isinstance(finding, dict)
            or not _PULSE_FINDING_FIELDS <= set(finding)
            or set(finding) - _PULSE_FINDING_FIELDS - {"issuer_evidence", "lineage_evidence", "publisher_profile", "family_evidence"}
        ):
            raise ValueError("Invalid finding shape")
        family = finding.get("family_evidence")
        if family is not None and (
            not isinstance(family, dict) or set(family) != {"name", "source_locator", "source_excerpt"}
            or not isinstance(family["name"], str) or not family["name"].strip()
            or not isinstance(family["source_excerpt"], str) or family["name"] not in family["source_excerpt"]
            or not isinstance(finding.get("observed_name"), str)
            or finding["observed_name"] not in family["source_excerpt"]
            or (family["source_locator"] is not None and not isinstance(family["source_locator"], str))
        ):
            raise ValueError("Invalid source-backed family evidence")
        lineage = finding.get("lineage_evidence", [])
        if not isinstance(lineage, list):
            raise TypeError("Invalid lineage evidence")
        lineage_keys = set()
        for relation in lineage:
            if (
                not isinstance(relation, dict)
                or set(relation) != {"relationship_kind", "parent_observed_name", "source_locator", "source_excerpt"}
                or relation["relationship_kind"] not in {"new_version", "finetune", "adapter", "quantized", "merge"}
                or not isinstance(relation["parent_observed_name"], str)
                or not relation["parent_observed_name"].strip()
                or not isinstance(relation["source_excerpt"], str)
                or not relation["source_excerpt"].strip()
                or not isinstance(finding["observed_name"], str)
                or finding["observed_name"].casefold() not in relation["source_excerpt"].casefold()
                or relation["parent_observed_name"].casefold() not in relation["source_excerpt"].casefold()
                or (relation["source_locator"] is not None and (
                    not isinstance(relation["source_locator"], str) or not relation["source_locator"].strip()
                ))
            ):
                raise ValueError("Invalid source-backed lineage evidence")
            relation_key = json.dumps(relation, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            if relation_key in lineage_keys:
                raise ValueError("Duplicate lineage evidence")
            lineage_keys.add(relation_key)
        profile = finding.get("publisher_profile")
        if profile is not None and (
            not isinstance(profile, dict)
            or set(profile) != {"handle", "display_name", "sources", "domains"}
            or not isinstance(profile["display_name"], str) or not profile["display_name"].strip()
            or not isinstance(profile["sources"], list) or not 1 <= len(profile["sources"]) <= 12
            or any(not isinstance(source, dict) or not {"id", "text"} <= set(source)
                   or set(source) - {"id", "text", "observed_at"}
                   or not isinstance(source["id"], str) or not source["id"]
                   or not isinstance(source["text"], str) or not source["text"] or len(source["text"]) > 2048
                   or ("observed_at" in source and not isinstance(source["observed_at"], str))
                   for source in profile["sources"])
            or not isinstance(profile["domains"], list) or len(profile["domains"]) > 16
            or any(not isinstance(domain, str) for domain in profile["domains"])
            or (profile["handle"] is not None and not isinstance(profile["handle"], str))
            or len(profile["display_name"]) > 256
            or not isinstance(finding.get("issuer_evidence"), dict)
            or finding["issuer_evidence"].get("relation") != "source_author"
            or finding["issuer_evidence"].get("observed_name") != profile["display_name"].strip()
        ):
            raise ValueError("Invalid source-author publisher profile")
        issuer = finding.get("issuer_evidence")
        if issuer is not None:
            if (
                not isinstance(issuer, dict)
                or set(issuer)
                != {"relation", "source_locator", "source_excerpt", "observed_name"}
                or issuer["relation"] not in {"source_author", "attributed_party"}
            ):
                raise ValueError("Invalid issuer evidence")
            if (
                not isinstance(issuer["source_excerpt"], str)
                or not issuer["source_excerpt"].strip()
            ):
                raise ValueError("Issuer evidence needs an excerpt")
            for field in ("source_locator", "observed_name"):
                if issuer[field] is not None and (
                    not isinstance(issuer[field], str) or not issuer[field].strip()
                ):
                    raise ValueError("Invalid issuer evidence text")
            if issuer["relation"] == "attributed_party" and (
                not issuer["observed_name"]
                or issuer["observed_name"] not in issuer["source_excerpt"]
            ):
                raise ValueError("Attributed issuer must occur in source excerpt")
        key = _pulse_revision(finding["finding_key"])
        if key in keys:
            raise ValueError("Duplicate finding key")
        keys.add(key)
        if finding["category"] is not None and finding["category"] not in TYPES:
            raise ValueError("Invalid finding category")
        if finding["novelty"] not in {
            "new_release",
            "availability_update",
            "historical_release",
            "unresolved",
        }:
            raise ValueError("Invalid finding novelty")
        for field in (
            "observed_name",
            "version",
            "variant",
            "brand_id",
            "candidate_repo_id",
        ):
            if finding[field] is not None and (
                not isinstance(finding[field], str) or not finding[field].strip()
            ):
                raise ValueError("Invalid finding text")
        if finding["brand_candidate_id"] is not None and (
            type(finding["brand_candidate_id"]) is not int
            or finding["brand_candidate_id"] <= 0
        ):
            raise ValueError("Invalid brand candidate")
        if finding["brand_id"] and finding["brand_candidate_id"]:
            raise ValueError("Conflicting finding owners")
        assertions = finding["assertions"]
        if not isinstance(assertions, (tuple, list)) or not assertions:
            raise ValueError("Finding needs assertions")
        # Assertions are a set of sourced facts: provider ordering is not identity.
        for assertion in assertions:
            _pulse_assertion(assertion)
        assertions = sorted(
            assertions,
            key=lambda item: json.dumps(
                item, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ),
        )
        finding = {**finding, "assertions": assertions}
        if "lineage_evidence" in finding:
            finding["lineage_evidence"] = sorted(
                lineage, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            )
        packet = {
            "schema": "pulse-release-intake-v1",
            "source": source,
            "revision_id": revision_id,
            "content_fingerprint": content_fingerprint,
            "extraction_version": extraction_version,
            "finding": finding,
        }
        body = json.dumps(
            packet,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        archive = archive_document(
            body,
            encoding="selected-json-canonical-v1",
            capture_kind="product_release_intake",
        )
        event = create_dossier(
            event_kind="product_release",
            identity_key=identity_key(
                "pulse-finding-v1",
                json.dumps([source, key], sort_keys=True, separators=(",", ":")),
            ),
            first_seen_at=first_seen,
        )
        # Merges retain historical rows and copy claims to the canonical dossier.
        from core.product_release_pipeline import canonical_dossier

        event = canonical_dossier(event.pk)
        linked = attach_source(
            event.pk,
            **(
                {"post_id": source["id"]}
                if source["kind"] == "post"
                else {"observation_id": source["id"]}
            ),
        )
        first = _pulse_assertion(assertions[0])
        # The dossier lock makes a repeated source/revision/key deterministic.
        EventDossier.objects.select_for_update().get(pk=event.pk)
        existing = EventDossierClaim.objects.filter(
            event_dossier_source=linked,
            extraction_version=revision,
            scope_key=f"pulse-finding-v1:{key}",
        ).first()
        if existing is not None and existing.source_archive_id != archive.pk:
            raise ValueError("Finding key reused with changed evidence")
        anchor = add_claim(
            linked.pk,
            claim_kind="release_report"
            if finding["observed_name"]
            else "release_signal",
            scope_key=f"pulse-finding-v1:{key}",
            assertion_text=finding["observed_name"] or first["assertion_text"],
            source_excerpt=first["source_excerpt"],
            source_locator=first["source_locator"],
            extraction_version=revision,
            source_archive_id=archive.pk,
            reported_brand_id=finding["brand_id"],
            reported_candidate_id=finding["brand_candidate_id"],
            release_maturity_id=ReleaseMaturity.objects.get(code="unknown").pk
            if finding["observed_name"]
            else None,
        )
        # A source-linked category projection lets the restricted web login
        # show this validated field without granting it raw archive access.
        if len(body) <= 64 * 1024:
            add_claim(linked.pk, claim_kind="release_context", scope_key=f"pulse-category-v1:{key}",
                      assertion_text=finding["category"] or "unknown", source_excerpt=first["source_excerpt"],
                      source_locator=first["source_locator"], extraction_version=revision,
                      source_archive_id=archive.pk)
        if source["kind"] == "post" and finding.get("category") in {"model-llm", "model-other"}:
            from core.product_release_acquisition import queue_after_commit

            queue_after_commit(anchor.pk, exact_only=True)
        claim_ids = []
        if issuer is not None:
            issuer_claim = add_claim(
                linked.pk,
                claim_kind="release_context",
                scope_key=f"pulse-reported-issuer-v1:{key}",
                assertion_text=(
                    "Source reports issuer relation: " + issuer["relation"]
                ),
                source_excerpt=issuer["source_excerpt"],
                source_locator=issuer["source_locator"],
                extraction_version=revision,
                source_archive_id=archive.pk,
            )
            claim_ids.append(str(issuer_claim.pk))
        for relation in finding.get("lineage_evidence", []):
            relation_key = hashlib.sha256(json.dumps(
                relation, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()).hexdigest()
            lineage_claim = add_claim(
                linked.pk, claim_kind="release_context",
                scope_key=f"pulse-lineage-v1:{key}:{relation_key}",
                assertion_text=f"Classifier-reported {relation['relationship_kind']}: {relation['parent_observed_name']}",
                source_excerpt=relation["source_excerpt"], source_locator=relation["source_locator"],
                extraction_version=revision, source_archive_id=archive.pk,
            )
            claim_ids.append(str(lineage_claim.pk))
        assertion_keys = set()
        for assertion in assertions:
            values = _pulse_assertion(assertion)
            assertion_key = hashlib.sha256(
                json.dumps(
                    assertion, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode()
            ).hexdigest()
            if assertion_key in assertion_keys:
                continue
            assertion_keys.add(assertion_key)
            if values["claim_kind"] == "release_report":
                values["release_maturity_id"] = ReleaseMaturity.objects.get(
                    code="unknown"
                ).pk
            claim = add_claim(
                linked.pk,
                scope_key=f"pulse-assertion-v1:{key}:{assertion_key}",
                extraction_version=revision,
                source_archive_id=archive.pk,
                **values,
            )
            claim_ids.append(str(claim.pk))
        saved.append(
            {
                "finding_key": key,
                "dossier_id": str(event.pk),
                "source_id": linked.pk,
                "anchor_claim_id": str(anchor.pk),
                "assertion_claim_ids": claim_ids,
                "archive_id": str(archive.pk),
                "identity": "unresolved",
            }
        )
    return {
        "source": source,
        "revision_id": revision_id,
        "outcome": "saved" if saved else "no_findings",
        "findings": saved,
    }


def _read_pulse_packet(claim):
    """Verify the saved anchor's checksum, source, revision and finding identity."""
    from core.collection_capture import read_document

    if claim.source_archive_id is None:
        raise ValueError("Finding archive missing")
    archive = claim.source_archive
    if (
        archive.capture_kind != "product_release_intake"
        or archive.encoding != "selected-json-canonical-v1"
    ):
        raise ValueError("Invalid finding archive type")
    packet = read_document(archive)
    linked = claim.event_dossier_source
    source = (
        {"kind": "post", "id": linked.post_id}
        if linked.post_id is not None
        else {"kind": "observation", "id": linked.collection_observation_id}
    )
    if (
        not isinstance(packet, dict)
        or set(packet)
        != {
            "schema",
            "source",
            "revision_id",
            "content_fingerprint",
            "extraction_version",
            "finding",
        }
        or packet["schema"] != "pulse-release-intake-v1"
        or packet["source"] != source
        or not isinstance(packet["finding"], dict)
        or not _PULSE_FINDING_FIELDS <= set(packet["finding"])
        or set(packet["finding"]) - _PULSE_FINDING_FIELDS - {"issuer_evidence", "lineage_evidence", "publisher_profile", "family_evidence"}
        or claim.scope_key != f"pulse-finding-v1:{packet['finding'].get('finding_key')}"
        or claim.extraction_version
        != f"pulse-classified-findings-v1:{packet['revision_id']}"
        or not isinstance(packet["extraction_version"], str)
        or not packet["extraction_version"].strip()
    ):
        raise ValueError("Finding archive source or identity mismatch")
    _pulse_revision(packet["revision_id"])
    _pulse_revision(packet["content_fingerprint"])
    _pulse_revision(packet["finding"]["finding_key"])
    return packet


def read_saved_release_findings(*, source, revision_id):
    """Read saved finding anchors for one source and exact classifier revision."""
    source, _ = _pulse_source(source)
    revision = f"pulse-classified-findings-v1:{_pulse_revision(revision_id)}"
    filters = (
        {"event_dossier_source__post_id": source["id"]}
        if source["kind"] == "post"
        else {"event_dossier_source__collection_observation_id": source["id"]}
    )
    claims = (
        EventDossierClaim.objects.filter(
            **filters,
            extraction_version=revision,
            scope_key__startswith="pulse-finding-v1:",
            claim_kind_reference__code__in=("release_report", "release_signal"),
            event_dossier_source__event_dossier__merged_into__isnull=True,
        )
        .select_related("source_archive", "event_dossier_source__event_dossier")
        .order_by("scope_key", "pk")
    )
    results = []
    for claim in claims:
        packet = _read_pulse_packet(claim)
        results.append(
            {
                "anchor_claim_id": str(claim.pk),
                "dossier_id": str(claim.event_dossier_source.event_dossier_id),
                "archive_id": str(claim.source_archive_id),
                "finding": packet["finding"],
            }
        )
    return tuple(results)


def resolve_saved_release_finding(*, claim_id):
    """Apply shared Product resolution to one persisted source finding."""
    from core.product_identity import resolve_saved_release_finding as resolve

    return resolve(claim_id=claim_id)
