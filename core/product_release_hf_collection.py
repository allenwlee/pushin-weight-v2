"""Source-qualified family names from publisher-owned Hugging Face collections."""

import re

from core.hf_metadata_client import REPO_ID

_COLLECTION_SLUG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,63}/[A-Za-z0-9_][A-Za-z0-9._-]{0,160}\Z")


def family_from_collection(document, repo):
    """Accept a title only when every collection member is in the same model line.

    The list endpoint contains only a preview; callers must pass the complete
    collection detail. An ambiguous or mixed collection is evidence, but not a
    family assignment.
    """
    if not isinstance(repo, str) or not REPO_ID.fullmatch(repo) or not isinstance(document, dict):
        return None
    owner = document.get("owner")
    owner = owner.get("name") if isinstance(owner, dict) else owner
    namespace = repo.split("/", 1)[0]
    title, slug, items = document.get("title"), document.get("slug"), document.get("items")
    if (not isinstance(owner, str) or owner.casefold() != namespace.casefold()
            or not isinstance(slug, str) or not _COLLECTION_SLUG.fullmatch(slug)
            or slug.split("/", 1)[0].casefold() != namespace.casefold()
            or not isinstance(title, str) or title != title.strip()
            or not 2 <= len(title) <= 100 or not isinstance(items, list)
            or not 1 <= len(items) <= 100):
        return None
    title_pattern = re.compile(r"^" + re.escape(title) + r"(?:$|[-_. ])", re.IGNORECASE)
    model_ids = []
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "model":
            return None
        item_id = item.get("id")
        if (not isinstance(item_id, str) or not REPO_ID.fullmatch(item_id)
                or item_id.split("/", 1)[0].casefold() != namespace.casefold()
                or not title_pattern.match(item_id.split("/", 1)[1])):
            return None
        model_ids.append(item_id.casefold())
    if repo.casefold() not in model_ids:
        return None
    return {"name": title, "source_excerpt": title,
            "source_locator": "https://huggingface.co/collections/" + slug}


PROJECTION = "hf-release-collection-v1"


def _target(job):
    from core.measurement_taxonomy import require

    repo = job.targets.get(target_role="model_collection").native_identifier
    require(isinstance(repo, str) and REPO_ID.fullmatch(repo), "invalid collection target")
    return repo


def collection_documents(observation):
    """Read and verify the exact retained detail response and its owner."""
    from core.collection_capture import read_document
    from core.measurement_taxonomy import require

    run, scope = observation.run, observation.scope_run
    require(observation.projection_kind == PROJECTION and run.job.source_id == "hf"
            and run.job.operation == "release_acquisition" and scope is not None
            and scope.run_id == run.pk and scope.scope_kind == "release_acquisition",
            "collection observation ownership mismatch")
    links = list(observation.inputs.select_related("input_request__archive", "input_request__attempt"))
    require(len(links) == 1, "collection needs one captured detail response")
    link = links[0]
    request = link.input_request
    require(link.input_role == "hf_model_collection" and request is not None
            and request.scope_run_id == scope.pk and request.attempt.run_id == run.pk
            and request.transport_outcome == "received" and request.http_status == 200
            and request.archive_id is not None and link.input_sha256 == request.archive.content_sha256
            and observation.payload_sha256 == request.archive.content_sha256,
            "collection response ownership or checksum mismatch")
    document = read_document(request.archive)
    slug = document.get("slug") if isinstance(document, dict) else None
    require(isinstance(slug, str) and _COLLECTION_SLUG.fullmatch(slug)
            and request.endpoint_url == f"https://huggingface.co/api/collections/{slug}"
            and observation.source_identifier.casefold() == _target(run.job).casefold(),
            "collection detail endpoint mismatch")
    return document, {"kind": "model_collection"}, {}


def integrate_collection(observation):
    """Attach the source and apply its name only to the exact existing Product."""
    from core import models
    from core.event_dossiers import add_claim, attach_source
    from core.product_identity import _apply_reported_family_name, _ensure_model_family
    from core.product_release_pipeline import canonical_dossier

    document, _, _ = collection_documents(observation)
    repo = _target(observation.run.job)
    family = family_from_collection(document, repo)
    if family is None:
        return 0
    product = models.Product.objects.filter(repo_id__iexact=repo).select_related("product_type").first()
    if product is None or not product.brand_id:
        return 0
    request = observation.inputs.select_related("input_request").get().input_request
    applied = 0
    for link in observation.run.job.dossier_claim_links.select_related("claim__event_dossier_source"):
        dossier = canonical_dossier(link.claim.event_dossier_source.event_dossier_id)
        latest = dossier.intake_decisions.order_by("-recorded_at", "-pk").first()
        if latest and latest.outcome in {"non_release", "scam", "superseded"}:
            continue
        source = attach_source(dossier.pk, observation_id=observation.pk)
        claim = add_claim(source.pk, claim_kind="release_context", scope_key=f"hf_collection:{observation.pk}",
                          assertion_text=family["name"], source_excerpt=family["source_excerpt"],
                          source_locator=family["source_locator"], source_archive_id=request.archive_id,
                          extraction_version=PROJECTION)
        _ensure_model_family(product, {"observed_name": product.display_name}, claim)
        applied += int(_apply_reported_family_name(product, family, claim) is not None)
    return applied


def queue_collection(claim_id, exact_observation_id):
    """Queue bounded discovery only for an already captured exact model."""
    from core import models
    from core.collection_jobs import register_job, set_job_state
    from core.measurement_taxonomy import digest, require
    from core.product_release_acquisition import hf_exact_observation_documents, link_claim_to_job
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
    require(REPO_ID.fullmatch(repo), "invalid repository")
    key = digest([PROJECTION, repo.casefold()])
    job = register_job(
        job_key="release-hf-collection:" + key, source=models.DataSource.objects.get(pk="hf"),
        purpose="content", operation="release_acquisition", mode="manual", definition={"version": 2, "options": {}},
        settings={"owner_kind": "source", "schedule_kind": "manual", "schedule_driver": "manual",
                  "max_requests": 3, "max_bytes": 1048576, "max_seconds": 30, "max_items": 1},
        targets=[{"target_key": key, "native_identifier": repo, "target_kind": "model",
                  "target_role": "model_collection", "resolution_state": "unresolved",
                  "gap_reason": "unresolved_product_identity"}],
    )
    link_claim_to_job(claim.pk, job.pk)
    if job.state == "paused" and not job.runs.exists():
        job = set_job_state(job.pk, "ready")
    if job.last_success_id:
        from core.product_release_acquisition import integrate_acquisition_run

        integrate_acquisition_run(job.last_success_id)
    return job


def execute_collection(job_id, *, client):
    """Capture at most one publisher collection, with explicit request budgets."""
    from datetime import timedelta

    from django.utils import timezone

    from core import models
    from core.collection_capture import RequestCapture, link_request
    from core.collection_state import claim_job, fenced_run, finish_run
    from core.hf_metadata_client import HFMetadataClient
    from core.measurement_taxonomy import digest, require
    from core.product_release_acquisition import _has_eligible_claim, integrate_acquisition_run

    job = models.CollectionJob.objects.get(pk=job_id)
    require(job.source_id == "hf" and job.operation == "release_acquisition"
            and job.mode == "manual" and job.dossier_claim_links.exists(), "manual collection acquisition required")
    repo = _target(job)
    if not _has_eligible_claim(job):
        return {"outcome": "excluded", "physical_requests": 0}
    if job.last_success_id:
        integrate_acquisition_run(job.last_success_id)
        return {"outcome": "found", "run_id": str(job.last_success_id), "physical_requests": 0}
    attempts = models.CollectionAttempt.objects.filter(run__job=job).count()
    checkpointed = bool(job.last_attempt_id and job.last_attempt.completed_at is None
                        and job.last_attempt.scopes.filter(scope_kind="release_acquisition",
                            scope_key="execution", outcome="found", enumeration_complete=True).exists())
    require(attempts < 3 or checkpointed, "collection retry limit exhausted")
    lease = claim_job(job.pk, typed=True, manual_authorized=True)
    run = models.CollectionRun.objects.get(pk=lease.run_id)
    scope = run.scopes.get(scope_kind="release_acquisition", scope_key="execution")
    if scope.outcome == "found" and scope.enumeration_complete:
        prior = sum(run.attempts.exclude(pk=lease.attempt_id).values_list("actual_requests", flat=True))
        count = run.observations.filter(projection_kind=PROJECTION).count()
        finish_run(lease, typed=True, status="success", request_count=prior,
                   selected_count=count, success_count=count, physical_accounting_complete=True)
        if count:
            integrate_acquisition_run(run.pk)
        return {"outcome": "found", "run_id": str(run.pk), "physical_requests": 0}
    hf = HFMetadataClient(client, max_requests=job.max_requests, max_seconds=job.max_seconds,
                          max_bytes=job.max_bytes, max_total_bytes=job.max_bytes)
    hf.capture, hf.collection_scope = RequestCapture(lease), scope
    listing = hf._get("/collections", params={"owner": repo.split("/", 1)[0], "item": "models/" + repo, "limit": 20})
    outcome, detail, request_record = listing.outcome, None, None
    transport_attempts = list(listing.attempts)
    if listing.outcome == "ok" and isinstance(listing.payload, list):
        # A full page can be truncated; do not claim uniqueness in that case.
        candidates = []
        for entry in listing.payload:
            if not isinstance(entry, dict):
                continue
            slug, title = entry.get("slug"), entry.get("title")
            owner = entry.get("owner")
            owner = owner.get("name") if isinstance(owner, dict) else owner
            if (isinstance(slug, str) and _COLLECTION_SLUG.fullmatch(slug)
                    and slug.split("/", 1)[0].casefold() == repo.split("/", 1)[0].casefold()
                    and isinstance(owner, str) and owner.casefold() == repo.split("/", 1)[0].casefold()
                    and isinstance(title, str) and 2 <= len(title) <= 100
                    and re.match(r"^" + re.escape(title) + r"(?:$|[-_. ])", repo.split("/", 1)[1], re.IGNORECASE)):
                candidates.append(slug)
        if len(listing.payload) >= 20 or len(set(candidates)) != 1:
            outcome = "found"  # no unambiguous publisher-named line
        else:
            slug = candidates[0]
            response = hf._get("/collections/" + slug)
            outcome = response.outcome
            transport_attempts.extend(response.attempts)
            if response.outcome == "ok" and isinstance(response.payload, dict):
                detail = response.payload
                attempt = next((entry for entry in reversed(response.attempts)
                                if entry.get("outcome") == "ok" and entry.get("collection_request_id")), None)
                require(attempt is not None, "collection detail receipt missing")
                request_record = models.CollectionRequest.objects.select_related("archive").get(pk=attempt["collection_request_id"])
                outcome = "found"
            elif response.outcome == "ok":
                outcome = "malformed"
    elif listing.outcome == "ok":
        outcome = "malformed"
    with fenced_run(lease):
        if detail is not None:
            require(request_record.archive_id is not None, "collection response was not retained")
            observation, created = models.CollectionObservation.objects.get_or_create(
                run=run, observation_key=digest([PROJECTION, repo.casefold(), request_record.archive.content_sha256]),
                defaults={"scope_run": scope, "source_identifier": repo, "source_subject_kind": "model",
                          "observation_kind": "hf_release_collection", "projection_kind": PROJECTION,
                          "payload_sha256": request_record.archive.content_sha256,
                          "observed_at": request_record.received_at, "processing_outcome": "unresolved"},
            )
            if created:
                link_request(observation, request_record, role="hf_model_collection")
        success = outcome == "found"
        scope.outcome = outcome
        scope.error_code = None if success else outcome[:64]
        scope.enumeration_complete = success
        scope.raw_count = int(detail is not None)
        scope.save(update_fields=["outcome", "error_code", "enumeration_complete", "raw_count"])
        run.physical_bytes_received = sum(run.attempts.values_list("actual_response_bytes", flat=True))
        run.save(update_fields=["physical_bytes_received", "updated_at"])
    prior = sum(run.attempts.exclude(pk=lease.attempt_id).values_list("actual_requests", flat=True))
    finish_run(lease, typed=True, status="success" if success else "failed" if attempts + 1 >= 3 else "partial",
               retry_at=None if success or attempts + 1 >= 3 else timezone.now() + timedelta(hours=6),
               request_count=prior + hf.requests, selected_count=int(detail is not None),
               success_count=int(detail is not None), error_code=None if success else outcome[:64],
               physical_accounting_complete=all(attempt.get("http_status") is not None for attempt in transport_attempts))
    if success and detail is not None:
        integrate_acquisition_run(run.pk)
    return {"outcome": outcome, "run_id": str(run.pk), "physical_requests": hf.requests}
