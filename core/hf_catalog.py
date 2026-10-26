"""Manual public model catalog: frozen publisher scope and resumable collection."""

from __future__ import annotations

import json
import uuid
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import yaml
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DataError, connection, transaction
from django.db.models import Q
from django.utils import timezone

from core.account_identity import publisher_discovery_label, publisher_identifier
from core.collection_groups import observation_group_outcomes, record_observation_group
from core.collection_state import claim_direct_run, fenced_run, register_direct_job
from core.hf_metadata_client import INVENTORY_VERSION, NAMESPACE, REPO_ID
from core.measurement_taxonomy import digest
from core.models import (
    Brand,
    BrandCompany,
    CollectionObservation,
    CollectionRun,
    CollectionScopeRun,
    Company,
    DataSource,
    Product,
)
from core.product_metadata import apply_metadata
from core.publisher_accounts import get_publisher, publisher_links

FRONTIER_COMPANIES = ("openai", "anthropic", "google", "xai")
CATALOG_LOCK = 6842060924
METADATA_GROUPS = ("detail", "expanded")


def groups_complete(groups):
    return all(groups.get(group) == "ok" for group in METADATA_GROUPS) and all(
        outcome == "ok" for outcome in groups.values()
    )


def resolve_scope(*, brands=None, companies=None, namespace=None, rules=None):
    """Read only. Every missing mapping stays visible in the frozen manifest."""
    if brands is None:
        brands = yaml.safe_load((Path(settings.BASE_DIR) / "config.yaml").read_text())[
            "enabled_models"
        ]
    if companies is None:
        companies = FRONTIER_COMPANIES
    if rules is None:
        rules = yaml.safe_load(
            (Path(settings.BASE_DIR) / "config/hf_catalog.yaml").read_text()
        )["brand_rules"]
    gaps, entries = [], []
    selected = set(companies)
    for name in sorted(set(brands)):
        if not Brand.objects.filter(pk=name, is_sentinel=False).exists():
            gaps.append({"brand": name, "reason": "missing_brand"})
            continue
        owners = list(
            BrandCompany.objects.filter(brand_id=name).values_list(
                "company_id", flat=True
            )
        )
        if not owners:
            gaps.append({"brand": name, "reason": "missing_company_edge"})
        selected.update(owners)
    for company in sorted(selected):
        if not Company.objects.filter(pk=company).exists():
            gaps.append({"company": company, "reason": "missing_company"})
            continue
        orgs = publisher_links(source="hf", company_id=company)
        if namespace:
            orgs = orgs.filter(account__normalized_identifier=namespace.casefold())
        if not orgs.exists():
            gaps.append({"company": company, "reason": "missing_namespace"})
        for org in orgs:
            if not org.ownership_confirmed:
                gaps.append(
                    {
                        "company": company,
                        "namespace": publisher_identifier(org.account),
                        "reason": "unconfirmed_namespace",
                    }
                )
                continue
            if not NAMESPACE.fullmatch(publisher_identifier(org.account)):
                raise ValueError("invalid stored HF namespace")
            entries.append(
                {
                    "namespace": publisher_identifier(org.account),
                    "company": company,
                    "brands": sorted(
                        BrandCompany.objects.filter(
                            company_id=company, brand__is_sentinel=False
                        ).values_list("brand_id", flat=True)
                    ),
                    "ownership_evidence": publisher_discovery_label(org.account),
                    "source_url": f"https://huggingface.co/{publisher_identifier(org.account)}",
                }
            )
    entries.sort(key=lambda row: row["namespace"].casefold())
    validate_rules(rules, entries)
    return {
        "version": 1,
        "inventory_version": INVENTORY_VERSION,
        "brands": sorted(set(brands)),
        "companies": sorted(set(companies)),
        "namespace_filter": namespace,
        "namespaces": entries,
        "gaps": gaps,
        "rules": deepcopy(rules),
    }


def validate_rules(rules, entries):
    known = {row["namespace"].casefold(): row for row in entries}
    seen = []
    for rule in rules:
        ns = rule.get("namespace", "")
        exact, prefix = rule.get("repo"), rule.get("prefix")
        if (
            not NAMESPACE.fullmatch(ns)
            or bool(exact) == bool(prefix)
            or not rule.get("source")
            or not rule.get("brand")
        ):
            raise ValueError("invalid HF attribution rule")
        if exact and (
            not REPO_ID.fullmatch(exact)
            or exact.split("/")[0].casefold() != ns.casefold()
        ):
            raise ValueError("invalid exact repository rule")
        if (
            ns.casefold() in known
            and rule["brand"] not in known[ns.casefold()]["brands"]
        ):
            raise ValueError("attribution rule brand does not own namespace")
        pattern = (exact or f"{ns}/{prefix}").casefold()
        for old_ns, old_pattern, old_exact in seen:
            if ns.casefold() != old_ns:
                continue
            overlap = (
                pattern == old_pattern
                or (not exact and old_pattern.startswith(pattern))
                or (not old_exact and pattern.startswith(old_pattern))
            )
            if overlap:
                raise ValueError("overlapping HF attribution rules")
        seen.append((ns.casefold(), pattern, bool(exact)))


def resolve_brand(repo_id, entry, rules):
    matches = [
        r["brand"]
        for r in rules
        if r["namespace"].casefold() == entry["namespace"].casefold()
        and (
            repo_id.casefold() == r.get("repo", "").casefold()
            or (
                r.get("prefix")
                and repo_id.split("/", 1)[1]
                .casefold()
                .startswith(r["prefix"].casefold())
            )
        )
    ]
    if matches:
        return matches[0]
    return entry["brands"][0] if len(entry["brands"]) == 1 else None


@contextmanager
def catalog_lock():
    if connection.vendor != "postgresql":
        raise ValueError("HF catalog requires PostgreSQL")
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [CATALOG_LOCK])
        acquired = cursor.fetchone()[0]
    if not acquired:
        raise ValueError("HF catalog is already running")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [CATALOG_LOCK])


def check_scope(scope):
    current = resolve_scope(
        brands=scope["brands"],
        companies=scope["companies"],
        namespace=scope["namespace_filter"],
        rules=scope["rules"],
    )
    if current != scope:
        raise ValueError("HF catalog scope changed; preview and start a new refresh")


@transaction.atomic
def persist_product(observation, entry, rules, payload, group):
    if (
        observation.run.purpose != "catalog"
        or observation.run.source_id != "hf"
        or observation.scope_run_id is None
        or observation.scope_run.run_id != observation.run_id
    ):
        raise ValueError("HF catalog projection requires matching catalog evidence")
    org = get_publisher(source="hf", identifier=entry["namespace"], lock=True)
    brands = sorted(
        BrandCompany.objects.select_for_update()
        .filter(company_id=org.company_id, brand__is_sentinel=False)
        .values_list("brand_id", flat=True)
    )
    if (
        not org.ownership_confirmed
        or org.company_id != entry["company"]
        or brands != entry["brands"]
    ):
        raise ValueError("HF catalog scope changed during collection")
    product, created = Product.objects.get_or_create(
        repo_id=observation.source_identifier,
        defaults={
            "publisher_account": org.account,
            "brand_id": resolve_brand(observation.source_identifier, entry, rules),
            "display_name": observation.source_identifier.split("/", 1)[1],
        },
    )
    product = Product.objects.select_for_update().get(pk=product.pk)
    if (
        product.hf_type != "model"
        or (
            product.hf_namespace
            and product.hf_namespace.casefold()
            != publisher_identifier(org.account).casefold()
        )
        or (product.brand_id and product.brand_id not in brands)
    ):
        observation.processing_outcome = "owner_conflict"
        observation.save(update_fields=["processing_outcome", "updated_at"])
        return
    observation.product = product
    observation.created_product = observation.created_product or created
    observation.processing_outcome = (
        "complete" if groups_complete(observation_group_outcomes(observation)) else "pending"
    )
    if not product.publisher_account_id:
        product.publisher_account = org.account
    if not product.brand_id:
        product.brand_id = resolve_brand(observation.source_identifier, entry, rules)
    product.save(update_fields=["brand", "publisher_account", "updated_at"])
    try:
        with transaction.atomic():
            apply_metadata(
                product,
                payload,
                group=group,
                observation={
                    "id": observation.pk,
                    "run_id": str(observation.run_id),
                },
            )
    except (ValidationError, DataError, ValueError, TypeError):
        record_observation_group(observation, group, "projection_error")
        observation.processing_outcome = "projection_error"
    else:
        if group == "listing":
            record_observation_group(observation, group, "ok")
        observation.processing_outcome = (
            "complete" if groups_complete(observation_group_outcomes(observation)) else "pending"
        )
    observation.save(
        update_fields=[
            "product",
            "created_product",
            "groups",
            "processing_outcome",
            "updated_at",
        ]
    )


def _envelopes(result, group):
    return [
        {
            **json.loads(json.dumps(attempt)),
            "group": group,
            "validation_outcome": result.outcome,
            "returned_fields": sorted(attempt["payload"])
            if isinstance(attempt.get("payload"), dict)
            else None,
            "source_sha": attempt["payload"].get("sha")
            if isinstance(attempt.get("payload"), dict)
            else None,
        }
        for attempt in result.attempts
    ]


def _accepted_request(result):
    """The accepted response, excluding failed retries and rejected payloads."""
    from core.models import CollectionRequest

    if result.outcome not in {"ok", "partial_expansion"}:
        return None
    for attempt in reversed(result.attempts):
        if attempt.get("outcome") == "ok" and attempt.get("collection_request_id"):
            return CollectionRequest.objects.get(pk=attempt["collection_request_id"])
    return None


@transaction.atomic
def _persist_page(ns, result, rules):
    from core.collection_capture import link_request
    from core.collection_cursors import replace_scope_cursor_history

    ns.envelopes += _envelopes(result, "listing")
    ns.raw_count += len(result.payload)
    request = _accepted_request(result)
    for ordinal, item in enumerate(result.payload):
        repo = item.get("id") or item["modelId"]
        observation, _ = ns.observations.get_or_create(
            resource_key=repo.casefold(),
            defaults={
                "run": ns.run,
                "source_identifier": repo,
                "source_subject_kind": "repository",
                "observation_key": digest(
                    ["catalog", str(ns.run_id), ns.scope_key, repo.casefold()]
                ),
                "processing_outcome": "pending",
            },
        )
        observation.listing = item
        observation.save(update_fields=["listing", "updated_at"])
        persist_product(observation, ns.ownership, rules, item, "listing")
        if request is not None:
            link_request(observation, request, role="listing", row_locator=str(ordinal))
    cursors = ns.recorded_cursors
    if result.next_cursor and result.next_cursor in cursors:
        ns.outcome = "repeated_cursor"
    elif result.next_cursor and not result.payload:
        ns.outcome = "empty_page_with_cursor"
    else:
        ns.cursor = result.next_cursor
        ns.enumeration_complete = not bool(result.next_cursor)
        ns.outcome = "exhausted" if ns.enumeration_complete else "pending"
        if result.next_cursor:
            cursors.append(result.next_cursor)
    replace_scope_cursor_history(ns, cursors)
    ns.save()


def _save_scope(ns, claim, **kwargs):
    from core.collection_cursors import replace_scope_cursor_history

    with fenced_run(claim):
        if ns.outcome == "cursor_restart":
            replace_scope_cursor_history(ns, [])
        ns.save(**kwargs)


def _enrich(ns, hf, rules, visited, max_models, attempted, claim):
    from core.collection_capture import link_request

    for observation in (
        ns.observations.exclude(processing_outcome__in=["owner_conflict", "complete"])
        .select_related("run__job")
        .defer("run__raw_payload", "run__job__definition")
        .order_by("id")
    ):
        if groups_complete(observation_group_outcomes(observation)):
            continue
        if (
            observation.resource_key not in visited
            and max_models is not None
            and len(visited) >= max_models
        ):
            return "model_cap"
        visited.add(observation.resource_key)
        for group in METADATA_GROUPS:
            if observation_group_outcomes(observation).get(group) == "ok":
                continue
            key = (observation.pk, group)
            if key in attempted:
                continue
            if hf.stop_reason:
                return hf.stop_reason
            attempted.add(key)
            result = hf.model_group(observation.source_identifier, group)
            with fenced_run(claim):
                observation.envelopes += _envelopes(result, group)
                record_observation_group(observation, group, result.outcome)
                if result.outcome in {"ok", "partial_expansion"}:
                    persist_product(
                        observation, ns.ownership, rules, result.payload, group
                    )
                    request = _accepted_request(result)
                    if request is not None:
                        link_request(observation, request, role=group)
                if observation.processing_outcome not in {
                    "owner_conflict",
                    "projection_error",
                }:
                    observation.processing_outcome = (
                        "complete" if groups_complete(observation_group_outcomes(observation)) else "partial"
                    )
                observation.save()
    return None


def _walk_namespace(ns, hf, rules, visited, max_models, claim):
    # Completed namespace identity and pages are durable; resuming enrichment
    # does not spend requests checking them again.
    if not any(
        e["group"] == "identity" and e.get("validation_outcome") == "ok"
        for e in ns.envelopes
    ):
        result = hf.namespace_info(ns.scope_key)
        ns.envelopes += _envelopes(result, "identity")
        ns.outcome = result.outcome
        _save_scope(ns, claim)
        if result.outcome != "ok":
            return
    attempted = set()
    if reason := _enrich(ns, hf, rules, visited, max_models, attempted, claim):
        ns.outcome = reason
        _save_scope(ns, claim, update_fields=["outcome"])
        return
    restarted = False
    while not ns.enumeration_complete:
        if hf.stop_reason:
            ns.outcome = hf.stop_reason
            _save_scope(ns, claim, update_fields=["outcome"])
            return
        remaining = None if max_models is None else max_models - len(visited)
        if remaining is not None and remaining <= 0:
            ns.outcome = "model_cap"
            _save_scope(ns, claim, update_fields=["outcome"])
            return
        result = hf.list_page(ns.scope_key, ns.cursor, limit=min(100, remaining or 100))
        if result.outcome != "ok":
            ns.envelopes += _envelopes(result, "listing")
            ns.outcome = result.outcome
            # Only an explicit invalid-cursor response permits a restart. One
            # restart per invocation prevents an expired cursor loop.
            if (
                ns.cursor
                and not restarted
                and result.outcome in {"http_400", "http_422"}
            ):
                ns.cursor = None
                ns.outcome = "cursor_restart"
                restarted = True
                _save_scope(ns, claim)
                continue
            _save_scope(ns, claim)
            return
        if len(result.payload) > min(100, remaining or 100):
            ns.envelopes += _envelopes(result, "listing")
            ns.outcome = "provider_exceeded_limit"
            _save_scope(ns, claim)
            return
        with fenced_run(claim):
            _persist_page(ns, result, rules)
        visited.update(
            (item.get("id") or item["modelId"]).casefold() for item in result.payload
        )
        if ns.outcome in {"repeated_cursor", "empty_page_with_cursor"}:
            return
        if reason := _enrich(ns, hf, rules, visited, max_models, attempted, claim):
            ns.outcome = reason
            _save_scope(ns, claim, update_fields=["outcome"])
            return
    ns.outcome = "exhausted"
    _save_scope(ns, claim, update_fields=["outcome"])


def catalog_report(run, *, requests=0, cumulative_requests=0, stop_reason=None):
    observations = CollectionObservation.objects.filter(scope_run__run=run)
    conflicts = observations.filter(processing_outcome="owner_conflict").count()
    gaps = observations.filter(
        product__isnull=False, product__brand__isnull=True
    ).count()
    namespaces = [
        {
            "namespace": ns.scope_key,
            "enumeration_complete": ns.enumeration_complete,
            "outcome": ns.outcome,
            "raw_count": ns.raw_count,
            "next_cursor": ns.cursor,
            "unique_models": ns.observations.count(),
        }
        for ns in run.scopes.filter(scope_kind="namespace").order_by("scope_key")
    ]
    enumeration_complete = bool(namespaces) and all(
        ns["enumeration_complete"] for ns in namespaces
    )
    enrichment_complete = (
        not observations.exclude(processing_outcome="complete").exists()
        and not observations.filter(product__isnull=True).exists()
    )
    stored_groups = [
        observation_group_outcomes(observation)
        for observation in observations.only("id", "run_id", "scope_run_id", "groups").prefetch_related("resource_scopes")
    ]
    group_outcomes = {
        group: dict(Counter(row.get(group, "pending") for row in stored_groups))
        for group in METADATA_GROUPS
    }
    imported = observations.filter(created_product=True).count()
    products = observations.filter(product__isnull=False).count()
    return {
        "run_id": str(run.pk),
        "complete": enumeration_complete
        and enrichment_complete
        and not run.job.scope["gaps"]
        and not gaps
        and not conflicts,
        "enumeration_complete": enumeration_complete,
        "enrichment_complete": enrichment_complete,
        "scope_gaps": run.job.scope["gaps"],
        "attribution_gaps": gaps,
        "conflicts": conflicts,
        "group_outcomes": group_outcomes,
        "attribution_gap_repositories": list(
            observations.filter(
                product__isnull=False, product__brand__isnull=True
            ).values_list("source_identifier", flat=True)
        ),
        "unique_models": observations.count(),
        "imported": imported,
        "updated": products - imported,
        "requests": requests,
        "cumulative_requests": cumulative_requests,
        "stop_reason": stop_reason
        or (
            "model_cap"
            if any(ns["outcome"] == "model_cap" for ns in namespaces)
            else None
        ),
        "namespaces": namespaces,
    }


def resolve_catalog_run(run_id):
    """Accept saved pre-merge UUIDs while isolating the HF catalog purpose."""
    return CollectionRun.objects.get(
        Q(pk=run_id) | Q(source_metadata__legacy_catalog__run_id=str(run_id)),
        job__source_id="hf",
        job__purpose="catalog",
    )


def catalog_scope(run):
    """Read the frozen instructions owned by this run's job."""
    return run.job.scope


def execute_catalog(*, hf, scope=None, run_id=None, max_models=None):
    if (scope is None) == (run_id is None):
        raise ValueError("supply scope or resume run, exclusively")
    if max_models is not None and max_models < 1:
        raise ValueError("model budget must be positive")
    limits = {
        "requests": hf.max_requests,
        "seconds": hf.max_seconds,
        "response_bytes": hf.max_bytes,
        "total_bytes": hf.max_total_bytes,
        "models": max_models,
    }
    with catalog_lock():
        if run_id is not None:
            run = resolve_catalog_run(run_id)
            check_scope(catalog_scope(run))
        else:
            check_scope(scope)
            with transaction.atomic():
                source, _ = DataSource.objects.get_or_create(
                    pk="hf",
                    defaults={"name": "Hugging Face", "source_type": "model_adoption"},
                )
                run_id = uuid.uuid4()
                run = CollectionRun(
                    id=run_id,
                    job=register_direct_job(
                        source_id=source.pk,
                        purpose="catalog",
                        scope=scope,
                        driver="execute_catalog",
                        limits=limits,
                    ),
                    status="pending",
                    ingestion_key=digest(["catalog", "hf", str(run_id)]),
                )
        claim = claim_direct_run(
            run,
            driver="execute_catalog",
            seconds=hf.max_seconds + 60,
            limits=limits,
        )
        prior_requests = sum(
            run.attempts.exclude(pk=claim.attempt_id).values_list(
                "actual_requests", flat=True
            )
        )
        if run_id is not None and not run.scopes.filter(scope_kind="namespace").exists():
            with fenced_run(claim):
                for entry in run.job.scope["namespaces"]:
                    CollectionScopeRun.objects.create(
                        run=run,
                        scope_key=entry["namespace"],
                        ownership=entry,
                    )
        run.status = "running"
        run.completed_at = None
        with fenced_run(claim):
            run.save()

        def record_request(_envelope):
            run.request_count = prior_requests + hf.requests
            with fenced_run(claim):
                attempt = run.attempts.get(pk=claim.attempt_id)
                attempt.retry_count = hf.retries
                attempt.save(update_fields=["retry_count"])
                run.save(update_fields=["request_count", "updated_at"])

        hf.on_attempt = record_request
        from core.collection_capture import RequestCapture

        previous_capture = hf.capture
        previous_scope = hf.collection_scope
        hf.capture = RequestCapture(claim)
        try:
            visited = set()
            for ns in run.scopes.filter(scope_kind="namespace").order_by("scope_key"):
                if hf.stop_reason:
                    break
                hf.collection_scope = ns
                _walk_namespace(
                    ns,
                    hf,
                    run.job.scope["rules"],
                    visited,
                    max_models,
                    claim,
                )
            report = catalog_report(
                run,
                requests=hf.requests,
                cumulative_requests=prior_requests + hf.requests,
                stop_reason=hf.stop_reason,
            )
            run.status = "success" if report["complete"] else "partial"
            report["stop_reason"] = (
                "complete"
                if report["complete"]
                else (report["stop_reason"] or "coverage_gaps")
            )
            run.report = report
            run.selected_count = report["unique_models"]
            run.success_count = run.observations.filter(
                processing_outcome="complete"
            ).count()
            run.completed_at = timezone.now() if report["complete"] else None
            return report
        except BaseException:
            run.status = "interrupted"
            run.report = {
                **run.report,
                "complete": False,
                "stop_reason": "interrupted",
                "requests": hf.requests,
            }
            raise
        finally:
            run.request_count = prior_requests + hf.requests
            try:
                with fenced_run(claim):
                    run.save()
                    from core.collection_state import complete_attempt

                    complete_attempt(
                        claim, run, status=run.status,
                        request_count=prior_requests + hf.requests,
                    )
            finally:
                hf.on_attempt = None
                hf.capture = previous_capture
                hf.collection_scope = previous_scope
