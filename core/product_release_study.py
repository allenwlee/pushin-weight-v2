"""Apply explicit, source-checked study assessments through canonical writers.

This is an offline review import, not an LLM or collection service. Source
assertions reference stored Posts or collected documents. Research notes retain
the reviewer's material separately; they are not physical HTTP receipts.
"""

from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID

from django.db import transaction

from core import models
from core.collection_capture import archive_document
from core.discussion_windows import capture_windows, discussion_packet, read_window
from core.event_dossiers import (
    ProductReleaseInput,
    _digest,
    add_claim,
    attach_source,
    create_dossier,
    identity_key,
)
from core.product_release_pipeline import merge_dossiers, persist_source, review_release
from core.product_release_report import release_rows, significance
from core.product_release_sources import stored_observations, stored_posts

METHOD = "product-release-study-v1"
KINDS = {
    "announcement",
    "source_stated_release",
    "availability",
    "first_observed_usage",
    "rumor",
    "release_context",
}


def _object(value, required, optional=()):
    if (
        not isinstance(value, dict)
        or not set(required) <= value.keys()
        or value.keys() - set(required) - set(optional)
    ):
        raise ValueError("Assessment has missing or unknown fields")


def _text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200000:
        raise ValueError("Assessment text must be nonempty and bounded")
    return value


def _instant(value):
    result = datetime.fromisoformat(_text(value))
    if result.tzinfo is None:
        raise ValueError("Assessment timestamps require a timezone")
    return result


def _document(doc):
    _object(doc, ("url", "text", "observed_at"))
    parsed = urlsplit(_text(doc["url"]))
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Research evidence needs a public HTTP source URL")
    _text(doc["text"])
    _instant(doc["observed_at"])


def _source_reference(item):
    if ("post_id" in item) == ("observation_id" in item):
        raise ValueError("Evidence must reference exactly one Post or observation")
    if "post_id" in item:
        return ("post", _text(item["post_id"]))
    if type(item["observation_id"]) is not int or item["observation_id"] <= 0:
        raise ValueError("Observation reference must be a positive integer")
    return ("observation", item["observation_id"])


def _attach(event, source):
    return attach_source(
        event.pk, post_id=source.post_id, observation_id=source.observation_id
    )


def validate_assessment(packet):
    _object(packet, ("schema", "actor", "assessed_at", "cases"))
    if (
        packet["schema"] != METHOD
        or not isinstance(packet["cases"], list)
        or not 1 <= len(packet["cases"]) <= 60
    ):
        raise ValueError("Unsupported or unbounded study packet")
    _text(packet["actor"])
    cutoff = _instant(packet["assessed_at"])
    keys = set()
    for case in packet["cases"]:
        _object(
            case,
            ("case_id", "identity", "name", "reason", "evidence", "significance"),
            (
                "brand_id",
                "product_key",
                "issuer_company_id",
                "version_label",
                "state",
                "availability",
                "verification",
                "research",
                "observed_publisher",
            ),
        )
        for field in ("case_id", "identity", "name", "reason"):
            _text(case[field])
        if case["identity"] in keys:
            raise ValueError("Duplicate release identity in study")
        keys.add(case["identity"])
        if case.get("state", "provisional") not in {"provisional", "confirmed"}:
            raise ValueError("Unsupported study review state")
        if case.get("availability", "unknown") not in {"unknown", "available"}:
            raise ValueError("Unsupported availability state")
        if case.get("product_key"):
            UUID(case["product_key"])
        rank = case["significance"]
        _object(rank, ("product_kind", "lineage", "change", "reason"))
        _text(rank["reason"])
        significance(**{k: rank[k] for k in ("product_kind", "lineage", "change")})
        evidence = case["evidence"]
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 40:
            raise ValueError("Each release needs 1..40 source assertions")
        for item in evidence:
            _object(
                item,
                ("excerpt", "kind"),
                (
                    "post_id",
                    "observation_id",
                    "effective_at",
                    "effective_date",
                    "access_channel",
                    "exclusive_source",
                ),
            )
            _source_reference(item)
            _text(item["excerpt"])
            if item["kind"] not in KINDS or (
                item.get("effective_at") and item.get("effective_date")
            ):
                raise ValueError("Unsupported or conflicting milestone")
            if "exclusive_source" in item and not isinstance(
                item["exclusive_source"], bool
            ):
                raise ValueError("exclusive_source must be boolean")
            if item.get("effective_at") and _instant(item["effective_at"]) > cutoff:
                raise ValueError("A study milestone cannot postdate its cutoff")
            if (
                item.get("effective_date")
                and date.fromisoformat(item["effective_date"]) > cutoff.date()
            ):
                raise ValueError("A study milestone cannot postdate its cutoff")
        research = case.get("research", [])
        if not isinstance(research, list) or len(research) > 40:
            raise ValueError("Research evidence must be a bounded list")
        for doc in research:
            _document(doc)
            if _instant(doc["observed_at"]) > cutoff:
                raise ValueError("Research evidence exceeds the review cutoff")
        if case.get("observed_publisher"):
            publisher = case["observed_publisher"]
            _object(publisher, ("post_id", "name"), ("handle",))
            _text(publisher["post_id"])
            _text(publisher["name"])
            if publisher.get("handle"):
                _text(publisher["handle"])
            if publisher["post_id"] not in {item.get("post_id") for item in evidence}:
                raise ValueError("Observed publisher must reference selected evidence")
        if case.get("verification"):
            _object(
                case["verification"],
                ("entity", "ownership"),
                ("post_id", "observation_id"),
            )
            _source_reference(case["verification"])
            for name in ("entity", "ownership"):
                _document(case["verification"][name])
                if _instant(case["verification"][name]["observed_at"]) > cutoff:
                    raise ValueError("Verification evidence exceeds the review cutoff")
        if case.get("state") == "confirmed" and not case.get("verification"):
            raise ValueError("Confirmation requires explicit publisher verification")
    return packet


def _archive(packet):
    import json

    return archive_document(
        json.dumps(
            packet, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode(),
        encoding="selected-json-canonical-v1",
        capture_kind="release_study_assessment",
    )


@transaction.atomic
def apply_case(case, *, actor, assessed_at):
    references = {_source_reference(item) for item in case["evidence"]}
    post_ids = [v for k, v in references if k == "post"]
    sources = {
        ("post", s.post_id): s for s in (stored_posts(post_ids) if post_ids else [])
    }
    sources.update(
        {
            ("observation", s.observation_id): s
            for s in stored_observations(
                [v for k, v in references if k == "observation"]
            )
        }
    )
    if set(sources) != references:
        raise ValueError("Selected source evidence is unavailable")
    post_texts = dict(
        models.Post.objects.filter(pk__in=post_ids).values_list("pk", "text")
    )
    for item in case["evidence"]:
        source = sources[_source_reference(item)]
        if source.observation_id and source.stored_at > _instant(assessed_at):
            raise ValueError("Source capture exceeds assessment cutoff")
        texts = (
            [post_texts[source.post_id] or ""]
            if source.post_id
            else [t.text for t in source.record.texts]
        )
        if not any(item["excerpt"] in text for text in texts):
            raise ValueError(
                "Study excerpt does not occur in its stored source evidence"
            )
    event = create_dossier(
        event_kind="product_release",
        identity_key=identity_key("product-release-identity-v1", case["identity"]),
        first_seen_at=min(s.stored_at for s in sources.values()),
    )
    archive = _archive(
        {"schema": METHOD, "actor": actor, "assessed_at": assessed_at, "case": case}
    )
    detected, claims = [], []
    for source in sources.values():
        result = persist_source(source)
        detected.append(result)
        source_items = [
            e
            for e in case["evidence"]
            if _source_reference(e) == ("post", source.post_id)
            or _source_reference(e) == ("observation", source.observation_id)
        ]
        if all(e.get("exclusive_source", False) for e in source_items):
            # A family-wide announcement attaches to each product independently.
            # Merge only a still-provisional, single-source intake container.
            for previous in result["dossier_ids"]:
                old = models.EventDossier.objects.get(pk=previous)
                if (
                    old.pk == event.pk
                    or old.current_review_id
                    or old.sources.count() != 1
                ):
                    continue
                if old.sources.filter(
                    claims__claim_kind_reference__code="release_report"
                ).exists():
                    continue
                merge_dossiers(
                    old.pk,
                    event.pk,
                    actor=actor,
                    reason="Source-checked atomic release: " + case["identity"],
                )
        linked = _attach(event, source)
        for item in source_items:
            instant = (
                _instant(item["effective_at"]) if item.get("effective_at") else None
            )
            day = (
                date.fromisoformat(item["effective_date"])
                if item.get("effective_date")
                else None
            )
            claim = add_claim(
                linked.pk,
                claim_kind=item["kind"],
                scope_key=case["identity"],
                assertion_text=item["excerpt"],
                source_excerpt=item["excerpt"],
                source_locator=source.source_url,
                source_archive_id=source.archive_id,
                extraction_version=METHOD,
                effective_precision="datetime"
                if instant
                else "day"
                if day
                else "unknown",
                effective_at=instant,
                effective_date=day,
                access_channel=item.get("access_channel"),
            )
            claims.append(claim)
    # This claim archives the assessor's interpretation, including references and
    # significance reasons. It does not add another purported source observation.
    context = add_claim(
        linked.pk,
        claim_kind="release_context",
        scope_key=case["identity"],
        assertion_text=case["reason"]
        + " Significance: "
        + case["significance"]["reason"],
        source_excerpt=source_items[0]["excerpt"],
        source_locator=source.source_url,
        source_archive_id=archive.pk,
        extraction_version=METHOD,
    )
    claims.append(context)
    publisher = case.get("observed_publisher")
    if publisher:
        from core.targeted_extraction import _organization_candidate

        post = models.Post.objects.get(pk=publisher["post_id"])
        observed = " ".join(
            (post.text or "", post.author_name or "", post.author_handle or "")
        ).casefold()
        if not any(
            value.casefold().removeprefix("@") in observed
            for value in (publisher["name"], publisher.get("handle"))
            if value
        ):
            raise ValueError("Publisher identity is absent from the selected source")
        candidate, _ = _organization_candidate(
            post=post,
            name=publisher["name"],
            handle=publisher.get("handle"),
            confidence=None,
        )
        publisher_source = attach_source(event.pk, post_id=post.pk)
        claims.append(
            add_claim(
                publisher_source.pk,
                claim_kind="release_context",
                scope_key="observed_publisher",
                assertion_text=f"Reported release publisher: {publisher['name']}; ownership requires verification",
                source_excerpt=post.text,
                source_locator=sources[("post", post.pk)].source_url,
                source_archive_id=archive.pk,
                reported_candidate_id=candidate.pk,
                extraction_version=METHOD,
            )
        )
    verification = case.get("verification")
    if verification:
        reference = _source_reference(verification)
        if reference not in sources or not case.get("issuer_company_id"):
            raise ValueError(
                "Verification must identify this release's announcing source and issuer"
            )
        source = sources[reference]
        linked = _attach(event, source)
        if source.post_id:
            account_id = models.Post.objects.get(pk=source.post_id).author_id
            control_scope = f"account:{account_id}:company:{case['issuer_company_id']}"
        else:
            observation = models.CollectionObservation.objects.select_related(
                "resource_snapshot", "run__job"
            ).get(pk=source.observation_id)
            if (
                observation.projection_kind == "release-document-v1"
                and observation.run.job.source_id == "publisher_web"
            ):
                if verification["ownership"]["url"] != source.source_url:
                    raise ValueError(
                        "Website ownership proof must identify the exact captured document URL"
                    )
                control_scope = (
                    f"observation:{observation.pk}:company:{case['issuer_company_id']}"
                )
            else:
                account_id = getattr(
                    getattr(observation, "resource_snapshot", None),
                    "publisher_account_id",
                    None,
                )
                control_scope = (
                    f"account:{account_id}:company:{case['issuer_company_id']}"
                )
        for kind, name, scope in (
            (
                "publisher_verification",
                "entity",
                f"company:{case['issuer_company_id']}",
            ),
            (
                "source_ownership",
                "ownership",
                control_scope,
            ),
        ):
            doc = verification[name]
            claim = add_claim(
                linked.pk,
                claim_kind=kind,
                scope_key=scope,
                assertion_text=doc["text"],
                source_excerpt=doc["text"],
                source_locator=doc["url"],
                source_archive_id=archive.pk,
                extraction_version=METHOD,
            )
            claims.append(claim)
    score, ranking_reason = significance(
        **{k: case["significance"][k] for k in ("product_kind", "lineage", "change")}
    )
    review = review_release(
        event.pk,
        release=ProductReleaseInput(
            observed_name=case["name"],
            native_identifier=case["identity"],
            product_key=case.get("product_key"),
            version_label=case.get("version_label"),
            release_issuer_company_id=case.get("issuer_company_id"),
            availability_state=case.get("availability", "unknown"),
        ),
        claim_ids=[c.pk for c in claims],
        actor=actor,
        reason=case["reason"] + " " + ranking_reason,
        evidence_cutoff_at=max(
            [_instant(assessed_at)]
            + [c.recorded_at for c in claims]
            + [c.event_dossier_source.linked_at for c in claims]
        ),
        state=case.get("state", "provisional"),
        significance_score=score,
    )
    return {
        "case_id": case["case_id"],
        "dossier_id": str(event.pk),
        "review_id": str(review.pk),
        "detected_sources": sum(bool(r["dossier_ids"]) for r in detected),
        "selected_sources": len(sources),
        "dated_claims": [
            str(c.pk) for c in claims if c.effective_precision in {"day", "datetime"}
        ],
    }


def capture_case_discussion(result, brand_id, *, anchor_id=None):
    """DB-only 7-day sides plus fine windows around one explicitly selected claim."""
    anchor_id = anchor_id or next(iter(result["dated_claims"]), None)
    if not anchor_id or not brand_id:
        return {"status": "no_dated_brand_anchor", "new_snapshots": 0}
    claim = models.EventDossierClaim.objects.get(
        pk=anchor_id, event_dossier_source__event_dossier_id=result["dossier_id"]
    )
    anchor = claim.effective_at or datetime.combine(
        claim.effective_date, datetime.min.time(), UTC
    )
    # Date-only anchors use UTC midnight for the study, never assert a release hour.
    windows = [
        (anchor + timedelta(hours=h), anchor + timedelta(hours=h + 2))
        for h in range(-168, 168, 2)
    ]
    windows += [
        (anchor + timedelta(minutes=m), anchor + timedelta(minutes=m + 15))
        for m in range(-120, 120, 15)
    ]
    windows += [
        (anchor - timedelta(days=7), anchor),
        (anchor, anchor + timedelta(days=7)),
    ]
    captured = capture_windows(brand_id, windows)
    for snapshot, _ in captured:
        models.EventDossierDiscussionWindow.objects.get_or_create(
            event_dossier_id=result["dossier_id"],
            anchor_claim=claim,
            review_id=result["review_id"],
            snapshot=snapshot,
            role="before"
            if snapshot.window_end <= anchor
            else "after"
            if snapshot.window_start >= anchor
            else "context",
        )
    totals = [read_window(s.pk) for s, _ in captured[-2:]]
    packet = discussion_packet(captured[-1][0].pk, source_limit=8)
    return {
        "status": "stored_only",
        "anchor_claim_id": str(claim.pk),
        "date_only_midnight_assumption": claim.effective_at is None,
        "new_snapshots": sum(created for _, created in captured),
        "total_snapshots": len(captured),
        "totals": totals,
        "representative_sources": packet,
    }


def apply_study(packet, *, discussion=False):
    validate_assessment(packet)
    results = []
    # Each case is atomic; an interrupted invocation resumes by content identity.
    for case in packet["cases"]:
        result = apply_case(
            case, actor=packet["actor"], assessed_at=packet["assessed_at"]
        )
        if discussion:
            result["discussion"] = capture_case_discussion(result, case.get("brand_id"))
        results.append(result)
    return {
        "schema": METHOD,
        "input_hash": _digest(packet),
        "cases": results,
        "releases": release_rows([r["dossier_id"] for r in results]),
    }
