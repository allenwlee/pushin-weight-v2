"""Bounded acquisition leads; neither a provider match nor a name proves a release."""

from core.product_release_intake import SourceRecord, TextEvidence, detect, search_leads


def _dispatch_if_enabled(job):
    import logging

    from django.conf import settings
    from django.db import connection, transaction

    if not settings.PRODUCT_RELEASE_BACKGROUND_ENABLED:
        return
    if connection.in_atomic_block:
        transaction.on_commit(lambda: _dispatch_if_enabled(job))
        return
    if job.last_success_id and not job.runs.filter(
        scopes__scope_kind="numeric_projection", scopes__outcome="pending"
    ).exists():
        return
    try:
        from monitor.tasks import acquire_product_release

        acquire_product_release.apply_async(
            kwargs={"job_id": str(job.pk)}, queue="trend-narratives", retry=False,
        )
    except Exception:
        logging.getLogger(__name__).exception(
            "Release acquisition dispatch failed for job %s; recovery sweep can retry", job.pk,
        )


def queue_after_commit(claim_id, *, provider="hf"):
    """Register follow-up after the evidence commits; never call a provider here.

    Failed registration leaves the saved claim available to the recovery sweep.
    """
    import logging

    from django.db import transaction

    def enqueue():
        try:
            job = (queue_github_repository(claim_id) if provider == "github"
                   else queue_hf_name_search(claim_id))
        except Exception:  # Preserve committed collection evidence; recovery can retry.
            logging.getLogger(__name__).exception(
                "Release acquisition registration failed for claim %s; recovery sweep can retry",
                claim_id,
            )
            return
        _dispatch_if_enabled(job)

    transaction.on_commit(enqueue)


def dispatch_due_recovery():
    """Wake one bounded recovery task from an existing harvest, when enabled."""
    import logging

    from django.conf import settings
    from django.db import transaction

    if not settings.PRODUCT_RELEASE_BACKGROUND_ENABLED:
        return {"status": "disabled"}
    def dispatch():
        try:
            from monitor.tasks import recover_due_product_releases

            recover_due_product_releases.apply_async(queue="trend-narratives", retry=False)
        except Exception:
            logging.getLogger(__name__).exception(
                "Release acquisition recovery dispatch failed; a later harvest can retry"
            )

    transaction.on_commit(dispatch)
    return {"status": "scheduled"}


def hf_search_observation_documents(observation):
    """Read one search hit only from its original, checksum-verified response."""
    from urllib.parse import parse_qs, urlsplit

    from core.collection_capture import read_document
    from core.measurement_taxonomy import digest, require

    run, scope = observation.run, observation.scope_run
    require(
        run.job.source_id == "hf" and run.job.operation == "release_acquisition"
        and scope is not None and scope.run_id == run.pk
        and scope.scope_kind == "release_acquisition",
        "search observation ownership mismatch",
    )
    links = list(observation.inputs.select_related("input_request__archive", "input_request__attempt"))
    require(len(links) == 1, "search observation needs one captured response")
    link = links[0]
    request = link.input_request
    require(
        link.input_role == "hf_search" and request is not None
        and request.scope_run_id == scope.pk and request.attempt.run_id == run.pk
        and request.transport_outcome == "received" and request.http_status == 200
        and request.archive_id is not None
        and link.input_sha256 == request.archive.content_sha256,
        "search response ownership or checksum mismatch",
    )
    endpoint = urlsplit(request.endpoint_url)
    target = run.job.targets.get(target_role="name_search")
    require(
        endpoint.scheme == "https" and endpoint.netloc == "huggingface.co"
        and endpoint.path == "/api/models" and not endpoint.fragment
        and parse_qs(endpoint.query).get("search") == [target.native_identifier],
        "search response endpoint or target mismatch",
    )
    locator = link.row_locator
    require(isinstance(locator, str) and locator.isascii() and locator.isdecimal()
            and str(int(locator)) == locator, "invalid search row locator")
    data = read_document(request.archive)
    require(isinstance(data, list) and int(locator) < len(data), "search row missing")
    row = data[int(locator)]
    require(isinstance(row, dict)
            and (row.get("id") or row.get("modelId")) == observation.source_identifier
            and digest(row) == observation.payload_sha256,
            "search result identity or content changed")
    return row, {}, {}


def hf_exact_observation_documents(observation):
    """Validate exact-repository evidence against its captured public response."""
    from urllib.parse import parse_qs, urlsplit

    from core.collection_capture import read_document
    from core.hf_metadata_client import EXPAND_FIELDS
    from core.measurement_taxonomy import digest, require

    run, scope = observation.run, observation.scope_run
    require(run.job.source_id == "hf" and run.job.operation == "release_acquisition"
            and scope is not None and scope.run_id == run.pk
            and scope.scope_kind == "release_acquisition", "exact observation ownership mismatch")
    links = list(observation.inputs.select_related("input_request__archive", "input_request__attempt"))
    require(len(links) == 1, "exact observation needs one captured response")
    link = links[0]
    request = link.input_request
    expanded = observation.projection_kind == "hf-release-expanded-v1"
    require(link.input_role == ("hf_expanded" if expanded else "hf_exact") and request is not None
            and request.scope_run_id == scope.pk and request.attempt.run_id == run.pk
            and request.transport_outcome == "received" and request.http_status == 200
            and request.archive_id is not None
            and link.input_sha256 == request.archive.content_sha256,
            "exact response ownership or checksum mismatch")
    target = run.job.targets.get(target_role="expanded_model" if expanded else "exact_model")
    endpoint = urlsplit(request.endpoint_url)
    require(endpoint.scheme == "https" and endpoint.netloc == "huggingface.co"
            and endpoint.path == f"/api/models/{target.native_identifier}"
            and not endpoint.fragment, "exact response endpoint or target mismatch")
    if expanded:
        fields = parse_qs(endpoint.query).get("expand", [])
        fallback = ["author", "sha", "private", "downloads", "likes", "tags", "cardData"]
        require(fields == list(EXPAND_FIELDS) or fields == fallback, "expanded response fields changed")
    row = read_document(request.archive)
    require(isinstance(row, dict)
            and (row.get("id") or row.get("modelId")) == observation.source_identifier
            and observation.source_identifier.casefold() == target.native_identifier.casefold()
            and digest(row) == observation.payload_sha256, "exact response identity or content changed")
    return row, {}, {}


def hf_socials_observation_documents(observation):
    """Read a source-attributed HF social claim without treating it as ownership."""
    from urllib.parse import urlsplit

    from core.collection_capture import read_document
    from core.measurement_taxonomy import digest, require

    run, scope = observation.run, observation.scope_run
    require(run.job.source_id == "hf" and run.job.operation == "release_acquisition"
            and scope is not None and scope.run_id == run.pk
            and scope.scope_kind == "release_acquisition", "socials observation ownership mismatch")
    links = list(observation.inputs.select_related("input_request__archive", "input_request__attempt"))
    require(len(links) == 1, "socials observation needs one captured response")
    link, = links
    request = link.input_request
    require(link.input_role == "hf_socials" and request is not None
            and request.scope_run_id == scope.pk and request.attempt.run_id == run.pk
            and request.transport_outcome == "received" and request.http_status == 200
            and request.archive_id is not None and link.input_sha256 == request.archive.content_sha256,
            "socials response ownership or checksum mismatch")
    target = run.job.targets.get(target_role="publisher_socials")
    endpoint = urlsplit(request.endpoint_url)
    org_path = f"/api/organizations/{target.native_identifier}/socials"
    user_path = f"/api/users/{target.native_identifier}/socials"
    require(endpoint.scheme == "https" and endpoint.netloc == "huggingface.co"
            and endpoint.path in {org_path, user_path}
            and not endpoint.query and not endpoint.fragment, "socials endpoint or target mismatch")
    row = read_document(request.archive)
    identity_field = "org" if endpoint.path == org_path else "user"
    require(isinstance(row, dict) and isinstance(row.get(identity_field), str)
            and row[identity_field].casefold() == target.native_identifier.casefold()
            and observation.source_identifier.casefold() == target.native_identifier.casefold()
            and isinstance(row.get("socialHandles"), dict) and digest(row) == observation.payload_sha256,
            "socials identity or content changed")
    return row, {}, {}


def _resolve_official_search_result(dossier, search_observation, exact_observation, payload):
    """Resolve a no-link report only when independent official evidence agrees."""
    import re

    from django.db import transaction
    from django.utils import timezone

    from core import models
    from core.product_release_intake import SourceRecord, TextEvidence, detect
    from core.product_verification import (
        _normalized_identity,
        _proposal_categories,
        attach_verified_product,
        evaluate_known_publisher,
    )

    hf_search_observation_documents(search_observation)
    hf_exact_observation_documents(exact_observation)
    search_run = search_observation.run
    if search_run.status != "success":
        return 0
    repo = exact_observation.source_identifier
    if search_observation.source_identifier.casefold() != repo.casefold():
        return 0
    name = search_run.job.targets.get(target_role="name_search").native_identifier
    normalized = _normalized_identity(name)
    if not normalized or normalized != _normalized_identity(repo.split("/", 1)[1]):
        return 0
    matching = set()
    for row in search_run.observations.all():
        hf_search_observation_documents(row)
        identifier = row.source_identifier
        if (identifier.split("/", 1)[0].casefold() == repo.split("/", 1)[0].casefold()
                and _normalized_identity(identifier.split("/", 1)[1]) == normalized):
            matching.add(identifier.casefold())
    if matching != {repo.casefold()}:
        return 0
    if models.ProductVerificationProposal.objects.filter(
        source_dossier_id=dossier.pk, review_status="rejected"
    ).exists():
        return 0
    source_links = search_run.job.dossier_claim_links.select_related(
        "claim__event_dossier_source__post__author", "claim__reported_brand"
    )
    for link in source_links:
        report = link.claim
        source = report.event_dossier_source
        if (source.event_dossier_id != dossier.pk or not source.post_id
                or report.claim_kind_reference.code != "release_report"
                or not report.reported_brand_id or report.assertion_text != name):
            continue
        post = source.post
        if not post.author_id or post.is_retweet or not post.text or not post.author_handle:
            continue
        if post.author_handle.removeprefix("@").casefold() != (post.author.handle or "").removeprefix("@").casefold():
            continue
        detected = detect(SourceRecord(
            "post", str(post.pk), (TextEvidence("post-text", "raw", post.text),)
        ))
        if not detected or set(detected.cautions) & {"future_or_uncertain", "negated", "question", "reshare"}:
            continue
        pattern = (r"\b(?:we|i)\s+(?:(?:are|have|today|now)\s+){0,2}"
                   r"(?:announc(?:e|ed|ing)|releas(?:e|ed|ing)|launch(?:ed|ing)?)\s+"
                   r"(?:(?:our|the|new)\s+){0,2}" + re.escape(name) + r"(?![\w.-])")
        if not re.search(pattern, post.text, flags=re.IGNORECASE):
            continue
        if not evaluate_known_publisher(account=post.author, brand=report.reported_brand,
                                        namespace=repo.split("/", 1)[0]).qualifies:
            continue
        with transaction.atomic():
            models.EventDossier.objects.select_for_update().get(pk=dossier.pk)
            post = models.Post.objects.select_for_update().get(pk=post.pk)
            if not post.author_id:
                continue
            account = models.Account.objects.select_for_update().get(pk=post.author_id)
            if (not post.author_handle or not account.handle or
                    post.author_handle.removeprefix("@").casefold()
                    != account.handle.removeprefix("@").casefold()
                    or not re.search(pattern, post.text or "", flags=re.IGNORECASE)):
                continue
            latest = dossier.intake_decisions.order_by("-recorded_at", "-pk").first()
            if (latest and latest.outcome in {"non_release", "scam"}) or models.ProductVerificationProposal.objects.filter(
                source_dossier_id=dossier.pk, review_status="rejected"
            ).exists():
                continue
            proposal = models.ProductVerificationProposal.objects.select_for_update().filter(
                source_post_id=post.pk, source_dossier_id=dossier.pk, proposed_brand_id=report.reported_brand_id,
                account_id=post.author_id, observed_name=name, review_status="pending",
                candidate_repo_id="",
            ).first()
            if (proposal is None or proposal.verification_claim_expires_at is not None
                    and proposal.verification_claim_expires_at > timezone.now()):
                continue
            categories = _proposal_categories(proposal)
            if len(categories) != 1:
                continue
            product = attach_verified_product(
                post=post, brand=report.reported_brand, repo_id=repo, observed_name=name,
                account=account, metadata=payload, product_type=categories[0], source_dossier=dossier,
                evidence={"search_observation_id": search_observation.pk,
                          "exact_observation_id": exact_observation.pk, "report_claim_id": str(report.pk)},
                policy_version="product-official-name-search-v1",
            )
            proposal.candidate_repo_id = repo
            proposal.resolved_product = product
            proposal.hf_outcome = "matched"
            proposal.hf_evidence = payload
            proposal.policy_version = "product-official-name-search-v1"
            proposal.rule_trace = [*proposal.rule_trace, "official_first_person_exact_name_and_verified_hf_owner"]
            proposal.review_status = "approved"
            proposal.review_reason = "automatic_official_name_search"
            proposal.reviewed_at = timezone.now()
            proposal.save()
            return 1
    return 0


def _resolve_candidate_from_socials(dossier, claim, social_observation, socials):
    """Apply the existing cross-platform publisher policy to two saved captures."""
    import uuid
    from datetime import timedelta

    from django.db import IntegrityError, transaction
    from django.utils import timezone

    from core import models
    from core.product_verification import (
        POLICY_VERSION,
        _evaluate_new_publisher_source,
        _finalize_new_publisher,
        _normalized_identity,
        _proposal_categories,
    )

    source = claim.event_dossier_source
    if not source.post_id:
        return 0
    namespace = social_observation.source_identifier
    jobs = models.CollectionJob.objects.filter(
        source_id="hf", operation="release_acquisition", last_success__isnull=False,
        dossier_claim_links__claim=claim, targets__target_role="exact_model",
    ).select_related("last_success").distinct()
    resolved = 0
    for job in jobs:
        target = job.targets.get(target_role="exact_model")
        if target.native_identifier.split("/", 1)[0].casefold() != namespace.casefold():
            continue
        exact = job.last_success.observations.get(projection_kind="hf-release-exact-v1")
        payload, _, _ = hf_exact_observation_documents(exact)
        proposal_ids = models.ProductVerificationProposal.objects.filter(
            source_dossier_id=dossier.pk, source_post_id=source.post_id,
            proposed_candidate__isnull=False, candidate_repo_id__iexact=target.native_identifier,
            review_status="pending", policy_version=POLICY_VERSION,
        ).values_list("pk", flat=True)
        for proposal_id in proposal_ids:
            with transaction.atomic():
                models.EventDossier.objects.select_for_update().get(pk=dossier.pk)
                proposal = models.ProductVerificationProposal.objects.select_for_update(of=("self",)).select_related(
                    "account", "source_post", "proposed_candidate"
                ).get(pk=proposal_id)
                now = timezone.now()
                if (proposal.review_status != "pending" or proposal.proposed_candidate_id is None
                        or proposal.verification_claim_expires_at is not None
                        and proposal.verification_claim_expires_at > now
                        or not _normalized_identity(proposal.observed_name)
                        or _normalized_identity(proposal.observed_name)
                        != _normalized_identity(target.native_identifier.split("/", 1)[1])
                        or len(_proposal_categories(proposal)) != 1
                        or not _evaluate_new_publisher_source(
                            proposal, namespace=namespace, allow_source_declaration=True
                        ).qualifies):
                    continue
                token = uuid.uuid4()
                proposal.verification_claim_token = token
                proposal.verification_claim_expires_at = now + timedelta(minutes=2)
                proposal.save(update_fields=["verification_claim_token", "verification_claim_expires_at", "updated_at"])
                try:
                    with transaction.atomic():
                        resolved += int(_finalize_new_publisher(
                            proposal.pk, token, model_payload=payload, socials_payload=socials,
                            allow_source_declaration=True,
                        ))
                except (IntegrityError, ValueError):
                    proposal.verification_claim_token = None
                    proposal.verification_claim_expires_at = None
                    proposal.rule_trace = [*proposal.rule_trace, "automatic_verification_stopped:identity_conflict"]
                    proposal.save(update_fields=["verification_claim_token", "verification_claim_expires_at",
                                                 "rule_trace", "updated_at"])
    return resolved


def _retain_exact_hf_product(observation, payload):
    """Retain the repository identity, without asserting it is the release.

    The captured response has already been validated against its exact target.
    Existing Product metadata and ownership are never overwritten by this path.
    """
    from django.core.exceptions import ValidationError
    from django.db import DataError, transaction

    from core import models
    from core.measurement_taxonomy import resolve_subject_id
    from core.product_metadata import apply_metadata

    with transaction.atomic():
        observed = models.CollectionObservation.objects.select_for_update().get(pk=observation.pk)
        repo = observed.source_identifier
        product, created = models.Product.objects.get_or_create(
            repo_id=repo, defaults={"display_name": repo.split("/", 1)[1], "hf_type": "model"}
        )
        product = models.Product.objects.select_for_update().get(pk=product.pk)
        models.MeasurementSubject.objects.get_or_create(
            pk=resolve_subject_id("product", str(product.product_key)),
            defaults={"subject_kind": "product", "product": product},
        )
        if observed.product_id not in (None, product.pk):
            raise ValueError("exact repository observation has conflicting product")
        if observed.product_id is None:
            observed.product = product
            observed.created_product = created
            observed.save(update_fields=["product", "created_product", "updated_at"])
        if created:
            try:
                with transaction.atomic():
                    apply_metadata(product, payload, group="detail", observation={
                        "id": observed.pk, "run_id": str(observed.run_id),
                    })
            except (ValidationError, DataError, ValueError, TypeError):
                observed.processing_outcome = "projection_error"
                observed.save(update_fields=["processing_outcome", "updated_at"])
        return product


def _integrate_acquisition_run(run_id):
    """Attach captured leads and reuse exact evidence for known-publisher identity.

    This does not confirm an announcement or infer that a search hit is the
    released product. Captures and existing reviews remain independently owned.
    """
    import uuid
    from datetime import timedelta

    from django.db import transaction
    from django.utils import timezone

    from core import models
    from core.event_dossiers import add_claim, attach_source
    from core.product_release_pipeline import canonical_dossier
    from core.product_verification import (
        POLICY_VERSION,
        HFMetadataResult,
        _finalize_known_publisher,
        _normalized_identity,
        _proposal_source_gate,
        evaluate_known_publisher,
    )

    run = models.CollectionRun.objects.select_related("job").get(pk=run_id)
    if run.job.operation != "release_acquisition" or run.job.source_id != "hf":
        raise ValueError("HF release acquisition run required")
    links = list(run.job.dossier_claim_links.select_related("claim__event_dossier_source"))
    totals = {"observations": 0, "dossiers": 0, "products_resolved": 0,
              "registration_failures": 0}
    selected_search_repos = set()
    for observation in run.observations.all().order_by("pk"):
        exact = observation.projection_kind == "hf-release-exact-v1"
        expanded = observation.projection_kind == "hf-release-expanded-v1"
        socials = observation.projection_kind == "hf-release-socials-v1"
        if exact or expanded:
            payload, _, _ = hf_exact_observation_documents(observation)
        elif socials:
            payload, _, _ = hf_socials_observation_documents(observation)
        else:
            payload, _, _ = hf_search_observation_documents(observation)
        request = observation.inputs.select_related("input_request").get().input_request
        repo = observation.source_identifier
        # An approved X-only Product may be this repository. Do not create a
        # competing identity before the existing verification path reconciles it.
        original_dossiers = {
            link.claim.event_dossier_source.event_dossier_id for link in links
        } if exact else set()
        dossier_ids = original_dossiers | {
            canonical_dossier(pk).pk for pk in original_dossiers
        }
        if dossier_ids:
            list(models.EventDossier.objects.select_for_update().filter(
                pk__in=dossier_ids
            ).order_by("pk").values_list("pk", flat=True))
        prior_x_only = exact and models.ProductVerificationProposal.objects.filter(
            source_dossier_id__in=dossier_ids, review_status="approved",
            resolved_product__isnull=False, resolved_product__repo_id__isnull=True,
        ).exists()
        search_followup = False
        if not exact and not socials and not expanded:
            normalized = repo.casefold()
            if normalized in selected_search_repos or len(selected_search_repos) < 3:
                selected_search_repos.add(normalized)
                search_followup = True
        seen_dossiers = set()
        eligible_dossiers = set()
        totals["observations"] += 1
        for link in links:
            source = link.claim.event_dossier_source
            dossier = canonical_dossier(source.event_dossier_id)
            latest = dossier.intake_decisions.order_by("-recorded_at", "-pk").first()
            eligible = not latest or latest.outcome not in {"non_release", "scam"}
            if eligible:
                eligible_dossiers.add(dossier.pk)
            if dossier.pk not in seen_dossiers:
                event_source = attach_source(dossier.pk, observation_id=observation.pk)
                captured_claim = add_claim(
                    event_source.pk, claim_kind="release_context",
                    scope_key=f"hf_capture:{observation.pk}",
                    assertion_text=(f"Captured HF publisher {repo} social links; ownership is unresolved"
                                    if socials else
                                    f"Captured HF repository {repo}; its release role is unresolved"),
                    source_excerpt=repo,
                    source_locator=f"https://huggingface.co/{repo}",
                    source_archive_id=request.archive_id,
                    extraction_version=observation.projection_kind,
                )
                if expanded:
                    from core.hf_metadata_client import REPO_ID
                    from core.measurement_taxonomy import digest

                    card = payload.get("cardData")
                    if isinstance(card, dict):
                        bases = card.get("base_model")
                        bases = [bases] if isinstance(bases, str) else bases if isinstance(bases, list) else []
                        relation = card.get("base_model_relation")
                        relation = relation if isinstance(relation, str) and len(relation) <= 64 else "unspecified"
                        for parent in dict.fromkeys(
                            value for value in bases[:50] if isinstance(value, str) and REPO_ID.fullmatch(value)
                        ):
                            add_claim(
                                event_source.pk, claim_kind="release_context",
                                scope_key="hf_base_model:" + digest([parent, relation]),
                                assertion_text=f"HF model card reports base model {parent}; relation {relation}",
                                source_excerpt=parent, source_locator=f"https://huggingface.co/{repo}",
                                source_archive_id=request.archive_id,
                                extraction_version="hf-card-base-model-v1",
                            )
                seen_dossiers.add(dossier.pk)
                totals["dossiers"] += 1
                if exact and eligible:
                    import logging

                    try:
                        followup = queue_hf_expanded_capture(captured_claim.pk, observation.pk)
                        _dispatch_if_enabled(followup)
                    except Exception:
                        totals["registration_failures"] += 1
                        logging.getLogger(__name__).exception(
                            "Expanded metadata registration failed for capture %s", observation.pk,
                        )
                    try:
                        from core.product_release_hf_card import queue_card

                        card_job = queue_card(captured_claim.pk, observation.pk)
                        if card_job is not None:
                            _dispatch_if_enabled(card_job)
                    except Exception:
                        totals["registration_failures"] += 1
                        logging.getLogger(__name__).exception(
                            "Model-card registration failed for capture %s", observation.pk,
                        )
                if search_followup and eligible:
                    import logging

                    try:
                        followup = queue_hf_search_hit(captured_claim.pk, observation.pk)
                        _dispatch_if_enabled(followup)
                    except Exception:
                        totals["registration_failures"] += 1
                        logging.getLogger(__name__).exception(
                            "Exact search-hit registration failed for capture %s", observation.pk,
                        )
            if socials and eligible:
                totals["products_resolved"] += _resolve_candidate_from_socials(
                    dossier, link.claim, observation, payload
                )
            if not exact:
                continue
            if not eligible:
                continue
            if not prior_x_only:
                _retain_exact_hf_product(observation, payload)
            if link.claim.reported_brand_id is None:
                import logging

                try:
                    publisher_job = queue_hf_publisher_socials(link.claim_id, observation.pk)
                    _dispatch_if_enabled(publisher_job)
                except Exception:
                    totals["registration_failures"] += 1
                    logging.getLogger(__name__).exception(
                        "Publisher evidence registration failed for acquisition claim %s",
                        link.claim_id,
                    )
            if not source.post_id:
                if (source.collection_observation_id
                        and source.collection_observation.projection_kind == "hf-release-search-v1"):
                    totals["products_resolved"] += _resolve_official_search_result(
                        dossier, source.collection_observation, observation, payload
                    )
                continue
            # A report must independently select the same repository and name;
            # links found in the post alone may identify teachers or comparators.
            proposals = models.ProductVerificationProposal.objects.filter(
                source_dossier_id=dossier.pk, source_post_id=source.post_id,
                candidate_repo_id__iexact=repo, proposed_brand__isnull=False,
                review_status="pending", policy_version=POLICY_VERSION,
            ).values_list("pk", flat=True)
            for proposal_id in proposals:
                with transaction.atomic():
                    models.EventDossier.objects.select_for_update().get(pk=dossier.pk)
                    proposal = models.ProductVerificationProposal.objects.select_for_update(of=("self",)).select_related(
                        "account", "source_post", "proposed_brand"
                    ).get(pk=proposal_id)
                    now = timezone.now()
                    if (proposal.review_status != "pending"
                            or proposal.source_dossier_id != dossier.pk
                            or proposal.verification_claim_expires_at is not None
                            and proposal.verification_claim_expires_at > now
                            or not _normalized_identity(proposal.observed_name)
                            or _normalized_identity(proposal.observed_name)
                            != _normalized_identity(repo.split("/", 1)[1])):
                        continue
                    namespace = repo.split("/", 1)[0]
                    if not (_proposal_source_gate(proposal, namespace=namespace).qualifies
                            and evaluate_known_publisher(account=proposal.account,
                                brand=proposal.proposed_brand, namespace=namespace).qualifies):
                        continue
                    token = uuid.uuid4()
                    proposal.verification_claim_token = token
                    proposal.verification_claim_expires_at = now + timedelta(minutes=2)
                    proposal.save(update_fields=["verification_claim_token", "verification_claim_expires_at", "updated_at"])
                    totals["products_resolved"] += int(_finalize_known_publisher(
                        proposal.pk, token, HFMetadataResult("matched", payload)
                    ))
        if exact and eligible_dossiers:
            from core.source_metric_projection import retain_release_projection_followup

            retain_release_projection_followup(observation)
        if (prior_x_only and eligible_dossiers
                and models.ProductVerificationProposal.objects.filter(
                    source_dossier_id__in=eligible_dossiers, review_status="approved",
                    resolved_product__repo_id__iexact=repo,
                ).exists()):
            _retain_exact_hf_product(observation, payload)
    return totals


def integrate_acquisition_run(run_id):
    """Reconcile a saved run with durable, finite follow-up retries."""
    from datetime import timedelta

    from django.db import transaction
    from django.utils import timezone

    from core import models

    with transaction.atomic():
        scope, _ = models.CollectionScopeRun.objects.get_or_create(
            run_id=run_id, scope_kind="release_integration", scope_key="post_capture",
            defaults={"phase": "release-integration-v1"},
        )
        scope = models.CollectionScopeRun.objects.select_for_update().get(pk=scope.pk)
        if scope.outcome == "failed":
            return {"status": "retry_limit", "registration_failures": 0}
        if scope.outcome == "pending" and scope.retry_at and scope.retry_at > timezone.now():
            return {"status": "cooldown", "registration_failures": 0}
        try:
            with transaction.atomic():
                result = _integrate_acquisition_run(run_id)
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Release integration failed for run %s", run_id)
            result = {"registration_failures": 1}
        if result["registration_failures"]:
            scope.raw_count += 1
            scope.outcome = "failed" if scope.raw_count >= 3 else "pending"
            scope.execution_state = "failed" if scope.outcome == "failed" else "pending"
            scope.coverage_state = "unavailable" if scope.outcome == "failed" else "partial"
            scope.retry_at = None if scope.outcome == "failed" else timezone.now() + timedelta(hours=6)
            scope.error_code = "followup_registration_failed"
            scope.enumeration_complete = False
        else:
            scope.outcome = "complete"
            scope.execution_state = "completed"
            scope.coverage_state = "complete"
            scope.retry_at = None
            scope.error_code = None
            scope.enumeration_complete = True
        scope.save(update_fields=["raw_count", "outcome", "execution_state", "coverage_state",
                                  "retry_at", "error_code", "enumeration_complete"])
        return {**result, "status": scope.outcome}


def _has_eligible_claim(job):
    """Recheck current decisions, including dossiers merged after queuing."""
    from core.product_release_pipeline import canonical_dossier

    links = list(job.dossier_claim_links.select_related("claim__event_dossier_source"))
    for link in links:
        if link.claim.scope_key.startswith("hf_name_lead:") and not _source_bound_raw_name(link.claim):
            continue
        dossier = canonical_dossier(link.claim.event_dossier_source.event_dossier_id)
        latest = dossier.intake_decisions.order_by("-recorded_at", "-pk").first()
        if not latest or latest.outcome not in {"non_release", "scam"}:
            return True
    return False


def execute_hf_name_search(job_id, *, client):
    """Execute a finite, manually authorized job and retain each physical response."""
    from datetime import timedelta

    from django.utils import timezone

    from core import models
    from core.collection_capture import RequestCapture, link_request
    from core.collection_cursors import replace_scope_cursor_history
    from core.collection_state import claim_job, fenced_run, finish_run
    from core.hf_metadata_client import HFMetadataClient
    from core.measurement_taxonomy import digest, require

    job = models.CollectionJob.objects.get(pk=job_id)
    require(job.source_id == "hf" and job.operation == "release_acquisition"
            and job.mode == "manual", "manual HF acquisition job required")
    links = list(job.dossier_claim_links.select_related("claim__event_dossier_source"))
    require(links, "acquisition needs a source claim")
    if not _has_eligible_claim(job):
        return {"run_id": None, "outcome": "excluded", "request_count": 0, "physical_requests": 0}
    if job.last_success_id:
        run = job.last_success
        integration = integrate_acquisition_run(run.pk)
        return {"run_id": str(run.pk), "outcome": "found", "request_count": run.request_count,
                "physical_requests": 0, "integration": integration}
    require(
        not job.last_attempt_id or job.last_attempt.error_code != "cursor_cycle",
        "cursor cycle requires a new reviewed search",
    )
    prior_attempts = models.CollectionAttempt.objects.filter(run__job=job).count()
    checkpointed = bool(job.last_attempt_id and job.last_attempt.completed_at is None
                        and job.last_attempt.scopes.filter(
        scope_kind="release_acquisition", scope_key="execution",
        outcome="found", enumeration_complete=True, cursor__isnull=True,
    ).exists())
    require(prior_attempts < 3 or checkpointed, "acquisition retry limit exhausted")
    claim = claim_job(job.pk, typed=True, manual_authorized=True)
    run = models.CollectionRun.objects.get(pk=claim.run_id)
    prior_requests = sum(run.attempts.exclude(pk=claim.attempt_id).values_list("actual_requests", flat=True))
    scope = run.scopes.get(scope_kind="release_acquisition", scope_key="execution")
    if scope.enumeration_complete and scope.outcome == "found" and scope.cursor is None:
        observations = list(run.observations.all())
        require(observations, "completed search checkpoint has no observations")
        for observation in observations:
            if observation.projection_kind in {"hf-release-exact-v1", "hf-release-expanded-v1"}:
                hf_exact_observation_documents(observation)
            elif observation.projection_kind == "hf-release-socials-v1":
                hf_socials_observation_documents(observation)
            else:
                hf_search_observation_documents(observation)
        finish_run(
            claim, typed=True, status="success", request_count=prior_requests,
            selected_count=len(observations), success_count=len(observations),
            physical_accounting_complete=True,
        )
        integration = integrate_acquisition_run(run.pk)
        return {"run_id": str(run.pk), "outcome": "found", "request_count": prior_requests,
                "physical_requests": 0, "integration": integration}
    seen_cursors = scope.recorded_cursors
    target = job.targets.get()
    hf = HFMetadataClient(client, max_requests=job.max_requests,
                          max_seconds=job.max_seconds, max_bytes=job.max_bytes,
                          max_total_bytes=job.max_bytes)
    hf.capture, hf.collection_scope = RequestCapture(claim), scope
    exact = target.target_role == "exact_model"
    expanded = target.target_role == "expanded_model"
    socials = target.target_role == "publisher_socials"
    require(exact or expanded or socials or target.target_role == "name_search", "unsupported acquisition target")
    response = (hf.model_group(target.native_identifier, "detail") if exact else
                hf.model_group(target.native_identifier, "expanded") if expanded else
                hf.organization_socials(target.native_identifier) if socials else
                hf.search_models(target.native_identifier, limit=job.max_items, cursor=scope.cursor))
    outcome = response.outcome
    count = 0
    new_observations = 0
    cursor_cycle = bool(response.next_cursor and response.next_cursor in seen_cursors)
    accepted = response.outcome in {"ok", "partial_expansion"}
    if accepted:
        request_ids = [attempt.get("collection_request_id") for attempt in response.attempts
                       if attempt.get("http_status") == 200]
        require(len(request_ids) == 1, "search result requires one captured successful response")
        request = models.CollectionRequest.objects.select_related("archive").get(pk=request_ids[0])
        RequestCapture.response_metadata(request, cursor=response.next_cursor)
    with fenced_run(claim):
        if accepted:
            rows = [response.payload] if exact or expanded or socials else response.payload
            for position, row in enumerate(rows):
                native_id = (row.get("org") or row["user"]) if socials else row.get("id") or row["modelId"]
                projection = ("hf-release-socials-v1" if socials else "hf-release-expanded-v1" if expanded else
                              "hf-release-exact-v1" if exact else "hf-release-search-v1")
                key = digest([projection, native_id.casefold(), digest(row)])
                observation, created = models.CollectionObservation.objects.get_or_create(
                    run=run, observation_key=key,
                    defaults={
                        "scope_run": scope, "source_identifier": native_id,
                        "source_subject_kind": "account" if socials else "model",
                        "observation_kind": "hf_release_socials" if socials else "hf_release_expanded" if expanded else "hf_release_exact" if exact else "hf_release_search",
                        "projection_kind": projection, "payload_sha256": digest(row),
                        "observed_at": request.received_at,
                        "processing_outcome": "partial_expansion" if response.outcome == "partial_expansion" else "unresolved",
                    },
                )
                require(observation.scope_run_id == scope.pk
                        and observation.source_identifier == native_id
                        and observation.payload_sha256 == digest(row),
                        "existing search observation differs")
                if created:
                    new_observations += 1
                    link_request(observation, request,
                                 role="hf_socials" if socials else "hf_expanded" if expanded else "hf_exact" if exact else "hf_search",
                                 row_locator=None if exact or expanded or socials else str(position))
                if exact:
                    from core.source_metric_projection import (
                        enqueue_authorized_release_projection,
                        retain_release_projection_followup,
                    )

                    enqueue_authorized_release_projection(claim, observation)
                    retain_release_projection_followup(observation)
                count += 1
            if not cursor_cycle:
                scope.cursor = response.next_cursor
                if response.next_cursor:
                    replace_scope_cursor_history(scope, [*seen_cursors, response.next_cursor])
            outcome = "cursor_cycle" if cursor_cycle else "incomplete" if response.next_cursor else "found" if run.observations.exists() else "empty"
        scope.outcome = outcome
        scope.error_code = None if outcome == "found" else outcome
        scope.enumeration_complete = accepted and response.next_cursor is None
        scope.raw_count += count
        scope.save(update_fields=["cursor", "outcome", "error_code", "enumeration_complete", "raw_count"])
        run.physical_bytes_received = sum(run.attempts.values_list("actual_response_bytes", flat=True))
        run.save(update_fields=["physical_bytes_received", "updated_at"])
        total_observations = run.observations.count()
        if accepted and total_observations:
            marker, marker_created = models.CollectionScopeRun.objects.get_or_create(
                run=run, scope_kind="release_integration", scope_key="post_capture",
                defaults={"phase": "release-integration-v1"},
            )
            if new_observations and not marker_created:
                marker = models.CollectionScopeRun.objects.select_for_update().get(pk=marker.pk)
                marker.outcome = "pending"
                marker.execution_state = "pending"
                marker.coverage_state = "pending"
                marker.retry_at = None
                marker.raw_count = 0
                marker.enumeration_complete = False
                marker.error_code = None
                marker.save(update_fields=["outcome", "execution_state", "coverage_state", "retry_at",
                                           "raw_count", "enumeration_complete", "error_code"])
    success = outcome == "found"
    exhausted = prior_attempts + 1 >= 3 or cursor_cycle
    finish_run(
        claim, typed=True, status="success" if success else "failed" if exhausted else "partial",
        retry_at=None if success or exhausted else timezone.now() + timedelta(hours=6),
        request_count=prior_requests + hf.requests,
        selected_count=total_observations, success_count=total_observations,
        error_code=None if success else outcome,
        physical_accounting_complete=all(a.get("http_status") is not None for a in response.attempts),
    )
    result = {"run_id": str(run.pk), "outcome": outcome, "request_count": prior_requests + hf.requests,
              "physical_requests": hf.requests}
    if expanded and accepted:
        result["metadata_coverage"] = response.outcome
    if accepted and total_observations:
        result["integration"] = integrate_acquisition_run(run.pk)
    return result


def drain_due_hf_acquisitions(*, client, limit=10, execute=False, job_ids=None):
    """Select a finite page of due HF or GitHub jobs; preview makes no calls."""
    from uuid import UUID

    from django.db.models import Exists, OuterRef, Q
    from django.utils import timezone

    from core import models
    from core.collection_state import BusyJob, StaleClaim
    from core.source_metric_projection import drain_pending_projections

    if type(limit) is not int or not 1 <= limit <= 100 or type(execute) is not bool:
        raise ValueError("Drain limit must be 1..100 and execute must be boolean")
    if job_ids is not None:
        if not isinstance(job_ids, (list, tuple)) or not 1 <= len(job_ids) <= 100:
            raise ValueError("Select 1..100 job identities")
        try:
            job_ids = [UUID(str(value)) for value in job_ids]
        except (ValueError, TypeError, AttributeError) as error:
            raise ValueError("Invalid job identity") from error
    now = timezone.now()
    pending = models.CollectionScopeRun.objects.filter(
        run__job_id=OuterRef("pk"), scope_kind="numeric_projection", outcome="pending",
    )
    pending_integration = models.CollectionScopeRun.objects.filter(
        Q(retry_at__isnull=True) | Q(retry_at__lte=now),
        run__job_id=OuterRef("pk"), scope_kind="release_integration", outcome="pending",
    )
    qs = models.CollectionJob.objects.filter(
            source_id__in=["hf", "github"], operation="release_acquisition", mode="manual", state="ready",
        ).annotate(projection_pending=Exists(pending), integration_pending=Exists(pending_integration)).filter(
            Q(last_success__isnull=True) | Q(projection_pending=True) | Q(integration_pending=True),
        ).filter(Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now) | Q(integration_pending=True))
    qs = qs.filter(Q(active_run__isnull=True) | Q(active_run__lease_expires_at__lte=now))
    if job_ids is not None:
        qs = qs.filter(pk__in=job_ids)
    jobs = qs.exclude(targets__target_role="registration_sweep").filter(
        ~Q(last_attempt__status="failed") | Q(projection_pending=True) | Q(integration_pending=True)
    ).order_by("created_at", "pk")
    rows = []
    skipped_excluded = 0
    for job in jobs.iterator(chunk_size=100):
        if not _has_eligible_claim(job):
            skipped_excluded += 1
            continue
        if not execute:
            result = {"outcome": "due", "physical_requests": 0,
                      "projection_pending": job.projection_pending}
        else:
            try:
                if job.integration_pending and job.active_run_id is None:
                    pending_scope = models.CollectionScopeRun.objects.filter(
                        Q(retry_at__isnull=True) | Q(retry_at__lte=now),
                        run__job=job, scope_kind="release_integration", outcome="pending",
                    ).order_by("pk").first()
                    result = {"outcome": "integration_only", "physical_requests": 0}
                    if pending_scope is not None:
                        result["integration"] = integrate_acquisition_run(pending_scope.run_id)
                elif (job.projection_pending and job.last_success_id is None
                        and job.last_attempt_id and job.last_attempt.status == "failed"):
                    result = {"outcome": "projection_only", "physical_requests": 0}
                else:
                    if job.source_id == "github":
                        result = execute_github_repository(job.pk, client=client)
                    elif job.targets.filter(target_role="model_card").exists():
                        from core.product_release_hf_card import execute_card

                        result = execute_card(job.pk, client=client)
                    else:
                        result = execute_hf_name_search(job.pk, client=client)
            except BusyJob:
                result = {"outcome": "busy", "physical_requests": 0}
            if job.source_id == "hf" and result["outcome"] in {"found", "projection_only"}:
                try:
                    result["projection"] = drain_pending_projections(job.pk)
                except (BusyJob, StaleClaim):
                    result["projection"] = {"pending": True, "outcome": "busy"}
                except ValueError as error:
                    if str(error) != "metric collection is already running":
                        raise
                    result["projection"] = {"pending": True, "outcome": "busy"}
        rows.append({"job_id": str(job.pk), **result})
        if len(rows) == limit:
            break
    return {"selected": len(rows), "provider_calls": sum(row["physical_requests"] for row in rows),
            "skipped_excluded": skipped_excluded, "jobs": rows}


def _source_bound_hf_repo(claim):
    """Return only a repo explicitly selected by the report and present in its Post."""
    from core.collection_capture import read_document
    from core.hf_metadata_client import REPO_ID
    from core.product_verification import _repo_from_hf_url, source_repo_evidence

    post = claim.event_dossier_source.post
    if post is None:
        return None
    candidates = []
    if claim.source_locator:
        candidates.append(_repo_from_hf_url(claim.source_locator))
    if claim.source_archive_id:
        packet = read_document(claim.source_archive)
        if isinstance(packet, dict) and isinstance(packet.get("record"), dict):
            candidates.append(packet["record"].get("candidate_repo_id"))
    for repo in candidates:
        if (isinstance(repo, str) and REPO_ID.fullmatch(repo)
                and source_repo_evidence(post, repo)["exact_hf_repo_link"]):
            return repo
    return None


def queue_hf_expanded_capture(claim_id, exact_observation_id):
    """Register a bounded metadata expansion using a retained exact capture."""
    from django.db import transaction

    from core import models
    from core.collection_jobs import register_job, set_job_state
    from core.measurement_taxonomy import digest, require
    from core.product_release_pipeline import canonical_dossier

    observation = models.CollectionObservation.objects.select_related("run__job").get(pk=exact_observation_id)
    require(observation.projection_kind == "hf-release-exact-v1", "exact model capture required")
    hf_exact_observation_documents(observation)
    claim = models.EventDossierClaim.objects.select_related("event_dossier_source").get(pk=claim_id)
    require(claim.event_dossier_source.collection_observation_id == observation.pk
            and claim.scope_key == f"hf_capture:{observation.pk}", "exact capture claim required")
    dossier = canonical_dossier(claim.event_dossier_source.event_dossier_id)
    latest = dossier.intake_decisions.order_by("-recorded_at", "-pk").first()
    require(not latest or latest.outcome not in {"non_release", "scam"}, "excluded release")
    repo = observation.source_identifier
    key = digest(["release-hf-expanded-v1", repo])
    with transaction.atomic():
        job = register_job(
            job_key="release-hf-expanded:" + key,
            source=models.DataSource.objects.get(pk="hf"), purpose="content",
            operation="release_acquisition", mode="manual", definition={"version": 2, "options": {}},
            settings={"owner_kind": "source", "schedule_kind": "manual", "schedule_driver": "manual",
                      "max_requests": 3, "max_bytes": 1048576, "max_seconds": 30, "max_items": 1},
            targets=[{"target_key": key, "native_identifier": repo, "target_kind": "model",
                      "target_role": "expanded_model", "resolution_state": "unresolved",
                      "gap_reason": "unresolved_product_identity"}],
        )
        link_claim_to_job(claim.pk, job.pk)
        if job.state == "paused" and not job.runs.exists():
            job = set_job_state(job.pk, "ready")
    if job.last_success_id:
        integrate_acquisition_run(job.last_success_id)
    return job


def queue_hf_search_hit(claim_id, search_observation_id):
    """Queue exact metadata for one retained search hit, without asserting identity."""
    from django.db import transaction

    from core import models
    from core.collection_jobs import register_job, set_job_state
    from core.hf_metadata_client import REPO_ID
    from core.measurement_taxonomy import digest, require
    from core.product_release_pipeline import canonical_dossier

    observation = models.CollectionObservation.objects.select_related("run__job").get(pk=search_observation_id)
    hf_search_observation_documents(observation)
    require(observation.run.status in {"success", "partial", "failed"}, "saved search page required")
    claim = models.EventDossierClaim.objects.select_related("event_dossier_source").get(pk=claim_id)
    require(claim.event_dossier_source.collection_observation_id == observation.pk
            and claim.scope_key == f"hf_capture:{observation.pk}", "search hit claim required")
    dossier = canonical_dossier(claim.event_dossier_source.event_dossier_id)
    linked_ids = observation.run.job.dossier_claim_links.values_list(
        "claim__event_dossier_source__event_dossier_id", flat=True
    )
    require(any(canonical_dossier(pk).pk == dossier.pk for pk in linked_ids),
            "search was not linked to this dossier")
    latest = dossier.intake_decisions.order_by("-recorded_at", "-pk").first()
    require(not latest or latest.outcome not in {"non_release", "scam"}, "excluded release")
    repo = observation.source_identifier
    require(REPO_ID.fullmatch(repo), "invalid repository identity")
    key = digest(["release-hf-exact-v1", repo])
    with transaction.atomic():
        job = register_job(
            job_key="release-hf-exact:" + key,
            source=models.DataSource.objects.get(pk="hf"), purpose="content",
            operation="release_acquisition", mode="manual", definition={"version": 2, "options": {}},
            settings={"owner_kind": "source", "schedule_kind": "manual", "schedule_driver": "manual",
                      "max_requests": 3, "max_bytes": 1048576, "max_seconds": 30, "max_items": 10},
            targets=[{"target_key": key, "native_identifier": repo, "target_kind": "model",
                      "target_role": "exact_model", "resolution_state": "unresolved",
                      "gap_reason": "unresolved_product_identity"}],
        )
        link_claim_to_job(claim.pk, job.pk)
        if job.state == "paused" and not job.runs.exists():
            job = set_job_state(job.pk, "ready")
    if job.last_success_id:
        integrate_acquisition_run(job.last_success_id)
    return job


def queue_hf_publisher_socials(claim_id, exact_observation_id):
    """Register a shared, bounded publisher-link lookup from captured repo evidence."""
    from django.db import transaction

    from core import models
    from core.collection_jobs import register_job, set_job_state
    from core.hf_metadata_client import NAMESPACE
    from core.measurement_taxonomy import digest, require
    from core.product_release_pipeline import canonical_dossier

    observation = models.CollectionObservation.objects.select_related("run__job").get(pk=exact_observation_id)
    hf_exact_observation_documents(observation)
    require(observation.run.job.dossier_claim_links.filter(claim_id=claim_id).exists(),
            "publisher lookup requires the original acquisition claim")
    claim = models.EventDossierClaim.objects.select_related("event_dossier_source").get(pk=claim_id)
    dossier = canonical_dossier(claim.event_dossier_source.event_dossier_id)
    latest = dossier.intake_decisions.order_by("-recorded_at", "-pk").first()
    require(not latest or latest.outcome not in {"non_release", "scam"}, "excluded release")
    namespace = observation.source_identifier.split("/", 1)[0]
    require(NAMESPACE.fullmatch(namespace), "invalid publisher namespace")
    key = digest(["release-hf-publisher-socials-v1", namespace])
    with transaction.atomic():
        job = register_job(
            job_key="release-hf-socials:" + key,
            source=models.DataSource.objects.get(pk="hf"), purpose="content",
            operation="release_acquisition", mode="manual", definition={"version": 2, "options": {}},
            settings={"owner_kind": "source", "schedule_kind": "manual", "schedule_driver": "manual",
                      "max_requests": 3, "max_bytes": 1048576, "max_seconds": 30, "max_items": 1},
            targets=[{"target_key": key, "native_identifier": namespace, "target_kind": "account",
                      "target_role": "publisher_socials", "resolution_state": "unresolved",
                      "gap_reason": "unverified_publisher"}],
        )
        link_claim_to_job(claim.pk, job.pk)
        if job.state == "paused" and not job.runs.exists():
            job = set_job_state(job.pk, "ready")
    if job.last_success_id:
        integrate_acquisition_run(job.last_success_id)
    return job


def _source_bound_raw_name(claim):
    """Recompute the deterministic lead from the current saved source text."""
    from core.product_release_intake import raw_versioned_name_leads

    post = claim.event_dossier_source.post
    if post is None or not post.text:
        return None
    for lead in raw_versioned_name_leads(post.text):
        if lead["term"] == claim.assertion_text:
            return lead["term"]
    return None


def github_exact_observation_documents(observation):
    """Resolve an exact public repository from its original checked response."""
    from core.collection_capture import read_document
    from core.github_metadata_client import GitHubMetadataClient
    from core.measurement_taxonomy import digest, require

    run, scope = observation.run, observation.scope_run
    require(observation.projection_kind == "github-release-exact-v1"
            and run.job.source_id == "github" and run.job.operation == "release_acquisition"
            and scope is not None and scope.run_id == run.pk
            and scope.scope_kind == "release_acquisition", "GitHub observation ownership mismatch")
    links = list(observation.inputs.select_related("input_request__archive", "input_request__attempt"))
    require(len(links) == 1, "GitHub observation needs one captured response")
    link = links[0]
    request = link.input_request
    require(link.input_role == "github_exact" and request is not None
            and request.scope_run_id == scope.pk and request.attempt.run_id == run.pk
            and request.transport_outcome == "received" and request.http_status == 200
            and request.archive_id is not None and link.input_sha256 == request.archive.content_sha256,
            "GitHub response ownership or checksum mismatch")
    target = run.job.targets.get(target_role="exact_repository")
    require(request.endpoint_url == GitHubMetadataClient.repo_url(target.native_identifier),
            "GitHub response endpoint or target mismatch")
    row = read_document(request.archive)
    require(isinstance(row, dict) and row.get("private") is False
            and isinstance(row.get("full_name"), str)
            and row["full_name"].casefold() == target.native_identifier.casefold()
            and type(row.get("id")) is int and str(row["id"]) == observation.source_identifier
            and digest(row) == observation.payload_sha256, "GitHub repository identity or content changed")
    return row, {"kind": "repository"}, {}


def integrate_github_capture(observation):
    """Attach a verified saved capture to every currently linked dossier."""
    from django.db import transaction

    from core.event_dossiers import add_claim, attach_source
    from core.product_release_pipeline import canonical_dossier

    with transaction.atomic():
        row, _, _ = github_exact_observation_documents(observation)
        request = observation.inputs.select_related("input_request").get().input_request
        for link in observation.run.job.dossier_claim_links.select_related("claim__event_dossier_source"):
            dossier = canonical_dossier(link.claim.event_dossier_source.event_dossier_id)
            event_source = attach_source(dossier.pk, observation_id=observation.pk)
            add_claim(event_source.pk, claim_kind="release_context",
                      scope_key=f"github_capture:{observation.pk}",
                      assertion_text=f"Captured GitHub repository {row['full_name']}; its release role and ownership are unresolved",
                      source_excerpt=row["full_name"], source_locator=f"https://github.com/{row['full_name']}",
                      source_archive_id=request.archive_id, extraction_version="github-release-exact-v1")


def execute_github_repository(job_id, *, client):
    """Fetch one public GitHub repository, retaining evidence without confirming ownership."""
    from datetime import timedelta

    from django.utils import timezone

    from core import models
    from core.collection_capture import RequestCapture, link_request
    from core.collection_state import claim_job, fenced_run, finish_run
    from core.github_metadata_client import GitHubMetadataClient
    from core.measurement_taxonomy import digest, require
    from scripts.benchmark_download_collector.sources import Budget, SourceError

    job = models.CollectionJob.objects.get(pk=job_id)
    require(job.source_id == "github" and job.operation == "release_acquisition"
            and job.mode == "manual", "manual GitHub acquisition required")
    require(job.dossier_claim_links.exists(), "acquisition needs a source claim")
    if not _has_eligible_claim(job):
        return {"outcome": "excluded", "physical_requests": 0}
    if job.last_success_id:
        observation = job.last_success.observations.get(projection_kind="github-release-exact-v1")
        integrate_github_capture(observation)
        return {"outcome": "found", "run_id": str(job.last_success_id), "physical_requests": 0}
    attempts = models.CollectionAttempt.objects.filter(run__job=job).count()
    checkpointed = bool(job.last_attempt_id and job.last_attempt.completed_at is None
                        and job.last_attempt.scopes.filter(scope_kind="release_acquisition",
                            scope_key="execution", outcome="found", enumeration_complete=True).exists())
    require(attempts < 3 or checkpointed, "acquisition retry limit exhausted")
    lease = claim_job(job.pk, typed=True, manual_authorized=True)
    run = models.CollectionRun.objects.get(pk=lease.run_id)
    scope = run.scopes.get(scope_kind="release_acquisition", scope_key="execution")
    if scope.outcome == "found" and scope.enumeration_complete:
        observation = run.observations.get(projection_kind="github-release-exact-v1")
        integrate_github_capture(observation)
        prior = sum(run.attempts.exclude(pk=lease.attempt_id).values_list("actual_requests", flat=True))
        finish_run(lease, typed=True, status="success", request_count=prior,
                   selected_count=1, success_count=1, physical_accounting_complete=True)
        return {"outcome": "found", "run_id": str(run.pk), "physical_requests": 0}
    target = job.targets.get(target_role="exact_repository")
    budget = Budget(client, max_requests=job.max_requests, max_seconds=job.max_seconds,
                    max_bytes=job.max_bytes, cumulative=True)
    github = GitHubMetadataClient(budget)
    github.capture, github.collection_scope = RequestCapture(lease), scope
    try:
        response = github.repository(target.native_identifier)
        row = response.payload
        if response.status == 200 and isinstance(row, dict) and row.get("private") is False:
            outcome = ("found" if isinstance(row.get("full_name"), str)
                       and row["full_name"].casefold() == target.native_identifier.casefold()
                       and type(row.get("id")) is int and row["id"] > 0 else "identity_mismatch")
        elif response.status == 404:
            outcome = "missing_or_private"
        elif response.status == 401:
            outcome = "unauthorized"
        elif response.status == 403:
            outcome = "forbidden_or_throttled"
        elif response.status == 429:
            outcome = "throttled"
        elif response.status == 200 and isinstance(row, dict) and row.get("private") is True:
            outcome = "private"
        elif response.status == 200:
            outcome = "private_or_unverified"
        else:
            outcome = "http_error"
    except SourceError:
        response, row, outcome = None, None, "request_error"
    with fenced_run(lease):
        if outcome == "found":
            request = models.CollectionRequest.objects.select_related("archive").get(
                pk=response.collection_request_id
            )
            require(request.archive_id is not None, "public repository capture required")
            observation, created = models.CollectionObservation.objects.get_or_create(
                run=run, observation_key=digest(["github-release-exact-v1", row["id"], digest(row)]),
                defaults={"scope_run": scope, "source_identifier": str(row["id"]),
                          "source_subject_kind": "repository", "observation_kind": "github_release_exact",
                          "projection_kind": "github-release-exact-v1", "payload_sha256": digest(row),
                          "observed_at": request.received_at, "processing_outcome": "unresolved"},
            )
            if created:
                link_request(observation, request, role="github_exact")
            integrate_github_capture(observation)
        scope.outcome = outcome
        scope.error_code = None if outcome == "found" else outcome
        scope.enumeration_complete = outcome == "found"
        scope.raw_count = int(outcome == "found")
        scope.save(update_fields=["outcome", "error_code", "enumeration_complete", "raw_count"])
    physical = job.max_requests - budget.remaining
    prior = sum(run.attempts.exclude(pk=lease.attempt_id).values_list("actual_requests", flat=True))
    success = outcome == "found"
    retry_at = timezone.now() + timedelta(hours=6)
    if response and response.retry_at:
        retry_at = max(retry_at, response.retry_at)
    finish_run(lease, typed=True, status="success" if success else "failed" if attempts + 1 >= 3 else "partial",
               retry_at=None if success or attempts + 1 >= 3 else retry_at,
               request_count=prior + physical, selected_count=int(success), success_count=int(success),
               error_code=None if success else outcome, physical_accounting_complete=response is not None)
    return {"outcome": outcome, "run_id": str(run.pk), "physical_requests": physical}


def _source_bound_github_repo(claim):
    from core.measurement_taxonomy import digest
    from core.product_release_sources import stored_posts

    source = claim.event_dossier_source
    if not source.post_id:
        return None
    candidate = detect(stored_posts([source.post_id])[0].record)
    if not candidate:
        return None
    matches = {ref.native_identifier for ref in candidate.references
               if ref.provider == "github" and ref.repository_type == "repository"
               and ref.url == claim.source_locator
               and claim.scope_key == "github_repo_lead:" + digest(ref.native_identifier.casefold())}
    return matches.pop() if len(matches) == 1 else None


def queue_github_repository(claim_id):
    """Register an exact GitHub lookup only for a retained source-backed lead.

    Registration makes no provider request and does not assert that the linked
    repository is the announced product or that its owner controls the Post.
    """
    from django.db import transaction

    from core import models
    from core.collection_jobs import register_job, set_job_state
    from core.github_catalog import register_github_source
    from core.github_metadata_client import GitHubMetadataClient
    from core.measurement_taxonomy import digest, require
    from core.product_release_pipeline import canonical_dossier

    with transaction.atomic():
        claim = models.EventDossierClaim.objects.select_related(
            "claim_kind_reference", "event_dossier_source__event_dossier__event_kind_reference"
        ).get(pk=claim_id)
        source = claim.event_dossier_source
        dossier = canonical_dossier(source.event_dossier_id)
        require(dossier.event_kind_reference.code == "product_release"
                and claim.claim_kind_reference.code == "release_context"
                and claim.scope_key.startswith("github_repo_lead:")
                and source.post_id is not None, "source-backed GitHub lead required")
        latest = dossier.intake_decisions.order_by("-recorded_at", "-pk").first()
        require(not latest or latest.outcome not in {"non_release", "scam"}, "excluded release")
        repo = _source_bound_github_repo(claim)
        require(repo is not None, "repository lead differs from saved source")
        GitHubMetadataClient.repo_url(repo)
        key = digest(["release-github-exact-v1", repo.casefold()])
        job = register_job(
            job_key="release-github-exact:" + key,
            source=register_github_source(), purpose="content",
            operation="release_acquisition", mode="manual", definition={"version": 2, "options": {}},
            settings={"owner_kind": "source", "schedule_kind": "manual", "schedule_driver": "manual",
                      "max_requests": 3, "max_bytes": 1048576, "max_seconds": 30, "max_items": 1},
            targets=[{"target_key": key, "native_identifier": repo, "target_kind": "repository",
                      "target_role": "exact_repository", "resolution_state": "unresolved",
                      "gap_reason": "unresolved_product_identity"}],
        )
        link_claim_to_job(claim.pk, job.pk)
        if job.state == "paused" and not job.runs.exists():
            job = set_job_state(job.pk, "ready")
    if job.last_success_id:
        integrate_github_capture(job.last_success.observations.get(projection_kind="github-release-exact-v1"))
    return job


def queue_hf_name_search(claim_id):
    """Queue a bounded source-linked exact lookup, or search the reported name."""
    from django.db import transaction

    from core import models
    from core.collection_jobs import register_job, set_job_state
    from core.measurement_taxonomy import digest
    from core.product_release_pipeline import canonical_dossier

    with transaction.atomic():
        claim = models.EventDossierClaim.objects.select_related(
            "claim_kind_reference", "event_dossier_source__event_dossier__event_kind_reference"
        ).get(pk=claim_id)
        dossier = canonical_dossier(claim.event_dossier_source.event_dossier_id)
        is_report = claim.claim_kind_reference.code == "release_report"
        is_repo_lead = (claim.claim_kind_reference.code == "release_context"
                        and claim.scope_key.startswith("hf_repo_lead:"))
        is_name_lead = (claim.claim_kind_reference.code == "release_context"
                        and claim.scope_key.startswith("hf_name_lead:"))
        if dossier.event_kind_reference.code != "product_release" or not (is_report or is_repo_lead or is_name_lead):
            raise ValueError("Saved product-release name or repository lead required")
        latest = dossier.intake_decisions.order_by("-recorded_at", "-pk").first()
        if latest and latest.outcome in {"non_release", "scam"}:
            raise ValueError("Excluded release is not eligible for acquisition")
        repo = _source_bound_hf_repo(claim)
        if is_repo_lead and not repo:
            raise ValueError("Repository lead is not present in the source post")
        if is_name_lead and not _source_bound_raw_name(claim):
            raise ValueError("Name lead is not present in the source post")
        if repo:
            term = repo
        else:
            candidate = detect(SourceRecord(
                "dossier-claim", str(claim.pk),
                (TextEvidence(f"event_dossier_claims:{claim.pk}", "release_extraction", claim.assertion_text),),
            ))
            leads = search_leads(candidate) if candidate else ()
            if len(leads) != 1 or not leads[0]["eligible"]:
                raise ValueError("Saved name is not eligible for bounded search")
            term = leads[0]["term"]
        role = "exact_model" if repo else "name_search"
        key = digest(["release-hf-exact-v1" if repo else "release-hf-name-search-v1", term])
        job = register_job(
            job_key=("release-hf-exact:" if repo else "release-hf-search:") + key,
            source=models.DataSource.objects.get(pk="hf"),
            purpose="content", operation="release_acquisition", mode="manual",
            definition={"version": 2, "options": {}},
            settings={
                "owner_kind": "source", "schedule_kind": "manual", "schedule_driver": "manual",
                "max_requests": 3, "max_bytes": 1048576, "max_seconds": 30, "max_items": 10,
            },
            targets=[{
                "target_key": key, "native_identifier": term, "target_kind": "model",
                "target_role": role, "resolution_state": "unresolved",
                "gap_reason": "unresolved_product_identity",
            }],
        )
        link_claim_to_job(claim.pk, job.pk)
        if job.state == "paused" and not job.runs.exists():
            job = set_job_state(job.pk, "ready")
    if job.last_success_id:
        integrate_acquisition_run(job.last_success_id)
    return job


def queue_saved_release_claims(*, limit=100, after=None, persist=False):
    """Sweep unqueued release reports and source-backed repository leads.

    The cursor is an exclusive (recorded_at, claim UUID) pair. A restart from
    the beginning skips claims already linked to this operation; unsearchable
    and excluded claims remain visible in the returned page rather than being
    marked as fraud or silently dropped.
    """
    from uuid import UUID

    from django.db.models import Exists, OuterRef, Q
    from django.utils.dateparse import parse_datetime

    from core import models
    from core.product_release_pipeline import canonical_dossier

    if type(limit) is not int or not 1 <= limit <= 1000 or type(persist) is not bool:
        raise ValueError("Sweep limit must be 1..1000 and persist must be boolean")
    links = models.EventDossierClaimCollectionJob.objects.filter(
        claim_id=OuterRef("pk"), job__operation="release_acquisition"
    )
    qs = models.EventDossierClaim.objects.filter(
        Q(claim_kind_reference__code="release_report")
        | Q(claim_kind_reference__code="release_context", scope_key__startswith="hf_repo_lead:")
        | Q(claim_kind_reference__code="release_context", scope_key__startswith="hf_name_lead:")
        | Q(claim_kind_reference__code="release_context", scope_key__startswith="github_repo_lead:"),
        event_dossier_source__event_dossier__event_kind_reference__code="product_release",
    ).annotate(already_queued=Exists(links)).filter(already_queued=False)
    if after is not None:
        if not isinstance(after, dict) or set(after) != {"recorded_at", "claim_id"}:
            raise ValueError("Invalid acquisition sweep cursor")
        try:
            when = parse_datetime(after["recorded_at"])
            identifier = UUID(after["claim_id"])
        except (TypeError, ValueError, AttributeError) as error:
            raise ValueError("Invalid acquisition sweep cursor") from error
        if when is None or when.tzinfo is None:
            raise ValueError("Acquisition cursor requires an aware timestamp")
        qs = qs.filter(Q(recorded_at__gt=when) | Q(recorded_at=when, pk__gt=identifier))
    claims = list(qs.select_related("event_dossier_source").order_by("recorded_at", "pk")[:limit])
    results = []
    for claim in claims:
        dossier = canonical_dossier(claim.event_dossier_source.event_dossier_id)
        latest = dossier.intake_decisions.order_by("-recorded_at", "-pk").first()
        if claim.scope_key.startswith("github_repo_lead:"):
            eligible = bool(_source_bound_github_repo(claim))
        elif claim.scope_key.startswith("hf_repo_lead:"):
            eligible = bool(_source_bound_hf_repo(claim))
        elif claim.scope_key.startswith("hf_name_lead:"):
            eligible = bool(_source_bound_raw_name(claim))
        else:
            candidate = detect(SourceRecord(
                "dossier-claim", str(claim.pk),
                (TextEvidence(f"event_dossier_claims:{claim.pk}", "release_extraction", claim.assertion_text),),
            ))
            leads = search_leads(candidate) if candidate else ()
            eligible = bool(leads and leads[0]["eligible"])
        if latest and latest.outcome in {"non_release", "scam"}:
            outcome = "excluded"
        elif not eligible:
            outcome = "ineligible"
        elif persist:
            try:
                job = (queue_github_repository(claim.pk) if claim.scope_key.startswith("github_repo_lead:")
                       else queue_hf_name_search(claim.pk))
                outcome = "queued"
            except Exception:
                import logging

                logging.getLogger(__name__).exception("Release registration recovery failed for claim %s", claim.pk)
                outcome = "registration_failed"
        else:
            outcome = "eligible"
        results.append({"claim_id": str(claim.pk), "outcome": outcome,
                        "job_id": str(job.pk) if outcome == "queued" else None})
    cursor = ({"recorded_at": claims[-1].recorded_at.isoformat(),
               "claim_id": str(claims[-1].pk)} if claims else after)
    return {"scanned": len(claims), "queued": sum(row["outcome"] == "queued" for row in results),
            "complete": len(claims) < limit, "next_cursor": cursor, "claims": results}


def recover_release_registrations(*, limit=25):
    """Revisit one durable bounded page; completed scans restart on the next wake-up."""
    import json

    from core import models
    from core.collection_jobs import register_job, set_job_state
    from core.collection_state import BusyJob, claim_job, fenced_run, finish_run
    from core.measurement_taxonomy import digest

    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Recovery page limit must be 1..100")
    key = digest(["release-registration-sweep-v1"])
    job = register_job(
        job_key="release-registration-sweep:" + key,
        source=models.DataSource.objects.get(pk="hf"), purpose="content",
        operation="release_acquisition", mode="manual", definition={"version": 2, "options": {}},
        settings={"owner_kind": "source", "schedule_kind": "manual", "schedule_driver": "manual",
                  "max_requests": 1, "max_bytes": 1048576, "max_seconds": 30, "max_items": 100},
        targets=[{"target_key": key, "native_identifier": "saved-release-claims", "target_kind": "query",
                  "target_role": "registration_sweep", "resolution_state": "unresolved",
                  "gap_reason": "registration_recovery"}],
    )
    if job.state == "paused" and not job.runs.exists():
        job = set_job_state(job.pk, "ready")
    try:
        lease = claim_job(job.pk, typed=True, manual_authorized=True)
    except BusyJob:
        return {"status": "busy", "scanned": 0, "queued": 0}
    run = models.CollectionRun.objects.get(pk=lease.run_id)
    scope = run.scopes.get(scope_kind="release_acquisition", scope_key="execution")
    after = json.loads(scope.cursor) if scope.cursor else None
    result = queue_saved_release_claims(limit=limit, after=after, persist=True)
    with fenced_run(lease):
        scope.cursor = json.dumps(result["next_cursor"], sort_keys=True) if result["next_cursor"] else None
        scope.enumeration_complete = result["complete"]
        scope.outcome = "complete" if result["complete"] else "pending"
        scope.raw_count += result["scanned"]
        scope.save(update_fields=["cursor", "enumeration_complete", "outcome", "raw_count"])
    finish_run(lease, typed=True, status="success" if result["complete"] else "partial",
               request_count=0, selected_count=result["scanned"], success_count=result["queued"],
               physical_accounting_complete=True)
    return {"status": scope.outcome, **result}


def link_claim_to_job(claim_id, job_id):
    """Record why a job is relevant without changing its sealed instructions."""
    from core import models

    claim = models.EventDossierClaim.objects.select_related(
        "event_dossier_source__event_dossier__event_kind_reference"
    ).get(pk=claim_id)
    if claim.event_dossier_source.event_dossier.event_kind_reference.code != "product_release":
        raise ValueError("Product-release claim required")
    return models.EventDossierClaimCollectionJob.objects.get_or_create(
        claim=claim, job_id=job_id
    )[0]


def dossier_name_leads(dossier_id):
    """Read only names claimed for this dossier, even when a Post spans releases."""
    from core import models
    from core.product_release_pipeline import canonical_dossier

    dossier = canonical_dossier(dossier_id)
    if dossier.event_kind_reference.code != "product_release":
        raise ValueError("Product-release dossier required")
    claims = models.EventDossierClaim.objects.filter(
        event_dossier_source__event_dossier=dossier,
        claim_kind_reference__code="release_report",
    ).order_by("recorded_at", "pk")
    rows = []
    for claim in claims:
        source = SourceRecord(
            "dossier-claim",
            str(claim.pk),
            (TextEvidence(f"event_dossier_claims:{claim.pk}", "release_extraction", claim.assertion_text),),
        )
        candidate = detect(source)
        if candidate:
            rows.extend(
                {**lead, "event_dossier_source_id": claim.event_dossier_source_id}
                for lead in search_leads(candidate)
            )
    return rows


def search_saved_names(candidate, client, *, limit=10):
    """Search saved names while preserving their source locators and unresolved gaps.

    The supplied client owns the physical request/time/byte budgets and capture
    hooks. Identical names share one lookup within this invocation. Returned
    repository identifiers are leads, not verified release or publisher claims.
    """
    return _search_leads(
        search_leads(candidate), client, limit=limit,
        excluded=candidate.disposition == "excluded",
    )


def search_dossier_names(dossier_id, client, *, limit=10):
    """Search names belonging to one dossier, keeping reviewed exclusions intact."""
    from core.product_release_pipeline import canonical_dossier

    dossier = canonical_dossier(dossier_id)
    latest = dossier.intake_decisions.order_by("-recorded_at", "-pk").first()
    return _search_leads(
        dossier_name_leads(dossier.pk), client, limit=limit,
        excluded=bool(latest and latest.outcome in {"non_release", "scam"}),
    )


def _search_leads(leads, client, *, limit, excluded):
    cache = {}
    results = []
    for lead in leads:
        row = {**lead, "repository_ids": [], "next_cursor": None, "attempts": []}
        if excluded:
            row["outcome"] = "excluded"
        elif not lead["eligible"]:
            row["outcome"] = "ineligible"
        else:
            term = lead["term"]
            if term not in cache:
                cache[term] = client.search_models(term, limit=limit)
            response = cache[term]
            row["outcome"] = response.outcome
            row["next_cursor"] = response.next_cursor
            row["attempts"] = response.attempts
            if response.outcome == "ok":
                row["repository_ids"] = [
                    item.get("id") or item["modelId"] for item in response.payload
                ]
        results.append(row)
    return results
