"""Bounded, revision-pinned model-card capture for a release candidate."""

import hashlib
import re
from contextlib import closing
from datetime import timedelta

import httpx
from django.db import transaction
from django.utils import timezone

from core import models
from core.collection_capture import RequestCapture, link_request
from core.collection_jobs import register_job, set_job_state
from core.collection_state import claim_job, fenced_run, finish_run
from core.hf_metadata_client import REPO_ID
from core.measurement_taxonomy import digest, require
from scripts.benchmark_download_collector.sources import Budget, SourceError

SHA = re.compile(r"[0-9a-f]{40}\Z")
PROJECTION = "hf-release-card-v1"
_OUTPUT_TEACHERS = re.compile(
    r"\b(?:outputs|responses)\s+from\s+(?P<names>[^\n]{1,200}?)\s+(?:teachers|specialists)\b",
    re.IGNORECASE,
)
_VERSIONED_TEACHER = re.compile(r"(?<![\w/])[A-Za-z][A-Za-z0-9_-]*\d[A-Za-z0-9_.-]*(?![\w.-])")


def teacher_mentions(text):
    """Extract narrowly worded publisher claims, not canonical identities."""
    if not isinstance(text, str):
        raise TypeError("model-card text required")
    found = {}
    for line in text.splitlines():
        if len(line) > 2000:
            continue
        for match in _OUTPUT_TEACHERS.finditer(line):
            before = re.split(r"(?<=[.!?])\s+", line[:match.start()])[-1]
            if (not re.search(r"\b(?:trained|training|distilled|distillation)\b", before, re.IGNORECASE)
                    or re.search(r"\b(?:not|never|without|may|might|could|would|alleged)\b",
                                 before + match.group("names"), re.IGNORECASE)):
                continue
            for name in _VERSIONED_TEACHER.finditer(match.group("names")):
                term = name.group().rstrip("-_.")
                found.setdefault(term.casefold(), {"name": term, "excerpt": line})
                if len(found) >= 20:
                    return tuple(found.values())
    return tuple(found.values())


def _target(job):
    target = job.targets.get(target_role="model_card")
    repo, separator, revision = (target.native_identifier or "").rpartition("@")
    require(separator and REPO_ID.fullmatch(repo) and SHA.fullmatch(revision), "invalid pinned card target")
    return repo, revision


def card_documents(observation):
    """Read the exact captured card, checking the request and archived bytes."""
    run, scope = observation.run, observation.scope_run
    require(observation.projection_kind == PROJECTION and run.job.source_id == "hf"
            and run.job.operation == "release_acquisition" and scope is not None
            and scope.run_id == run.pk and scope.scope_kind == "release_acquisition",
            "model-card observation ownership mismatch")
    links = list(observation.inputs.select_related("input_request__archive", "input_request__attempt"))
    require(len(links) == 1, "model card needs one captured response")
    link = links[0]
    request = link.input_request
    repo, revision = _target(run.job)
    require(link.input_role == "hf_model_card" and request is not None
            and request.scope_run_id == scope.pk and request.attempt.run_id == run.pk
            and request.transport_outcome == "received" and request.http_status == 200
            and request.endpoint_url == f"https://huggingface.co/{repo}/raw/{revision}/README.md"
            and request.archive_id is not None and link.input_sha256 == request.archive.content_sha256,
            "model-card response ownership or checksum mismatch")
    body = bytes(request.archive.body)
    require(hashlib.sha256(body).hexdigest() == request.archive.content_sha256
            and observation.payload_sha256 == request.archive.content_sha256
            and observation.source_identifier.casefold() == repo.casefold(), "model-card content changed")
    text = body.decode("utf-8-sig")
    require(bool(text.strip()), "empty model card")
    return {"text": text, "revision": revision}, {"kind": "model_card"}, {}


def integrate_card(observation):
    """Attach a retained card to each interested dossier without inferring lineage."""
    from core.event_dossiers import add_claim, attach_source
    from core.product_release_pipeline import canonical_dossier

    with transaction.atomic():
        document, _, _ = card_documents(observation)
        repo, revision = _target(observation.run.job)
        request = observation.inputs.select_related("input_request").get().input_request
        for link in observation.run.job.dossier_claim_links.select_related("claim__event_dossier_source"):
            dossier = canonical_dossier(link.claim.event_dossier_source.event_dossier_id)
            source = attach_source(dossier.pk, observation_id=observation.pk)
            add_claim(source.pk, claim_kind="release_context", scope_key=f"hf_card:{observation.pk}",
                      assertion_text=f"Captured model card for {repo} at revision {revision}; its claims require assessment",
                      source_excerpt=document["text"][:500],
                      source_locator=f"https://huggingface.co/{repo}/blob/{revision}/README.md",
                      source_archive_id=request.archive_id, extraction_version=PROJECTION)
            for teacher in teacher_mentions(document["text"]):
                add_claim(source.pk, claim_kind="release_context",
                          scope_key="hf_card_teacher:" + digest([observation.pk, teacher["name"].casefold()]),
                          assertion_text=(f"Model card reports {teacher['name']} as a specialist supplying training outputs; "
                                          "the exact Product identity is unresolved"),
                          source_excerpt=teacher["excerpt"],
                          source_locator=f"https://huggingface.co/{repo}/blob/{revision}/README.md",
                          source_archive_id=request.archive_id, extraction_version="hf-card-teacher-v1")


def queue_card(claim_id, exact_observation_id):
    """Register a card only from the exact capture and its immutable revision."""
    from core.product_release_acquisition import (
        hf_exact_observation_documents,
        link_claim_to_job,
    )
    from core.product_release_pipeline import canonical_dossier

    observation = models.CollectionObservation.objects.select_related("run__job").get(pk=exact_observation_id)
    require(observation.projection_kind == "hf-release-exact-v1", "exact model capture required")
    row, _, _ = hf_exact_observation_documents(observation)
    revision = row.get("sha")
    if not isinstance(revision, str) or not SHA.fullmatch(revision):
        return None
    claim = models.EventDossierClaim.objects.select_related("event_dossier_source").get(pk=claim_id)
    require(claim.event_dossier_source.collection_observation_id == observation.pk
            and claim.scope_key == f"hf_capture:{observation.pk}", "exact capture claim required")
    dossier = canonical_dossier(claim.event_dossier_source.event_dossier_id)
    latest = dossier.intake_decisions.order_by("-recorded_at", "-pk").first()
    require(not latest or latest.outcome not in {"non_release", "scam"}, "excluded release")
    repo = observation.source_identifier
    require(REPO_ID.fullmatch(repo), "invalid repository")
    key = digest([PROJECTION, repo.casefold(), revision])
    with transaction.atomic():
        job = register_job(
            job_key="release-hf-card:" + key, source=models.DataSource.objects.get(pk="hf"),
            purpose="content", operation="release_acquisition", mode="manual", definition={"version": 2, "options": {}},
            settings={"owner_kind": "source", "schedule_kind": "manual", "schedule_driver": "manual",
                      "max_requests": 3, "max_bytes": 1048576, "max_seconds": 30, "max_items": 1},
            targets=[{"target_key": key, "native_identifier": f"{repo}@{revision}", "target_kind": "model",
                      "target_role": "model_card", "resolution_state": "unresolved",
                      "gap_reason": "unresolved_product_identity"}],
        )
        link_claim_to_job(claim.pk, job.pk)
        if job.state == "paused" and not job.runs.exists():
            job = set_job_state(job.pk, "ready")
    if job.last_success_id:
        integrate_card(job.last_success.observations.get(projection_kind=PROJECTION))
    return job


def execute_card(job_id, *, client):
    """Fetch one public text file at a pinned revision, never weights or redirects."""
    from core.product_release_acquisition import _has_eligible_claim

    job = models.CollectionJob.objects.get(pk=job_id)
    require(job.source_id == "hf" and job.operation == "release_acquisition"
            and job.mode == "manual" and job.dossier_claim_links.exists(), "manual card acquisition required")
    repo, revision = _target(job)
    if not _has_eligible_claim(job):
        return {"outcome": "excluded", "physical_requests": 0}
    if job.last_success_id:
        integrate_card(job.last_success.observations.get(projection_kind=PROJECTION))
        return {"outcome": "found", "run_id": str(job.last_success_id), "physical_requests": 0}
    attempts = models.CollectionAttempt.objects.filter(run__job=job).count()
    checkpointed = bool(job.last_attempt_id and job.last_attempt.completed_at is None
                        and job.last_attempt.scopes.filter(scope_kind="release_acquisition",
                            scope_key="execution", outcome="found", enumeration_complete=True).exists())
    require(attempts < 3 or checkpointed, "card retry limit exhausted")
    lease = claim_job(job.pk, typed=True, manual_authorized=True)
    run = models.CollectionRun.objects.get(pk=lease.run_id)
    scope = run.scopes.get(scope_kind="release_acquisition", scope_key="execution")
    if scope.outcome == "found" and scope.enumeration_complete:
        integrate_card(run.observations.get(projection_kind=PROJECTION))
        prior = sum(run.attempts.exclude(pk=lease.attempt_id).values_list("actual_requests", flat=True))
        finish_run(lease, typed=True, status="success", request_count=prior,
                   selected_count=1, success_count=1, physical_accounting_complete=True)
        return {"outcome": "found", "run_id": str(run.pk), "physical_requests": 0}
    budget = Budget(client, max_requests=job.max_requests, max_seconds=job.max_seconds,
                    max_bytes=job.max_bytes, cumulative=True)
    url = f"https://huggingface.co/{repo}/raw/{revision}/README.md"
    capture = RequestCapture(lease)
    request_record = capture.start(scope, url)
    outcome, response, body = "request_error", None, None
    response_accounted = False
    try:
        request = budget.public_request(url, None, headers={"User-Agent": "PushinWeight-public-metadata"})
        with closing(client.send(request, stream=True, auth=None, follow_redirects=False)) as response:
            if response.status_code == 200:
                body = budget.response_bytes(response, cumulative=True)
                decoded = body.decode("utf-8-sig")
                outcome = "found" if decoded.strip() else "empty"
            else:
                outcome = {401: "unauthorized", 403: "forbidden", 404: "missing_or_private",
                           429: "throttled"}.get(response.status_code, "http_error")
            capture.received(request_record, body=body if outcome == "found" else None,
                             status=response.status_code, response_bytes=budget.total_bytes_read,
                             media_type="text/markdown")
            response_accounted = True
    except (SourceError, UnicodeError) as exc:
        outcome = str(exc) if isinstance(exc, SourceError) else "malformed_text"
        if response is not None:
            capture.received(request_record, body=None, status=response.status_code,
                             response_bytes=budget.total_bytes_read, error_code=outcome[:64],
                             media_type="text/markdown")
            response_accounted = True
        else:
            capture.failed(request_record, error_code=outcome[:64])
    except httpx.HTTPError:
        outcome = "request_error"
        capture.failed(request_record, error_code=outcome)
    with fenced_run(lease):
        if outcome == "found":
            request_record.refresh_from_db()
            require(request_record.archive_id is not None, "card response was not retained")
            observation, created = models.CollectionObservation.objects.get_or_create(
                run=run, observation_key=digest([PROJECTION, repo.casefold(), revision, request_record.archive.content_sha256]),
                defaults={"scope_run": scope, "source_identifier": repo, "source_subject_kind": "model",
                          "observation_kind": "hf_release_card", "projection_kind": PROJECTION,
                          "payload_sha256": request_record.archive.content_sha256,
                          "observed_at": request_record.received_at, "processing_outcome": "unresolved"},
            )
            if created:
                link_request(observation, request_record, role="hf_model_card")
            integrate_card(observation)
        scope.outcome = outcome
        scope.error_code = None if outcome == "found" else outcome
        scope.enumeration_complete = outcome == "found"
        scope.raw_count = int(outcome == "found")
        scope.save(update_fields=["outcome", "error_code", "enumeration_complete", "raw_count"])
        run.physical_bytes_received = sum(run.attempts.values_list("actual_response_bytes", flat=True))
        run.save(update_fields=["physical_bytes_received", "updated_at"])
    physical = job.max_requests - budget.remaining
    prior = sum(run.attempts.exclude(pk=lease.attempt_id).values_list("actual_requests", flat=True))
    success = outcome == "found"
    finish_run(lease, typed=True, status="success" if success else "failed" if attempts + 1 >= 3 else "partial",
               retry_at=None if success or attempts + 1 >= 3 else timezone.now() + timedelta(hours=6),
               request_count=prior + physical, selected_count=int(success), success_count=int(success),
               error_code=None if success else outcome, physical_accounting_complete=response_accounted)
    return {"outcome": outcome, "run_id": str(run.pk), "physical_requests": physical}
