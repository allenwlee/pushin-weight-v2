"""Manual public model catalog: frozen publisher scope and resumable collection."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import yaml
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DataError, connection, transaction
from django.utils import timezone

from core.hf_metadata_client import INVENTORY_VERSION, NAMESPACE, REPO_ID
from core.models import (
    Brand,
    BrandCompany,
    Company,
    HFModelCatalogNamespaceRun,
    HFModelCatalogObservation,
    HFModelCatalogRun,
    HFOrg,
    Product,
)
from core.product_metadata import apply_metadata

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
        orgs = HFOrg.objects.filter(company_id=company)
        if namespace:
            orgs = orgs.filter(namespace=namespace)
        if not orgs.exists():
            gaps.append({"company": company, "reason": "missing_namespace"})
        for org in orgs:
            if not org.confirmed:
                gaps.append(
                    {
                        "company": company,
                        "namespace": org.pk,
                        "reason": "unconfirmed_namespace",
                    }
                )
                continue
            if not NAMESPACE.fullmatch(org.pk):
                raise ValueError("invalid stored HF namespace")
            entries.append(
                {
                    "namespace": org.pk,
                    "company": company,
                    "brands": sorted(
                        BrandCompany.objects.filter(
                            company_id=company, brand__is_sentinel=False
                        ).values_list("brand_id", flat=True)
                    ),
                    "ownership_evidence": org.discovered_via,
                    "source_url": f"https://huggingface.co/{org.pk}",
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
    org = HFOrg.objects.select_for_update().get(pk=entry["namespace"])
    brands = sorted(
        BrandCompany.objects.select_for_update()
        .filter(company_id=org.company_id, brand__is_sentinel=False)
        .values_list("brand_id", flat=True)
    )
    if (
        not org.confirmed
        or org.company_id != entry["company"]
        or brands != entry["brands"]
    ):
        raise ValueError("HF catalog scope changed during collection")
    product, created = Product.objects.get_or_create(
        repo_id=observation.repo_id,
        defaults={
            "hf_org": org,
            "brand_id": resolve_brand(observation.repo_id, entry, rules),
            "display_name": observation.repo_id.split("/", 1)[1],
        },
    )
    product = Product.objects.select_for_update().get(pk=product.pk)
    if (
        product.hf_type != "model"
        or (product.hf_org_id and product.hf_org_id.casefold() != org.pk.casefold())
        or (product.brand_id and product.brand_id not in brands)
    ):
        observation.outcome = "owner_conflict"
        observation.save(update_fields=["outcome", "updated_at"])
        return
    observation.product = product
    observation.created_product = observation.created_product or created
    observation.outcome = (
        "complete" if groups_complete(observation.groups) else "pending"
    )
    if not product.hf_org_id:
        product.hf_org = org
    if not product.brand_id:
        product.brand_id = resolve_brand(observation.repo_id, entry, rules)
    product.save(update_fields=["brand", "hf_org", "updated_at"])
    try:
        with transaction.atomic():
            apply_metadata(
                product,
                payload,
                group=group,
                observation={
                    "id": observation.pk,
                    "run_id": str(observation.namespace_run.run_id),
                },
            )
        if group == "listing":
            observation.groups[group] = "ok"
        observation.outcome = (
            "complete" if groups_complete(observation.groups) else "pending"
        )
    except (ValidationError, DataError, ValueError, TypeError):
        observation.groups[group] = "projection_error"
        observation.outcome = "projection_error"
    observation.save(
        update_fields=["product", "created_product", "groups", "outcome", "updated_at"]
    )


def _envelopes(result, group):
    return [
        {
            **attempt,
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


@transaction.atomic
def _persist_page(ns, result, rules):
    ns.envelopes += _envelopes(result, "listing")
    ns.raw_count += len(result.payload)
    for item in result.payload:
        repo = item.get("id") or item["modelId"]
        observation, _ = ns.observations.get_or_create(
            repo_key=repo.casefold(), defaults={"repo_id": repo}
        )
        observation.listing = item
        observation.save(update_fields=["listing", "updated_at"])
        persist_product(observation, ns.ownership, rules, item, "listing")
    if result.next_cursor and result.next_cursor in ns.cursor_history:
        ns.outcome = "repeated_cursor"
    elif result.next_cursor and not result.payload:
        ns.outcome = "empty_page_with_cursor"
    else:
        ns.cursor = result.next_cursor
        ns.enumeration_complete = not bool(result.next_cursor)
        ns.outcome = "exhausted" if ns.enumeration_complete else "pending"
        if result.next_cursor:
            ns.cursor_history.append(result.next_cursor)
    ns.save()


def _enrich(ns, hf, rules, visited, max_models, attempted):
    for observation in ns.observations.exclude(
        outcome__in=["owner_conflict", "complete"]
    ).order_by("id"):
        if groups_complete(observation.groups):
            continue
        if (
            observation.repo_key not in visited
            and max_models is not None
            and len(visited) >= max_models
        ):
            return "model_cap"
        visited.add(observation.repo_key)
        for group in METADATA_GROUPS:
            if observation.groups.get(group) == "ok":
                continue
            key = (observation.pk, group)
            if key in attempted:
                continue
            if hf.stop_reason:
                return hf.stop_reason
            attempted.add(key)
            result = hf.model_group(observation.repo_id, group)
            with transaction.atomic():
                observation.envelopes += _envelopes(result, group)
                observation.groups[group] = result.outcome
                if result.outcome in {"ok", "partial_expansion"}:
                    persist_product(
                        observation, ns.ownership, rules, result.payload, group
                    )
                if observation.outcome not in {"owner_conflict", "projection_error"}:
                    observation.outcome = (
                        "complete" if groups_complete(observation.groups) else "partial"
                    )
                observation.save()
    return None


def _walk_namespace(ns, hf, rules, visited, max_models):
    # Completed namespace identity and pages are durable; resuming enrichment
    # does not spend requests checking them again.
    if not any(
        e["group"] == "identity" and e.get("validation_outcome") == "ok"
        for e in ns.envelopes
    ):
        result = hf.namespace_info(ns.namespace)
        ns.envelopes += _envelopes(result, "identity")
        ns.outcome = result.outcome
        ns.save()
        if result.outcome != "ok":
            return
    attempted = set()
    if reason := _enrich(ns, hf, rules, visited, max_models, attempted):
        ns.outcome = reason
        ns.save(update_fields=["outcome"])
        return
    restarted = False
    while not ns.enumeration_complete:
        if hf.stop_reason:
            ns.outcome = hf.stop_reason
            ns.save(update_fields=["outcome"])
            return
        remaining = None if max_models is None else max_models - len(visited)
        if remaining is not None and remaining <= 0:
            ns.outcome = "model_cap"
            ns.save(update_fields=["outcome"])
            return
        result = hf.list_page(ns.namespace, ns.cursor, limit=min(100, remaining or 100))
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
                ns.cursor_history = []
                ns.outcome = "cursor_restart"
                restarted = True
                ns.save()
                continue
            ns.save()
            return
        if len(result.payload) > min(100, remaining or 100):
            ns.envelopes += _envelopes(result, "listing")
            ns.outcome = "provider_exceeded_limit"
            ns.save()
            return
        _persist_page(ns, result, rules)
        visited.update(
            (item.get("id") or item["modelId"]).casefold() for item in result.payload
        )
        if ns.outcome in {"repeated_cursor", "empty_page_with_cursor"}:
            return
        if reason := _enrich(ns, hf, rules, visited, max_models, attempted):
            ns.outcome = reason
            ns.save(update_fields=["outcome"])
            return
    ns.outcome = "exhausted"
    ns.save(update_fields=["outcome"])


def catalog_report(run, *, requests=0, stop_reason=None):
    observations = HFModelCatalogObservation.objects.filter(namespace_run__run=run)
    conflicts = observations.filter(outcome="owner_conflict").count()
    gaps = observations.filter(
        product__isnull=False, product__brand__isnull=True
    ).count()
    namespaces = [
        {
            "namespace": ns.namespace,
            "enumeration_complete": ns.enumeration_complete,
            "outcome": ns.outcome,
            "raw_count": ns.raw_count,
            "next_cursor": ns.cursor,
            "unique_models": ns.observations.count(),
        }
        for ns in run.namespaces.order_by("namespace")
    ]
    enumeration_complete = bool(namespaces) and all(
        ns["enumeration_complete"] for ns in namespaces
    )
    enrichment_complete = (
        not observations.exclude(outcome="complete").exists()
        and not observations.filter(product__isnull=True).exists()
    )
    stored_groups = list(observations.values_list("groups", flat=True))
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
        and not run.scope["gaps"]
        and not gaps
        and not conflicts,
        "enumeration_complete": enumeration_complete,
        "enrichment_complete": enrichment_complete,
        "scope_gaps": run.scope["gaps"],
        "attribution_gaps": gaps,
        "conflicts": conflicts,
        "group_outcomes": group_outcomes,
        "attribution_gap_repositories": list(
            observations.filter(
                product__isnull=False, product__brand__isnull=True
            ).values_list("repo_id", flat=True)
        ),
        "unique_models": observations.count(),
        "imported": imported,
        "updated": products - imported,
        "requests": requests,
        "cumulative_requests": sum(i["requests"] for i in run.invocations),
        "stop_reason": stop_reason
        or (
            "model_cap"
            if any(ns["outcome"] == "model_cap" for ns in namespaces)
            else None
        ),
        "namespaces": namespaces,
    }


def execute_catalog(*, hf, scope=None, run_id=None, max_models=None):
    if (scope is None) == (run_id is None):
        raise ValueError("supply scope or resume run, exclusively")
    if max_models is not None and max_models < 1:
        raise ValueError("model budget must be positive")
    with catalog_lock():
        if run_id is not None:
            run = HFModelCatalogRun.objects.get(pk=run_id)
            check_scope(run.scope)
        else:
            check_scope(scope)
            with transaction.atomic():
                run = HFModelCatalogRun.objects.create(scope=scope)
                for entry in scope["namespaces"]:
                    HFModelCatalogNamespaceRun.objects.create(
                        run=run,
                        namespace=entry["namespace"],
                        ownership=entry,
                    )
        invocation = {
            "started_at": timezone.now().isoformat(),
            "requests": 0,
            "retries": 0,
            "max_requests": hf.max_requests,
            "max_models": max_models,
            "outcome": "running",
        }
        run.invocations.append(invocation)
        run.outcome = "running"
        run.finished_at = None
        run.save()

        def record_request(envelope):
            invocation["requests"] = hf.requests
            invocation["retries"] = hf.retries
            invocation["last_request"] = {
                key: envelope[key] for key in ("endpoint", "attempted_at")
            }
            run.save(update_fields=["invocations", "updated_at"])

        hf.on_attempt = record_request
        try:
            visited = set()
            for ns in run.namespaces.order_by("namespace"):
                if hf.stop_reason:
                    break
                _walk_namespace(ns, hf, run.scope["rules"], visited, max_models)
            report = catalog_report(
                run, requests=hf.requests, stop_reason=hf.stop_reason
            )
            run.outcome = "complete" if report["complete"] else "partial"
            report["stop_reason"] = (
                "complete"
                if report["complete"]
                else (report["stop_reason"] or "coverage_gaps")
            )
            run.report = report
            run.finished_at = timezone.now() if report["complete"] else None
            return report
        except BaseException:
            run.outcome = "interrupted"
            run.report = {
                **run.report,
                "complete": False,
                "stop_reason": "interrupted",
                "requests": hf.requests,
            }
            raise
        finally:
            invocation.update(
                requests=hf.requests,
                retries=hf.retries,
                outcome=run.outcome,
                ended_at=timezone.now().isoformat(),
            )
            run.save()
            hf.on_attempt = None
