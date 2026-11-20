"""Source-backed relationships within an explicitly selected taxonomy snapshot."""

import hashlib
import json
import re
from time import monotonic

from django.db import connection, transaction


def _same_product_name(first, second):
    """Use the same PostgreSQL case rules as indexed Product lookups."""
    if not first or not second:
        return False
    with connection.cursor() as cursor:
        cursor.execute("SELECT UPPER(%s) = UPPER(%s)", [first, second])
        return cursor.fetchone()[0]


def _supports_relation(relation, child_name):
    """Accept only explicit directional wording; other evidence remains pending."""
    from core.product_release_intake import _FUTURE, _NEGATED

    excerpt = relation["source_excerpt"]
    if (_FUTURE.search(excerpt) or _NEGATED.search(excerpt) or "?" in excerpt or "？" in excerpt
            or re.search(r"\b(?:not|no|never|neither|nobody|denied|deny|false|don't|doesn't|isn't|wasn't|rumou?r(?:ed)?|may|might|could|would|should|if|unless|whether|suppose|hypothetically|reportedly|allegedly)\b", excerpt, re.IGNORECASE)):
        return False
    verbs = {
        "new_version": r"(?:succeeds|is\s+(?:the\s+)?successor\s+to|is\s+(?:a\s+)?new\s+version\s+of)",
        "finetune": r"(?:is\s+)?(?:fine[- ]tuned\s+from|a\s+fine[- ]tune\s+of)",
        "adapter": r"(?:is\s+)?(?:an?\s+)?adapter\s+(?:for|of)",
        "quantized": r"(?:is\s+)?(?:a\s+)?quantized\s+version\s+of",
        "merge": r"(?:is\s+)?(?:a\s+)?merge\s+of",
    }
    verb = verbs.get(relation["relationship_kind"])
    return bool(verb and re.search(
        rf"(?<![\w./:+-]){re.escape(child_name)}(?!\w|[._:/+-]\w)\s+{verb}\s+{re.escape(relation['parent_observed_name'])}(?!\w|[._:/+-]\w)",
        excerpt, re.IGNORECASE,
    ))


@transaction.atomic
def register_qualified_lineage(*, child_claim_id, parent_claim_id, relation_index,
                               basis_version_id, max_subjects, max_seconds, expected_parent_id=None,
                               expected_child_id=None, expected_child_brand=None):
    """Save one explicit relationship against the supplied immutable basis.

    ``basis_version_id=None`` starts a compact two-product version. Existing
    versions are never combined or called current without a caller's selection.
    """
    from core.measurement_taxonomy import configure_taxonomy, prepare_taxonomy
    from core.models import (
        EventDossier,
        EventDossierClaim,
        EventDossierReviewClaim,
        Product,
        ProductRelationship,
        ProductReleaseDetail,
        TaxonomyVersion,
    )
    from core.product_identity import _qualified_anchor_name, _resolved_anchor_product
    from core.product_release_dossiers import _read_pulse_packet
    from core.product_release_pipeline import canonical_dossier

    if type(relation_index) is not int or relation_index < 0:
        raise ValueError("Explicit lineage selection required")
    if type(max_subjects) is not int or max_subjects <= 0:
        raise ValueError("Explicit lineage subject budget required")
    if expected_parent_id is not None and (type(expected_parent_id) is not int or expected_parent_id <= 0):
        raise ValueError("Invalid expected parent Product")
    if expected_child_id is not None and (type(expected_child_id) is not int or expected_child_id <= 0):
        raise ValueError("Invalid expected child Product")
    if type(max_seconds) not in (int, float) or not 0 < max_seconds <= 3600:
        raise ValueError("Explicit lineage time budget required")
    deadline = monotonic() + max_seconds
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_setting('statement_timeout'), current_setting('lock_timeout'), "
            "(SELECT setting::bigint FROM pg_settings WHERE name='statement_timeout'), "
            "(SELECT setting::bigint FROM pg_settings WHERE name='lock_timeout')"
        )
        statement_before, lock_before, statement_ms, lock_ms = cursor.fetchone()
        budget_ms = max(1, int(max_seconds * 1000))
        cursor.execute("SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)",
                       [f"{min(statement_ms or budget_ms, budget_ms)}ms", f"{min(lock_ms or budget_ms, budget_ms)}ms"])

    def canonical_anchor(pk, *, allow_legacy=False):
        original = EventDossierClaim.objects.select_related(
            "source_archive", "claim_kind_reference", "event_dossier_source__event_dossier"
        ).get(pk=pk)
        dossier = canonical_dossier(original.event_dossier_source.event_dossier_id)
        if allow_legacy and not original.scope_key.startswith("pulse-finding-v1:"):
            if (dossier.pk == original.event_dossier_source.event_dossier_id
                    and dossier.current_review_id and dossier.current_review.review_state == "confirmed"
                    and EventDossierReviewClaim.objects.filter(review_id=dossier.current_review_id,
                                                               claim=original, disposition="accepted").exists()):
                detail = ProductReleaseDetail.objects.filter(review_id=dossier.current_review_id).select_related("product").first()
                if detail and detail.product_id:
                    return dossier, original, {"finding": {"observed_name": detail.observed_name}}, detail.product.pk
            return dossier, None, {"finding": {}}, None
        if original.claim_kind_reference.code not in {"release_report", "release_signal"}:
            raise ValueError("Invalid lineage finding anchor")
        packet = _read_pulse_packet(original)
        anchor = EventDossierClaim.objects.select_related("source_archive", "event_dossier_source").filter(
            event_dossier_source__event_dossier=dossier,
            event_dossier_source__post_id=original.event_dossier_source.post_id,
            event_dossier_source__collection_observation_id=original.event_dossier_source.collection_observation_id,
            scope_key=original.scope_key, source_archive_id=original.source_archive_id,
        ).first()
        return dossier, anchor, packet, None

    child_dossier, child_anchor, child_packet, _ = canonical_anchor(child_claim_id)
    parent_dossier, parent_anchor, parent_packet, legacy_parent_id = canonical_anchor(parent_claim_id, allow_legacy=True)
    dossiers = {
        row.pk: row for row in EventDossier.objects.select_for_update(of=("self",))
        .filter(pk__in=[child_dossier.pk, parent_dossier.pk]).select_related("current_review").order_by("pk")
    }
    child_dossier, parent_dossier = dossiers[child_dossier.pk], dossiers[parent_dossier.pk]
    result = {"status": "unresolved"}
    if expected_parent_id is not None and (not parent_anchor or parent_dossier.merged_into_id):
        result = {"status": "stale_parent"}
    if expected_child_id is not None and (not child_anchor or child_dossier.merged_into_id):
        result = {"status": "stale_child"}
    if child_anchor and parent_anchor and not child_dossier.merged_into_id and not parent_dossier.merged_into_id:
        relations = child_packet["finding"].get("lineage_evidence", [])
        if relation_index >= len(relations):
            raise ValueError("Lineage selection is missing")
        relation = relations[relation_index]
        relation_hash = hashlib.sha256(json.dumps(
            relation, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()).hexdigest()
        stored = EventDossierClaim.objects.filter(
            event_dossier_source=child_anchor.event_dossier_source, source_archive_id=child_anchor.source_archive_id,
            scope_key=f"pulse-lineage-v1:{child_packet['finding']['finding_key']}:{relation_hash}",
            extraction_version=child_anchor.extraction_version,
        ).exists()
        parent_name = (_qualified_anchor_name(parent_anchor, parent_dossier, packet=parent_packet)
                       if not legacy_parent_id else parent_packet["finding"].get("observed_name"))
        child_name = child_packet["finding"].get("observed_name")
        child_id = _resolved_anchor_product(child_anchor, child_dossier)
        if legacy_parent_id:
            detail = ProductReleaseDetail.objects.filter(review_id=parent_dossier.current_review_id, product__id=legacy_parent_id,
                                                         observed_name__iexact=parent_name).first()
            parent_id = legacy_parent_id if (
                parent_dossier.current_review_id and parent_dossier.current_review.review_state == "confirmed"
                and detail and EventDossierReviewClaim.objects.filter(review_id=parent_dossier.current_review_id,
                                                                       claim=parent_anchor, disposition="accepted").exists()
            ) else None
        else:
            parent_id = _resolved_anchor_product(parent_anchor, parent_dossier)
        post = child_anchor.event_dossier_source.post if child_anchor.event_dossier_source.post_id else None
        child_eligible, parent_eligible = (
            dossier.intake_decisions.order_by("-recorded_at", "-pk").values_list("outcome", flat=True).first()
            not in {"non_release", "scam", "superseded"} for dossier in (child_dossier, parent_dossier)
        )
        if expected_child_id is not None and (child_id != expected_child_id or not child_eligible):
            result = {"status": "stale_child"}
        elif expected_parent_id is not None and (parent_id != expected_parent_id or not parent_eligible):
            result = {"status": "stale_parent"}
        elif (stored and child_eligible and parent_eligible and post and relation["source_excerpt"] in (post.text or "")
                and parent_name and child_name and _same_product_name(parent_name, relation["parent_observed_name"])
                and _supports_relation(relation, child_name) and child_id and parent_id and child_id != parent_id):
            products = {row.pk: row for row in Product.objects.select_for_update(of=("self",)).select_related("product_type")
                        .filter(pk__in=[child_id, parent_id]).order_by("pk")}
            child, parent = products[child_id], products[parent_id]
            if expected_child_brand is not None and child.brand_id != expected_child_brand:
                result = {"status": "stale_child"}
            elif child.brand_id and child.brand_id == parent.brand_id and child.product_type_id and parent.product_type_id:
                edges = ProductRelationship.objects.filter(parent_product_id=parent.product_key, child_product_id=child.product_key)
                replay = edges.filter(product_relationship_type__code=relation["relationship_kind"],
                                      evidence__finding_claim_id=str(child_anchor.pk)).first()
                if basis_version_id is None and replay:
                    result = {"status": "matched_replay", "relationship_id": str(replay.pk), "taxonomy_version_id": str(replay.taxonomy_version_id)}
                elif basis_version_id is None and edges.exists():
                    result = {"status": "basis_required"}
                else:
                    spec = {"reviewed_by": "pulse-classifier-source-evidence-v1", "subjects": [], "relationships": [], "groups": [], "affiliations": []}
                    basis_snapshot = None
                    if basis_version_id is not None:
                        basis = TaxonomyVersion.objects.get(pk=basis_version_id)
                        snapshot = basis.snapshot
                        basis_snapshot = snapshot
                        # Group rules have mutable shared owners; do not revise
                        # them implicitly while writing a relationship.
                        if snapshot["groups"] or snapshot["affiliations"]:
                            result = {"status": "unsupported_basis"}
                        for row in snapshot["subjects"].values():
                            if row["kind"] != "product_group":
                                entry = {"kind": row["kind"], "key": row["key"]}
                                qualification = snapshot["products"].get(row["key"], {}).get("model_kind_qualification")
                                if qualification:
                                    entry["model_kind_qualification"] = qualification
                                spec["subjects"].append(entry)
                        spec["relationships"] = list(snapshot["relationships"])
                        spec["affiliations"] = list(snapshot["affiliations"])
                        allowed = {"key", "name", "description", "group_kind", "rule_kind", "root", "owner_brands", "include", "exclude", "rule_version"}
                        spec["groups"] = [{key: value for key, value in group.items() if key in allowed} for group in snapshot["groups"].values()]
                        existing = edges.filter(taxonomy_version=basis).select_related("product_relationship_type").first()
                        if existing and result["status"] == "unresolved":
                            kinds = set(edges.filter(taxonomy_version=basis).values_list("product_relationship_type__code", flat=True))
                            result = ({"status": "matched", "relationship_id": str(existing.pk), "taxonomy_version_id": str(basis.pk)}
                                      if kinds == {relation["relationship_kind"]} else {"status": "conflict"})
                    if result["status"] == "unresolved":
                        known = {(row["kind"], str(row["key"])) for row in spec["subjects"]}
                        for product in (parent, child):
                            if ("product", str(product.product_key)) not in known:
                                spec["subjects"].append({"kind": "product", "key": str(product.product_key)})
                        if len(spec["subjects"]) > max_subjects:
                            result = {"status": "subject_limit"}
                        else:
                            spec["relationships"].append({"parent": str(parent.product_key), "child": str(child.product_key),
                                "type": relation["relationship_kind"], "evidence_method": "source_reported",
                                "evidence": {"finding_claim_id": str(child_anchor.pk), "source_archive_id": str(child_anchor.source_archive_id),
                                             "source_excerpt": relation["source_excerpt"], "source_locator": relation["source_locator"]}})
                            try:
                                prepared = prepare_taxonomy(spec)
                            except ValueError:
                                result = {"status": "conflict"}
                            else:
                                drifted = basis_snapshot is not None and any(
                                    prepared[section].get(key) != value
                                    for section in ("subjects", "products")
                                    for key, value in basis_snapshot[section].items()
                                )
                                if drifted:
                                    result = {"status": "basis_drift"}
                                else:
                                    class BasisDrift(Exception):
                                        pass

                                    try:
                                        with transaction.atomic():
                                            version = configure_taxonomy(spec)
                                            if basis_snapshot is not None and any(
                                                version.snapshot[section].get(key) != value
                                                for section in ("subjects", "products")
                                                for key, value in basis_snapshot[section].items()
                                            ):
                                                raise BasisDrift
                                            edge = ProductRelationship.objects.get(taxonomy_version=version, parent_product_id=parent.product_key,
                                                                                   child_product_id=child.product_key)
                                    except BasisDrift:
                                        result = {"status": "basis_drift"}
                                    else:
                                        result = {"status": "created", "relationship_id": str(edge.pk), "taxonomy_version_id": str(version.pk)}
    if monotonic() >= deadline:
        raise TimeoutError("Lineage time budget exceeded")
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)",
                       [statement_before, lock_before])
    return result


@transaction.atomic
def resolve_reported_lineage(*, child_claim_id, relation_index, basis_version_id,
                             max_candidates, max_subjects, max_seconds):
    """Find one source-qualified parent and register its reported relationship.

    Unresolved or ambiguous results are durable in the original saved claim;
    ``candidate_limit`` and ``busy`` are retryable without another model call.
    """
    from django.db.models import F

    from core.models import (
        EventDossierClaim,
        EventDossierReviewClaim,
        PostBrandProduct,
        Product,
        ProductReleaseDetail,
    )
    from core.product_identity import _qualified_anchor_name, _resolved_anchor_product
    from core.product_release_dossiers import _read_pulse_packet
    from core.product_release_pipeline import canonical_dossier

    if type(max_candidates) is not int or max_candidates <= 0:
        raise ValueError("Explicit lineage candidate budget required")
    if type(max_seconds) not in (int, float) or not 0 < max_seconds <= 3600:
        raise ValueError("Explicit lineage time budget required")
    if type(relation_index) is not int or relation_index < 0:
        raise ValueError("Explicit lineage selection required")
    deadline = monotonic() + max_seconds
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_setting('statement_timeout'), current_setting('lock_timeout'), "
            "(SELECT setting::bigint FROM pg_settings WHERE name='statement_timeout'), "
            "(SELECT setting::bigint FROM pg_settings WHERE name='lock_timeout')"
        )
        statement_before, lock_before, statement_ms, lock_ms = cursor.fetchone()
        budget_ms = max(1, int(max_seconds * 1000))
        cursor.execute("SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)",
                       [f"{min(statement_ms or budget_ms, budget_ms)}ms", f"{min(lock_ms or budget_ms, budget_ms)}ms"])
    original = EventDossierClaim.objects.select_related(
        "source_archive", "event_dossier_source__event_dossier", "claim_kind_reference"
    ).get(pk=child_claim_id)
    if original.claim_kind_reference.code not in {"release_report", "release_signal"}:
        raise ValueError("Invalid lineage finding anchor")
    packet = _read_pulse_packet(original)
    dossier = canonical_dossier(original.event_dossier_source.event_dossier_id)
    anchor = EventDossierClaim.objects.select_related("source_archive", "event_dossier_source").filter(
        event_dossier_source__event_dossier=dossier,
        event_dossier_source__post_id=original.event_dossier_source.post_id,
        event_dossier_source__collection_observation_id=original.event_dossier_source.collection_observation_id,
        scope_key=original.scope_key, source_archive_id=original.source_archive_id,
    ).first()
    relations = packet["finding"].get("lineage_evidence", [])
    if relation_index >= len(relations):
        raise ValueError("Lineage selection is missing")
    result = {"status": "unresolved", "retryable": False}
    child_id = _resolved_anchor_product(anchor, dossier) if anchor else None
    if child_id:
        child = Product.objects.get(pk=child_id)
        relation = relations[relation_index]
        name = relation["parent_observed_name"]
        if child.brand_id:
            from core.product_identity_locks import (
                ProductNameBusy,
                lock_product_evidence_names,
            )

            try:
                lock_product_evidence_names([name])
            except ProductNameBusy:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)",
                                   [statement_before, lock_before])
                return {"status": "busy", "retryable": True}
            edges = PostBrandProduct.objects.filter(
                brand_id=child.brand_id, observed_name__iexact=name,
            ).values_list("product_id", flat=True).distinct()[:max_candidates + 1]
            reviews = ProductReleaseDetail.objects.filter(
                observed_name__iexact=name,
                review__review_state="confirmed", review__event_dossier__current_review_id=F("review_id"),
                review__event_dossier__merged_into__isnull=True,
            ).values_list("product__id", flat=True).distinct()[:max_candidates + 1]
            candidates = set(edges) | set(reviews)
            if len(candidates) > max_candidates:
                result = {"status": "candidate_limit", "retryable": True}
            elif len(candidates) > 1:
                result = {"status": "ambiguous", "retryable": False}
            elif len(candidates) == 1:
                parent_id = next(iter(candidates))
                evidence = list(EventDossierClaim.objects.filter(
                    reported_product_id=parent_id, scope_key__startswith="pulse-self-identity-v1:",
                    extraction_version="pulse-product-identity-v1", source_archive__isnull=False,
                    event_dossier_source__event_dossier__merged_into__isnull=True,
                ).select_related("event_dossier_source", "source_archive").order_by("recorded_at", "pk")[:max_candidates + 1])
                matches = []
                for identity in evidence[:max_candidates]:
                    key = identity.scope_key.removeprefix("pulse-self-identity-v1:")
                    parent_anchor = EventDossierClaim.objects.select_related("source_archive", "event_dossier_source").filter(
                        event_dossier_source=identity.event_dossier_source, source_archive_id=identity.source_archive_id,
                        scope_key="pulse-finding-v1:" + key,
                    ).first()
                    if parent_anchor:
                        parent_dossier = canonical_dossier(parent_anchor.event_dossier_source.event_dossier_id)
                        parent_packet = _read_pulse_packet(parent_anchor)
                        latest = parent_dossier.intake_decisions.order_by("-recorded_at", "-pk").values_list("outcome", flat=True).first()
                        if (latest not in {"non_release", "scam", "superseded"}
                                and _same_product_name(_qualified_anchor_name(parent_anchor, parent_dossier, packet=parent_packet), name)
                                and _resolved_anchor_product(parent_anchor, parent_dossier, packet=parent_packet) == parent_id):
                            matches.append(parent_anchor)
                            break
                if not matches:
                    accepted = list(EventDossierReviewClaim.objects.filter(
                        review__review_state="confirmed", review__product_release__product__id=parent_id,
                        review__product_release__observed_name__iexact=name,
                        review__event_dossier__current_review_id=F("review_id"),
                        review__event_dossier__merged_into__isnull=True, disposition="accepted",
                    ).select_related("claim__event_dossier_source").order_by("pk")[:max_candidates + 1])
                    for decision in accepted[:max_candidates]:
                        parent_dossier = canonical_dossier(decision.claim.event_dossier_source.event_dossier_id)
                        latest = parent_dossier.intake_decisions.order_by("-recorded_at", "-pk").values_list("outcome", flat=True).first()
                        qualified = True
                        if decision.claim.scope_key.startswith("pulse-finding-v1:"):
                            parent_packet = _read_pulse_packet(decision.claim)
                            qualified = (
                                _same_product_name(_qualified_anchor_name(decision.claim, parent_dossier, packet=parent_packet), name)
                                and _resolved_anchor_product(decision.claim, parent_dossier, packet=parent_packet) == parent_id
                            )
                        if latest not in {"non_release", "scam", "superseded"} and qualified:
                            matches.append(decision.claim)
                            break
                    if not matches and len(accepted) > max_candidates:
                        result = {"status": "candidate_limit", "retryable": True}
                if matches:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Lineage time budget exceeded")
                    result = register_qualified_lineage(
                        child_claim_id=child_claim_id, parent_claim_id=matches[0].pk,
                        relation_index=relation_index, basis_version_id=basis_version_id,
                        max_subjects=max_subjects, max_seconds=remaining, expected_parent_id=parent_id,
                        expected_child_id=child_id, expected_child_brand=child.brand_id,
                    )
                    result["retryable"] = result["status"] in {"busy", "candidate_limit", "stale_parent", "stale_child"}
                elif len(evidence) > max_candidates:
                    result = {"status": "candidate_limit", "retryable": True}
    if monotonic() >= deadline:
        raise TimeoutError("Lineage time budget exceeded")
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)",
                       [statement_before, lock_before])
    return result
