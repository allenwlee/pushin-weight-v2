"""Bounded GitHub owner evidence for a captured release repository."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core import models
from core.collection_capture import RequestCapture, link_request, read_document
from core.collection_jobs import register_job, set_job_state
from core.collection_state import claim_job, fenced_run, finish_run
from core.github_metadata_client import GitHubMetadataClient
from core.measurement_taxonomy import digest, require
from core.product_release_acquisition import (
    _has_eligible_claim,
    github_exact_observation_documents,
    link_claim_to_job,
)
from scripts.benchmark_download_collector.sources import Budget, SourceError


def _owner_from_repository(observation):
    row, _, _ = github_exact_observation_documents(observation)
    owner = row.get("owner")
    if not isinstance(owner, dict):
        return None
    login, owner_id = owner.get("login"), owner.get("id")
    if (type(owner_id) is not int or owner_id <= 0 or not isinstance(login, str)
            or row["full_name"].split("/", 1)[0].casefold() != login.casefold()):
        return None
    GitHubMetadataClient.repo_url(f"{login}/owner-check")
    return login, owner_id


def queue_owner(claim_id, observation_id):
    """Register owner evidence only from a captured repository and its dossier."""
    observation = models.CollectionObservation.objects.get(pk=observation_id)
    owner = _owner_from_repository(observation)
    if owner is None:
        return None
    claim = models.EventDossierClaim.objects.select_related("event_dossier_source").get(pk=claim_id)
    require(claim.scope_key == f"github_capture:{observation.pk}"
            and claim.event_dossier_source.collection_observation_id == observation.pk,
            "owner lookup requires the repository capture claim")
    key = digest(["release-github-owner-v1", observation.pk, owner[1]])
    with transaction.atomic():
        job = register_job(
            job_key="release-github-owner:" + key,
            source=models.DataSource.objects.get(pk="github"), purpose="content",
            operation="release_acquisition", mode="manual", definition={"version": 2, "options": {}},
            settings={"owner_kind": "source", "schedule_kind": "manual", "schedule_driver": "manual",
                      "max_requests": 3, "max_bytes": 1048576, "max_seconds": 30, "max_items": 1},
            targets=[{"target_key": key, "native_identifier": owner[0], "target_kind": "account",
                      "target_role": "publisher_profile", "resolution_state": "unresolved",
                      "gap_reason": "unverified_publisher", "evidence_observation_id": observation.pk}],
        )
        link_claim_to_job(claim.pk, job.pk)
        if job.state == "paused" and not job.runs.exists():
            job = set_job_state(job.pk, "ready")
    if job.last_success_id:
        integrate_owner(job.last_success.observations.get(projection_kind="github-release-owner-v1"))
    return job


def owner_documents(observation):
    run, scope = observation.run, observation.scope_run
    require(observation.projection_kind == "github-release-owner-v1"
            and run.job.source_id == "github" and run.job.operation == "release_acquisition"
            and scope is not None and scope.run_id == run.pk
            and scope.scope_kind == "release_acquisition", "GitHub owner observation mismatch")
    target = run.job.targets.get(target_role="publisher_profile")
    owner = _owner_from_repository(target.evidence_observation)
    require(owner is not None and owner[0].casefold() == target.native_identifier.casefold(),
            "owner target no longer matches repository evidence")
    inputs = list(observation.inputs.select_related("input_request__archive", "input_request__attempt"))
    require(len(inputs) == 1, "GitHub owner needs one captured response")
    link = inputs[0]
    request = link.input_request
    require(link.input_role == "github_owner" and request is not None
            and request.scope_run_id == scope.pk and request.attempt.run_id == run.pk
            and request.transport_outcome == "received" and request.http_status == 200
            and request.archive_id is not None and link.input_sha256 == request.archive.content_sha256
            and request.endpoint_url == f"https://api.github.com/users/{target.native_identifier}",
            "GitHub owner response ownership or checksum mismatch")
    row = read_document(request.archive)
    require(isinstance(row, dict) and type(row.get("id")) is int and row["id"] == owner[1]
            and isinstance(row.get("login"), str) and row["login"].casefold() == owner[0].casefold()
            and observation.source_identifier == str(owner[1]) and digest(row) == observation.payload_sha256,
            "GitHub owner identity or content changed")
    return row, {"kind": "account"}, {}


def integrate_owner(observation):
    import re

    from core.event_dossiers import add_claim, attach_source
    from core.product_release_pipeline import canonical_dossier

    row, _, _ = owner_documents(observation)
    request = observation.inputs.select_related("input_request").get().input_request
    for link in observation.run.job.dossier_claim_links.select_related("claim__event_dossier_source"):
        dossier = canonical_dossier(link.claim.event_dossier_source.event_dossier_id)
        source = attach_source(dossier.pk, observation_id=observation.pk)
        add_claim(source.pk, claim_kind="release_context", scope_key=f"github_owner:{observation.pk}",
                  assertion_text=f"Captured GitHub owner profile {row['login']}; publisher and source control are unresolved",
                  source_excerpt=row["login"], source_locator=f"https://github.com/{row['login']}",
                  source_archive_id=request.archive_id, extraction_version="github-release-owner-v1")
        handle = row.get("twitter_username")
        if isinstance(handle, str) and re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle):
            add_claim(source.pk, claim_kind="release_context", scope_key=f"github_owner_x:{observation.pk}",
                      assertion_text=f"GitHub profile reports X account @{handle}; source control is unresolved",
                      source_excerpt=f"@{handle}", source_locator=f"https://github.com/{row['login']}",
                      source_archive_id=request.archive_id, extraction_version="github-release-owner-v1")


def execute_owner(job_id, *, client):
    job = models.CollectionJob.objects.get(pk=job_id)
    require(job.source_id == "github" and job.operation == "release_acquisition"
            and job.mode == "manual" and job.dossier_claim_links.exists(), "manual owner acquisition required")
    if not _has_eligible_claim(job):
        return {"outcome": "excluded", "physical_requests": 0}
    if job.last_success_id:
        integrate_owner(job.last_success.observations.get(projection_kind="github-release-owner-v1"))
        return {"outcome": "found", "physical_requests": 0}
    attempts = models.CollectionAttempt.objects.filter(run__job=job).count()
    checkpointed = bool(job.last_attempt_id and job.last_attempt.completed_at is None
                        and job.last_attempt.scopes.filter(scope_kind="release_acquisition",
                            scope_key="execution", outcome="found", enumeration_complete=True).exists())
    require(attempts < 3 or checkpointed, "owner acquisition retry limit exhausted")
    lease = claim_job(job.pk, typed=True, manual_authorized=True)
    run = models.CollectionRun.objects.get(pk=lease.run_id)
    scope = run.scopes.get(scope_kind="release_acquisition", scope_key="execution")
    if scope.outcome == "found" and scope.enumeration_complete:
        observation = run.observations.get(projection_kind="github-release-owner-v1")
        integrate_owner(observation)
        prior = sum(run.attempts.exclude(pk=lease.attempt_id).values_list("actual_requests", flat=True))
        finish_run(lease, typed=True, status="success", request_count=prior,
                   selected_count=1, success_count=1, physical_accounting_complete=True)
        return {"outcome": "found", "physical_requests": 0}
    target = job.targets.get(target_role="publisher_profile")
    owner = _owner_from_repository(target.evidence_observation)
    require(owner is not None and owner[0].casefold() == target.native_identifier.casefold(),
            "owner target no longer matches repository evidence")
    budget = Budget(client, max_requests=job.max_requests, max_seconds=job.max_seconds,
                    max_bytes=job.max_bytes, cumulative=True)
    github = GitHubMetadataClient(budget)
    github.capture, github.collection_scope = RequestCapture(lease), scope
    try:
        response = github.owner(owner[0])
        row = response.payload
        if response.status == 200:
            outcome = ("found" if isinstance(row, dict) and type(row.get("id")) is int
                       and row["id"] == owner[1] and isinstance(row.get("login"), str)
                       and row["login"].casefold() == owner[0].casefold() else "identity_mismatch")
        else:
            outcome = {401: "unauthorized", 403: "forbidden_or_throttled", 404: "missing_or_inaccessible",
                       429: "throttled"}.get(response.status, "http_error")
    except SourceError:
        response, row, outcome = None, None, "request_error"
    with fenced_run(lease):
        if outcome == "found":
            request = models.CollectionRequest.objects.select_related("archive").get(pk=response.collection_request_id)
            require(request.archive_id is not None, "public owner capture required")
            observation, created = models.CollectionObservation.objects.get_or_create(
                run=run, observation_key=digest(["github-release-owner-v1", owner[1], digest(row)]),
                defaults={"scope_run": scope, "source_identifier": str(owner[1]),
                          "source_subject_kind": "account", "observation_kind": "github_release_owner",
                          "projection_kind": "github-release-owner-v1", "payload_sha256": digest(row),
                          "observed_at": request.received_at, "processing_outcome": "unresolved"},
            )
            if created:
                link_request(observation, request, role="github_owner")
            integrate_owner(observation)
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
