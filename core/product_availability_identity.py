"""Identify an undated model upload from its publisher's already saved X post."""

import re

from core.classified_product_releases import read_publication_findings
from core.models import BrandAccount, EventDossier, Post

# A present-tense publisher upload and its consecutive list of model IDs.
# The list ends at a heading, prose, or a blank line.
_UPLOAD_LIST = re.compile(
    r"(?:(?:we are|i am) (?:currently )?|currently )uploading (?:the following|these) models(?: to [\w. /-]+)?:",
    re.IGNORECASE,
)
_LIST_ITEM = re.compile(r"(?:[-*•]\s+)?([\w][\w.-]*)")


def names_uploaded_model(text, finding):
    issuer = finding.get("issuer_evidence") or {}
    lines = (text or "").strip().splitlines()
    if not lines or not _UPLOAD_LIST.fullmatch(lines[0].strip()):
        return False
    # P1 can quote the list introduction or the individual item. Both must
    # come from this list; a sibling item's quote cannot identify the model.
    allowed_excerpts = {lines[0].strip(), finding["observed_name"]}
    if (
        issuer.get("relation") != "source_author"
        or issuer.get("source_excerpt") not in allowed_excerpts
        or not any(
            a["claim_kind"] == "availability"
            and a["source_excerpt"] in allowed_excerpts
            for a in finding["assertions"]
        )
    ):
        return False
    for line in lines[1:]:
        item = _LIST_ITEM.fullmatch(line.strip())
        if item is None:
            break
        if item[1].casefold() == finding["observed_name"].casefold():
            return True
    return False


def _official_upload(post, finding):
    brand = finding.get("brand_id")
    if (
        not brand
        or not post.author_id
        or post.author.data_source_id != "x"
        or post.is_retweet
        or post.is_quote
        or post.quoted_status_id_id
        or finding.get("novelty") != "availability_update"
        or finding.get("brand_candidate_id")
        or not names_uploaded_model(post.text, finding)
    ):
        return False
    owners = list(
        BrandAccount.objects.filter(
            account_id=post.author_id,
            role_id="official",
            brand__is_sentinel=False,
        ).values_list("brand_id", flat=True)[:2]
    )
    return owners == [brand]


def _inactive(dossier):
    latest = (
        dossier.intake_decisions.order_by("-recorded_at", "-pk")
        .values_list("outcome", flat=True)
        .first()
    )
    return latest in {"scam", "non_release", "superseded"}


def saved_upload_source(post, finding, claim_id, dossier):
    """Return (existing Brand, issuer evidence, original claim ID) or no match."""
    if (
        finding["novelty"] not in {"availability_update", "historical_release"}
        or finding["category"] not in {"model-llm", "model-other"}
        or finding.get("brand_candidate_id")
        or post.is_retweet
    ):
        return None
    if _inactive(dossier):
        return None
    if finding.get("issuer_evidence"):
        if _official_upload(post, finding):
            return finding["brand_id"], finding["issuer_evidence"], str(claim_id)
        return None
    if not post.created_at or not (
        post.is_quote or post.quoted_status_id_id or post.in_reply_to_id
    ):
        return None

    # The classifier bound each assertion to its original post URL. Recover
    # by primary key even when only the retained quote text and URL survived.
    from monitor.editorial.chatter_discovery import post_id

    name = finding["observed_name"]
    cited = {}
    for assertion in finding["assertions"]:
        if assertion["source_excerpt"].strip().casefold() != name.casefold():
            continue
        try:
            original_id = post_id(assertion["source_locator"])
        except (ValueError, TypeError):
            continue
        if original_id != post.pk:
            cited[original_id] = assertion["source_locator"]
    if len(cited) != 1:
        return None
    original_id, locator = next(iter(cited.items()))
    links = {pk for pk in (post.quoted_status_id_id, post.in_reply_to_id) if pk}
    if links and original_id not in links:
        return None
    original = (
        Post.objects.select_related("author")
        .filter(pk=original_id, created_at__lte=post.created_at)
        .first()
    )
    if original is None or (not links and post.quoted_text != original.text):
        return None

    matches = [
        row
        for row in read_publication_findings(original_id) or ()
        if row["finding"]["observed_name"]
        and row["finding"]["observed_name"].casefold() == name.casefold()
        and row["finding"]["category"] == finding["category"]
        and (
            not finding.get("brand_id")
            or row["finding"]["brand_id"] == finding["brand_id"]
        )
        and all(
            not row["finding"].get(key)
            or row["finding"][key].casefold() in name.casefold()
            for key in ("version", "variant")
        )
        and (row["finding"].get("issuer_evidence") or {}).get("source_locator")
        == locator
    ]
    if len(matches) != 1:
        return None
    (row,) = matches
    original_dossier = EventDossier.objects.filter(
        pk=row["dossier_id"],
        current_review_id__isnull=True,
        merged_into__isnull=True,
    ).first()
    if not original_dossier or not _official_upload(original, row["finding"]):
        return None
    if _inactive(original_dossier):
        return None
    return (
        row["finding"]["brand_id"],
        row["finding"]["issuer_evidence"],
        row["anchor_claim_id"],
    )
