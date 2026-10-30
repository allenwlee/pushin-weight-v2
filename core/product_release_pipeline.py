"""Persist inclusive source candidates and explicitly reconcile release identities.

Detection creates pending evidence. Confirmation is a separate evidenced review,
which must establish the publisher and its control of the announcing account.
"""

from __future__ import annotations

import re
from dataclasses import asdict

from django.db import connection, transaction

from core import models
from core.event_dossiers import (
    ClaimDecision,
    ProductReleaseInput,
    _digest,
    add_claim,
    attach_source,
    complete_review,
    create_dossier,
    identity_key,
)
from core.product_release_intake import detect, search_leads
from core.product_release_milestones import METHOD as MILESTONE_METHOD
from core.product_release_milestones import extract_milestones
from core.product_release_sources import StoredSource

METHOD = "product-release-persistence-v1"


class ReleaseIdentityBusy(ValueError):
    """Another detector is reconciling the same native release."""


def canonical_dossier(dossier_id):
    seen = set()
    while dossier_id not in seen:
        seen.add(dossier_id)
        row = models.EventDossier.objects.get(pk=dossier_id)
        if row.merged_into_id is None:
            return row
        dossier_id = row.merged_into_id
    raise ValueError("Existing dossier merge cycle")


@transaction.atomic
def record_intake_decision(
    dossier_id, *, claim_id, outcome, actor, reason, method_version=METHOD
):
    if outcome not in {"pending", "non_release", "scam", "superseded"}:
        raise ValueError("Unknown intake outcome; confirmation requires a review")
    if any(not value.strip() for value in (actor, reason, method_version)):
        raise ValueError("Intake decisions require actor, reason and method")
    event = models.EventDossier.objects.select_for_update().get(pk=dossier_id)
    claim = models.EventDossierClaim.objects.get(pk=claim_id)
    if claim.event_dossier_source.event_dossier_id != event.pk:
        raise ValueError("Intake evidence belongs to another dossier")
    values = {
        "supporting_claim_id": claim.pk,
        "outcome": outcome,
        "actor": actor,
        "reason": reason,
        "method_version": method_version,
    }
    row, _ = models.EventDossierIntakeDecision.objects.get_or_create(
        event_dossier=event,
        input_hash=_digest(values),
        defaults=values,
    )
    return row


def _known_dossiers(source):
    sources = models.EventDossierSource.objects.filter(
        post_id=source.post_id,
        collection_observation_id=source.observation_id,
        claims__claim_kind_reference__code="release_report",
        event_dossier__event_kind_reference__code="product_release",
    )
    return {
        canonical_dossier(pk).pk
        for pk in sources.values_list("event_dossier_id", flat=True)
    }


def _github_release_identity(source):
    """Use the provider's repository and release IDs, not capture-row IDs."""
    if source.observation_id is None:
        return None
    from core.collection_capture import observation_object_documents
    from core.measurement_taxonomy import require

    observation = models.CollectionObservation.objects.select_related(
        "run__job", "resource_snapshot",
    ).get(pk=source.observation_id)
    if observation.run.job.source_id != "github" or observation.observation_kind != "releases":
        return None
    payload, _, _ = observation_object_documents(observation)
    require(isinstance(payload, dict) and type(payload.get("id")) is int and payload["id"] > 0
            and payload.get("draft") is False and payload.get("published_at")
            and observation.resource_snapshot.resource_kind == "releases"
            and observation.resource_snapshot.native_stable_id == str(payload["id"])
            and observation.source_identifier.isascii() and observation.source_identifier.isdigit()
            and int(observation.source_identifier) > 0, "GitHub native release identity mismatch")
    return observation.source_identifier, str(payload["id"])


def _github_release_dossiers(native):
    """Reuse source-backed prior dossiers, including reviewed ones, without merging them."""
    from core.collection_capture import observation_object_documents
    from core.measurement_taxonomy import require

    sources = list(models.EventDossierSource.objects.filter(
        event_dossier__event_kind_reference__code="product_release",
        collection_observation__run__job__source_id="github",
        collection_observation__observation_kind="releases",
        collection_observation__source_identifier=native[0],
        collection_observation__resource_snapshot__resource_kind="releases",
        collection_observation__resource_snapshot__native_stable_id=native[1],
    ).select_related("collection_observation").order_by("event_dossier_id", "-pk").distinct("event_dossier_id")[:51])
    require(len(sources) <= 50, "too many dossiers for one GitHub release")
    for source in sources:
        row, _, _ = observation_object_documents(source.collection_observation)
        require(isinstance(row, dict) and type(row.get("id")) is int and str(row["id"]) == native[1]
                and row.get("draft") is False, "prior GitHub release evidence conflicts")
    return {canonical_dossier(source.event_dossier_id).pk for source in sources}


def _named_announcement_dossier(source, candidate):
    """Match a single explicit named release to an existing source-bound claim.

    Search leads alone are not identity proof. Multi-product, future, quoted and
    uncertain statements deliberately stay source-level candidates.
    """
    from core.product_release_intake import _RELEASED_NAME

    if not source.post_id or candidate.disposition != "pending" or set(candidate.cautions) & {
        "future_or_uncertain", "question", "negated", "reshare", "quoted_context"
    }:
        return None
    raw = [item.text for item in source.record.texts if item.kind == "raw"]
    if len(raw) != 1:
        return None
    matches = list(_RELEASED_NAME.finditer(raw[0]))
    if len(matches) != 1:
        return None
    match = matches[0]
    name = match.group("name").rstrip("-_.")
    if not any(c.isalpha() for c in name) or not any(c.isdigit() for c in name):
        return None
    # A comma, conjunction or slash can introduce a second product. A dash
    # followed by descriptive prose is common in single-product announcements.
    if re.match(r"\s*(?:,|/|&|\band\b|\bor\b)", raw[0][match.end("name"):], re.IGNORECASE):
        return None
    # Preserve version punctuation: Model-3, Model3 and Model3.1 may be
    # distinct products. Existing study scopes encode spaces as hyphens.
    normalized = re.sub(r"\s+", "-", name.casefold())
    generic_key = identity_key("product-release-source-v1", ":".join(source.record.identity))
    claims = list(models.EventDossierClaim.objects.filter(
        event_dossier_source__post_id=source.post_id,
        event_dossier_source__event_dossier__event_kind_reference__code="product_release",
        claim_kind_reference__code="announcement",
    ).exclude(event_dossier_source__event_dossier__identity_key=generic_key).values_list(
        "event_dossier_source__event_dossier_id", "scope_key", "id"
    )[:51])
    if len(claims) > 50:
        return None
    canonical = {pk: canonical_dossier(pk).pk for pk in {pk for pk, _, _ in claims}}
    if len(set(canonical.values())) != 1:
        return None
    target_id = next(iter(canonical.values()))
    target = models.EventDossier.objects.get(pk=target_id)
    matching_claims = [claim_id for pk, scope, claim_id in claims
                       if canonical[pk] == target_id and scope.rsplit("/", 1)[-1].casefold() == normalized]
    if not matching_claims and target.current_review_id:
        # A reviewed Product's exact repository name can retain punctuation
        # lost by an older release-identity slug. It is still only an identity
        # match; the review must have accepted this source's announcement.
        repo = models.ProductReleaseDetail.objects.filter(
            review_id=target.current_review_id
        ).values_list("product__repo_id", flat=True).first()
        if repo and repo.rsplit("/", 1)[-1].casefold() == normalized:
            matching_claims = [claim_id for pk, _, claim_id in claims if canonical[pk] == target_id]
    if not matching_claims:
        return None
    if target.current_review_id and not models.EventDossierReviewClaim.objects.filter(
        review_id=target.current_review_id, claim_id__in=matching_claims, disposition="accepted"
    ).exists():
        return None
    return target_id, target.current_review_id


def _observed_publisher(source, linked, candidate):
    """Retain a source's self-attribution, separately from verification."""
    if not source.post_id:
        return
    post = models.Post.objects.get(pk=source.post_id)
    text = post.text or ""
    if (candidate.disposition != "pending" or not post.author_handle
            or post.is_retweet or post.quoted_status_id
            or set(candidate.cautions) & {
                "future_or_uncertain", "question", "negated", "reshare", "quoted_context"
            }):
        return
    statement = re.search(
        r"\b(?:we|I)(?:['’](?:ve|re|m))?\s+(?:(?:are|am|have|today|now)\s+)?(?:releas|launch|announc|introduc|publish)"
        r"|\b(?:excited|pleased|proud|thrilled)\s+to\s+(?:announce|introduce|release|launch)\b"
        r"|我们.*(?:发布|推出)", text, re.IGNORECASE,
    )
    if not statement or re.search(
        r"(?:says?|wrote|quot(?:e|ed))\s*:?\s*[\"“]?\s*$",
        text[max(0, statement.start() - 32):statement.start()], re.IGNORECASE,
    ):
        return
    brands = (
        list(
            models.BrandCompany.objects.filter(
                company__accounts__account_id=post.author_id,
                company__accounts__ownership_confirmed=True,
            )
            .values_list("brand_id", flat=True)
            .distinct()
        )
        if post.author_id
        else []
    )
    candidate_id = None
    brand_id = brands[0] if len(brands) == 1 else None
    if not brand_id:
        from core.targeted_extraction import _organization_candidate

        candidate, _ = _organization_candidate(
            post=post,
            name=post.author_name or post.author_handle,
            handle=post.author_handle,
            confidence=None,
        )
        candidate_id = candidate.pk
    add_claim(
        linked.pk,
        claim_kind="release_context",
        scope_key="observed_publisher",
        assertion_text=f"Source author {post.author_handle} describes its own release; ownership still requires verification",
        source_excerpt=post.text,
        source_locator=source.source_url,
        extraction_version=METHOD,
        reported_brand_id=brand_id,
        reported_candidate_id=candidate_id,
    )


def _attach_github_release_repository(source, dossier_id):
    """Reuse the repository captured by the same GitHub release collection."""
    from core.benchmark_metric_timing import aware_instant
    from core.collection_capture import observation_object_documents
    from core.github_metadata_client import GitHubMetadataClient
    from core.measurement_taxonomy import require

    observation = models.CollectionObservation.objects.select_related(
        "run__job", "scope_run__resource_observation",
    ).get(pk=source.observation_id)
    if observation.run.job.source_id != "github" or observation.observation_kind != "releases":
        return
    scope = observation.scope_run
    require(scope is not None and scope.run_id == observation.run_id
            and scope.scope_kind == "repository_events" and scope.resource_observation_id is not None,
            "GitHub release repository evidence missing")
    repository = scope.resource_observation
    release, _, _ = observation_object_documents(observation)
    repo, _, _ = observation_object_documents(repository)
    require(repository.run_id == observation.run_id and repository.observation_kind == "repository"
            and isinstance(repo, dict) and type(repo.get("id")) is int
            and str(repo["id"]) == observation.source_identifier == repository.source_identifier
            and isinstance(release, dict) and release.get("draft") is False and release.get("published_at")
            and isinstance(repo.get("full_name"), str), "GitHub release/repository identity mismatch")
    published = aware_instant(release["published_at"])
    require(observation.published_at == published, "GitHub release publication timestamp mismatch")
    GitHubMetadataClient.repo_url(repo["full_name"])
    from core.product_release_acquisition import link_reviewed_github_product

    lock_key = int(_digest(["catalog-native-v1", "github", "repository", "repository_id", str(repo["id"])])[:15], 16)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [lock_key])
        if not cursor.fetchone()[0]:
            raise ReleaseIdentityBusy("repository identity review is busy")
    repository = models.CollectionObservation.objects.select_for_update().get(pk=repository.pk)
    observation = models.CollectionObservation.objects.select_for_update().get(pk=observation.pk)
    mapping = link_reviewed_github_product(repository, repo)
    if mapping:
        link_reviewed_github_product(observation, repo)
    release_source = attach_source(dossier_id, observation_id=observation.pk)
    add_claim(release_source.pk, claim_kind="release_context", scope_key=f"github_published:{observation.pk}",
              assertion_text="GitHub published this release record at the stated time",
              source_excerpt=release["published_at"], source_locator=source.source_url,
              extraction_version="github-release-publication-v1", effective_precision="datetime",
              effective_at=published)
    linked = attach_source(dossier_id, observation_id=repository.pk)
    add_claim(linked.pk, claim_kind="release_context", scope_key=f"github_repository:{repository.pk}",
              assertion_text=f"GitHub collection captured repository {repo['full_name']}; release role is unresolved",
              source_excerpt=repo["full_name"], source_locator=f"https://github.com/{repo['full_name']}",
              extraction_version="github-release-repository-v1")


@transaction.atomic
def persist_source(source: StoredSource):
    candidate = detect(source.record)
    if candidate is None:
        return {
            "source": source.record.identity,
            "disposition": "no_signal",
            "dossier_ids": [],
        }
    native = _github_release_identity(source)
    if native is not None:
        lock_key = int(_digest(["github-release-detection-v1", *native])[:15], 16)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [lock_key])
            if not cursor.fetchone()[0]:
                raise ReleaseIdentityBusy("GitHub release identity is busy")
    dossier_ids = _known_dossiers(source)
    if native is not None:
        dossier_ids |= _github_release_dossiers(native)
    if not dossier_ids:
        match = _named_announcement_dossier(source, candidate)
        if match:
            matched, target_review_id = match
            generic = models.EventDossier.objects.filter(identity_key=identity_key(
                "product-release-source-v1", ":".join(source.record.identity)
            )).first()
            if generic is not None and canonical_dossier(generic.pk).pk != matched:
                if generic.merged_into_id:
                    matched = None
                else:
                    try:
                        merge_dossiers(generic.pk, matched, actor=METHOD,
                                       reason="Exact single-product announcement identity on the same source",
                                       guard_unreviewed_post=source.post_id,
                                       guard_target_review_id=target_review_id)
                    except ValueError as error:
                        if str(error) != "source dossier is not safe for automatic reconciliation":
                            raise
                        matched = None
            if matched:
                dossier_ids = {matched}
    if not dossier_ids:
        event = create_dossier(
            event_kind="product_release",
            identity_key=(identity_key("github-release-v1", ":".join(native)) if native else
                          identity_key("product-release-source-v1", ":".join(source.record.identity))),
            first_seen_at=source.stored_at,
        )
        dossier_ids = {canonical_dossier(event.pk).pk}
    texts = {item.locator: item for item in source.record.texts}
    by_locator = {}
    for signal in candidate.signals:
        by_locator.setdefault(signal.locator, []).append(signal)
    for dossier_id in sorted(dossier_ids, key=str):
        linked = attach_source(
            dossier_id, post_id=source.post_id, observation_id=source.observation_id
        )
        if source.observation_id is not None:
            _attach_github_release_repository(source, dossier_id)
        _observed_publisher(source, linked, candidate)
        first_claim = None
        for locator, signals in sorted(by_locator.items()):
            text = texts.get(locator)
            excerpt = (
                text.text if text else "; ".join(sorted({s.excerpt for s in signals}))
            )
            claim = add_claim(
                linked.pk,
                claim_kind="release_signal",
                scope_key=locator,
                assertion_text="Release candidate from "
                + ", ".join(sorted({s.kind for s in signals})),
                source_excerpt=excerpt,
                source_locator=source.source_url,
                extraction_version=candidate.rule_version,
            )
            first_claim = first_claim or claim
            # Family-wide statements must be assigned explicitly to each release.
            # Saved translations/commentary never become independent dated proof.
            if (len(dossier_ids) == 1 and text and text.kind == "raw"
                    and not source.record.is_reshare
                    and "quoted_context" not in candidate.cautions):
                for milestone in extract_milestones(
                    text.text, published_at=source.published_at
                ):
                    add_claim(
                        linked.pk,
                        claim_kind=milestone.kind,
                        scope_key=locator,
                        assertion_text=milestone.excerpt,
                        source_excerpt=milestone.excerpt,
                        source_locator=source.source_url,
                        extraction_version=MILESTONE_METHOD,
                        effective_precision=milestone.precision,
                        effective_at=milestone.effective_at,
                        effective_date=milestone.effective_date,
                        access_channel=milestone.access_channel,
                    )
        # An explicit upstream decision is required for exclusion; lack of posts
        # or an unrecognized name is never a fraud decision.
        reason = (
            source.record.fraud.reason
            if source.record.fraud
            else "Release signal retained; product identity and publisher require reconciliation"
        )
        latest = (
            models.EventDossierIntakeDecision.objects.filter(
                event_dossier_id=dossier_id
            )
            .order_by("-recorded_at", "-pk")
            .first()
        )
        # New observations do not silently undo a reviewed exclusion.
        if not latest or latest.outcome not in {"non_release", "scam"}:
            record_intake_decision(
                dossier_id,
                claim_id=first_claim.pk,
                outcome="scam" if source.record.fraud else "pending",
                actor=METHOD,
                reason=reason
                + (
                    "; cautions=" + ",".join(candidate.cautions)
                    if candidate.cautions
                    else ""
                ),
            )
        # A linked repository is a lead, not proof that this is the announced
        # product: it may be a teacher, comparison or third-party upload.
        if source.post_id and not source.record.fraud:
            from core.hf_metadata_client import REPO_ID
            from core.product_release_acquisition import queue_after_commit
            from core.product_verification import (
                _repo_from_hf_url,
                source_repo_evidence,
            )

            post = models.Post.objects.get(pk=source.post_id)
            # Keep GitHub references as explicit leads even before a publisher is
            # known. A link may point to a dependency or quoted project, so it
            # does not establish that the repository is the released product.
            github_repos = {}
            for reference in candidate.references:
                if reference.provider == "github" and reference.repository_type == "repository":
                    github_repos.setdefault(reference.native_identifier.casefold(), reference)
            for reference in sorted(github_repos.values(), key=lambda item: item.native_identifier.casefold())[:3]:
                lead = add_claim(
                    linked.pk,
                    claim_kind="release_context",
                    scope_key="github_repo_lead:" + _digest(reference.native_identifier.casefold()),
                    assertion_text=f"Source references GitHub repository {reference.native_identifier}; its role is unresolved",
                    source_excerpt=reference.url,
                    source_locator=reference.url,
                    extraction_version=METHOD,
                )
                if not latest or latest.outcome not in {"non_release", "scam"}:
                    queue_after_commit(lead.pk, provider="github")
            repos = {}
            for reference in candidate.references:
                if reference.provider != "huggingface" or reference.repository_type != "model":
                    continue
                repo = _repo_from_hf_url(reference.url)
                if (repo and REPO_ID.fullmatch(repo)
                        and source_repo_evidence(post, repo)["exact_hf_repo_link"]):
                    repos.setdefault(repo.casefold(), (repo, reference.url))
            for repo, url in sorted(repos.values(), key=lambda item: item[0].casefold())[:3]:
                lead = add_claim(
                    linked.pk,
                    claim_kind="release_context",
                    scope_key="hf_repo_lead:" + _digest(repo.casefold()),
                    assertion_text=f"Post references HF repository {repo}; its role is unresolved",
                    source_excerpt=post.text or url,
                    source_locator=url,
                    extraction_version=METHOD,
                )
                if not latest or latest.outcome not in {"non_release", "scam"}:
                    queue_after_commit(lead.pk)
            if not repos:
                from core.product_release_intake import raw_versioned_name_leads

                for name in raw_versioned_name_leads(post.text or ""):
                    lead = add_claim(
                        linked.pk,
                        claim_kind="release_context",
                        scope_key="hf_name_lead:" + _digest(name["term"].casefold()),
                        assertion_text=name["term"],
                        source_excerpt=post.text,
                        source_locator=source.source_url,
                        extraction_version=METHOD,
                    )
                    if not latest or latest.outcome not in {"non_release", "scam"}:
                        queue_after_commit(lead.pk)
    return {
        "source": source.record.identity,
        "disposition": candidate.disposition,
        "dossier_ids": sorted(map(str, dossier_ids)),
        "input_hash": _digest(asdict(source.record)),
        "cautions": candidate.cautions,
        "references": [asdict(ref) for ref in candidate.references],
        "search_leads": list(search_leads(candidate)),
    }


def persist_collected_posts(post_ids):
    """Explicitly detect saved posts in bounded batches without model calls.

    This synchronous helper is for explicit replay, not the harvest path.
    Each source commits independently; failures remain eligible for replay.
    """
    import logging

    from core.product_release_sources import stored_posts

    ids = sorted({str(value) for value in post_ids if value})
    totals = {"selected": len(ids), "read": 0, "candidates": 0, "failed": 0}
    for start in range(0, len(ids), 2000):
        batch = ids[start:start + 2000]
        existing = set(models.Post.objects.filter(pk__in=batch).values_list("pk", flat=True))
        totals["failed"] += len(batch) - len(existing)
        if not existing:
            continue
        try:
            rows = stored_posts(sorted(existing))
        except Exception:  # Preserve the harvest; explicit replay can recover the batch.
            logging.getLogger(__name__).exception("Release intake failed to load saved post batch")
            totals["failed"] += len(existing)
            continue
        for source in rows:
            totals["read"] += 1
            if detect(source.record) is None:
                continue
            try:
                result = persist_source(source)
            except Exception:  # Preserve the harvest; explicit replay can recover this source.
                logging.getLogger(__name__).exception("Release intake failed for post %s", source.post_id)
                totals["failed"] += 1
                continue
            totals["candidates"] += int(result["disposition"] != "no_signal")
    return totals


def _copy_claim(claim, source_id):
    return add_claim(
        source_id,
        claim_kind=claim.claim_kind_reference.code,
        scope_key=claim.scope_key,
        assertion_text=claim.assertion_text,
        source_excerpt=claim.source_excerpt,
        source_locator=claim.source_locator,
        extraction_version=claim.extraction_version,
        event_timezone=claim.event_timezone_reference_id,
        access_channel=claim.release_access_channel_reference.code
        if claim.release_access_channel_reference_id
        else None,
        effective_precision=claim.effective_precision,
        effective_at=claim.effective_at,
        effective_date=claim.effective_date,
        effective_year=claim.effective_year,
        effective_month=claim.effective_month,
        not_before=claim.not_before,
        not_after=claim.not_after,
        reported_brand_id=claim.reported_brand_id,
        reported_candidate_id=claim.reported_brand_discovery_candidate_id,
        source_archive_id=claim.source_archive_id,
        release_maturity_id=claim.release_maturity_reference_id,
    )


@transaction.atomic
def merge_dossiers(source_id, target_id, *, actor, reason, guard_unreviewed_post=None,
                   guard_target_review_id=None):
    # A shared advisory lock serializes merge-graph changes before row locks;
    # immutable evidence is copied by semantic identity, never moved or deleted.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(64382061)")
    source = models.EventDossier.objects.get(pk=source_id)
    target = canonical_dossier(target_id)
    if source.pk == target.pk:
        raise ValueError("A dossier merge cannot target itself or form a cycle")
    rows = {
        row.pk: row
        for row in models.EventDossier.objects.select_for_update()
        .filter(pk__in=[source.pk, target.pk])
        .order_by("pk")
    }
    source, target = rows[source.pk], rows[target.pk]
    if source.merged_into_id:
        if canonical_dossier(source.pk).pk == target.pk:
            return target
        raise ValueError("A dossier merge cannot be reassigned")
    if guard_unreviewed_post is not None:
        latest = source.intake_decisions.order_by("-recorded_at", "-pk").first()
        if (target.current_review_id != guard_target_review_id
                or source.current_review_id or source.reviews.exists()
                or latest and latest.outcome in {"non_release", "scam"}
                or source.sources.filter(post__isnull=False).exclude(post_id=guard_unreviewed_post).exists()):
            raise ValueError("source dossier is not safe for automatic reconciliation")
    if source.event_kind_reference_id != target.event_kind_reference_id:
        raise ValueError("A dossier merge must preserve event kind")
    first_claim = None
    for linked in source.sources.order_by("pk"):
        destination = attach_source(
            target.pk,
            post_id=linked.post_id,
            observation_id=linked.collection_observation_id,
        )
        for claim in linked.claims.select_related(
            "claim_kind_reference", "release_access_channel_reference"
        ).order_by("pk"):
            first_claim = first_claim or claim
            _copy_claim(claim, destination.pk)
    if first_claim is None:
        raise ValueError("A merge needs evidence")
    record_intake_decision(
        source.pk,
        claim_id=first_claim.pk,
        outcome="superseded",
        actor=actor,
        reason=f"{reason}; canonical={target.pk}",
    )
    models.EventDossier.objects.filter(pk=source.pk).update(merged_into=target)
    return target


@transaction.atomic
def review_release(
    dossier_id,
    *,
    release: ProductReleaseInput,
    claim_ids,
    actor,
    reason,
    evidence_cutoff_at,
    state="provisional",
    significance_score=None,
):
    """Complete an assessed release; strong claims need explicit ownership proof."""
    event = canonical_dossier(dossier_id)
    event = models.EventDossier.objects.select_for_update().get(pk=event.pk)
    claims = list(
        models.EventDossierClaim.objects.filter(
            pk__in=claim_ids, event_dossier_source__event_dossier=event
        ).select_related(
            "claim_kind_reference",
            "event_dossier_source__post",
            "event_dossier_source__collection_observation__resource_snapshot",
        )
    )
    if len(claims) != len(set(map(str, claim_ids))):
        raise ValueError("Review claims must exist in this dossier")
    by_kind = {}
    for claim in claims:
        by_kind.setdefault(claim.claim_kind_reference.code, []).append(claim)
    if release.availability_state == "available" and not by_kind.get("availability"):
        raise ValueError("Availability requires its own evidence")
    if state == "confirmed":
        issuer = release.release_issuer_company_id
        entity_proof = any(
            c.scope_key == f"company:{issuer}" and c.source_locator
            for c in by_kind.get("publisher_verification", [])
        )
        official_assertion = False
        for claim in by_kind.get("announcement", []) + by_kind.get(
            "source_stated_release", []
        ):
            source = claim.event_dossier_source
            observation = (
                source.collection_observation
                if source.collection_observation_id
                else None
            )
            if (
                observation
                and observation.projection_kind == "release-document-v1"
                and observation.run.job.source_id == "publisher_web"
            ):
                from core.product_release_documents import observation_documents

                document, _, _ = observation_documents(observation)
                if (
                    claim.source_locator == document["web_url"]
                    and claim.source_archive_id == observation.run.payload_archive_id
                    and claim.source_excerpt in document["body"]
                    and any(
                        c.event_dossier_source_id == source.pk
                        and c.scope_key
                        == f"observation:{observation.pk}:company:{issuer}"
                        and c.source_locator == document["web_url"]
                        and c.source_archive_id is not None
                        for c in by_kind.get("source_ownership", [])
                    )
                ):
                    official_assertion = True
                continue
            account_id = (
                source.post.author_id
                if source.post_id
                else getattr(
                    getattr(source.collection_observation, "resource_snapshot", None),
                    "publisher_account_id",
                    None,
                )
            )
            if source.post_id and (source.post.is_retweet or source.post.quoted_status_id):
                continue
            control = any(
                c.scope_key == f"account:{account_id}:company:{issuer}"
                and c.source_locator
                for c in by_kind.get("source_ownership", [])
            )
            if (
                account_id
                and control
                and models.CompanyAccount.objects.filter(
                    account_id=account_id, company_id=issuer, ownership_confirmed=True
                ).exists()
            ):
                official_assertion = True
        if not issuer or not entity_proof or not official_assertion:
            raise ValueError(
                "Confirmation requires verified publisher identity and source ownership evidence"
            )
    # Complete_review hashes cutoff and inputs; pass a stable reviewed_at so an
    # unchanged assessed packet is a no-op, including after the current pointer moves.
    return complete_review(
        event.pk,
        expected_current_review_id=event.current_review_id,
        display_title=release.observed_name,
        review_state=state,
        evidence_cutoff_at=evidence_cutoff_at,
        reviewed_at=evidence_cutoff_at,
        method_version=METHOD,
        actor=actor,
        reason=reason,
        claims=[
            ClaimDecision(c.pk, "accepted", "Source checked in release assessment")
            for c in sorted(claims, key=lambda c: str(c.pk))
        ],
        product_release=release,
        significance_score=significance_score,
        ranking_method="release-significance-v1"
        if significance_score is not None
        else "",
    )
