"""Connect selected classification history to durable Pulse evidence.

The existing current judgments prove that a complete, possibly empty release
answer was published. Source claims store findings; queue rows only track work.
"""

from __future__ import annotations

import hashlib
import json
import logging
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
from core.product_release_findings import SCHEMA, cited_publisher_handle, finding_identity

OUTPUT_MANIFEST_SCHEMA = "pulse-classified-release-output-v1"
TARGETED_RELEASE_REVISION = "model-release-extraction-v2"


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


def _release_date_supported(precision, value, excerpt, *, offering_name=None):
    import calendar
    from datetime import date

    if precision not in {"day", "month", "year"} or not isinstance(value, str):
        return False
    if isinstance(offering_name, str) and offering_name:
        excerpt = excerpt.replace(offering_name, " " * len(offering_name))
    try:
        parsed = date.fromisoformat(value if precision == "day" else value + ("-01" if precision == "month" else "-01-01"))
    except ValueError:
        return False
    if re.search(r"(?<![\w])" + re.escape(value) + r"(?![\w])", excerpt):
        return True
    names = {calendar.month_name[parsed.month], calendar.month_abbr[parsed.month]}
    month = "(?:" + "|".join(re.escape(name) for name in names) + r")\.?"
    if precision == "day":
        patterns = [rf"\b{month}\s+0?{parsed.day},?\s+{parsed.year}\b",
                    rf"\b0?{parsed.day}\s+{month}\s+{parsed.year}\b",
                    rf"{parsed.year}年0?{parsed.month}月0?{parsed.day}日"]
    elif precision == "month":
        patterns = [rf"\b{month}\s+{parsed.year}\b", rf"{parsed.year}年0?{parsed.month}月"]
    else:
        patterns = [rf"\b{parsed.year}\b", rf"{parsed.year}年"]
    return any(re.search(pattern, excerpt, re.IGNORECASE) for pattern in patterns)


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


def selected_release_matches(post_id, tweet):
    from x_monitor.attribution import (
        _canonical_reviewed_affiliations, _two_role_fingerprint, _validated_tracked_brand_catalog_snapshot,
    )

    publication = _selected_release_publication(post_id)
    if publication is None:
        return False
    from core.models import TargetedExtractionState

    if TargetedExtractionState.objects.filter(
        post_id=post_id, role="model_release_extraction", prompt_version=TARGETED_RELEASE_REVISION,
        status__in=["pending", "failed"],
    ).exists():
        return False
    catalog = _validated_tracked_brand_catalog_snapshot({
        "revision": str(tweet.get("_classification_catalog_revision") or ""),
        "brands": tweet.get("tracked_brand_catalog"),
    })
    if publication[2][0] == TARGETED_RELEASE_REVISION:
        fingerprint = _targeted_release_fingerprint(Post.objects.get(pk=post_id), tweet, catalog)
    else:
        states = list(PostBrandClassificationState.objects.filter(post_id=post_id).select_related("selected_final_judgment"))
        brands = set(tweet.get("brand_ids") or [])
        complete = _complete_release_publication(post_id)
        if (complete is not None and complete[0]["revision_id"] == publication[0]["revision_id"]
                and states and {state.brand_id for state in states} == brands):
            affiliations = _canonical_reviewed_affiliations(tweet.get("affiliations"))
            base = {key: tweet.get(key) for key in ("text", "english_translation", "context", "source_language", "author_handle")}
            matched = True
            for state in states:
                final = state.selected_final_judgment
                source = {**base, "brand_id": state.brand_id,
                          "affiliations": [row for row in affiliations if row["brand_id"] == state.brand_id]}
                source_hash = hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False,
                                                         separators=(",", ":")).encode()).hexdigest()
                if (final is None or final.prompt_version not in {row[2] for row in COMPRESSED_CLASSIFIER_SUPPORTED_REVISIONS}
                        or not isinstance(final.changes_json, dict)
                        or final.changes_json.get("feed_input_fingerprint") != source_hash):
                    matched = False
                    break
            if matched:
                return True
        fingerprint = _two_role_fingerprint(tweet, tracked_catalog=catalog)
    return publication[0]["content_fingerprint"] == fingerprint


def _targeted_release_fingerprint(post, tweet, catalog):
    from core.targeted_extraction import _source_urls
    from x_monitor.attribution import _two_role_fingerprint

    return hashlib.sha256(_encoded({
        "feed_input": _two_role_fingerprint(tweet, tracked_catalog={}),
        "author_handle": tweet.get("author_handle"),
        "author_profile": _material_release_profile(tweet.get("author_profile_evidence")),
        "author_affiliations": tweet.get("release_author_affiliations", tweet.get("affiliations", [])),
        "source_urls": sorted(_source_urls(post)),
        "source_evidence_hash": _release_source_hash(post),
    }).encode()).hexdigest()


def _material_release_profile(profile):
    if not isinstance(profile, dict):
        return profile
    return {**profile, "sources": [
        {key: value for key, value in source.items() if key != "observed_at"}
        for source in profile.get("sources", []) if isinstance(source, dict)
    ]}


def _release_source_hash(post):
    parent = Post.objects.filter(pk=post.in_reply_to_id).values_list("text", flat=True).first()
    return hashlib.sha256(_encoded({"text": post.text or "", "quote": post.quoted_text or "",
                                    "parent_id": post.in_reply_to_id, "parent": parent or "",
                                    "is_retweet": post.is_retweet}).encode()).hexdigest()


def classifier_owns_release_extraction(post_id):
    """A selected combined judgment owns release processing even while its evidence is incomplete."""
    from core.models import TargetedExtractionState

    if TargetedExtractionState.objects.filter(
        post_id=post_id, role="model_release_extraction", prompt_version=TARGETED_RELEASE_REVISION,
        status__in=["pending", "failed"],
    ).exists():
        return True
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
    targeted = partial.prompt_version == TARGETED_RELEASE_REVISION
    if targeted:
        revisions = (TARGETED_RELEASE_REVISION,) * 3
    fingerprint = partial.input_context_fingerprint
    expected_metadata = {"release_output", "brand_ids", "selection", "source_evidence_hash"} if targeted else {"release_output", "brand_ids"}
    if (not isinstance(metadata, dict) or set(metadata) != expected_metadata
            or metadata["brand_ids"] != brands or partial.brand_id not in brands
            or revisions is None or partial.provider_role != (
                "targeted-release" if targeted else "classifier-release"
            )
            or partial.contract_version != "pulse-release-only-v1"
            or partial.taxonomy_version != "pulse-release-only-v1"
            or partial.canonical_judgment != {} or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
            or (targeted and (not isinstance(metadata["selection"], str) or not 1 <= len(metadata["selection"]) <= 128))):
        return complete
    producer = "targeted-release-v1" if targeted else "pulse-release-only-v1"
    revision_payload = {"post_id": post_id, "fingerprint": fingerprint, "producer": producer}
    if targeted:
        revision_payload["selection"] = metadata["selection"]
    expected_revision = hashlib.sha256(_encoded(revision_payload).encode()).hexdigest()
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


def _named_launch_publishers(name, excerpt):
    return {(m.group(1), m.group(2).casefold()) for m in re.finditer(
        rf"(?:^|(?<=[.!?\n]))[ \t]*([\w.-]+(?: [A-Z][\w.-]*){{0,4}}) "
        rf"\(@([A-Za-z0-9_]{{1,15}})\) (?:released|launched|introduced|announced) "
        rf"{re.escape(name)}(?![\w-])", excerpt,
    )}


def _cited_launch_profile(issuer, name, handle, profile):
    from core.release_publisher_recovery import _announcement_title

    if (not isinstance(profile, dict) or not name or not handle
            or (profile.get("handle") or "").casefold() != handle.casefold()
            or not _announcement_title(issuer.get("source_excerpt"), name)):
        return None
    display = profile.get("display_name")
    if isinstance(display, str) and display.strip() and any(
        re.fullmatch(r"account:[0-9]+:display_name", source.get("id", ""))
        and source.get("text") == display for source in profile.get("sources", ())
    ):
        return display.strip()
    return None


def replay_saved_publisher(finding, post):
    """Project a missing issuer from this selected packet and its saved source observation."""
    name = finding.get("observed_name")
    if not post or not name or post.is_retweet:
        return finding
    locator = _saved_locator(post)
    if not locator:
        return finding
    issuer = finding.get("issuer_evidence") or {}
    if issuer.get("observed_name"):
        return finding
    witnesses = [a["source_excerpt"] for a in finding.get("assertions", ())
                 if a.get("source_locator") == locator and a.get("source_excerpt") in (post.text or "")]
    subjects = {(publisher, handle, quote) for quote in witnesses
                for publisher, handle in _named_launch_publishers(name, quote)}
    if len({(pub, handle) for pub, handle, _ in subjects}) == 1:
        pub, handle, quote = min(subjects)
        if handle != (post.author_handle or "").casefold():
            return {**finding, "issuer_evidence": {"relation": "attributed_party", "observed_name": pub,
                    "observed_handle": handle, "source_excerpt": quote, "source_locator": locator}}
    if (subjects or issuer.get("relation") != "source_author" or issuer.get("source_excerpt") not in witnesses
            or issuer.get("source_locator") != locator or not post.author_id or not post.author_name
            or not str(post.native_author_id or "").isdecimal()
            or str(post.native_author_id) != str(post.author.author_id)):
        return finding
    profile = {"handle": post.author_handle, "display_name": post.author_name, "domains": [],
               "sources": [{"id": f"account:{post.native_author_id}:display_name", "text": post.author_name}]}
    if post.author_description:
        profile["sources"].append({"id": f"post:{post.pk}:author_description", "text": post.author_description[:2048]})
    if _cited_launch_profile(issuer, name, post.author_handle, profile):
        return {**finding, "issuer_evidence": {**issuer, "observed_name": post.author_name},
                "publisher_profile": profile}
    return finding


def _targeted_lineage(relations, child, passages, limits):
    """Recover a short citation only from one explicit, directional source sentence."""
    from core.product_release_lineage import _supports_relation, name_pattern, quoted_parent_spelling

    supported = []
    if not child or not isinstance(relations, list) or len(relations) > limits.max_assertions:
        return supported
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        parent = relation.get("parent_observed_name")
        quote = relation.get("source_excerpt")
        kind = relation.get("relationship_kind")
        if (kind not in ("new_version", "finetune", "adapter", "quantized", "merge")
                or not isinstance(parent, str) or not parent.strip() or len(parent) > limits.max_text_chars
                or not isinstance(quote, str) or not quote.strip()):
            continue
        matches = [key for key, text in passages.items() if quote in text]
        if len(matches) != 1:
            continue
        locator = matches[0]
        if not re.search(name_pattern(parent), quote):
            # Prefer the publisher's literal name, including an independently verified alias.
            parent = quoted_parent_spelling(parent, quote) or parent
        if not re.search(name_pattern(child), quote) or not re.search(name_pattern(parent), quote):
            sentences = re.split(r"(?<=[.!?])\s+|[\r\n]+", passages[locator])
            candidates = [line for line in sentences if quote in line and child in line and parent in line
                          and _supports_relation({**relation, "parent_observed_name": parent, "source_excerpt": line}, child)]
            if len(candidates) != 1:
                continue
            quote = candidates[0]
        item = {"relationship_kind": kind, "parent_observed_name": parent,
                "source_locator": locator, "source_excerpt": quote}
        if len(quote) <= limits.max_text_chars and item not in supported:
            supported.append(item)
    return supported


def targeted_release_findings(*, post, tweet, records):
    """Convert source-quoted release extraction into the shared finding contract."""
    from core.product_release_findings import parse_release_findings
    from x_monitor.compressed_classifier import RELEASE_LIMITS, sources
    from x_monitor.compressed_classifier_prompts import CHANNEL_MEANINGS

    passages = {row["id"]: row["text"] for row in sources({
        "source_text": tweet["text"], "english_translation": tweet.get("english_translation"),
        "context": tweet.get("context") or [],
    }) if row["id"] != "translation"}
    raw = []
    owners = []
    for record in records:
        excerpt = record.get("source_excerpt")
        if not isinstance(excerpt, str) or not excerpt.strip():
            raise ValueError("targeted_release_excerpt_missing")
        name = record.get("model_name") or None
        if name is not None and (not isinstance(name, str) or name not in excerpt):
            raise ValueError("targeted_release_name_not_in_excerpt")
        matches = [key for key, value in passages.items() if excerpt in value]
        if len(matches) != 1:
            raise ValueError("targeted_release_excerpt_ambiguous")
        locator = matches[0]
        relation = record.get("publisher_relation")
        organization = record.get("organization_name")
        if name and locator == "post":
            subjects = _named_launch_publishers(name, excerpt)
            if len(subjects) == 1:
                named_party, handle = subjects.pop()
                if handle != str(getattr(post, "author_handle", "") or "").lower().lstrip("@"):
                    relation, organization = "attributed_party", named_party
            elif subjects:
                relation = None
        issuer = None
        if relation == "source_author" and locator == "post":
            issuer = {
                "relation": relation, "source_locator": locator,
                "source_excerpt": excerpt, "observed_name": None,
            }
        elif (relation == "attributed_party" and isinstance(organization, str)
              and organization.strip() and organization in excerpt):
            issuer = {
                "relation": relation, "source_locator": locator,
                "source_excerpt": excerpt, "observed_name": organization,
            }
        categories = record.get("categories") or []
        if not isinstance(categories, list):
            raise ValueError("targeted_release_categories_invalid")
        category = categories[0] if len(categories) == 1 else None
        novelty = record.get("novelty")
        if novelty not in {"new_release", "historical_release", "availability_update", "unresolved"}:
            novelty = "unresolved"
        precision = record.get("release_precision")
        value = record.get("release_value")
        effective = {"precision": "unknown", "value": None, "timezone": None}
        if _release_date_supported(precision, value, excerpt, offering_name=name):
            effective = {"precision": precision, "value": value, "timezone": None}
        family_name = record.get("family_name")
        family_excerpt = record.get("family_excerpt")
        family = None
        if family_name is not None or family_excerpt is not None:
            family_matches = [key for key, value in passages.items()
                              if isinstance(family_excerpt, str) and family_excerpt in value]
            if len(family_matches) != 1:
                raise ValueError("targeted_release_family_excerpt_ambiguous")
            family = {"name": family_name, "source_locator": family_matches[0],
                      "source_excerpt": family_excerpt}
        reported_lineage = record.get("lineage_evidence")
        lineage = _targeted_lineage(reported_lineage, name, passages, RELEASE_LIMITS)
        if reported_lineage and (not isinstance(reported_lineage, list) or len(lineage) < len(reported_lineage)):
            logging.getLogger(__name__).info("Unresolved optional lineage on release post %s", post.pk)
        claim_kind = record.get("claim_kind")
        channel = record.get("access_channel")
        if claim_kind != "availability" or channel not in CHANNEL_MEANINGS:
            claim_kind, channel = "release_report", None
        assertions = [{
            "claim_kind": claim_kind, "assertion_text": excerpt,
            "source_excerpt": excerpt, "source_locator": locator,
            "access_channel": channel, "effective": effective,
        }]
        milestones = record.get("milestones") or []
        if not isinstance(milestones, list):
            raise ValueError("targeted_release_milestones_invalid")
        for milestone in milestones:
            if not isinstance(milestone, dict):
                raise ValueError("targeted_release_milestone_invalid")
            quote = milestone.get("source_excerpt")
            locations = [key for key, text in passages.items()
                         if isinstance(quote, str) and quote.strip() and quote in text]
            if len(locations) != 1:
                raise ValueError("targeted_release_milestone_excerpt_ambiguous")
            # An explicitly named different owner is evidence for that owner,
            # not for the offering in this finding.
            possessive = re.search(r"\b([A-Z][\w.-]*)[’']s\b", quote)
            named_offering = bool(name and re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", quote, re.IGNORECASE))
            if possessive and name and not named_offering:
                continue
            if not named_offering and re.search(r"\b(?:for|of)\s+[A-Z][\w.-]*", quote):
                continue
            other_prefix = re.match(r"^([A-Z][\w.-]*)\s+(?:API|weights?)\b", quote.strip())
            if name and not named_offering and other_prefix and other_prefix.group(1) not in {"The", "Its"}:
                continue
            milestone_channel = milestone.get("access_channel")
            if milestone.get("claim_kind") != "availability" or milestone_channel not in CHANNEL_MEANINGS:
                raise ValueError("targeted_release_milestone_invalid")
            milestone_precision = milestone.get("release_precision")
            milestone_value = milestone.get("release_value")
            milestone_effective = {"precision": "unknown", "value": None, "timezone": None}
            if _release_date_supported(milestone_precision, milestone_value, quote, offering_name=name):
                milestone_effective = {"precision": milestone_precision, "value": milestone_value, "timezone": None}
            assertion = {"claim_kind": "availability", "assertion_text": quote,
                         "source_excerpt": quote, "source_locator": locations[0],
                         "access_channel": milestone_channel, "effective": milestone_effective}
            if assertion not in assertions:
                assertions.append(assertion)
        raw.append({
            "observed_name": name, "version": record.get("version") or None,
            "variant": None, "novelty": novelty, "category": category,
            "issuer_evidence": issuer, "family_evidence": family, "lineage_evidence": lineage,
            "assertions": assertions,
        })
        owners.append(record.get("brand_id"))
    findings = parse_release_findings(
        {"schema": SCHEMA, "findings": raw},
        source={"kind": "post", "id": str(post.pk)}, passages=passages,
        allowed_channels=tuple(CHANNEL_MEANINGS), limits=RELEASE_LIMITS,
    )
    for finding, owner, record in zip(findings, owners, records):
        repository = record.get("candidate_repo_id")
        if isinstance(repository, str) and repository:
            from core.product_verification import source_repo_evidence

            if source_repo_evidence(post, repository)["exact_hf_repo_link"]:
                finding["candidate_repo_id"] = repository
        issuer = finding["issuer_evidence"]
        if issuer is None:
            continue
        if issuer["relation"] == "source_author":
            if post.is_retweet:
                finding["issuer_evidence"] = None
                continue
            if isinstance(owner, str) and any(row.get("brand_id") == owner and row.get("role") in {"official", "staff"}
                   and row.get("reviewed") is True
                   for row in tweet.get("release_author_affiliations", tweet.get("affiliations", []))):
                finding["brand_id"] = owner
            else:
                profile = tweet.get("author_profile_evidence")
                name = record.get("organization_name")
                if not name:
                    name = _cited_launch_profile(issuer, finding["observed_name"], getattr(post, "author_handle", None), profile)
                if (isinstance(profile, dict) and isinstance(name, str)
                        and name.strip().casefold() == str(profile.get("display_name") or "").strip().casefold()
                        and any(name.casefold() in str(source.get("text") or "").casefold()
                                for source in profile.get("sources", []))):
                    issuer["observed_name"] = profile["display_name"].strip()
                    finding["publisher_profile"] = profile
        else:
            handle = cited_publisher_handle(issuer["observed_name"], issuer["source_excerpt"])
            if handle:
                issuer["observed_handle"] = handle
            if not isinstance(owner, str):
                continue
            entry = next((row for row in tweet.get("tracked_brand_catalog", [])
                          if row.get("brand_id") == owner), {})
            issuer_name = issuer["observed_name"].casefold()
            if issuer_name in {str(value).casefold() for value in
                               [entry.get("display_name"), *entry.get("aliases", [])] if value}:
                finding["brand_id"] = owner
    return findings


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
    enqueue_saved_post(post.pk, evidence_ready=True)
    return outcome


def read_publication_findings(post_id, *, allow_pending=False):
    """Read saved findings only; None means pending and an empty tuple is final."""
    publication = _selected_release_publication(post_id)
    if publication is None:
        from core import models
        from core.product_release_intake import SourceRecord, TextEvidence, detect
        from django.db.models import F
        from x_monitor.attribution import _TWO_ROLE_ALLOWED_REVISION_TRIPLETS

        two_role_revisions = {row[2] for row in _TWO_ROLE_ALLOWED_REVISION_TRIPLETS
                              if row[2].startswith("stage1-two-role-merge-0731-v")}

        if not allow_pending and models.TargetedExtractionState.objects.filter(
            post_id=post_id, role="model_release_extraction", prompt_version=TARGETED_RELEASE_REVISION,
            status__in=["pending", "failed"],
        ).exists():
            return None
        completed = models.ProductReleaseDetectionState.objects.filter(
            post_id=post_id, completed_at__isnull=False, completed_at__gte=F("requested_at"),
        ).exists()
        state = models.PostEnrichmentState.objects.select_related("post").filter(
            post_id=post_id, classification_status="succeeded",
        ).first() if completed else None
        if state is not None:
            brands = set(PostBrand.objects.filter(post_id=post_id).values_list("brand_id", flat=True))
            rows = list(PostBrandClassificationState.objects.filter(post_id=post_id).values_list(
                "brand_id", "outcome", "prompt_version", "selected_final_judgment__content_judgment__canonical_judgment",
            ))
            texts = [TextEvidence(locator="post", kind="raw", text=state.post.text or "")]
            if state.post.quoted_text:
                texts.append(TextEvidence(locator="quote", kind="quote", text=state.post.quoted_text))
            parent = Post.objects.filter(pk=state.post.in_reply_to_id).values_list("text", flat=True).first()
            if parent:
                texts.append(TextEvidence(locator="parent", kind="quote", text=parent))
            if (brands and {row[0] for row in rows} == brands
                    and all(row[1] in {"classified", "context_missing"} and row[2] in two_role_revisions
                            and isinstance(row[3], dict) and "releases_updates" not in row[3].get("post_types", []) for row in rows)
                    and not models.PostBrandSignal.objects.filter(post_id=post_id, post_type_id="releases_updates").exists()
                    and detect(SourceRecord(namespace="x", source_id=str(post_id), texts=tuple(texts))) is None):
                return ()
        return None
    if not allow_pending:
        from core.models import TargetedExtractionState

        pending = TargetedExtractionState.objects.filter(
            post_id=post_id, role="model_release_extraction", prompt_version=TARGETED_RELEASE_REVISION,
            status__in=["pending", "failed"],
        ).first()
        if pending is not None:
            publication_time = PostBrandClassificationJudgment.objects.filter(
                post_id=post_id, revision_id=publication[0]["revision_id"], stage="content",
            ).values_list("created_at", flat=True).first()
            if publication_time is None:
                times = PostBrandClassificationState.objects.filter(post_id=post_id).values_list(
                    "selected_final_judgment__created_at", flat=True,
                )
                publication_time = max((value for value in times if value is not None), default=None)
            if publication_time is None or pending.updated_at >= publication_time:
                return None
    revision, manifest, _ = publication
    from core.product_release_dossiers import read_saved_release_findings

    findings = read_saved_release_findings(
        source={"kind": "post", "id": post_id}, revision_id=revision["revision_id"],
    )
    if _output_manifest([row["finding"] for row in findings]) != manifest:
        raise ValueError("classification_release_output_mismatch")
    if not allow_pending and publication[2][0] == TARGETED_RELEASE_REVISION:
        post = Post.objects.get(pk=post_id)
        saved_hash = PostBrandClassificationJudgment.objects.filter(
            post_id=post_id, revision_id=revision["revision_id"], stage="content",
        ).values_list("changes_json__source_evidence_hash", flat=True).first()
        if saved_hash != _release_source_hash(post):
            return None
        parent = Post.objects.filter(pk=post.in_reply_to_id).values_list("text", flat=True).first()
        passages = [post.text or "", post.quoted_text or "", parent or ""]
        if any(not any(assertion.get("source_excerpt", "") in passage for passage in passages)
               for row in findings for assertion in row["finding"].get("assertions", [])):
            return None
    return findings


def persist_release_only(*, post_id, tweet, result, model, run_id, preserve_selected=False,
                         targeted=False):
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
        fingerprint = (_targeted_release_fingerprint(claim.post, tweet, catalog) if targeted
                       else _two_role_fingerprint(tweet, tracked_catalog=catalog))
        if preserve_selected:
            publication = _selected_release_publication(post_id)
            if publication is None:
                raise ValueError("classification_release_generation_incomplete")
            saved = read_publication_findings(post_id, allow_pending=True)
            if saved is None:
                raise ValueError("classification_release_generation_incomplete")
            fingerprint = publication[0]["content_fingerprint"]
            source = PostBrandClassificationJudgment.objects.filter(
                post_id=post_id, revision_id=publication[0]["revision_id"], stage="content",
            ).first()
            if source is not None:
                model = source.model
            else:
                source_models = set(PostBrandClassificationState.objects.filter(
                    post_id=post_id, brand_id__in=brands,
                ).values_list("selected_final_judgment__content_judgment__model", flat=True))
                if len(source_models) != 1 or None in source_models:
                    raise ValueError("classification_release_source_model_ambiguous")
                model = source_models.pop()
            findings = [row["finding"] for row in saved]
            manifest = _output_manifest(findings)
            targeted = publication[2][0] == TARGETED_RELEASE_REVISION
        else:
            findings, manifest = prepare_publication_findings(post=claim.post, tweet=tweet, result=result)
        producer = "targeted-release-v1" if targeted else "pulse-release-only-v1"
        prompt_version = (
            publication[2][0] if preserve_selected
            else TARGETED_RELEASE_REVISION if targeted else COMPRESSED_CLASSIFIER_REVISIONS[0]
        )
        provider_role = "targeted-release" if targeted else "classifier-release"
        revision_payload = {"post_id": post_id, "fingerprint": fingerprint, "producer": producer}
        if targeted:
            revision_payload["selection"] = str(run_id)[:128]
        revision = hashlib.sha256(_encoded(revision_payload).encode()).hexdigest()
        metadata = {"release_output": manifest, "brand_ids": brands}
        if targeted:
            metadata["selection"] = str(run_id)[:128]
            metadata["source_evidence_hash"] = _release_source_hash(claim.post)
        judgment, created = PostBrandClassificationJudgment.objects.get_or_create(
            post_id=post_id, brand_id=brands[0], revision_id=revision, stage="content",
            defaults={"canonical_judgment": {}, "contract_version": "pulse-release-only-v1",
                      "taxonomy_version": "pulse-release-only-v1",
                      "prompt_version": prompt_version, "model": model,
                      "provider_role": provider_role, "input_context_fingerprint": fingerprint,
                      "selector_version": "pulse-release-only-v1", "validation_state": "release_only",
                      "changes_json": metadata},
        )
        if not created and (judgment.changes_json != metadata or judgment.input_context_fingerprint != fingerprint
                            or judgment.validation_state != "release_only" or judgment.provider_role != provider_role
                            or judgment.selector_version != "pulse-release-only-v1"
                            or judgment.prompt_version != prompt_version
                            or judgment.contract_version != "pulse-release-only-v1"
                            or judgment.taxonomy_version != "pulse-release-only-v1" or judgment.canonical_judgment != {}):
            raise ValueError("classification_release_only_generation_conflict")
        persist_classified_release_findings(
            source={"kind": "post", "id": post_id}, revision_id=revision, content_fingerprint=fingerprint,
            findings=findings, extraction_version=prompt_version,
        )
        if targeted:
            from core.models import TargetedExtractionState

            TargetedExtractionState.objects.filter(
                post_id=post_id, role="model_release_extraction", prompt_version=TARGETED_RELEASE_REVISION,
            ).update(status="succeeded", completed_at=timezone.now(), result_hash=None)
        enqueue_saved_post(post_id, evidence_ready=True)
        return True
