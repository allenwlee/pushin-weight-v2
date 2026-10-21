"""Account-owned publisher jobs use the existing registration and scheduler.

Enrollment reads already confirmed accounts; it never discovers accounts or
contacts a provider. Only an active authority for the same company can enroll
another account into its existing role.
"""

from collections import defaultdict
from copy import deepcopy

from django.db import transaction
from django.db.models import Prefetch

from core.collection_jobs import register_job, set_job_state
from core.measurement_taxonomy import digest, require, resolve_subject_id
from core.models import (
    BrandCompany,
    CollectionJob,
    CollectionJobTarget,
    CompanyAccount,
    DataSource,
    MeasurementSubject,
)


def subject_target(kind, key, *, role="selected"):
    subject, _ = MeasurementSubject.objects.get_or_create(
        pk=resolve_subject_id(kind, key),
        defaults={"subject_kind": kind, kind + "_id": key},
    )
    return {
        "target_key": kind + ":" + str(key),
        "subject_id": subject.pk,
        "target_kind": kind,
        "target_role": role,
        "resolution_state": "resolved",
    }


def publisher_job_spec(
    *,
    job_key,
    account,
    budgets,
    mode="recurring",
    schedule=None,
    options=None,
    numeric_contract_id=None,
    brands=None,
    routine_role=None,
    origin_job_id=None,
):
    """Build typed arguments for register_job, without activating any work."""
    require(account.data_source_id in {"hf", "github"}, "native publisher required")
    companies = list(account.companies.filter(role_id="official"))
    if account.data_source_id == "hf":
        require(
            len(companies) == 1 and companies[0].ownership_confirmed is True,
            "unambiguous confirmed HF publisher company required",
        )
    else:
        require(len(companies) <= 1, "ambiguous publisher company")
    company_id = companies[0].company_id if companies else None
    selected_brands = (
        set(
            BrandCompany.objects.filter(
                company_id=company_id,
                brand__is_sentinel=False,
            ).values_list("brand_id", flat=True)
        )
        if company_id
        else set(
            account.brands.filter(
                role_id="official", brand__is_sentinel=False
            ).values_list("brand_id", flat=True)
        )
    )
    require(company_id or selected_brands, "reviewed official publisher required")
    if brands is not None:
        require(
            set(brands) <= selected_brands, "publisher does not own selected brands"
        )
        selected_brands = set(brands)
    targets = (
        [subject_target("company", company_id, role="owner")] if company_id else []
    )
    targets.extend(subject_target("brand", key) for key in sorted(selected_brands))
    schedule = schedule or (
        {"kind": "daily_utc", "driver": "shared", "hour": 10}
        if mode == "recurring"
        else {"kind": "manual", "driver": "manual"}
    )
    return {
        "job_key": job_key,
        "source": account.data_source,
        "purpose": "catalog",
        "operation": "model_inventory"
        if account.data_source_id == "hf"
        else "github_catalog",
        "mode": mode,
        "definition": {"version": 2, "options": options or {}},
        "targets": targets,
        "settings": {
            "owner_kind": "account",
            "owner_account_id": account.pk,
            "numeric_contract_id": numeric_contract_id,
            "origin_job_id": origin_job_id,
            "routine_role": routine_role,
            "schedule_kind": schedule["kind"],
            "schedule_driver": schedule["driver"],
            "interval_seconds": schedule.get("seconds"),
            "daily_utc_hour": schedule.get("hour"),
            **{"max_" + name: value for name, value in budgets.items()},
        },
    }


def _native_contract(template, account):
    """Reuse the reviewed native-counter policy, with a new qualified account FK."""
    if template.numeric_contract_id is None:
        return None
    from core.benchmark_metric_identity import SOURCE_STATISTICS_POLICY
    from core.measurement_taxonomy import configure_taxonomy
    from core.source_metric_projection import configure_source_statistics

    config = deepcopy(
        template.numeric_contract.source_configuration[template.source_id]
    )
    require(
        config.get("eligibility_policy") == SOURCE_STATISTICS_POLICY
        and config.get("native_resources", True),
        "account enrollment requires an admitted native-counter policy",
    )
    # Collection scheduling remains owned by the catalog job, never the legacy
    # metric dispatcher. No source flag or existing contract is modified.
    config["scheduling_enabled"] = False
    reviewer = "confirmed-account-enrollment-v1"
    taxonomy = configure_taxonomy(
        {
            "reviewed_by": reviewer,
            "subjects": [{"kind": "account", "key": str(account.pk)}],
        }
    )
    contract = configure_source_statistics(
        {
            "reviewed_by": reviewer,
            "taxonomy_version": str(taxonomy.pk),
            "source_configuration": {template.source_id: config},
            "mappings": [
                {
                    "source": template.source_id,
                    "source_subject_kind": "account",
                    "identifier_scope": account.account_kind,
                    "external_identifier": account.normalized_identifier,
                    "subject_id": str(resolve_subject_id("account", account.pk)),
                    "publisher_account_key": str(account.pk),
                    "evidence_url": (
                        "https://huggingface.co/" + account.normalized_identifier
                        if template.source_id == "hf"
                        else "https://api.github.com/user/"
                        + account.normalized_identifier
                    ),
                }
            ],
        }
    )
    return contract.pk


@transaction.atomic
def enroll_confirmed_accounts(source_id):
    """Enroll once under an existing enabled role; no new collection authority."""
    if source_id not in {"hf", "github"}:
        return []
    source = DataSource.objects.select_for_update().get(pk=source_id)
    if not source.enabled:
        return []
    templates = list(
        CollectionJob.objects.filter(
            source=source,
            instruction_version=2,
            owner_kind="account",
            state="ready",
            mode="recurring",
            schedule_driver="shared",
            authority_enabled=True,
            operation="model_inventory" if source_id == "hf" else "github_catalog",
        )
        .select_related("owner_account", "numeric_contract")
        .prefetch_related(
            Prefetch(
                "owner_account__companies",
                queryset=CompanyAccount.objects.filter(role_id="official"),
                to_attr="collection_official_links",
            ),
            Prefetch(
                "targets",
                queryset=CollectionJobTarget.objects.filter(
                    target_kind="brand"
                ).select_related("subject"),
                to_attr="selected_brand_targets",
            ),
        )
        .order_by("created_at", "pk")
    )
    peers_by_role = defaultdict(list)
    policies = {}
    for peer in templates:
        for link in peer.owner_account.collection_official_links:
            peers_by_role[(link.company_id, peer.routine_role)].append(peer)
        policies[peer.pk] = (
            peer.operation,
            peer.definition,
            peer.budgets,
            peer.schedule,
            peer.numeric_contract.source_configuration
            if peer.numeric_contract_id
            else None,
            sorted(target.subject.brand_id for target in peer.selected_brand_targets),
        )
    created, handled = [], set()
    for template in templates:
        company_ids = [
            link.company_id
            for link in template.owner_account.collection_official_links
            if link.ownership_confirmed is True
        ]
        if len(company_ids) != 1:
            continue
        company_id, role = company_ids[0], template.routine_role
        if not role or (company_id, role) in handled:
            continue
        handled.add((company_id, role))
        # Conflicting policies require a deliberate choice; never choose a
        # publisher's budget or metric policy merely by insertion order.
        if any(
            policies[peer.pk] != policies[template.pk]
            for peer in peers_by_role[(company_id, role)]
        ):
            continue
        existing_owners = set(
            CollectionJob.objects.filter(
                source=source,
                routine_role=role,
            ).values_list("owner_account_id", flat=True)
        )
        links = (
            CompanyAccount.objects.filter(
                company_id=company_id,
                role_id="official",
                ownership_confirmed=True,
                account__data_source=source,
            )
            .select_related("account__data_source")
            .prefetch_related(
                Prefetch(
                    "account__companies",
                    queryset=CompanyAccount.objects.filter(role_id="official"),
                    to_attr="collection_official_links",
                )
            )
            .order_by("account_id")
        )
        for link in links:
            account = link.account
            if len(account.collection_official_links) != 1:
                continue
            if source_id == "github" and account.account_kind not in {
                "organization",
                "individual",
            }:
                continue
            if account.pk in existing_owners:
                # A paused/cancelled existing job represents an operator decision.
                continue
            spec = publisher_job_spec(
                job_key="publisher-enrollment:"
                + digest([str(template.pk), str(account.pk), role]),
                account=account,
                budgets=template.budgets,
                schedule=template.schedule,
                options=template.definition["options"],
                routine_role=role,
                numeric_contract_id=_native_contract(template, account),
                brands=[
                    target.subject.brand_id
                    for target in template.selected_brand_targets
                ],
                origin_job_id=template.pk,
            )
            job = register_job(**spec)
            from core.collection_scheduling import take_collection_authority

            set_job_state(job.pk, "ready")
            take_collection_authority(job.pk)
            existing_owners.add(account.pk)
            created.append(job.pk)
    return created
