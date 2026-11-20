"""Shared exact native Product registration for already-qualified callers.

A repository identity is not evidence that it is a particular announcement or
that its publisher owns it. Callers retain their source-specific qualification.
"""

from django.db import transaction

from core.models import Product


def find_or_create_product(
    *, defaults, repo_id=None, product_key=None, allow_new=False
):
    """Register an already-qualified identity through one Product boundary.

    A caller without a native/UUID key must explicitly qualify creation and
    hold its source-specific identity lock. Names alone are never lookup keys.
    """
    if not isinstance(defaults, dict) or (
        repo_id is not None and product_key is not None
    ):
        raise ValueError("Invalid Product registration")
    if repo_id is not None:
        if not isinstance(repo_id, str) or not repo_id.strip():
            raise ValueError("Exact HF repository identity required")
        return Product.objects.get_or_create(repo_id=repo_id, defaults=defaults)
    if product_key is not None:
        return Product.objects.get_or_create(product_key=product_key, defaults=defaults)
    if allow_new is not True:
        raise ValueError("Qualified Product identity required")
    return Product.objects.create(**defaults), True


def register_hf_product(repo_id, *, defaults):
    """Reuse the existing case-insensitive HF repository identity or create it."""
    return find_or_create_product(repo_id=repo_id, defaults=defaults)


def _ensure_model_family(product, finding, claim):
    """Give a confirmed model a stable family until stronger evidence arrives."""
    import re

    from django.db.models import F

    from core.measurement_taxonomy import configure_taxonomy
    from core.models import ProductGroup, ProductGroupMembership

    product = Product.objects.select_for_update(of=("self",)).select_related("product_type").get(pk=product.pk)
    qualification = None
    if product.product_type:
        if product.product_type.code not in {"model-llm", "model-other"}:
            return None
    elif product.repo_id and product.hf_type == "model":
        from core.model_kind_qualification import qualify_model_kind

        qualification = qualify_model_kind(product)
        if qualification is None:
            return None
    else:
        return None
    memberships = list(
        ProductGroupMembership.objects.filter(
            product=product,
            group__group_kind="family",
            membership_status="included",
            taxonomy_version_id=F("group__rule_taxonomy_version_id"),
        ).values_list("group_id", flat=True)[:2]
    )
    if memberships:
        return memberships[0] if len(memberships) == 1 else None
    name = product.display_name or finding.get("observed_name")
    if not name:
        return None
    # Remove only version and variant values actually supplied for this Product.
    # This keeps meaningful names intact when the source gives no such detail.
    for field in ("variant", "version"):
        value = finding.get(field)
        if value:
            shortened = re.sub(r"(?:[\s._-]+|(?<=\D))" + re.escape(value) + r"$", "", name, flags=re.IGNORECASE).strip(" ._-")
            if shortened:
                name = shortened
    # These suffixes identify model size or ordinary variants, not a publisher's
    # explicit family name. The result is provisional and never joins groups.
    while True:
        shortened = re.sub(
            r"[\s._-]+(?:base|instruct|chat|one|two|three|four|five|six|seven|eight|nine|ten|\d+(?:\.\d+)?[bmk])$",
            "", name, flags=re.IGNORECASE,
        ).strip(" ._-")
        if not shortened or shortened == name:
            break
        name = shortened
    product_key = str(product.product_key)
    group_key = "pulse-family:" + product_key
    configure_taxonomy({
        "reviewed_by": "pulse-classification",
        "subjects": [{"kind": "product", "key": product_key,
                      **({"model_kind_qualification": qualification} if qualification else {})}],
        "groups": [{
            "key": group_key,
            "name": name,
            "group_kind": "family",
            "include": [product_key],
            "evidence": {
                "method": "single_model_fallback",
                "finding_claim_id": str(claim.pk),
                "observed_name": finding.get("observed_name"),
                "version": finding.get("version"),
                "variant": finding.get("variant"),
            },
        }],
    })
    return ProductGroup.objects.get(group_key=group_key).pk


@transaction.atomic
def resolve_saved_release_finding(*, claim_id):
    """Resolve only a Product already accepted for this exact evidence.

    Unresolved is a durable domain outcome; a queue must not treat it as a
    failed classifier request or create a Product from a name alone.
    """
    from core.models import (
        EventDossierClaim,
        EventDossierReviewClaim,
        ProductReleaseDetail,
    )
    from core.product_release_dossiers import _read_pulse_packet
    from core.product_release_pipeline import canonical_dossier

    claim = EventDossierClaim.objects.select_related(
        "source_archive", "claim_kind_reference", "event_dossier_source"
    ).get(pk=claim_id)
    if (
        not claim.scope_key.startswith("pulse-finding-v1:")
        or not claim.extraction_version.startswith("pulse-classified-findings-v1:")
        or claim.claim_kind_reference.code not in {"release_report", "release_signal"}
        or claim.source_archive_id is None
    ):
        raise ValueError("Invalid saved finding anchor")
    packet = _read_pulse_packet(claim)
    dossier = canonical_dossier(claim.event_dossier_source.event_dossier_id)
    from core.models import EventDossier

    dossier = EventDossier.objects.select_for_update().get(pk=dossier.pk)
    if dossier.merged_into_id:
        raise ValueError("Dossier changed while resolving; retry")
    accepted = (
        EventDossierReviewClaim.objects.filter(
            review_id=dossier.current_review_id,
            claim__event_dossier_source__event_dossier=dossier,
            claim__scope_key=claim.scope_key,
            claim__source_archive=claim.source_archive,
            disposition="accepted",
        ).exists()
        if dossier.current_review_id
        and dossier.current_review.review_state == "confirmed"
        else False
    )
    detail = (
        ProductReleaseDetail.objects.select_related("product")
        .filter(review_id=dossier.current_review_id)
        .first()
        if accepted
        else None
    )
    product = detail.product if detail else None
    identity_claim = None
    identity_conflict = False
    # A previously verified Post/Product edge identifies this exact spelling;
    # it does not establish a release by itself. Never override a saved review.
    finding = packet["finding"]
    name, brand_id = finding.get("observed_name"), finding.get("brand_id")
    if detail and any(
        getattr(detail, reviewed) and finding.get(reported)
        and getattr(detail, reviewed).casefold() != finding[reported].casefold()
        for reviewed, reported in (("version_label", "version"), ("variant", "variant"))
    ):
        product = None
    identity_is_specific = bool(name) and all(
        not finding.get(field) or finding[field].casefold() in name.casefold()
        for field in ("version", "variant")
    )
    if (
        product is None
        and dossier.current_review_id is None
        and claim.event_dossier_source.post_id
        and identity_is_specific
        and name.casefold() in (claim.event_dossier_source.post.text or "").casefold()
    ):
        from django.db.models import F, Q

        from core.event_dossiers import add_claim
        from core.models import PostBrandProduct

        edges = PostBrandProduct.objects.select_for_update().filter(
            post_id=claim.event_dossier_source.post_id,
            observed_name__iexact=name,
        ).filter(Q(product__brand_id__isnull=True) | Q(product__brand_id=F("brand_id")))
        if brand_id:
            edges = edges.filter(brand_id=brand_id)
        candidates = list(edges.select_related("product")[:2])
        if len(candidates) == 1:
            linked = dossier.sources.get(post_id=claim.event_dossier_source.post_id)
            prior = EventDossierClaim.objects.filter(
                event_dossier_source=linked,
                scope_key="pulse-self-identity-v1:" + finding["finding_key"],
                extraction_version="pulse-product-identity-v1",
                source_archive_id=claim.source_archive_id,
            )
            prior_ids = set(prior.values_list("reported_product_id", flat=True).distinct()[:2])
            if not prior_ids or prior_ids == {candidates[0].product_id}:
                product = candidates[0].product
                identity_claim = prior.order_by("pk").first() if prior_ids else add_claim(
                    linked.pk,
                    claim_kind="release_context",
                    scope_key="pulse-self-identity-v1:" + finding["finding_key"],
                    assertion_text="Existing verified post/product association identifies the named offering",
                    source_excerpt=claim.source_excerpt,
                    source_locator=claim.source_locator,
                    extraction_version="pulse-product-identity-v1",
                    source_archive_id=claim.source_archive_id,
                    reported_brand_id=candidates[0].brand_id,
                    reported_product_id=product.pk,
                )
            else:
                identity_conflict = True
    created = False
    issuer = finding.get("issuer_evidence")
    post = (
        claim.event_dossier_source.post if claim.event_dossier_source.post_id else None
    )
    # A selected v2 publication already contains P1's release and publisher
    # judgment. Archived older packets keep their original qualification path.
    trusted_finding = False
    trusted_publisher = False
    attributed_name = (issuer.get("observed_name") if isinstance(issuer, dict) and (
        issuer.get("relation") == "attributed_party"
        or (issuer.get("relation") == "source_author" and (
            finding.get("publisher_profile")
            or (issuer.get("observed_name") and issuer["observed_name"] in issuer.get("source_excerpt", ""))
        ))
    ) else None)
    if post and name and packet["extraction_version"] == "compressed8-pulse-content-v2":
        from core.classified_product_releases import (
            read_publication_findings,
            selected_release_revision,
        )

        selected = selected_release_revision(post.pk)
        if selected and selected["revision_id"] == packet["revision_id"]:
            published = read_publication_findings(post.pk)
            trusted_finding = bool(published and any(
                row["anchor_claim_id"] == str(claim.pk) for row in published
            ))
    trusted_publisher = bool(trusted_finding and (brand_id or attributed_name))
    if trusted_publisher and not brand_id:
        from django.db import connection
        from django.utils.text import slugify

        from core.measurement_taxonomy import digest
        from core.models import Brand

        slug = slugify(attributed_name)[:48] or "publisher"
        lock_key = int(digest(["pulse-publisher-name-v1", slug])[:15], 16)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [lock_key])
            if not cursor.fetchone()[0]:
                raise ValueError("Publisher identity is busy; retry")
        matches = list(Brand.objects.filter(display_name__iexact=attributed_name, is_sentinel=False)[:2])
        if len(matches) > 1:
            trusted_publisher = False
        elif matches:
            brand_id = matches[0].pk
        else:
            brand_key = slug
            if Brand.objects.filter(pk=brand_key).exists():
                brand_key = f"{slug[:47]}-{digest([attributed_name.casefold()])[:16]}"
            brand, created_brand = Brand.objects.get_or_create(
                pk=brand_key, defaults={"display_name": attributed_name},
            )
            if not created_brand and (brand.is_sentinel or (brand.display_name or "").casefold() != attributed_name.casefold()):
                trusted_publisher = False
            else:
                brand_id = brand.pk
    if (
        product is None
        and not identity_conflict
        and dossier.current_review_id is None
        and post
        and (finding.get("novelty") == "new_release"
             or (trusted_publisher and finding.get("novelty") == "historical_release"))
        and (trusted_publisher or (
        identity_is_specific
        and isinstance(issuer, dict)
        and issuer.get("relation") == "source_author"
        and isinstance(issuer.get("source_excerpt"), str)
        and issuer["source_excerpt"] in (post.text or "")
        and name.casefold() in issuer["source_excerpt"].casefold()
        and not post.is_retweet
        and not post.is_quote
        and post.author_id
        and post.author.data_source_id == "x"
        ))
    ):
        import re

        from django.db import connection

        from core.measurement_taxonomy import digest, resolve_subject_id
        from core.models import (
            BrandAccount,
            MeasurementSubject,
            PostBrandProduct,
            PostSubjectAttribution,
            ProductReleaseDetail,
            ProductType,
        )
        from core.product_release_intake import _FUTURE, _NEGATED

        # Preserve the historical fallback for older saved generations. New
        # selected generations use P1's saved publisher decision directly.
        statement = issuer["source_excerpt"]
        prefix = post.text[: post.text.find(statement)]
        direct_launch = re.search(
            r"\b(?:we|i|our\s+team)\s+(?:(?:have|just|are|had)\s+)*"
            r"(?:release[ds]?|releasing|launch(?:ed|ing)?|introduc(?:e|ed|ing))\b"
            r"\s+(?:our\s+|the\s+|new\s+)*" + re.escape(name) + r"(?!\w)",
            statement,
            re.IGNORECASE,
        )
        lead = prefix + (statement[:direct_launch.start()] if direct_launch else "")
        quoted = bool(re.search(r'["“”]', lead)) or bool(
            re.search(r"(?:says?|said|wrote|quot(?:e|ed))\s*:?\s*$", lead, re.IGNORECASE)
        )
        owners = [brand_id] if trusted_publisher else list(
            BrandAccount.objects.filter(
                account_id=post.author_id,
                role_id="official",
                brand__is_sentinel=False,
            ).values_list("brand_id", flat=True)[:2]
        )
        category = finding.get("category")
        category_row = (
            ProductType.objects.filter(code=category).first() if category else None
        )
        if trusted_publisher or (
            direct_launch
            and not _FUTURE.search(statement)
            and not _NEGATED.search(statement)
            and not quoted
            and post.text.count(statement) == 1
            and len(owners) == 1
            and (not brand_id or brand_id == owners[0])
            and not finding.get("brand_candidate_id")
            and (category is None or category_row)
        ):
            owner = owners[0]
            lock_key = int(digest(["pulse-create-v1", owner, name.casefold()])[:15], 16)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [lock_key])
                if not cursor.fetchone()[0]:
                    raise ValueError("Product identity is busy; retry")
            # Existing source-backed exact names can resolve only when all
            # candidate records point to one Product. A display name alone is
            # a lead and cannot justify a match or creation.
            edge_ids = set(
                PostBrandProduct.objects.filter(
                    brand_id=owner,
                    observed_name__iexact=name,
                )
                .values_list("product_id", flat=True)
                .distinct()[:2]
            )
            named_ids = set(
                Product.objects.filter(
                    brand_id=owner,
                    display_name__iexact=name,
                ).values_list("pk", flat=True)[:2]
            )
            reviewed_ids = set(
                ProductReleaseDetail.objects.filter(
                    product__brand_id=owner,
                    observed_name__iexact=name,
                )
                .values_list("product__id", flat=True)
                .distinct()[:2]
            )
            attributed_ids = set(
                PostSubjectAttribution.objects.filter(
                    subject__subject_kind="product",
                    subject__product__brand_id=owner,
                    observed_name__iexact=name,
                )
                .values_list("subject__product__id", flat=True)
                .distinct()[:2]
            )
            candidate_ids = edge_ids | named_ids | reviewed_ids | attributed_ids
            if len(candidate_ids) == 1 and (trusted_publisher or edge_ids == candidate_ids):
                product = Product.objects.select_for_update().get(
                    pk=next(iter(candidate_ids))
                )
            elif not candidate_ids:
                product, created = find_or_create_product(
                    defaults={
                        "brand_id": owner,
                        "display_name": name,
                        "product_type": category_row,
                        "hf_type": "",
                    },
                    allow_new=True,
                )
            if product is not None:
                subject_id = resolve_subject_id("product", str(product.product_key))
                subject, _ = MeasurementSubject.objects.get_or_create(
                    pk=subject_id,
                    defaults={"subject_kind": "product", "product": product},
                )
                if (
                    subject.subject_kind != "product"
                    or subject.product_id != product.product_key
                ):
                    raise ValueError("Product subject identity conflict")
                from core.product_identity_locks import lock_product_evidence_names

                lock_product_evidence_names([name])
                PostBrandProduct.objects.get_or_create(
                    post=post,
                    brand_id=owner,
                    product=product,
                    defaults={
                        "observed_name": name,
                        "source_evidence": {
                            "finding_claim_id": str(claim.pk),
                            "issuer_claim": issuer["relation"],
                        },
                        "verification_policy_version": "pulse-product-identity-v1",
                    },
                )
                from core.event_dossiers import add_claim

                linked = dossier.sources.get(post_id=post.pk)
                identity_claim = add_claim(
                    linked.pk,
                    claim_kind="release_context",
                    scope_key="pulse-self-identity-v1:" + finding["finding_key"],
                    assertion_text=("Classifier identified the offering's publisher" if trusted_publisher
                                    else "Official source identifies its named offering"),
                    source_excerpt=issuer["source_excerpt"],
                    source_locator=issuer.get("source_locator"),
                    extraction_version="pulse-product-identity-v1",
                    source_archive_id=claim.source_archive_id,
                    reported_brand_id=owner,
                    reported_product_id=product.pk,
                )
    if product is not None and (identity_is_specific or trusted_publisher) and finding["novelty"] != "unresolved":
        from core.event_dossiers import add_claim

        linked = dossier.sources.get(
            post_id=claim.event_dossier_source.post_id,
            collection_observation_id=claim.event_dossier_source.collection_observation_id,
        )
        add_claim(
            linked.pk, claim_kind="release_context",
            scope_key=f"pulse-event-member-v1:{finding['finding_key']}:{_event_identity_hash(product, finding)}",
            assertion_text="Finding has an exact source-qualified Product and version identity",
            source_excerpt=claim.source_excerpt, source_locator=claim.source_locator,
            extraction_version="pulse-event-identity-v1", source_archive_id=claim.source_archive_id,
            reported_product_id=product.pk,
        )
        from core.product_identity_locks import lock_product_evidence_names
        from core.product_release_lineage_recovery import (
            WAKEUP_BUDGETS,
            register_lineage_wakeup,
        )

        lock_product_evidence_names([name])
        if _resolved_anchor_product(claim, dossier, packet=packet) == product.pk:
            register_lineage_wakeup(parent_claim_id=claim.pk, cause_review_id=dossier.current_review_id,
                                    budgets=WAKEUP_BUDGETS, only_if_dependents=True)
    if product is not None:
        if trusted_finding:
            _join_reported_successor_family(product, finding, claim)
        _ensure_model_family(product, finding, claim)
        if trusted_finding and finding.get("family_evidence"):
            _apply_reported_family_name(product, finding["family_evidence"], claim)
    return {
        "status": "created" if created else "matched" if product else "unresolved",
        "product_id": product.pk if product else None,
        "product_key": str(product.product_key) if product else None,
        "dossier_id": str(dossier.pk),
        "anchor_claim_id": str(claim.pk),
        "identity_claim_id": str(identity_claim.pk) if identity_claim else None,
    }


def _event_identity_hash(product, finding):
    from core.measurement_taxonomy import digest

    return digest([str(product.product_key), *(
        (finding.get(field) or "").casefold() for field in ("version", "variant")
    )])


def _resolved_anchor_product(anchor, dossier, *, packet=None):
    """Use only this finding's current review or its exact saved identity claim."""
    from core.models import (
        EventDossierClaim,
        EventDossierReviewClaim,
        ProductReleaseDetail,
    )

    reviewed_product = None
    if dossier.current_review_id:
        if dossier.current_review.review_state != "confirmed":
            return None
        detail = ProductReleaseDetail.objects.filter(review_id=dossier.current_review_id).values(
            "product__id", "version_label", "variant"
        ).first()
        if detail is None:
            return None
        from core.product_release_dossiers import _read_pulse_packet

        finding = (packet or _read_pulse_packet(anchor))["finding"]
        if any(
            detail[field] and finding.get(source)
            and detail[field].casefold() != finding[source].casefold()
            for field, source in (("version_label", "version"), ("variant", "variant"))
        ):
            return None
        reviewed_product = detail["product__id"]
        disposition = EventDossierReviewClaim.objects.filter(
            review_id=dossier.current_review_id, claim=anchor,
        ).values_list("disposition", flat=True).first()
        if disposition == "accepted":
            return reviewed_product
        if disposition is not None:
            return None
    key = anchor.scope_key.removeprefix("pulse-finding-v1:")
    ids = set(EventDossierClaim.objects.filter(
        event_dossier_source=anchor.event_dossier_source,
        source_archive_id=anchor.source_archive_id,
        scope_key="pulse-self-identity-v1:" + key,
        extraction_version="pulse-product-identity-v1", reported_product__isnull=False,
    ).values_list("reported_product_id", flat=True)[:2])
    result = next(iter(ids)) if len(ids) == 1 else None
    if dossier.current_review_id and result != reviewed_product:
        return None
    return result


def _qualified_anchor_name(anchor, dossier, *, packet):
    """Use the current accepted review's name, preserving the source packet."""
    from core.models import EventDossierReviewClaim, ProductReleaseDetail

    if (dossier.current_review_id and dossier.current_review.review_state == "confirmed"
            and EventDossierReviewClaim.objects.filter(review_id=dossier.current_review_id,
                                                       claim=anchor, disposition="accepted").exists()
            and _resolved_anchor_product(anchor, dossier, packet=packet)):
        name = ProductReleaseDetail.objects.filter(review_id=dossier.current_review_id).values_list("observed_name", flat=True).first()
        if name:
            return name
    return packet["finding"].get("observed_name")


@transaction.atomic
def reconcile_product_release_events(*, claim_id, candidate_limit, claim_limit, max_merges, max_seconds):
    """Bound reconciliation work and preserve the caller's stricter SQL timeouts."""
    from time import monotonic

    from django.db import connection

    if type(max_seconds) not in (int, float) or not 0 < max_seconds <= 3600:
        raise ValueError("Explicit reconciliation time budget required")
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
    result = _reconcile_product_release_events(
        claim_id=claim_id, candidate_limit=candidate_limit, claim_limit=claim_limit, max_merges=max_merges, deadline=deadline,
        statement_ms=statement_ms, lock_ms=lock_ms,
    )
    if result["status"] in {"matched", "merged", "conflict"} and not result.get("more_remaining"):
        remaining_merges = max_merges - len(result["merged_ids"])
        if remaining_merges > 0:
            compatible = _reconcile_missing_release_metadata(
                claim_id=claim_id, candidate_limit=candidate_limit, claim_limit=claim_limit,
                max_merges=remaining_merges, deadline=deadline,
            )
            if compatible["merged_ids"]:
                result = {**compatible, "merged_ids": result["merged_ids"] + compatible["merged_ids"]}
    if monotonic() >= deadline:
        raise TimeoutError("Release reconciliation time budget exceeded")
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)",
                       [statement_before, lock_before])
    return result


def _reconcile_product_release_events(*, claim_id, candidate_limit, claim_limit, max_merges, deadline, statement_ms, lock_ms):
    """Join compatible findings for one exact Product, keeping all source evidence."""
    from time import monotonic

    from django.db import connection
    from django.db.models import (
        Count,
        Exists,
        IntegerField,
        OuterRef,
        Q,
        Subquery,
        Value,
    )
    from django.db.models.functions import Coalesce, Concat, Substr

    from core.models import (
        EventDossier,
        EventDossierClaim,
        EventDossierIntakeDecision,
        EventDossierReviewClaim,
        EventDossierSource,
    )
    from core.product_release_dossiers import _read_pulse_packet
    from core.product_release_pipeline import canonical_dossier, merge_dossiers

    if any(type(value) is not int or value <= 0 for value in (candidate_limit, claim_limit, max_merges)):
        raise ValueError("Explicit positive reconciliation budgets required")
    # Match the existing graph mutation lock order before taking dossier locks.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_xact_lock(64382061)")
        if not cursor.fetchone()[0]:
            return {"status": "busy", "merged_ids": [], "more_remaining": True}
    original = EventDossierClaim.objects.select_related(
        "source_archive", "claim_kind_reference", "event_dossier_source__event_dossier"
    ).get(pk=claim_id)
    if original.claim_kind_reference.code not in {"release_report", "release_signal"}:
        raise ValueError("Invalid saved finding anchor")
    packet = _read_pulse_packet(original)
    current = canonical_dossier(original.event_dossier_source.event_dossier_id)
    anchor = EventDossierClaim.objects.select_related("source_archive", "event_dossier_source").filter(
        event_dossier_source__event_dossier=current,
        event_dossier_source__post_id=original.event_dossier_source.post_id,
        event_dossier_source__collection_observation_id=original.event_dossier_source.collection_observation_id,
        scope_key=original.scope_key, source_archive_id=original.source_archive_id,
    ).first()
    if anchor is None or packet["finding"]["novelty"] == "unresolved":
        return {"status": "unresolved", "merged_ids": [], "more_remaining": False}
    product_id = _resolved_anchor_product(anchor, current)
    if product_id is None:
        return {"status": "unresolved", "merged_ids": [], "more_remaining": False}
    product = Product.objects.only("product_key").get(pk=product_id)
    wanted_hash = _event_identity_hash(product, packet["finding"])
    anchors = EventDossierClaim.objects.filter(
        event_dossier_source__event_dossier_id=OuterRef("pk"),
        scope_key__startswith="pulse-finding-v1:",
        claim_kind_reference__code__in=("release_report", "release_signal"),
    )
    marker_base = Concat(Value("pulse-event-member-v1:"),
                         Substr(OuterRef("scope_key"), len("pulse-finding-v1:") + 1), Value(":"))
    marker = EventDossierClaim.objects.filter(
        event_dossier_source_id=OuterRef("event_dossier_source_id"),
        source_archive_id=OuterRef("source_archive_id"),
        scope_key=Concat(marker_base, Value(wanted_hash)),
        extraction_version="pulse-event-identity-v1", reported_product_id=product_id,
    )
    other_marker = EventDossierClaim.objects.filter(
        event_dossier_source_id=OuterRef("event_dossier_source_id"),
        source_archive_id=OuterRef("source_archive_id"), scope_key__startswith=marker_base,
        extraction_version="pulse-event-identity-v1",
    ).exclude(scope_key=Concat(marker_base, Value(wanted_hash)))
    bad_anchors = anchors.annotate(qualified=Exists(marker), conflicting=Exists(other_marker)).filter(
        Q(qualified=False) | Q(conflicting=True)
    )
    bad_review = EventDossierReviewClaim.objects.filter(
        review_id=OuterRef("current_review_id"), claim__event_dossier_source__event_dossier_id=OuterRef("pk"),
        claim__scope_key__startswith="pulse-finding-v1:", disposition__in=("rejected", "uncertain"),
    )
    latest = EventDossierIntakeDecision.objects.filter(event_dossier_id=OuterRef("pk")).order_by(
        "-recorded_at", "-pk"
    ).values("outcome")[:1]
    source_count = EventDossierSource.objects.filter(event_dossier_id=OuterRef("pk")).order_by().values(
        "event_dossier_id"
    ).annotate(total=Count("pk")).values("total")[:1]
    claim_count = EventDossierClaim.objects.filter(event_dossier_source__event_dossier_id=OuterRef("pk")).order_by().values(
        "event_dossier_source__event_dossier_id"
    ).annotate(total=Count("pk")).values("total")[:1]
    version = packet["finding"].get("version") or ""
    variant = packet["finding"].get("variant") or ""
    review_version = Q(current_review__product_release__version_label__iexact=version)
    review_variant = Q(current_review__product_release__variant__iexact=variant)
    if not version:
        review_version |= Q(current_review__product_release__version_label__isnull=True)
    if not variant:
        review_variant |= Q(current_review__product_release__variant__isnull=True)
    valid_review = (
        Q(current_review__isnull=True)
        | (Q(current_review__review_state="confirmed", current_review__product_release__product_id=product.product_key)
           & review_version & review_variant
           & Q(bad_review=False))
    )
    candidates = EventDossier.objects.filter(
        Q(sources__claims__reported_product_id=product_id,
          sources__claims__scope_key__startswith="pulse-event-member-v1:",
          sources__claims__scope_key__endswith=":" + wanted_hash,
          sources__claims__extraction_version="pulse-event-identity-v1")
        | Q(current_review__review_state="confirmed", current_review__product_release__product_id=product.product_key),
        merged_into__isnull=True,
    ).annotate(
        bad_anchors=Exists(bad_anchors), has_anchor=Exists(anchors), bad_review=Exists(bad_review),
        latest_outcome=Subquery(latest), source_count=Coalesce(Subquery(source_count), Value(0), output_field=IntegerField()),
        claim_count=Coalesce(Subquery(claim_count), Value(0), output_field=IntegerField()),
    ).filter(valid_review, bad_anchors=False).filter(Q(has_anchor=True) | Q(current_review__isnull=False)).filter(
        Q(latest_outcome__isnull=True) | ~Q(latest_outcome__in=("non_release", "scam", "superseded"))
    ).order_by("first_seen_at", "pk").distinct()
    if not candidates.filter(pk=current.pk).exists():
        return {"status": "conflict", "merged_ids": [], "more_remaining": False}
    oversized = candidates.filter(source_count__lte=1, current_review__isnull=True, claim_count__gt=claim_limit)
    if oversized.filter(pk=current.pk).exists():
        return {"status": "candidate_limit", "merged_ids": [], "more_remaining": True}
    oversized_exists = oversized.exists()
    candidates = candidates.filter(Q(source_count__gt=1) | Q(current_review__isnull=False) | Q(claim_count__lte=claim_limit))
    reviewed_ids = list(candidates.filter(current_review__isnull=False).values_list("pk", flat=True)[:2])
    if len(reviewed_ids) > 1:
        return {"status": "review_conflict", "merged_ids": [], "more_remaining": False}
    consolidated_ids = list(candidates.filter(source_count__gt=1).values_list("pk", flat=True)[:2])
    if len(consolidated_ids) > 1 or (reviewed_ids and consolidated_ids and reviewed_ids[0] != consolidated_ids[0]):
        return {"status": "conflict", "merged_ids": [], "more_remaining": False}
    ids = list(candidates.values_list("pk", flat=True)[:candidate_limit + 1])
    more_candidates = len(ids) > candidate_limit
    ids = ids[:candidate_limit]
    required_ids = {current.pk, *reviewed_ids, *consolidated_ids}
    if len(required_ids) > candidate_limit:
        return {"status": "candidate_limit", "merged_ids": [], "more_remaining": True}
    for required in required_ids:
        if required not in ids:
            replace = next((index for index in range(len(ids) - 1, -1, -1) if ids[index] not in required_ids), None)
            if replace is None:
                return {"status": "candidate_limit", "merged_ids": [], "more_remaining": True}
            ids[replace] = required
    dossiers = list(EventDossier.objects.select_for_update(of=("self",)).filter(pk__in=ids).select_related("current_review").order_by("pk"))
    valid_ids = set(candidates.filter(pk__in=ids).values_list("pk", flat=True))
    eligible = []
    for dossier in dossiers:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("Release reconciliation time budget exceeded")
        remaining_ms = max(1, int(remaining * 1000))
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)",
                           [f"{min(statement_ms or remaining_ms, remaining_ms)}ms", f"{min(lock_ms or remaining_ms, remaining_ms)}ms"])
        if dossier.pk not in valid_ids:
            continue
        anchors = EventDossierClaim.objects.filter(
            event_dossier_source__event_dossier=dossier,
            scope_key__startswith="pulse-finding-v1:",
            claim_kind_reference__code__in=("release_report", "release_signal"),
        )
        first_anchor = anchors.select_related("event_dossier_source").first()
        if first_anchor or dossier.current_review_id:
            eligible.append((dossier, first_anchor))
    reviewed = [(dossier, anchors) for dossier, anchors in eligible if dossier.current_review_id]
    if len(reviewed) > 1:
        return {"status": "review_conflict", "merged_ids": [], "more_remaining": False}
    if not any(dossier.pk == current.pk for dossier, _ in eligible):
        return {"status": "conflict", "merged_ids": [], "more_remaining": False}
    eligible.sort(key=lambda pair: (pair[0].first_seen_at, str(pair[0].pk)))
    if not eligible:
        return {"status": "unresolved", "merged_ids": [], "more_remaining": False}
    source_counts = dict(EventDossierSource.objects.filter(event_dossier_id__in=ids)
                         .values("event_dossier_id").annotate(total=Count("pk"))
                         .values_list("event_dossier_id", "total"))
    consolidated = [dossier for dossier, _ in eligible if source_counts.get(dossier.pk, 0) > 1]
    if len(consolidated) > 1 or (reviewed and consolidated and reviewed[0][0].pk != consolidated[0].pk):
        return {"status": "conflict", "merged_ids": [], "more_remaining": False}
    target = reviewed[0][0] if reviewed else consolidated[0] if consolidated else eligible[0][0]
    merged_ids = []
    pending = []
    conflicts = False
    for source, source_anchor in eligible:
        if source.pk == target.pk:
            continue
        post_id = source_anchor.event_dossier_source.post_id
        if post_id is None:
            conflicts = True
            continue
        if source.sources.exclude(post_id=post_id).exists():
            conflicts = True
            continue
        pending.append((source, post_id))
    for source, post_id in pending[:max_merges]:
        if EventDossierClaim.objects.filter(event_dossier_source__event_dossier=source).count() > claim_limit:
            return {"status": "candidate_limit", "merged_ids": merged_ids, "more_remaining": True,
                    "dossier_id": str(target.pk)}
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("Release reconciliation time budget exceeded")
        remaining_ms = max(1, int(remaining * 1000))
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)",
                           [f"{min(statement_ms or remaining_ms, remaining_ms)}ms", f"{min(lock_ms or remaining_ms, remaining_ms)}ms"])
        try:
            merge_dossiers(source.pk, target.pk, actor="pulse-product-identity-v1",
                           reason="Same source-qualified Product and compatible version and variant",
                           guard_unreviewed_post=post_id,
                           guard_target_review_id=target.current_review_id)
        except ValueError as error:
            if str(error) != "source dossier is not safe for automatic reconciliation":
                raise
            conflicts = True
            continue
        merged_ids.append(str(source.pk))
    return {"status": "candidate_limit" if oversized_exists else "merged" if merged_ids else "conflict" if conflicts else "matched",
            "dossier_id": str(target.pk), "merged_ids": merged_ids,
            "more_remaining": oversized_exists or len(pending) > max_merges or (more_candidates and bool(merged_ids))}


def _reconcile_missing_release_metadata(*, claim_id, candidate_limit, claim_limit, max_merges, deadline):
    """Merge the same named Product when a source omitted version metadata.

    Conflicting explicit values, multiple consolidated dossiers, reviews and
    over-budget candidate sets are left untouched. Exact archive-backed claims
    and the existing graph lock are required for every participating dossier.
    """
    from time import monotonic

    from core.models import EventDossier, EventDossierClaim, EventDossierIntakeDecision
    from core.product_release_dossiers import _read_pulse_packet
    from core.product_release_pipeline import canonical_dossier, merge_dossiers

    empty = {"status": "matched", "merged_ids": [], "more_remaining": False}
    original = EventDossierClaim.objects.select_related(
        "source_archive", "event_dossier_source__event_dossier"
    ).get(pk=claim_id)
    current = canonical_dossier(original.event_dossier_source.event_dossier_id)
    current_anchor = EventDossierClaim.objects.select_related("source_archive", "event_dossier_source").filter(
        event_dossier_source__event_dossier=current,
        event_dossier_source__post_id=original.event_dossier_source.post_id,
        scope_key=original.scope_key, source_archive_id=original.source_archive_id,
    ).first()
    if current_anchor is None or current.current_review_id:
        return empty
    packet = _read_pulse_packet(current_anchor)
    product_id = _resolved_anchor_product(current_anchor, current, packet=packet)
    if not product_id or not packet["finding"].get("observed_name"):
        return empty
    product = Product.objects.only("product_key").get(pk=product_id)
    target_name = packet["finding"]["observed_name"].casefold()
    ids = list(EventDossier.objects.filter(
        merged_into__isnull=True, current_review__isnull=True,
        sources__claims__reported_product_id=product_id,
        sources__claims__scope_key__startswith="pulse-event-member-v1:",
        sources__claims__extraction_version="pulse-event-identity-v1",
    ).order_by("first_seen_at", "pk").values_list("pk", flat=True).distinct()[:candidate_limit + 1])
    if len(ids) > candidate_limit or current.pk not in ids:
        return empty
    dossiers = list(EventDossier.objects.select_for_update(of=("self",)).filter(pk__in=ids).order_by("first_seen_at", "pk"))
    eligible = []
    for dossier in dossiers:
        if monotonic() >= deadline:
            raise TimeoutError("Release reconciliation time budget exceeded")
        if dossier.current_review_id or dossier.merged_into_id:
            continue
        latest = EventDossierIntakeDecision.objects.filter(event_dossier=dossier).order_by("-recorded_at", "-pk").first()
        if latest and latest.outcome in {"non_release", "scam", "superseded"}:
            continue
        claims = list(EventDossierClaim.objects.filter(event_dossier_source__event_dossier=dossier)
                      .select_related("source_archive", "event_dossier_source", "claim_kind_reference")[:claim_limit + 1])
        if len(claims) > claim_limit:
            return empty
        anchors = [claim for claim in claims if claim.scope_key.startswith("pulse-finding-v1:")
                   and claim.claim_kind_reference.code in {"release_report", "release_signal"}]
        if not anchors:
            continue
        values = []
        for anchor in anchors:
            saved = _read_pulse_packet(anchor)
            finding = saved["finding"]
            if (finding.get("novelty") == "unresolved"
                    or (finding.get("observed_name") or "").casefold() != target_name
                    or _resolved_anchor_product(anchor, dossier, packet=saved) != product_id):
                break
            expected = f"pulse-event-member-v1:{finding['finding_key']}:{_event_identity_hash(product, finding)}"
            if not any(c.scope_key == expected and c.reported_product_id == product_id
                       and c.source_archive_id == anchor.source_archive_id
                       and c.event_dossier_source_id == anchor.event_dossier_source_id
                       and c.extraction_version == "pulse-event-identity-v1" for c in claims):
                break
            values.append(tuple((finding.get(field) or "").casefold() for field in ("version", "variant")))
        else:
            sources = list(dossier.sources.all()[:candidate_limit + 1])
            if len(sources) > candidate_limit:
                return empty
            eligible.append((dossier, sources, values))
    if len(eligible) < 2 or not any(item[0].pk == current.pk for item in eligible):
        return empty
    versions = [value for _, _, values in eligible for value in values]
    if any(len({value[i] for value in versions if value[i]}) > 1 for i in (0, 1)):
        return empty
    if not any(any(value[i] for value in versions) and any(not value[i] for value in versions) for i in (0, 1)):
        return empty
    consolidated = [item for item in eligible if len(item[1]) > 1]
    if len(consolidated) > 1:
        return empty
    target = consolidated[0] if consolidated else eligible[0]
    merged = []
    for dossier, sources, _ in eligible:
        if dossier.pk == target[0].pk:
            continue
        if len(merged) >= max_merges:
            break
        if len(sources) != 1 or not sources[0].post_id:
            continue
        try:
            merge_dossiers(dossier.pk, target[0].pk, actor="pulse-product-identity-v1",
                           reason="Same source-qualified Product with compatible missing version metadata",
                           guard_unreviewed_post=sources[0].post_id, guard_target_review_id=None)
        except ValueError as error:
            if str(error) != "source dossier is not safe for automatic reconciliation":
                raise
            continue
        merged.append(str(dossier.pk))
    return {"status": "merged" if merged else "matched", "dossier_id": str(target[0].pk),
            "merged_ids": merged, "more_remaining": len(eligible) - 1 > len(merged)}


def _family_subjects(keys, groups):
    """Reuse pinned model-kind evidence when a family has an untyped HF model."""
    from core.model_kind_qualification import qualify_model_kind

    keys = set(keys)
    products = list(Product.objects.filter(product_key__in=keys).select_related("product_type"))
    if len(products) != len(keys):
        return None
    snapshots = [group.rule_taxonomy_version.snapshot.get("products", {}) for group in groups]
    subjects = []
    for product in products:
        key = str(product.product_key)
        subject = {"kind": "product", "key": key}
        if product.product_type_id is None:
            qualification = next((snapshot.get(key, {}).get("model_kind_qualification")
                                  for snapshot in snapshots
                                  if snapshot.get(key, {}).get("model_kind_qualification")), None)
            qualification = qualification or qualify_model_kind(product)
            if not qualification:
                return None
            subject["model_kind_qualification"] = qualification
        subjects.append(subject)
    return sorted(subjects, key=lambda item: item["key"])


def _join_reported_successor_family(product, finding, claim):
    """Join an explicitly reported same-publisher successor to its predecessor's family."""
    import re
    from os.path import commonprefix

    from django.db import connection
    from django.db.models import F

    from core.measurement_taxonomy import configure_taxonomy
    from core.models import ProductGroupMembership

    relations = [item for item in finding.get("lineage_evidence", [])
                 if item.get("relationship_kind") == "new_version"]
    if len(relations) != 1 or not product.brand_id:
        return None
    relation = relations[0]
    parents = list(Product.objects.filter(brand_id=product.brand_id,
                                          display_name__iexact=relation["parent_observed_name"])
                   .exclude(pk=product.pk).order_by("pk")[:2])
    if len(parents) != 1:
        return None
    parent = parents[0]
    if not product.product_type_id or not parent.product_type_id:
        return None
    if product.product_type.code not in {"model-llm", "model-other"} or parent.product_type.code not in {"model-llm", "model-other"}:
        return None
    # Serialize family graph writes before locking the participating Products.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_xact_lock(64382064)")
        if not cursor.fetchone()[0]:
            raise ValueError("Family identity is busy; retry")
    list(Product.objects.select_for_update(of=("self",)).filter(pk__in=[product.pk, parent.pk]).order_by("pk"))

    def families(subject):
        return list(ProductGroupMembership.objects.filter(
            product=subject, group__group_kind="family", membership_status="included",
            taxonomy_version_id=F("group__rule_taxonomy_version_id"),
        ).select_related("group__rule_taxonomy_version")[:2])

    parent_memberships = families(parent)
    if not parent_memberships:
        _ensure_model_family(parent, {"observed_name": parent.display_name, "version": None, "variant": None}, claim)
        parent_memberships = families(parent)
    child_memberships = families(product)
    if len(parent_memberships) != 1 or len(child_memberships) > 1:
        return None
    parent_group = parent_memberships[0].group
    child_group = child_memberships[0].group if child_memberships else None
    if child_group and child_group.pk == parent_group.pk:
        return parent_group.pk
    groups = [parent_group] + ([child_group] if child_group else [])
    if any(group.rule_kind != "manual" for group in groups):
        return None

    def group_data(group):
        return group.rule_taxonomy_version.snapshot.get("groups", {}).get(group.group_key, {})

    def is_explicit(group):
        return group_data(group).get("evidence", {}).get("method") not in {
            "single_model_fallback", "same_line_new_version",
        }

    if child_group and is_explicit(parent_group) and is_explicit(child_group) and parent_group.name != child_group.name:
        return None
    target = child_group if child_group and is_explicit(child_group) and not is_explicit(parent_group) else parent_group
    retired = next((group for group in groups if group.pk != target.pk), None)
    memberships = list(ProductGroupMembership.objects.filter(
        group__in=groups, taxonomy_version_id=F("group__rule_taxonomy_version_id"),
    ).values_list("group_id", "product_id", "membership_status")[:1001])
    if len(memberships) > 1000:
        return None
    included = {str(key) for _, key, status in memberships if status == "included"}
    excluded = {str(key) for _, key, status in memberships if status == "excluded"}
    included.add(str(product.product_key))
    if included & excluded:
        return None
    name = target.name
    if not is_explicit(target):
        parent_name, child_name = parent.display_name or "", product.display_name or ""
        shared = commonprefix([parent_name, child_name])
        if (shared and shared[-1].isalnum() and len(shared) < min(len(parent_name), len(child_name))
                and parent_name[len(shared)].isalnum() and child_name[len(shared)].isalnum()):
            shared = re.sub(r"[\w]+$", "", shared)
        prefix = shared.rstrip(" ._-/")
        if prefix and len(prefix) < min(len(parent_name), len(child_name)):
            name = prefix
    relation_evidence = {"finding_claim_id": str(claim.pk), "parent_name": parent.display_name,
                         "child_name": product.display_name, "source_excerpt": relation["source_excerpt"]}
    if is_explicit(target):
        evidence = {**group_data(target).get("evidence", {}), "successor_evidence": relation_evidence}
    else:
        evidence = {"method": "same_line_new_version", **relation_evidence}
    target_spec = {**group_data(target), "key": target.group_key, "name": name, "group_kind": "family",
                   "include": sorted(included), "exclude": sorted(excluded), "evidence": evidence}
    specs = [target_spec]
    if retired:
        specs.append({**group_data(retired), "key": retired.group_key, "name": retired.name,
                      "group_kind": "family", "include": [], "exclude": [],
                      "evidence": {"method": "merged_into_family", "target_key": target.group_key,
                                   "finding_claim_id": str(claim.pk)}})
    subjects = _family_subjects(included | excluded, groups)
    if subjects is None:
        return None
    configure_taxonomy({"reviewed_by": "pulse-classification", "subjects": subjects, "groups": specs})
    return target.pk


def _apply_reported_family_name(product, family, claim):
    """Apply a source-confirmed name to a stable family or an existing named line."""
    from django.db import connection
    from django.db.models import F

    from core.measurement_taxonomy import configure_taxonomy
    from core.models import ProductGroup, ProductGroupMembership

    if not product.brand_id or not family.get("name"):
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_xact_lock(64382064)")
        if not cursor.fetchone()[0]:
            raise ValueError("Family identity is busy; retry")
    current = list(ProductGroupMembership.objects.filter(
        product=product, group__group_kind="family", membership_status="included",
        taxonomy_version_id=F("group__rule_taxonomy_version_id"),
    ).select_related("group__rule_taxonomy_version")[:2])
    if len(current) != 1:
        return None
    previous = current[0].group
    candidates = list(ProductGroup.objects.filter(
        group_kind="family", name__iexact=family["name"],
        productgroupmembership__product__brand_id=product.brand_id,
        productgroupmembership__membership_status="included",
        productgroupmembership__taxonomy_version_id=F("rule_taxonomy_version_id"),
    ).select_related("rule_taxonomy_version").distinct()[:101])
    if len(candidates) > 100:
        return None
    named = [group for group in candidates if group.pk != previous.pk and
             group.rule_taxonomy_version.snapshot.get("groups", {}).get(group.group_key, {})
             .get("evidence", {}).get("method") not in {"single_model_fallback", "same_line_new_version"}]
    previous_evidence = previous.rule_taxonomy_version.snapshot.get("groups", {}).get(previous.group_key, {}).get("evidence", {})
    if len(named) > 1 or (named and previous_evidence.get("method") not in {"single_model_fallback", "same_line_new_version"}):
        return None
    target = named[0] if named else previous
    groups = [previous] if target.pk == previous.pk else [previous, target]
    if any(group.rule_kind != "manual" for group in groups):
        return None
    list(ProductGroup.objects.select_for_update().filter(pk__in=[g.pk for g in groups]).order_by("pk"))

    def group_data(group):
        return group.rule_taxonomy_version.snapshot.get("groups", {}).get(group.group_key, {})

    prior = group_data(previous).get("evidence", {})
    if (prior.get("method") not in {"single_model_fallback", "same_line_new_version"}
            and previous.name.casefold() != family["name"].casefold()):
        return None
    rows = list(ProductGroupMembership.objects.filter(
        group__in=groups, taxonomy_version_id=F("group__rule_taxonomy_version_id"),
    ).values_list("product_id", "membership_status")[:1001])
    if len(rows) > 1000:
        return None
    included = {str(key) for key, status in rows if status == "included"}
    excluded = {str(key) for key, status in rows if status == "excluded"}
    if included & excluded:
        return None
    evidence = {"method": "publisher_named", "finding_claim_id": str(claim.pk),
                "source_excerpt": family["source_excerpt"], "source_locator": family["source_locator"]}
    data = group_data(target)
    if (target.pk == previous.pk and target.name == family["name"]
            and data.get("evidence", {}).get("method") == "publisher_named"):
        return target.pk
    specs = [{**data, "key": target.group_key, "name": family["name"], "group_kind": "family",
              "include": sorted(included), "exclude": sorted(excluded), "evidence": evidence}]
    if target.pk != previous.pk:
        specs.append({**group_data(previous), "key": previous.group_key, "name": previous.name,
                      "group_kind": "family", "include": [], "exclude": [],
                      "evidence": {"method": "merged_into_family", "target_key": target.group_key,
                                   "finding_claim_id": str(claim.pk)}})
    subjects = _family_subjects(included | excluded, groups)
    if subjects is None:
        return None
    configure_taxonomy({"reviewed_by": "pulse-classification", "subjects": subjects, "groups": specs})
    return target.pk
