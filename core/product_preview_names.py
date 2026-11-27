"""Publisher-disclosed preview names. Keep the dated disclosure and original post edges."""

import re

from django.db.models import F, OuterRef, Q, Subquery
from django.utils import timezone

from core.models import (
    BrandAccount,
    EventDossierClaim,
    EventDossierIntakeDecision,
    Product,
)

POLICY = "pulse-publisher-preview-v1"
_SCOPE = POLICY + ":"
# A declaration in the publisher's own opening list. A question, quotation,
# alternative, or reference elsewhere in the post cannot introduce a claim.
_PREVIEW = re.compile(
    r"^[-*•] Previously previewed as (?P<name>\w+(?:[.\-]\w+)*(?: \w+(?:[.\-]\w+)*){0,5})"
    r"(?:, running [^?\n]+)?\.?$",
    re.IGNORECASE,
)


def register_publisher_preview(post, product, anchor, finding):
    from core.event_dossiers import add_claim
    from core.measurement_attribution import record_attribution
    from core.measurement_taxonomy import configure_taxonomy, resolve_subject_id
    from core.product_identity_locks import lock_product_evidence_names

    if (
        not product.display_name
        or not post
        or not post.created_at
        or not post.author_id
        or post.is_quote
        or post.is_retweet
        or finding["novelty"] != "new_release"
        or not product.brand_id
        or (finding.get("issuer_evidence") or {}).get("relation") != "source_author"
    ):
        return
    lines = (post.text or "").splitlines()
    if (
        not lines
        or lines[0].strip().casefold()
        != f"introducing {product.display_name}".casefold()
    ):
        return
    declarations = []
    offset = 0
    for line in (post.text or "").splitlines(keepends=True):
        body = line.rstrip("\r\n")
        if offset and body and not body.startswith(("- ", "* ", "• ")):
            break
        match = _PREVIEW.fullmatch(body)
        if match:
            declarations.append((match["name"], offset + match.start("name"), body))
        offset += len(line)
    if len(declarations) != 1:
        return
    name, start, excerpt = declarations[0]
    if len(name) > 80 or name.casefold() == product.display_name.casefold():
        return
    if re.search(
        r"\b(?:or|and|possibly|maybe|not|never|might|could)\b", name, re.IGNORECASE
    ):
        return
    if not BrandAccount.objects.filter(
        account_id=post.author_id,
        role_id="official",
        brand_id=product.brand_id,
        account__data_source_id="x",
    ).exists():
        return
    lock_product_evidence_names([name])
    claim = add_claim(
        anchor.event_dossier_source_id,
        claim_kind="release_context",
        scope_key=_SCOPE + name.casefold(),
        assertion_text=f"{product.display_name} was previewed as {name}",
        source_excerpt=excerpt,
        source_locator=f"https://x.com/i/status/{post.pk}",
        source_archive_id=anchor.source_archive_id,
        extraction_version=POLICY,
        reported_brand_id=product.brand_id,
        reported_product_id=product.pk,
        effective_precision="datetime",
        effective_at=post.created_at,
    )
    subject = {"kind": "product", "key": str(product.product_key)}
    if not product.product_type_id:
        from core.model_kind_qualification import qualify_model_kind

        qualification = qualify_model_kind(product)
        if not qualification:
            return
        subject["model_kind_qualification"] = qualification
    version = configure_taxonomy({"reviewed_by": POLICY, "subjects": [subject]})
    record_attribution(
        version,
        post,
        resolve_subject_id("product", product.product_key),
        observed_name=name,
        policy_version=POLICY,
        evidence={
            "reviewed_by": POLICY,
            "claim_id": str(claim.pk),
            "span_start": start,
            "span_end": start + len(name),
        },
    )


def _disclosures(brand_id, as_of, strict):
    active = EventDossierIntakeDecision.objects.filter(
        event_dossier_id=OuterRef("event_dossier_source__event_dossier_id")
    )
    if strict:
        active = active.filter(recorded_at__lte=as_of)
    claims = (
        EventDossierClaim.objects.filter(
            extraction_version=POLICY,
            reported_product__brand_id=F("reported_brand_id"),
            effective_at__lte=as_of,
            event_dossier_source__event_dossier__merged_into_id__isnull=True,
        )
        .annotate(
            last_decision=Subquery(
                active.order_by("-recorded_at", "-pk").values("outcome")[:1]
            )
        )
        .filter(
            Q(last_decision__isnull=True)
            | ~Q(last_decision__in=("scam", "non_release", "superseded"))
        )
    )
    if brand_id is not None:
        claims = claims.filter(reported_brand_id=brand_id)
    if strict:
        claims = claims.filter(
            recorded_at__lte=as_of, event_dossier_source__linked_at__lte=as_of
        )
    return claims.filter(
        Q(event_dossier_source__event_dossier__current_review__isnull=True)
        | Q(
            review_decisions__review=F(
                "event_dossier_source__event_dossier__current_review"
            ),
            review_decisions__review__review_state="confirmed",
            review_decisions__disposition="accepted",
        )
    )


def preview_targets(brand_id, name, *, as_of=None, strict=False):
    """Multiple publisher identifications deliberately remain ambiguous."""
    return set(
        _disclosures(brand_id, as_of or timezone.now(), strict)
        .filter(scope_key=_SCOPE + name.casefold())
        .values_list("reported_product_id", flat=True)
        .distinct()[:2]
    )


def resolve_preview_candidates(owner, name, candidates):
    # Only a provisional Product with this literal name can be superseded by
    # a disclosure. A different already identified repository remains a conflict.
    targets = preview_targets(owner, name)
    if len(targets) != 1:
        return candidates | targets
    others = candidates - targets
    if (
        others
        and Product.objects.filter(pk__in=others)
        .exclude(repo_id__isnull=True, brand_id=owner, display_name__iexact=name)
        .exists()
    ):
        return candidates | targets
    return targets


def chart_preview_names(product, cutoff, strict):
    rows = _disclosures(product.brand_id, cutoff, strict)
    names = (
        rows.filter(reported_product=product)
        .values_list("scope_key", flat=True)
        .distinct()
    )
    competing = rows.exclude(reported_product=product).values("scope_key")
    return [v.removeprefix(_SCOPE) for v in names.exclude(scope_key__in=competing)]


def preview_redirects(provisional, *, cutoff, strict):
    """Batch a bounded page of provisional catalog names without moving their source records."""
    names = {
        pk: (brand, _SCOPE + name.casefold())
        for pk, brand, name in provisional
        if brand and name
    }
    pairs = set(names.values())
    if not pairs:
        return {}
    rows = (
        _disclosures(None, cutoff, strict)
        .filter(
            reported_brand_id__in={brand for brand, _ in pairs},
            scope_key__in={scope for _, scope in pairs},
        )
        .values_list("reported_brand_id", "scope_key", "reported_product_id")
        .distinct()
    )
    matches = {}
    for brand, scope, target in rows:
        if (brand, scope) in pairs:
            matches.setdefault((brand, scope), set()).add(target)
    return {
        pk: next(iter(matches[key]))
        for pk, key in names.items()
        if len(matches.get(key, ())) == 1
    }
