"""Conservative crosswalk proposals from stored evidence, without provider calls.

Preview is read-only. Reviewed choices become immutable collection instructions;
only the fenced executor calls the shared catalog admission writer.
"""

from __future__ import annotations

import json
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
SOURCES = ("github", "openrouter", "arena", "opencode")
MAX_CANDIDATES = 5
MAX_ENVELOPE_BYTES = 32768


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

    return {
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


def _native(observation, scope, row_index=None, documents=None):
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
        "evidence": _evidence_pin(observation, documents),
        "publisher_account_key": str(publisher.pk) if publisher else None,
        "repo": repo_pin,
        "publication_row_index": row_index,
    }


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


def _candidate(product, native):
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
    row["evidence_url"] = (
        f"https://github.com/{native['observed_label']}"
        if native["source"] == "github"
        else f"https://openrouter.ai/{native['identifier']}"
        if native["source"] == "openrouter"
        else "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset"
        if native["source"] == "arena"
        else "https://opencode.ai/data"
    )
    from core.collection_identity import qualified_catalog_ownership

    if publisher is None or not qualified_catalog_ownership(publisher, product=product):
        row["decision"], row["reasons"] = (
            "unmatched",
            ["publisher_ownership_unqualified"],
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
            Product.objects.filter(repo_id__isnull=False)
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
            candidates = [
                _candidate(product, row)
                for row in index[name_key(product.repo_id.split("/")[-1])]
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
                    candidate.update(decision="unmatched", reasons=["candidate_cap"])
                    candidate["input_sha256"] = digest(
                        {k: v for k, v in candidate.items() if k != "input_sha256"}
                    )
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
                    candidate.update(
                        decision="unmatched", reasons=["competing_product_identity"]
                    )
                    candidate["input_sha256"] = digest(
                        {k: v for k, v in candidate.items() if k != "input_sha256"}
                    )

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
            targets.append(
                {
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
            )
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
        _candidate(product, current)["input_sha256"] == choice["input_sha256"],
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
