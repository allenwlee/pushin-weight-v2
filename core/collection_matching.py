"""Conservative crosswalk proposals from stored evidence, without provider calls.

Preview is read-only. Reviewed choices become immutable collection instructions;
only the fenced executor calls the shared catalog admission writer.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from time import monotonic

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from core.benchmark_metric_store import aware_instant
from core.collection_capture import observation_object_documents
from core.measurement_taxonomy import digest, require
from core.models import (
    Account,
    Brand,
    BrandAccount,
    BrandCompany,
    CollectionObservation,
    CompanyAccount,
    Product,
    SourceSubjectMapping,
)

RULESET = "product-crosswalk-v1"
SOURCES = ("github", "openrouter", "arena", "opencode", "gdpx")


STATIC_EVIDENCE_URLS = {
    "arena": "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset",
    "gdpx": "https://gdpx.semianalysis.com/",
}


def _unmatch(candidate, reason):
    """Mark a candidate unmatched and re-seal its input digest."""
    candidate.update(decision="unmatched", reasons=[reason])
    candidate["input_sha256"] = digest(
        {k: v for k, v in candidate.items() if k != "input_sha256"}
    )
MAX_CANDIDATES = 5
MAX_ENVELOPE_BYTES = 32768
logger = logging.getLogger(__name__)


@contextmanager
def bounded_reads():
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_setting('statement_timeout'), current_setting('lock_timeout'), current_setting('work_mem'), current_setting('max_parallel_workers_per_gather')"
            )
            previous = cursor.fetchone()
            cursor.execute("SET LOCAL statement_timeout = '12s'")
            cursor.execute("SET LOCAL lock_timeout = '1s'")
            cursor.execute("SET LOCAL work_mem = '1MB'")
            cursor.execute("SET LOCAL max_parallel_workers_per_gather = 0")
        yield
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true), set_config('work_mem', %s, true), set_config('max_parallel_workers_per_gather', %s, true)",
                previous,
            )


def name_key(value):
    """Punctuation within versions and variant suffixes remains significant."""
    return re.sub(r"[\s_-]+", "", value.casefold())


def ensure_product_match_target(job, scope_key, ownership):
    """Link a product decision to its frozen target, including legacy v1 jobs."""
    from core.identifier_namespaces import target_namespace_id
    from core.measurement_taxonomy import resolve_subject_id
    from core.models import CollectionJob, CollectionJobTarget, MeasurementSubject

    require(
        isinstance(ownership, dict)
        and set(ownership) == {"product_key", "input_sha256"}
        and isinstance(ownership["product_key"], str)
        and isinstance(ownership["input_sha256"], str)
        and re.fullmatch(r"[0-9a-f]{64}", ownership["input_sha256"]),
        "product match requires frozen product and input digest",
    )
    product_key = uuid.UUID(ownership["product_key"])
    target = job.targets.filter(target_key=scope_key).select_related("subject").first()
    if target is None:
        CollectionJob.objects.select_for_update().get(pk=job.pk)
        target = job.targets.filter(target_key=scope_key).select_related("subject").first()
    if target is None:
        require(job.instruction_version == 1, "sealed match job requires a target")
        matches = [
            row for row in job.definition.get("scope", {}).get("matches", [])
            if row.get("candidate_id") == scope_key
        ]
        require(len(matches) == 1, "frozen product match candidate is missing")
        choice = matches[0]
        require(
            choice.get("product_key") == str(product_key)
            and choice.get("input_sha256") == ownership["input_sha256"]
            and len(choice.get("reasons", [])) == 1,
            "product match differs from frozen instruction",
        )
        product = Product.objects.get(product_key=product_key)
        subject, _ = MeasurementSubject.objects.get_or_create(
            id=resolve_subject_id("product", str(product_key)),
            defaults={"subject_kind": "product", "product": product},
        )
        require(
            subject.subject_kind == "product" and subject.product_id == product_key,
            "product match subject changed",
        )
        values = {
            "target_kind": "match_candidate",
            "evidence_observation_id": choice["evidence"]["observation_id"],
            "identifier_scope": choice["identifier_scope"],
        }
        namespace = target_namespace_id(values)
        maximum = job.targets.order_by("-ordinal").values_list("ordinal", flat=True).first()
        target = CollectionJobTarget.objects.create(
            job=job, target_key=scope_key,
            ordinal=0 if maximum is None else maximum + 1,
            subject=subject, target_kind="match_candidate",
            target_role=choice["decision"], resolution_state="resolved",
            native_identifier=choice["identifier"],
            identifier_scope_id=namespace,
            source_row_index=choice.get("publication_row_index"),
            evidence_observation_id=choice["evidence"]["observation_id"],
            selection_basis=choice["reasons"][0],
            selection_sha256=ownership["input_sha256"],
            review_confirmed=scope_key in job.definition["scope"]["review"]["candidate_ids"],
        )
    require(
        target.target_kind == "match_candidate"
        and target.subject_id is not None
        and target.subject.subject_kind == "product"
        and target.subject.product_id == product_key
        and target.selection_sha256 == ownership["input_sha256"],
        "product match target differs from scope ownership",
    )
    return target


def ownership_pin(product, publisher):
    def links(account):
        if account is None:
            return None
        return {
            "account_key": str(account.pk),
            "source": account.data_source_id,
            "native_id": account.normalized_identifier,
            "companies": list(
                CompanyAccount.objects.filter(account=account)
                .order_by("company_id")
                .values("company_id", "role_id", "ownership_confirmed")
            ),
            "brands": list(
                BrandAccount.objects.filter(account=account)
                .order_by("brand_id")
                .values("brand_id", "role_id")
            ),
        }

    result = {
        "product_key": str(product.product_key),
        "repo_id": product.repo_id,
        "brand_id": product.brand_id,
        "product_type": product.product_type_code,
        "product_evidence_sha256": digest(product.card_data),
        "product_publisher": links(product.publisher_account),
        "source_publisher": links(publisher),
        "brand_companies": sorted(
            BrandCompany.objects.filter(brand_id=product.brand_id).values_list(
                "company_id", flat=True
            )
        )
        if product.brand_id
        else [],
    }
    if product.repo_id is None:
        result["display_name"] = product.display_name
    return result


def _pages(query, *, size=500):
    """Stable, bounded query results; never aggregate full histories in SQL."""
    offset = 0
    while True:
        page = list(query[offset : offset + size])
        yield from page
        if len(page) < size:
            return
        offset += size


def _evidence_pin(observation, documents=None):
    listing, dimensions, source_metadata = documents or observation_object_documents(observation)
    return {
        "observation_id": observation.pk,
        "observation_key": observation.observation_key,
        "run_id": str(observation.run_id),
        "source": observation.run.job.source_id,
        "source_identifier": observation.source_identifier,
        "source_subject_kind": observation.source_subject_kind,
        "observed_at": observation.observed_at.isoformat(),
        "payload_hash": digest([listing, dimensions, source_metadata]),
    }


def _native(observation, scope, row_index=None, documents=None, evidence_pin=None):
    source, identifier = observation.run.job.source_id, observation.source_identifier
    documents = documents or observation_object_documents(observation)
    listing, _, _ = documents
    if not isinstance(listing, dict):
        return None
    if row_index is not None:
        rows = listing.get("rows", [])
        if not (
            source in {"arena", "openrouter"}
            and isinstance(rows, list)
            and type(row_index) is int
            and 0 <= row_index < len(rows)
            and isinstance(rows[row_index], dict)
        ):
            return None
        identifier = rows[row_index].get(
            "model_permaslug" if source == "openrouter" else "model_name"
        )
        if not isinstance(identifier, str):
            return None
    if not identifier or identifier == "other":
        return None
    repo = listing
    label, publisher, repo_pin = identifier, None, None
    gdpx = {}
    if source == "gdpx":
        # KTD14: the display name is the label; the slug never matches a name.
        if not (
            listing.get("id") == identifier
            and isinstance(listing.get("name"), str)
            and listing["name"].strip()
        ):
            return None
        label = listing["name"]
        gdpx = {
            "publisher_hint": listing.get("lab"),
            "review_only_variant": bool(listing.get("specialist"))
            or "abliterated" in identifier.casefold()
            or "abliterated" in label.casefold(),
        }
    if source == "github":
        owner = repo.get("owner", {})
        if not (
            type(repo.get("id")) is int
            and str(repo["id"]) == identifier
            and repo.get("private") is False
            and type(owner.get("id")) is int
            and isinstance(repo.get("full_name"), str)
        ):
            return None
        label = repo["full_name"]
        publisher = Account.objects.filter(
            data_source_id=source, normalized_identifier=str(owner["id"])
        ).first()
        repo_pin = {
            "id": repo["id"],
            "full_name": label,
            "private": False,
            "owner": {"id": owner["id"], "login": owner.get("login")},
        }
    return {
        "source": source,
        "identifier": identifier,
        "identifier_scope": scope,
        "source_subject_kind": "repository" if source == "github" else "model",
        "observed_label": label,
        "db_presence": "present",
        "evidence": evidence_pin if evidence_pin is not None else _evidence_pin(observation, documents),
        "publisher_account_key": str(publisher.pk) if publisher else None,
        "repo": repo_pin,
        "publication_row_index": row_index,
        **gdpx,
    }


def _pending_native(observation, identifier_scope, row_index, documents=None, evidence_pin=None):
    native = _native(observation, identifier_scope, row_index, documents=documents, evidence_pin=evidence_pin)
    require(
        native is not None and native["source"] in {"arena", "openrouter"}
        and row_index is not None
        and identifier_scope == {"arena": "arena_model_name", "openrouter": "rankings_permaslug"}[native["source"]]
        and observation.observation_kind == "publication_window"
        and observation.source_subject_kind == "aggregate"
        and observation.status == "ok" and observation.run.status in {"success", "partial"},
        "saved Arena or OpenRouter publication row required",
    )
    return native


def pending_target_pin(observation, identifier_scope, row_index):
    """Pin the exact saved publication row before an unresolved target is sealed."""
    native = _pending_native(observation, identifier_scope, row_index)
    return digest({"version": "pending-product-row-v1", "native": native})


def _validate_pending_budgets(budgets):
    from core.collection_jobs import BUDGET_LIMITS

    require(
        isinstance(budgets, dict) and set(budgets) == {"requests", "bytes", "seconds", "items"}
        and all(type(value) is int and 0 < value <= BUDGET_LIMITS[name] for name, value in budgets.items()),
        "explicit pending-target budgets required",
    )


@transaction.atomic
def register_pending_publication_targets(*, observation_id, row_indices, budgets):
    """Seal explicit unresolved row selections from one already-saved publication."""
    from core.collection_jobs import register_job
    from core.models import CollectionEvidenceArchive

    require(
        isinstance(row_indices, (list, tuple)) and bool(row_indices)
        and all(type(index) is int and index >= 0 for index in row_indices)
        and len(set(row_indices)) == len(row_indices),
        "distinct publication row selections required",
    )
    _validate_pending_budgets(budgets)
    require(budgets["items"] >= len(row_indices), "pending-target item budget is too small")
    deadline = monotonic() + budgets["seconds"]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_setting('statement_timeout'), current_setting('lock_timeout'), "
            "(SELECT setting::bigint FROM pg_settings WHERE name='statement_timeout'), "
            "(SELECT setting::bigint FROM pg_settings WHERE name='lock_timeout')"
        )
        statement_before, lock_before, statement_ms, lock_ms = cursor.fetchone()
        budget_ms = budgets["seconds"] * 1000
        statement_limit = min(statement_ms or budget_ms, budget_ms)
        lock_limit = min(lock_ms or budget_ms, budget_ms)
        cursor.execute("SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)",
                       [f"{statement_limit}ms", f"{lock_limit}ms"])
    observation = CollectionObservation.objects.select_for_update(of=("self",)).select_related("run__job__source").get(pk=observation_id)
    source = observation.run.job.source
    require(source.pk in {"arena", "openrouter"}, "unsupported pending publication source")
    scope = {"arena": "arena_model_name", "openrouter": "rankings_permaslug"}[source.pk]
    archive_id = (
        observation.run.payload_archive_id
        if observation.projection_kind == "publication-window-v1"
        else observation.legacy_archive_id
    )
    if archive_id is not None:
        require(
            CollectionEvidenceArchive.objects.values_list("byte_count", flat=True).get(pk=archive_id) <= budgets["bytes"],
            "pending-target evidence exceeds byte or time budget",
        )
    documents = observation_object_documents(observation)
    require(
        len(json.dumps(documents, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()) <= budgets["bytes"]
        and monotonic() < deadline,
        "pending-target evidence exceeds byte or time budget",
    )
    targets = []
    evidence_pin = _evidence_pin(observation, documents)
    for index in sorted(row_indices):
        require(monotonic() < deadline, "pending-target time budget exceeded")
        native = _pending_native(observation, scope, index, documents=documents, evidence_pin=evidence_pin)
        pin = digest({"version": "pending-product-row-v1", "native": native})
        targets.append({
            "target_key": "pending-row:" + pin, "target_kind": "match_candidate",
            "target_role": "selected", "resolution_state": "unresolved",
            "gap_reason": "unmatched_source_identifier", "native_identifier": native["identifier"],
            "identifier_scope": scope, "source_row_index": index,
            "evidence_observation_id": observation.pk, "selection_sha256": pin,
        })
    key = digest({"source": source.pk, "observation": observation.pk,
                  "pins": [target["selection_sha256"] for target in targets], "budgets": budgets})
    remaining = deadline - monotonic()
    require(remaining > 0, "pending-target time budget exceeded")
    remaining_ms = max(1, int(remaining * 1000))
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)",
                       [f"{min(statement_ms or remaining_ms, remaining_ms)}ms",
                        f"{min(lock_ms or remaining_ms, remaining_ms)}ms"])
    job = register_job(
        job_key="pending-match:" + key, source=source, purpose="catalog",
        operation="match_crosswalk", mode="historical",
        definition={"version": 2, "options": {"ruleset": RULESET, "preview_sha256": key}}, targets=targets,
        settings={"owner_kind": "source", "schedule_kind": "manual", "schedule_driver": "manual",
                  **{"max_" + name: value for name, value in budgets.items()}},
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)",
                       [statement_before, lock_before])
    require(monotonic() < deadline, "pending-target time budget exceeded")
    return job


def _process_pending_publication_scope(scope, observation, budgets):
    """Run a bounded local page while holding the observation and scope locks."""
    from datetime import timedelta

    from core.collection_identity import DEDICATED_ROLES
    from core.models import CollectionEvidenceArchive, CollectionJobTarget

    source = observation.run.job.source_id
    deadline = monotonic() + budgets["seconds"]
    try:
        with transaction.atomic():
            archive_id = observation.run.payload_archive_id if observation.projection_kind == "publication-window-v1" else observation.legacy_archive_id
            if (archive_id is not None and CollectionEvidenceArchive.objects.values_list("byte_count", flat=True).get(pk=archive_id) > budgets["bytes"]):
                scope.outcome, scope.error_code, scope.retry_at = "blocked", "pending_admission_byte_limit", None
                scope.enumeration_complete = False
                scope.save(update_fields=["outcome", "error_code", "retry_at", "enumeration_complete"])
                return {"status": "blocked", "reused": False, "admitted": 0, "job_id": None}
            documents = observation_object_documents(observation)
            require(monotonic() < deadline, "publication admission time budget exceeded")
            if len(json.dumps(documents, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()) > budgets["bytes"]:
                scope.outcome, scope.error_code, scope.retry_at = "blocked", "pending_admission_byte_limit", None
                scope.enumeration_complete = False
                scope.save(update_fields=["outcome", "error_code", "retry_at", "enumeration_complete"])
                return {"status": "blocked", "reused": False, "admitted": 0, "job_id": None}
            listing, _, _ = documents
            rows = listing.get("rows") if isinstance(listing, dict) else None
            require(isinstance(rows, list), "publication rows missing")
            field = "model_permaslug" if source == "openrouter" else "model_name"
            namespace = "rankings_permaslug" if source == "openrouter" else "arena_model_name"
            candidates = {index: row.get(field) for index, row in enumerate(rows) if isinstance(row, dict)
                          and isinstance(row.get(field), str) and row[field] and row[field] != "other"}
            mapped_subjects, dedicated = defaultdict(set), set()
            for identifier, subject, role in SourceSubjectMapping.objects.filter(
                source_id=source, purpose="catalog", source_subject_kind="model", identifier_scope__code=namespace,
                normalized_identifier__in=set(candidates.values()), subject__product__isnull=False,
            ).values_list("normalized_identifier", "subject_id", "identity_snapshot__role"):
                mapped_subjects[identifier].add(subject)
                if role in DEDICATED_ROLES:
                    dedicated.add(identifier)
            require(monotonic() < deadline, "publication admission time budget exceeded")
            mapped = {identifier for identifier, subjects in mapped_subjects.items() if len(subjects) == 1 and identifier in dedicated}
            prior = defaultdict(set)
            for index, pin in CollectionJobTarget.objects.filter(
                evidence_observation=observation, target_kind="match_candidate", source_row_index__in=candidates,
                identifier_scope__code=namespace, resolution_state="unresolved",
                job__operation="match_crosswalk", job__job_key__startswith="pending-match:",
                job__instructions_sealed_at__isnull=False,
            ).values_list("source_row_index", "selection_sha256"):
                prior[index].add(pin)
            require(monotonic() < deadline, "publication admission time budget exceeded")
            evidence_pin = _evidence_pin(observation, documents) if prior else None
            existing = {index for index, pins in prior.items() if digest({
                "version": "pending-product-row-v1",
                "native": _pending_native(observation, namespace, index, documents=documents, evidence_pin=evidence_pin),
            }) in pins}
            unresolved = [index for index, identifier in candidates.items() if identifier not in mapped and index not in existing]
            page = unresolved[:budgets["items"]]
            require(monotonic() < deadline, "publication admission time budget exceeded")
            admitted = register_pending_publication_targets(
                observation_id=observation.pk, row_indices=page,
                budgets={**budgets, "seconds": max(1, min(budgets["seconds"], int(deadline - monotonic())))},
            ) if page else None
            require(monotonic() < deadline, "publication admission time budget exceeded")
            more = len(unresolved) > len(page)
            scope.raw_count = len(rows)
            scope.outcome = "pending" if more else "complete"
            scope.error_code = "pending_admission_item_limit" if more else None
            scope.enumeration_complete = not more
            scope.retry_at = timezone.now() if more else None
            scope.save(update_fields=["raw_count", "outcome", "error_code", "enumeration_complete", "retry_at"])
            return {"status": "pending" if more else "complete", "reused": False, "rows": len(rows),
                    "admitted": len(page), "job_id": str(admitted.pk) if admitted else None}
    except Exception:
        logger.exception("Saved publication admission remains pending for observation %s", observation.pk)
        scope.error_code = "pending_admission_failed"
        scope.outcome = "pending"
        scope.enumeration_complete = False
        scope.retry_at = timezone.now() + timedelta(seconds=60)
        scope.save(update_fields=["error_code", "outcome", "enumeration_complete", "retry_at"])
        return {"status": "pending", "reused": False, "admitted": 0, "job_id": None}



def admit_saved_publication_rows(*, claim, publication_id, budgets):
    """Save an admission page during the existing collection without provider calls."""
    from datetime import timedelta

    from django.db import OperationalError

    from core.collection_state import fenced_run
    from core.models import CollectionScopeRun

    _validate_pending_budgets(budgets)
    budgets = {**budgets, "seconds": min(budgets["seconds"], 5)}
    with fenced_run(claim) as (parent_job, run):
        observation = CollectionObservation.objects.select_related("run__job__source").get(pk=publication_id)
        require(observation.run.job.source_id in {"arena", "openrouter"} and parent_job.source_id == observation.run.job.source_id,
                "saved publication source differs from its collector")
        key = digest(["pending-publication-admission-v1", observation.pk])
        scope, created = CollectionScopeRun.objects.get_or_create(
            run=run, scope_kind="pending_publication_admission", scope_key=key,
            defaults={"resource_observation": observation, "phase": "pending-publication-v1"},
        )
        require(scope.resource_observation_id == observation.pk and scope.phase == "pending-publication-v1",
                "pending publication admission identity changed")
        if not created and scope.enumeration_complete:
            return {"status": "complete", "reused": True}
        try:
            with transaction.atomic():
                observation = CollectionObservation.objects.select_for_update(of=("self",), nowait=True).select_related("run__job__source").get(pk=publication_id)
        except OperationalError as exc:
            if getattr(exc.__cause__, "sqlstate", None) != "55P03":
                raise
            scope.outcome, scope.error_code = "pending", "pending_admission_busy"
            scope.retry_at = timezone.now() + timedelta(seconds=5)
            scope.save(update_fields=["outcome", "error_code", "retry_at"])
            return {"status": "busy", "reused": False}
        require(parent_job.source_id == observation.run.job.source_id,
                "saved publication source changed")
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('lock_timeout'), current_setting('statement_timeout'), (SELECT setting::bigint FROM pg_settings WHERE name='lock_timeout'), (SELECT setting::bigint FROM pg_settings WHERE name='statement_timeout')")
            previous_lock, previous_statement, old_lock_ms, old_statement_ms = cursor.fetchone()
            time_ms = budgets["seconds"] * 1000
            cursor.execute("SELECT set_config('lock_timeout', %s, true), set_config('statement_timeout', %s, true)",
                           [f"{min(old_lock_ms or 1000, 1000)}ms", f"{min(old_statement_ms or time_ms, time_ms)}ms"])
        try:
            return _process_pending_publication_scope(scope, observation, budgets)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('lock_timeout', %s, true), set_config('statement_timeout', %s, true)", [previous_lock, previous_statement])


def stage_saved_publications(*, claim, publication_ids):
    """Record bounded cached-publication recovery without reading their contents."""
    from core.collection_state import fenced_run
    from core.models import CollectionScopeRun

    ids = sorted(set(publication_ids))
    if not ids:
        return 0
    with fenced_run(claim) as (parent_job, run):
        require(len(ids) <= parent_job.budgets["items"], "publication staging item budget exceeded")
        observations = CollectionObservation.objects.filter(pk__in=ids, run__job__source_id=parent_job.source_id)
        require(observations.count() == len(ids) and parent_job.source_id in {"arena", "openrouter"},
                "staged publication source differs from its collector")
        now = timezone.now()
        CollectionScopeRun.objects.bulk_create([
            CollectionScopeRun(run=run, scope_kind="pending_publication_admission",
                               scope_key=digest(["pending-publication-admission-v1", pk]),
                               resource_observation_id=pk, phase="pending-publication-v1",
                               outcome="pending", retry_at=now)
            for pk in ids
        ], ignore_conflicts=True, batch_size=500)
    return len(ids)


def drain_pending_publication_scope(scope_id, *, budgets=None):
    """Retry one saved observation locally; explicit budgets may repair a blocked page."""
    from datetime import timedelta

    from django.db import OperationalError

    from core.models import CollectionScopeRun

    try:
        with transaction.atomic():
            candidate = CollectionScopeRun.objects.select_related("run__job").get(pk=scope_id, scope_kind="pending_publication_admission")
            selected_budgets = budgets if budgets is not None else candidate.run.job.budgets
            _validate_pending_budgets(selected_budgets)
            with connection.cursor() as cursor:
                cursor.execute("SELECT setting::bigint FROM pg_settings WHERE name='statement_timeout'")
                old_ms = cursor.fetchone()[0]
                limit_ms = selected_budgets["seconds"] * 1000
                cursor.execute("SELECT set_config('statement_timeout', %s, true)", [f"{min(old_ms or limit_ms, limit_ms)}ms"])
            observation = CollectionObservation.objects.select_for_update(of=("self",), nowait=True).select_related("run__job__source").get(pk=candidate.resource_observation_id)
            scope = CollectionScopeRun.objects.select_for_update(nowait=True).get(pk=scope_id)
            require(scope.resource_observation_id == observation.pk and scope.phase == "pending-publication-v1"
                    and scope.run.job.source_id == observation.run.job.source_id, "pending publication ownership changed")
            if scope.enumeration_complete:
                return {"status": "complete", "reused": True}
            if scope.outcome == "blocked" and budgets is None:
                return {"status": "blocked", "reused": True}
            return _process_pending_publication_scope(scope, observation, selected_budgets)
    except OperationalError as exc:
        if getattr(exc.__cause__, "sqlstate", None) != "55P03":
            raise
        with transaction.atomic():
            scope = CollectionScopeRun.objects.select_for_update(skip_locked=True).filter(pk=scope_id, outcome="pending").first()
            if scope:
                scope.retry_at = timezone.now() + timedelta(seconds=5)
                scope.save(update_fields=["retry_at"])
        return {"status": "busy", "reused": False}


def drain_pending_publication_scopes(*, max_jobs, max_seconds):
    """Attempt a finite due page of saved publication admissions; no provider work."""
    from core.models import CollectionScopeRun

    require(type(max_jobs) is int and 1 <= max_jobs <= 100 and type(max_seconds) in (int, float)
            and 0 < max_seconds <= 120, "explicit local recovery limits required")
    deadline = monotonic() + max_seconds
    ids = list(CollectionScopeRun.objects.filter(scope_kind="pending_publication_admission", outcome="pending",
                                                retry_at__lte=timezone.now()).order_by("retry_at", "pk").values_list("pk", flat=True)[:max_jobs])
    results = []
    for scope_id in ids:
        remaining = deadline - monotonic()
        if remaining < 1:
            break
        scope = CollectionScopeRun.objects.select_related("run__job").get(pk=scope_id)
        budgets = {**scope.run.job.budgets, "seconds": min(scope.run.job.budgets["seconds"], int(remaining))}
        results.append(drain_pending_publication_scope(scope_id, budgets=budgets))
    return {"selected": len(ids), "processed": len(results), "results": results}

def _pending_target(target_id):
    from core.models import CollectionJobTarget

    target = CollectionJobTarget.objects.select_related(
        "job", "evidence_observation__run__job", "identifier_scope"
    ).get(pk=target_id)
    require(
        target.job.instructions_sealed_at is not None
        and target.target_kind == "match_candidate"
        and target.resolution_state == "unresolved"
        and target.subject_id is None and target.evidence_observation_id is not None
        and target.identifier_scope_id is not None and target.source_row_index is not None
        and target.job.source_id == target.evidence_observation.run.job.source_id,
        "sealed unresolved source target required",
    )
    native = _native(target.evidence_observation, target.identifier_scope_code, target.source_row_index)
    require(
        native is not None and native["identifier"] == target.native_identifier
        and target.selection_sha256 == pending_target_pin(
            target.evidence_observation, target.identifier_scope_code, target.source_row_index
        ),
        "unresolved source target evidence changed",
    )
    return target, native


def preview_pending_target(*, target_id, product_key):
    """Inspect one frozen unresolved row against a known Product, without writes."""
    target, native = _pending_target(target_id)
    product = Product.objects.select_related("publisher_account").get(product_key=product_key)
    require(product.brand_id is not None, "a Product brand is required for matching")
    candidate = _candidate(product, native, origin_target_id=target.pk)
    report = {
        "ruleset": RULESET, "cutoff": timezone.now().isoformat(),
        "brands": [product.brand_id], "sources": [native["source"]],
        "products": [{"product_key": str(product.product_key), "candidates": [candidate]}],
        "partial": [], "writes": 0, "request_count": 0,
    }
    report["input_sha256"] = digest(report)
    return report


def _native_inventory(sources, cutoff):
    records, partial = {}, []
    for source in sources:
        base = (
            CollectionObservation.objects.filter(
                run__job__source_id=source,
                status="ok",
                observed_at__lte=cutoff,
                run__status__in=["success", "partial"],
            )
            .select_related("run__job", "legacy_archive")
            .only(
                "id",
                "run_id",
                "source_identifier",
                "source_subject_kind",
                "observed_at",
                "observation_key",
                "observation_kind",
                "legacy_archive_id",
                "legacy_archive__body",
                "legacy_archive__content_sha256",
                "run__job__source_id",
            )
        )
        if source == "github":
            scopes = [
                (
                    "repository_id",
                    base.filter(
                        source_subject_kind="repository",
                        observation_kind__in=["repository", "repository_access"],
                    ),
                )
            ]
        elif source == "openrouter":
            scopes = [
                (
                    "catalog_id",
                    base.filter(
                        source_subject_kind="model", observation_kind="model_catalog"
                    ),
                ),
                (
                    "rankings_permaslug",
                    base.filter(source_subject_kind="model").filter(
                        Q(run__job__purpose="metric")
                        | Q(observation_kind="publication_row")
                    ),
                ),
            ]
        elif source == "gdpx":
            # Published cells only; endpoint checks and publication markers
            # carry no model labels.
            scopes = [
                (
                    "model_id",
                    base.filter(source_subject_kind="model", observation_kind__isnull=True),
                )
            ]
        else:
            scopes = [
                (
                    "arena_model_name" if source == "arena" else "model_id",
                    base.filter(source_subject_kind="model"),
                )
            ]
        for scope, query in scopes:
            latest = (
                query
                .order_by("source_identifier", "-observed_at", "-pk")
                .distinct("source_identifier")
            )
            for observation in _pages(latest[:10001]):
                documents = observation_object_documents(observation)
                if len(json.dumps(documents, sort_keys=True, separators=(",", ":")).encode()) > MAX_ENVELOPE_BYTES:
                    partial.append(
                        {"source": source, "scope": scope, "reason": "oversized_evidence"}
                    )
                    continue
                row = _native(observation, scope, documents=documents)
                if row:
                    records[(source, scope, row["identifier"])] = row
            if len([k for k in records if k[0] == source]) > 10000:
                partial.append(
                    {"source": source, "scope": scope, "reason": "native_inventory_cap"}
                )
        if source in {"arena", "openrouter"}:
            windows = base.filter(
                source_subject_kind="aggregate", observation_kind="publication_window"
            )
            scope = (
                "rankings_permaslug" if source == "openrouter" else "arena_model_name"
            )
            for position, observation in enumerate(
                _pages(
                    windows.order_by(
                        "-observed_at", "-pk"
                    )[:501]
                )
            ):
                if position == 500:
                    partial.append(
                        {"source": source, "reason": "embedded_publication_cap"}
                    )
                    break
                documents = observation_object_documents(observation)
                if len(json.dumps(documents, sort_keys=True, separators=(",", ":")).encode()) > MAX_ENVELOPE_BYTES:
                    partial.append(
                        {"source": source, "reason": "oversized_embedded_publication"}
                    )
                    continue
                listing = documents[0]
                rows = listing.get("rows", []) if isinstance(listing, dict) else []
                if not isinstance(rows, list) or len(rows) > 500:
                    partial.append({"source": source, "reason": "embedded_row_cap"})
                    continue
                for row_index in range(len(rows)):
                    row = _native(observation, scope, row_index, documents)
                    if row:
                        records.setdefault((source, scope, row["identifier"]), row)
    return records, partial


def identifier_presence(*, source, kind, scope, identifier, cutoff=None, checked=True):
    """Presence is independent of candidacy, admission and numeric coverage."""
    if identifier is None:
        return "not_applicable"
    if not checked:
        return "not_checked"
    require(source in SOURCES, "unsupported matcher source")
    cutoff = aware_instant(cutoff or timezone.now())
    with bounded_reads():
        if SourceSubjectMapping.objects.filter(
            source_id=source,
            source_subject_kind=kind,
            identifier_scope__code=scope,
            external_identifier=identifier,
            reviewed_at__lte=cutoff,
        ).exists():
            return "present"
        native, partial = _native_inventory([source], cutoff)
        row = native.get((source, scope, identifier))
        return (
            "present"
            if row and row["source_subject_kind"] == kind
            else "not_checked"
            if partial
            else "absent"
        )


def _existing_mappings(product_keys, sources, cutoff):
    query = (
        SourceSubjectMapping.objects.filter(
            source_id__in=sources,
            subject__subject_kind="product",
            subject__product_id__in=product_keys,
            reviewed_at__lte=cutoff,
        )
        .select_related("subject", "identifier_scope")
        .order_by("pk")
    )
    result = defaultdict(list)
    for mapping in _pages(query):
        result[str(mapping.subject.product_id)].append(
            {
                "source": mapping.source_id,
                "identifier": mapping.external_identifier,
                "identifier_scope": mapping.identifier_scope_code,
                "source_subject_kind": mapping.source_subject_kind,
                "observed_label": mapping.identifier_metadata.get(
                    "current_full_name", mapping.external_identifier
                ),
                "db_presence": "present",
                "confidence_pct": 99,
                "confidence_basis": "legacy_review_rank_not_calibrated",
                "decision": "existing",
                "role": mapping.identity_snapshot.get("role"),
                "mapping_id": str(mapping.pk),
                "mapping_hash": mapping.mapping_hash,
                "purpose": mapping.purpose,
                "evidence_url": mapping.evidence_url,
            }
        )
    return result


def _candidate(product, native, *, origin_target_id=None):
    if origin_target_id is not None:
        name = product.repo_id.split("/")[-1] if product.repo_id else product.display_name
        require(
            bool(name) and name_key(name) == name_key(native["observed_label"].split("/")[-1]),
            "pending target does not match Product name",
        )
    publisher = (
        Account.objects.get(pk=native["publisher_account_key"])
        if native["publisher_account_key"]
        else product.publisher_account
    )
    row = {
        **native,
        "product_key": str(product.product_key),
        "role": "dedicated_model",
        "confidence_pct": 90,
        "confidence_basis": "normalized_name_only_not_calibrated",
        "decision": "needs_review",
        "reasons": ["independent_identity_review_required"],
        "publisher_account_key": str(publisher.pk) if publisher else None,
        "ownership": ownership_pin(product, publisher),
    }
    if origin_target_id is not None:
        row["origin_target_id"] = origin_target_id
    if native["source"] == "github":
        row["evidence_url"] = f"https://github.com/{native['observed_label']}"
    elif native["source"] == "openrouter":
        row["evidence_url"] = f"https://openrouter.ai/{native['identifier']}"
    else:
        row["evidence_url"] = STATIC_EVIDENCE_URLS.get(
            native["source"], "https://opencode.ai/data"
        )
    from core.collection_identity import qualified_catalog_ownership

    if publisher is None or not qualified_catalog_ownership(publisher, product=product):
        row["decision"], row["reasons"] = (
            "unmatched",
            ["publisher_ownership_unqualified"],
        )
    if native.get("review_only_variant"):
        # R13: specialist and abliterated rows never link to a base product.
        row["decision"], row["reasons"] = (
            "unmatched",
            ["specialist_or_abliterated_variant"],
        )
    # A structured explicit provider cross-reference is stronger than spelling.
    refs = (
        product.card_data.get("github", [])
        if isinstance(product.card_data, dict)
        else []
    )
    if isinstance(refs, str):
        refs = [refs]
    if (
        native["source"] == "github"
        and row["decision"] == "needs_review"
        and row["evidence_url"] in refs
    ):
        row.update(
            confidence_pct=99,
            confidence_basis="explicit_hf_repository_reference",
            decision="qualified",
            reasons=["explicit_reference_and_publisher"],
        )
    row["candidate_id"] = digest(
        {
            "product": row["product_key"],
            "source": row["source"],
            "scope": row["identifier_scope"],
            "native": row["identifier"],
        }
    )
    row["input_sha256"] = digest(row)
    return row


def preview_matches(*, brand_ids, sources=SOURCES, cutoff=None):
    require(
        isinstance(brand_ids, list) and 0 < len(brand_ids) <= 21,
        "one to 21 brands required",
    )
    require(len(set(brand_ids)) == len(brand_ids), "distinct brands required")
    require(sources and set(sources) <= set(SOURCES), "unsupported matcher source")
    cutoff = aware_instant(cutoff or timezone.now())
    with bounded_reads():
        require(
            set(Brand.objects.filter(pk__in=brand_ids).values_list("pk", flat=True))
            == set(brand_ids),
            "brand missing",
        )
        companies = BrandCompany.objects.filter(brand_id__in=brand_ids).values_list(
            "company_id", flat=True
        )
        publishers = CompanyAccount.objects.filter(
            company_id__in=companies, role_id="official", ownership_confirmed=True
        ).values_list("account_id", flat=True)
        query = (
            Product.objects.filter(
                Q(repo_id__isnull=False)
                | (Q(display_name__isnull=False) & ~Q(display_name=""))
            )
            .filter(Q(brand_id__in=brand_ids) | Q(publisher_account_id__in=publishers))
            .select_related("publisher_account")
            .order_by("product_key")
        )
        products = list(_pages(query[:10001], size=250))
        require(len(products) <= 10000, "product inventory limit exceeded")
        native, partial = _native_inventory(sources, cutoff)
        index = defaultdict(list)
        for row in native.values():
            index[name_key(row["observed_label"].split("/")[-1])].append(row)
        existing = _existing_mappings(
            [p.product_key for p in products], sources, cutoff
        )
        output = []
        for product in products:
            retained = existing[str(product.product_key)]
            known = {(r["source"], r["identifier"]) for r in retained}
            product_name = product.repo_id.split("/")[-1] if product.repo_id else product.display_name
            candidates = [
                _candidate(product, row)
                for row in index[name_key(product_name or "")]
                if (row["source"], row["identifier"]) not in known
            ]
            candidates.sort(
                key=lambda r: (r["source"], r["identifier_scope"], r["identifier"])
            )
            too_many = len(candidates) > MAX_CANDIDATES
            if too_many:
                partial.append(
                    {"product_key": str(product.product_key), "reason": "candidate_cap"}
                )
                for candidate in candidates[:MAX_CANDIDATES]:
                    _unmatch(candidate, "candidate_cap")
            output.append(
                {
                    "product_key": str(product.product_key),
                    "hf_product": product.repo_id,
                    "created_at": product.created_at.isoformat()
                    if product.created_at
                    else None,
                    "brand_id": product.brand_id,
                    "product_type": product.product_type_code,
                    "existing": retained,
                    "candidates": candidates[:MAX_CANDIDATES],
                    "candidate_overflow": too_many,
                    "unmatched_sources": sorted(
                        set(sources) - {r["source"] for r in [*retained, *candidates]}
                    ),
                }
            )
        # A normalized signature collision is never resolved by iteration order.
        claims = defaultdict(set)
        for product in output:
            for candidate in product["candidates"]:
                claims[
                    (
                        candidate["source"],
                        candidate["identifier_scope"],
                        candidate["identifier"],
                    )
                ].add(product["product_key"])
        for product in output:
            for candidate in product["candidates"]:
                key = (
                    candidate["source"],
                    candidate["identifier_scope"],
                    candidate["identifier"],
                )
                if len(claims[key]) > 1:
                    _unmatch(candidate, "competing_product_identity")
            # GDPx publishes one id per model, so two ids sharing a product
            # name are ambiguous rather than spellings of one identity.
            gdpx = [c for c in product["candidates"] if c["source"] == "gdpx"]
            if len(gdpx) > 1:
                for candidate in gdpx:
                    _unmatch(candidate, "competing_source_identity")

    def sort_key(row):
        confidence = max(
            [c["confidence_pct"] for c in [*row["existing"], *row["candidates"]]],
            default=-1,
        )
        created = (
            datetime.fromisoformat(row["created_at"]).timestamp()
            if row["created_at"]
            else float("-inf")
        )
        return (-confidence, -created, row["product_key"])

    output.sort(key=sort_key)
    report = {
        "ruleset": RULESET,
        "cutoff": cutoff.isoformat(),
        "brands": sorted(brand_ids),
        "sources": sorted(set(sources)),
        "products": output,
        "partial": partial,
        "writes": 0,
        "request_count": 0,
    }
    report["input_sha256"] = digest(report)
    return report


def _register_matches(
    preview, input_sha256, reviewed_by, review_basis, reviewed_candidate_ids
):
    from core.collection_jobs import register_job
    from core.models import DataSource

    require(
        isinstance(reviewed_by, str) and 0 < len(reviewed_by.strip()) <= 256,
        "reviewer required",
    )
    require(
        isinstance(review_basis, str) and 0 < len(review_basis.strip()) <= 2048,
        "review basis required",
    )
    require(
        preview["ruleset"] == RULESET
        and input_sha256
        == preview["input_sha256"]
        == digest({k: v for k, v in preview.items() if k != "input_sha256"}),
        "stale preview fingerprint",
    )
    choices = [c for p in preview["products"] for c in p["candidates"]]
    reviewed = set(reviewed_candidate_ids)
    require(
        not preview["partial"]
        or not any(
            c["decision"] == "qualified" and c["candidate_id"] not in reviewed
            for c in choices
        ),
        "partial preview requires explicit candidate review",
    )
    require(
        reviewed <= {c["candidate_id"] for c in choices},
        "reviewed candidate not in preview",
    )
    require(
        not any(
            c["candidate_id"] in reviewed and c["decision"] == "unmatched"
            for c in choices
        ),
        "review cannot override identity/ownership conflict",
    )
    jobs = []
    for source in preview["sources"]:
        selected = [c for c in choices if c["source"] == source]
        if not selected:
            continue
        definition = {
            "version": 1,
            "schedule": {"kind": "manual", "driver": "manual"},
            "budgets": {
                "requests": 1,
                "bytes": MAX_ENVELOPE_BYTES,
                "seconds": 120,
                "items": 50,
            },
            "scope": {
                "ruleset": RULESET,
                "preview_sha256": input_sha256,
                "cutoff": preview["cutoff"],
                "brands": preview["brands"],
                "matches": selected,
                "review": {
                    "reviewed_by": reviewed_by,
                    "basis": review_basis,
                    "candidate_ids": sorted(
                        reviewed & {c["candidate_id"] for c in selected}
                    ),
                },
            },
        }
        from core.measurement_taxonomy import resolve_subject_id
        from core.models import CollectionJob, MeasurementSubject

        key = "crosswalk:" + digest(definition)
        existing = CollectionJob.objects.filter(job_key=key).first()
        if existing and existing.instruction_version == 1:
            # Existing instructions retain their identity through expansion.
            jobs.append(
                register_job(
                    job_key=key,
                    source=DataSource.objects.get(pk=source),
                    purpose="catalog",
                    operation="match_crosswalk",
                    mode="historical",
                    definition=definition,
                )
            )
            continue
        targets = []
        for brand in preview["brands"]:
            subject, _ = MeasurementSubject.objects.get_or_create(
                id=resolve_subject_id("brand", brand),
                defaults={"subject_kind": "brand", "brand_id": brand},
            )
            targets.append(
                {
                    "target_key": "brand:" + brand,
                    "subject_id": subject.pk,
                    "target_kind": "brand",
                    "target_role": "selected",
                    "resolution_state": "resolved",
                }
            )
        for choice in selected:
            origin_id = choice.get("origin_target_id")
            parent_key = None
            if origin_id is not None:
                origin, origin_native = _pending_target(origin_id)
                require(
                    origin_native["evidence"] == choice["evidence"]
                    and origin_native["identifier"] == choice["identifier"]
                    and origin_native["publication_row_index"] == choice["publication_row_index"],
                    "pending target differs from reviewed candidate",
                )
                parent_key = f"origin-target:{origin.pk}"
                if not any(row["target_key"] == parent_key for row in targets):
                    targets.append({
                        "target_key": parent_key, "target_kind": "pending_origin",
                        "target_role": "selected", "resolution_state": "unresolved",
                        "gap_reason": origin.gap_reason, "native_identifier": origin.native_identifier,
                        "evidence_observation_id": origin.evidence_observation_id,
                        "source_row_index": origin.source_row_index,
                        "selection_sha256": origin.selection_sha256,
                    })
            subject, _ = MeasurementSubject.objects.get_or_create(
                id=resolve_subject_id("product", choice["product_key"]),
                defaults={
                    "subject_kind": "product",
                    "product_id": choice["product_key"],
                },
            )
            require(
                len(choice["reasons"]) == 1,
                "matching reason requires a typed disposition",
            )
            target_values = {
                    "target_key": choice["candidate_id"],
                    "subject_id": subject.pk,
                    "target_kind": "match_candidate",
                    "target_role": choice["decision"],
                    "resolution_state": "resolved",
                    "native_identifier": choice["identifier"],
                    "identifier_scope": choice["identifier_scope"],
                    "source_row_index": choice.get("publication_row_index"),
                    "evidence_observation_id": choice["evidence"]["observation_id"],
                    "selection_basis": choice["reasons"][0],
                    "selection_sha256": choice["input_sha256"],
                    "review_confirmed": choice["candidate_id"] in reviewed,
                }
            if parent_key:
                target_values["parent_target_key"] = parent_key
            targets.append(target_values)
        options = {
            name: definition["scope"][name]
            for name in ("ruleset", "preview_sha256", "cutoff")
        }
        options.update(reviewed_by=reviewed_by, review_basis=review_basis)
        jobs.append(
            register_job(
                job_key=key,
                source=DataSource.objects.get(pk=source),
                purpose="catalog",
                operation="match_crosswalk",
                mode="historical",
                definition={"version": 2, "options": options},
                targets=targets,
                settings={
                    "owner_kind": "source",
                    "schedule_kind": "manual",
                    "schedule_driver": "manual",
                    **{
                        "max_" + name: value
                        for name, value in definition["budgets"].items()
                    },
                },
            )
        )
    return jobs


def _admit_choice(choice, review):
    from core.collection_identity import review_catalog_mapping, review_github_mapping
    from core.measurement_taxonomy import resolve_subject_id
    from core.models import MeasurementSubject

    product = (
        Product.objects.select_for_update(of=("self",))
        .select_related("publisher_account")
        .get(product_key=choice["product_key"])
    )
    observation = (
        CollectionObservation.objects.select_for_update(of=("self",))
        .select_related("run__job")
        .get(pk=choice["evidence"]["observation_id"])
    )
    require(_evidence_pin(observation) == choice["evidence"], "source evidence changed")
    publisher = (
        Account.objects.get(pk=choice["publisher_account_key"])
        if choice["publisher_account_key"]
        else None
    )
    require(
        ownership_pin(product, publisher) == choice["ownership"],
        "product/publisher ownership changed",
    )
    require(
        choice["input_sha256"]
        == digest({k: v for k, v in choice.items() if k != "input_sha256"}),
        "candidate evidence changed",
    )
    current = _native(
        observation, choice["identifier_scope"], choice.get("publication_row_index")
    )
    require(
        current is not None
        and current["source"] == choice["source"]
        and current["identifier"] == choice["identifier"],
        "native evidence changed",
    )
    origin_id = choice.get("origin_target_id")
    if origin_id is not None:
        _, original = _pending_target(origin_id)
        require(original == current, "pending target evidence changed")
    require(
        observation.status == "ok" and observation.run.status in {"success", "partial"},
        "source evidence unavailable",
    )
    approved = choice["candidate_id"] in review["candidate_ids"]
    if choice["decision"] != "qualified" and not (
        approved and choice["decision"] == "needs_review"
    ):
        return {
            "kind": "product_match_decision",
            "candidate_id": choice["candidate_id"],
            "decision": "unmatched",
            "reasons": choice["reasons"],
            "db_presence": choice["db_presence"],
        }
    require(
        _candidate(product, current, origin_target_id=origin_id)["input_sha256"] == choice["input_sha256"],
        "candidate identity evidence changed",
    )
    subject, _ = MeasurementSubject.objects.get_or_create(
        id=resolve_subject_id("product", product.product_key),
        defaults={"subject_kind": "product", "product": product},
    )
    metadata = {
        "match_review": {
            "ruleset": RULESET,
            "basis": review["basis"],
            "reviewed_by": review["reviewed_by"],
            "owner_confirmed": approved,
            "candidate_id": choice["candidate_id"],
            "confidence_pct": choice["confidence_pct"],
            "confidence_basis": choice["confidence_basis"],
            "evidence": choice["evidence"],
            "input_sha256": choice["input_sha256"],
        }
    }
    if choice["source"] == "github":
        mapping = review_github_mapping(
            subject=subject,
            repo=current["repo"],
            role=choice["role"],
            evidence_url=choice["evidence_url"],
            reviewed_by=review["reviewed_by"],
            identifier_metadata=metadata,
        )
    else:
        mapping = review_catalog_mapping(
            source=observation.run.job.source,
            subject=subject,
            external_identifier=choice["identifier"],
            source_subject_kind=choice["source_subject_kind"],
            identifier_scope=choice["identifier_scope"],
            publisher_account=publisher,
            role=choice["role"],
            version_selector=None,
            evidence_url=choice["evidence_url"],
            reviewed_by=review["reviewed_by"],
            identifier_metadata=metadata,
            identity_snapshot={
                "provider": choice["source"],
                "native_id": choice["identifier"],
                "evidence": choice["evidence"],
            },
        )
    return {
        "kind": "product_match_decision",
        "candidate_id": choice["candidate_id"],
        "decision": "admitted",
        "mapping_id": str(mapping.pk),
        "mapping_hash": mapping.mapping_hash,
        "db_presence": "present",
    }


def execute_matches(job_id):
    from collections import Counter

    from core.collection_identity import MappingBusy, MappingConflict
    from core.collection_jobs import set_job_state, validate_job
    from core.collection_state import checkpoint_scope, claim_job, finish_run
    from core.models import (
        CollectionJob,
        CollectionObservation,
        CollectionObservationInput,
        CollectionScopeRun,
    )

    job = CollectionJob.objects.get(pk=job_id)
    validate_job(job)
    scope = job.scope
    require(
        job.operation == "match_crosswalk" and scope["ruleset"] == RULESET,
        "matching instruction required",
    )
    require(
        bool(scope["matches"]) and scope["review"]["reviewed_by"] and scope["review"]["basis"],
        "pending selections need a reviewed resolution before execution",
    )
    if job.state == "completed":
        return {
            "job_id": str(job.pk),
            "run_id": str(job.last_success_id),
            "status": "success",
            "reused": True,
        }
    if job.state == "paused":
        set_job_state(job.pk, "ready")
    claim = claim_job(job.pk, typed=True)
    completed = set(
        CollectionScopeRun.objects.filter(
            run_id=claim.run_id, enumeration_complete=True
        ).values_list("scope_key", flat=True)
    )
    pending = [c for c in scope["matches"] if c["candidate_id"] not in completed]
    deadline = monotonic() + job.budgets["seconds"]
    try:
        for choice in pending[:50]:
            if monotonic() >= deadline:
                break
            def write(run, scoped, choice=choice):
                decision = _admit_choice(choice, scope["review"])
                require(
                    len(json.dumps(decision).encode()) <= MAX_ENVELOPE_BYTES,
                    "decision byte cap",
                )
                require(
                    decision["decision"] in {"admitted", "unmatched"},
                    "unsupported product-match decision",
                )
                scoped.admission_outcome = decision["decision"]
                result = CollectionObservation.objects.create(
                    run=run, scope_run=scoped,
                    observation_kind="product_match_decision",
                    observation_key=digest(["product_match_decision", str(scoped.pk)]),
                    source_identifier=choice["candidate_id"],
                    source_subject_kind=choice["source_subject_kind"],
                    product_id=scoped.job_target.subject.product.pk,
                    mapping_id=(
                        uuid.UUID(decision["mapping_id"])
                        if decision["decision"] == "admitted" else None
                    ),
                    processing_outcome=decision["decision"],
                )
                CollectionObservationInput.objects.create(
                    observation=result,
                    input_observation_id=choice["evidence"]["observation_id"],
                    input_role="match_candidate",
                    input_sha256=choice["evidence"]["payload_hash"],
                    row_locator=(
                        f"target:{choice['origin_target_id']};row:{choice['publication_row_index']}"
                        if choice.get("origin_target_id") is not None else None
                    ),
                )

            admitted = choice["decision"] == "qualified" or (
                choice["decision"] == "needs_review"
                and choice["candidate_id"] in scope["review"]["candidate_ids"]
            )
            try:
                with bounded_reads():
                    checkpoint_scope(
                        claim,
                        scope_kind="product_match",
                        scope_key=choice["candidate_id"],
                        ownership={
                            "product_key": choice["product_key"],
                            "input_sha256": choice["input_sha256"],
                        },
                        outcome="admitted" if admitted else "unmatched",
                        enumeration_complete=True,
                        typed=True,
                        write=write,
                    )
            except MappingBusy:
                break
            except MappingConflict:
                def record_conflict(run, scoped, choice=choice):
                    scoped.admission_outcome = "conflict"
                    scoped.error_code = "native_dedicated_identity_conflict"
                    result = CollectionObservation.objects.create(
                        run=run, scope_run=scoped,
                        observation_kind="product_match_decision",
                        observation_key=digest(["product_match_decision", str(scoped.pk)]),
                        source_identifier=choice["candidate_id"],
                        source_subject_kind=choice["source_subject_kind"],
                        product_id=scoped.job_target.subject.product.pk,
                        processing_outcome="conflict",
                        status="error",
                        error_code="native_dedicated_identity_conflict",
                    )
                    CollectionObservationInput.objects.create(
                        observation=result,
                        input_observation_id=choice["evidence"]["observation_id"],
                        input_role="match_candidate",
                        input_sha256=choice["evidence"]["payload_hash"],
                        row_locator=(
                            f"target:{choice['origin_target_id']};row:{choice['publication_row_index']}"
                            if choice.get("origin_target_id") is not None else None
                        ),
                    )

                checkpoint_scope(
                    claim,
                    scope_kind="product_match",
                    scope_key=choice["candidate_id"],
                    ownership={
                        "product_key": choice["product_key"],
                        "input_sha256": choice["input_sha256"],
                    },
                    outcome="conflict",
                    enumeration_complete=True,
                    typed=True,
                    write=record_conflict,
                )
        scopes = list(CollectionScopeRun.objects.filter(
            run_id=claim.run_id, scope_kind="product_match",
        ))
        counts = Counter(s.outcome for s in scopes if s.enumeration_complete)
        complete = len(scopes) == len(scope["matches"])
        run = finish_run(
            claim,
            status="success" if complete else "partial",
            request_count=0,
            selected_count=len(scopes),
            success_count=counts["admitted"],
            typed=True,
            physical_accounting_complete=True,
        )
        return {
            "job_id": str(job.pk),
            "run_id": str(run.pk),
            "status": run.status,
            "decisions": dict(counts),
            "remaining": len(scope["matches"]) - len(scopes),
        }
    except Exception:
        finish_run(
            claim,
            status="partial",
            error_code="matching_validation_failed",
            request_count=0,
            typed=True,
            physical_accounting_complete=True,
        )
        raise


def match_report(run):
    """Rebuild match outcomes from frozen candidates and typed scope decisions."""
    from collections import Counter

    require(run.job.operation == "match_crosswalk", "product-match run required")
    scopes = list(run.scopes.filter(scope_kind="product_match", phase="typed-product-match-v1"))
    require(
        all(scope.admission_outcome == scope.outcome for scope in scopes),
        "product-match scope decision changed",
    )
    for scope in scopes:
        decisions = list(scope.observations.filter(
            observation_kind="product_match_decision",
        ).select_related("mapping"))
        require(
            len(decisions) == 1
            and decisions[0].processing_outcome == scope.outcome
            and (decisions[0].mapping_id is not None) == (scope.outcome == "admitted")
            and decisions[0].inputs.filter(
                input_role="match_candidate",
                input_observation_id=scope.job_target.evidence_observation_id,
            ).count() == 1,
            "product-match decision evidence changed",
        )
    counts = Counter(scope.outcome for scope in scopes if scope.enumeration_complete)
    attempt = run.attempts.order_by("-ordinal").first()
    return {
        "ruleset": RULESET,
        "decisions": dict(counts),
        "remaining": len(run.job.scope["matches"]) - len(scopes),
        "provider_calls": 0,
        "historical_metrics_changed": False,
        "physical_accounting_complete": attempt.accounting_complete is True if attempt else False,
    }


def apply_matches(
    *,
    preview=None,
    input_sha256=None,
    reviewed_by=None,
    review_basis=None,
    reviewed_candidate_ids=(),
    resume_job_id=None,
):
    if resume_job_id is not None:
        require(preview is None, "resume uses database instructions only")
        return execute_matches(resume_job_id)
    require(preview is not None, "preview required")
    with transaction.atomic():
        jobs = _register_matches(
            preview, input_sha256, reviewed_by, review_basis, reviewed_candidate_ids
        )
    results = [execute_matches(job.pk) for job in jobs]
    return {
        "status": "success"
        if all(r["status"] == "success" for r in results)
        else "partial",
        "jobs": results,
        "request_count": 0,
    }


def markdown_report(report):
    """Same evidence and decisions as JSON; formatting adds no business state."""
    lines = [
        "# Product crosswalk report",
        "",
        "```json",
        json.dumps({k: v for k, v in report.items() if k != "products"}, indent=2),
        "```",
    ]
    for row in report.get("products", []):
        lines.extend(
            [
                "",
                f"## {row['hf_product']}",
                "",
                "```json",
                json.dumps(row, indent=2),
                "```",
            ]
        )
    return "\n".join(lines)
