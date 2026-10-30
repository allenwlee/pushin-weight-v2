"""Strict remaining instruction options and sealed relational job ownership.

This is the implementation of register_job's typed boundary, not a second
registration API. Scheduling, membership and identities never enter options.
"""

from copy import deepcopy

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.measurement_taxonomy import digest, require
from core.models import CollectionJob, CollectionJobTarget

OPTION_TYPES = {
    "release_document_import": {},
    "model_inventory": {
        "ingest_metadata": bool,
        "watch_inventory": bool,
        "inventory_version": str,
        "recheck_days": int,
        "projection_policy": str,
    },
    "model_history": {
        "cutoff": str,
        "global_start_at": str,
        "cap_per_brand": int,
        "qualification_policy": str,
        "window_policy": str,
        "arena_config": str,
        "arena_publication_mode": str,
        "publication_window_policy": str,
        "publication_recheck_days": int,
        "publication_window_days": int,
    },
    "github_catalog": {"github_role": str},
    "hf_catalog": {"rules_version": str},
    "collect_metrics": {},
    "match_crosswalk": {
        "ruleset": str,
        "preview_sha256": str,
        "reviewed_by": str,
        "review_basis": str,
        "cutoff": str,
    },
    "x_cycle": {"adapter": str, "credential_purpose": str},
    "x_backfill": {
        "adapter": str,
        "credential_purpose": str,
        "config_digest": str,
        "policy_sha256": str,
        "maximum_api_requests": int,
        "maximum_model_requests": int,
        "model_requests_per_run": int,
        "deadline": str,
    },
}

SETTINGS = (
    "owner_kind",
    "owner_account_id",
    "campaign_id",
    "campaign_role",
    "campaign_phase",
    "origin_job_id",
    "numeric_contract_id",
    "schedule_kind",
    "schedule_driver",
    "interval_seconds",
    "daily_utc_hour",
    "max_requests",
    "max_bytes",
    "max_seconds",
    "max_items",
    "routine_role",
)
TARGET_FIELDS = (
    "target_key",
    "ordinal",
    "subject_id",
    "mapping_id",
    "native_identifier",
    "target_kind",
    "target_role",
    "resolution_state",
    "gap_reason",
    "evidence_observation_id",
    "parent_target_id",
    "search_query_id",
    "requested_start_at",
    "requested_end_at",
    "membership_source",
    "membership_run_reference",
    "last_reconciled_at",
    "selection_basis",
    "selection_sha256",
    "identifier_scope",
    "source_row_index",
    "review_confirmed",
)


def scope_for_job(job):
    """Render adapter inputs from fixed selections, without another stored copy."""
    scope = deepcopy(job.definition["options"])
    targets = list(
        job.targets.select_related(
            "subject__product__publisher_account",
            "mapping",
            "evidence_observation__run__job",
        ).order_by("ordinal")
    )
    brands = sorted(
        {
            target.subject.brand_id
            for target in targets
            if target.subject_id and target.subject.subject_kind == "brand"
        }
    )
    companies = sorted(
        {
            target.subject.company_id
            for target in targets
            if target.subject_id and target.subject.subject_kind == "company"
        }
    )
    if brands:
        scope["brands"] = brands
    if companies:
        scope["companies"] = companies
    if job.numeric_contract_id:
        scope["numeric_contract_id"] = str(job.numeric_contract_id)
    if job.routine_role:
        scope["routine_role"] = job.routine_role
    if job.campaign_id:
        scope["cohort_hash"] = job.campaign.cohort_hash
    owner = job.owner_account
    if job.source_id == "github" and owner:
        scope["publishers"] = [
            {
                "account_key": str(owner.pk),
                "native_id": owner.normalized_identifier,
                "login": owner.handle,
                "account_kind": owner.account_kind,
            }
        ]
    if (
        job.source_id == "hf"
        and owner
        and job.operation in {"model_inventory", "hf_catalog"}
    ):
        from core.account_identity import (
            publisher_discovery_label,
            publisher_identifier,
        )
        from core.hf_metadata_client import INVENTORY_VERSION

        require(
            len(companies) == 1,
            "HF publisher selection requires one frozen company target",
        )
        namespace = publisher_identifier(owner)
        entry = {
            "namespace": namespace,
            "company": companies[0],
            "brands": brands,
            "ownership_evidence": publisher_discovery_label(owner),
            "source_url": "https://huggingface.co/" + namespace,
        }
        rules = []
        for target in targets:
            if target.target_kind in {"repository_rule", "prefix_rule"}:
                require(
                    target.subject_id and target.subject.subject_kind == "brand",
                    "attribution rule requires brand subject",
                )
                rules.append(
                    {
                        "namespace": namespace,
                        "repo"
                        if target.target_kind == "repository_rule"
                        else "prefix": target.native_identifier,
                        "brand": target.subject.brand_id,
                        "source": "collection_job_target",
                    }
                )
        frozen = {
            "version": 1,
            "inventory_version": INVENTORY_VERSION,
            "brands": brands,
            "companies": companies,
            "namespace_filter": namespace,
            "namespaces": [entry],
            "gaps": [
                {"reason": t.gap_reason, "identifier": t.native_identifier}
                for t in targets
                if t.resolution_state == "unresolved"
            ],
            "rules": rules,
        }
        scope["hf_scope"] = frozen
    if job.source_id == "openrouter" and job.operation == "model_inventory":
        scope["authors"] = sorted(
            {
                target.native_identifier
                for target in targets
                if target.target_role == "publisher" and target.native_identifier
            }
        )
    if job.operation == "match_crosswalk":
        from core.collection_matching import _candidate, _native

        matches, approved = [], []
        for target in targets:
            if target.target_kind != "match_candidate":
                continue
            native = _native(
                target.evidence_observation,
                target.identifier_scope_code,
                target.source_row_index,
            )
            require(
                native is not None and native["identifier"] == target.native_identifier,
                "native evidence changed",
            )
            candidate = _candidate(target.subject.product, native)
            candidate["decision"] = target.target_role
            candidate["reasons"] = [target.selection_basis]
            candidate["input_sha256"] = target.selection_sha256
            require(
                digest(
                    {
                        key: value
                        for key, value in candidate.items()
                        if key != "input_sha256"
                    }
                )
                == target.selection_sha256,
                "product/publisher or candidate identity evidence changed",
            )
            require(
                candidate["candidate_id"] == target.target_key,
                "candidate identity changed",
            )
            matches.append(candidate)
            if target.review_confirmed:
                approved.append(target.target_key)
        scope["matches"] = matches
        scope["review"] = {
            "reviewed_by": scope.pop("reviewed_by"),
            "basis": scope.pop("review_basis"),
            "candidate_ids": approved,
        }
    return scope


def validate_options(definition, operation):
    require(
        set(definition) == {"version", "options"}
        and type(definition["version"]) is int
        and definition["version"] == 2,
        "strict instruction version 2 required",
    )
    options = definition["options"]
    require(
        isinstance(options, dict) and operation in OPTION_TYPES,
        "unsupported operation options",
    )
    fields = OPTION_TYPES[operation]
    require(set(options) <= set(fields), "unknown or relocated instruction option")
    for name, value in options.items():
        require(type(value) is fields[name], "invalid instruction option type")
        if type(value) is int:
            require(0 < value <= 1000000, "instruction option out of range")
        elif type(value) is str:
            require(
                0
                < len(value)
                <= (
                    2048
                    if operation == "match_crosswalk" and name == "review_basis"
                    else 1024
                )
                and not any(
                    ord(c) < 32 and not (name == "review_basis" and c in "\n\r\t")
                    for c in value
                ),
                "invalid instruction option string",
            )


def validate_settings(job):
    from core.collection_jobs import BUDGET_LIMITS

    require(
        job.owner_kind in {"account", "source"},
        "typed job requires account or source ownership",
    )
    require(
        (job.owner_kind == "account") == (job.owner_account_id is not None),
        "job account ownership mismatch",
    )
    if job.owner_account_id and job.source_id in {"hf", "github", "x"}:
        require(
            job.owner_account.data_source_id == job.source_id,
            "native collector owner source mismatch",
        )
    require(
        job.schedule_driver in {"manual", "shared", "external_render_cron"},
        "schedule driver required",
    )
    if job.mode == "recurring":
        require(
            job.schedule_kind in {"interval", "daily_utc"}
            and job.schedule_driver != "manual",
            "recurring schedule required",
        )
        if job.schedule_kind == "interval":
            require(
                type(job.interval_seconds) is int
                and 0 < job.interval_seconds <= 366 * 86400
                and job.daily_utc_hour is None,
                "invalid interval schedule",
            )
        else:
            require(
                type(job.daily_utc_hour) is int
                and 0 <= job.daily_utc_hour <= 23
                and job.interval_seconds is None,
                "invalid daily schedule",
            )
    else:
        require(
            job.schedule_kind == "manual"
            and job.schedule_driver == "manual"
            and job.interval_seconds is None
            and job.daily_utc_hour is None,
            "manual schedule required",
        )
    if job.schedule_driver == "external_render_cron":
        require(
            job.operation == "x_cycle"
            and job.source_id == "x"
            and job.purpose == "content",
            "external driver reserved for X cycle",
        )
    for key, maximum in BUDGET_LIMITS.items():
        value = getattr(job, "max_" + key)
        require(type(value) is int and 0 < value <= maximum, "invalid typed budget")
    require(
        job.numeric_contract_id is None or job.purpose == "catalog",
        "numeric output contract belongs to catalog jobs",
    )
    if job.campaign_id:
        require(
            job.campaign_role in {"inventory", "history", "projection"}
            and job.campaign_phase in {"acquire", "replay"},
            "campaign role/phase required",
        )
    else:
        require(
            job.campaign_role is None and job.campaign_phase is None,
            "campaign settings require campaign",
        )


def _normalize_references(model, values):
    values = dict(values)
    for name, value in values.items():
        if name.endswith("_id") and value is not None:
            field = model._meta.get_field(name[:-3])
            require(not isinstance(value, bool), "invalid relationship identifier")
            try:
                values[name] = field.target_field.to_python(value)
            except (ValidationError, TypeError, ValueError) as exc:
                raise ValueError("invalid relationship identifier") from exc
        elif name.endswith("_at") and value is not None:
            from core.benchmark_metric_timing import aware_instant

            values[name] = aware_instant(value)
    return values


def validate_selection_ownership(job):
    if job.owner_account_id is None:
        return
    from core.collection_identity import qualified_catalog_ownership

    owner = job.owner_account
    if owner.data_source_id == "hf":
        links = list(
            owner.companies.filter(role_id="official").values_list(
                "ownership_confirmed", flat=True
            )
        )
        require(
            len(links) == 1 and links[0] is True,
            "confirmed unambiguous HF publisher required",
        )
    for target in job.targets.select_related("subject__product"):
        if target.subject_id and target.subject.subject_kind in {
            "company",
            "brand",
            "product",
        }:
            require(
                qualified_catalog_ownership(owner, target.subject),
                "publisher does not own selected subject",
            )


def target_documents(query):
    """Preserve the sealed string-based instruction format after FK conversion."""
    rows = list(query.values(*(
        "identifier_scope__code" if name == "identifier_scope" else name
        for name in TARGET_FIELDS
    )))
    for row in rows:
        row["identifier_scope"] = row.pop("identifier_scope__code")
    return rows


def relational_identity(job):
    values = {name: getattr(job, name) for name in SETTINGS}
    values = {
        key: str(value) if key.endswith("_id") and value is not None else value
        for key, value in values.items()
    }
    targets = target_documents(job.targets.order_by("ordinal"))
    for target in targets:
        for name, value in target.items():
            if hasattr(value, "isoformat"):
                target[name] = value.isoformat()
            elif name.endswith("_id") and value is not None:
                target[name] = str(value)
    return digest(
        {
            "definition_sha256": job.definition_sha256,
            "settings": values,
            "targets": targets,
        }
    )


def validate_sealed_job(job, *, deep=True):
    validate_options(job.definition, job.operation)
    validate_settings(job)
    require(
        job.instructions_sealed_at is not None
        and job.relational_sha256
        and (not deep or job.relational_sha256 == relational_identity(job)),
        "sealed relational instruction mismatch",
    )
    if deep:
        validate_selection_ownership(job)


@transaction.atomic
def register_relational_job(
    *,
    job_key,
    source,
    purpose,
    operation,
    mode,
    definition,
    contract,
    identity,
    settings,
    targets,
):
    require(
        isinstance(settings, dict) and set(settings) <= set(SETTINGS),
        "typed job settings required",
    )
    require(
        isinstance(targets, (list, tuple)) and len(targets) <= 100000,
        "bounded target list required",
    )
    settings = _normalize_references(CollectionJob, settings)
    allowed_target_fields = set(TARGET_FIELDS) | {"parent_target_key"}
    normalized_targets = []
    for target in targets:
        require(
            isinstance(target, dict) and set(target) <= allowed_target_fields,
            "unsupported target field",
        )
        scalar = {key: value for key, value in target.items() if key != "identifier_scope"}
        normalized = _normalize_references(CollectionJobTarget, scalar)
        if "identifier_scope" in target:
            require(target["identifier_scope"] is None or isinstance(target["identifier_scope"], str),
                    "identifier scope must be a source code")
            normalized["identifier_scope"] = target["identifier_scope"]
        normalized_targets.append(normalized)
    targets = normalized_targets
    candidate = CollectionJob(
        job_key=job_key,
        source=source,
        purpose=purpose,
        operation=operation,
        mode=mode,
        definition=definition,
        definition_sha256=identity,
        instruction_version=2,
        contract=contract,
        **settings,
    )
    validate_settings(candidate)
    # Serialize registration before the first job exists, preserving immutable job-key identity.
    type(source).objects.select_for_update().get(pk=source.pk)
    existing = CollectionJob.objects.filter(job_key=job_key).first()
    if existing:
        require(
            existing.definition_sha256 == identity
            and all(
                getattr(existing, name) == getattr(candidate, name) for name in SETTINGS
            ),
            "immutable job identity changed; register a new job",
        )
        requested = []
        existing_target_ids = dict(existing.targets.values_list("target_key", "pk"))
        for ordinal, target in enumerate(targets):
            target = dict(target)
            parent_key = target.pop("parent_target_key", None)
            if parent_key is not None:
                require(parent_key in existing_target_ids, "parent target is missing")
                target["parent_target_id"] = existing_target_ids[parent_key]
            defaults = CollectionJobTarget()
            normalized = {name: getattr(defaults, name) for name in TARGET_FIELDS}
            normalized.update({"ordinal": ordinal, "gap_reason": "", **target})
            requested.append(normalized)
        actual = target_documents(existing.targets.order_by("ordinal"))
        require(
            requested == actual, "immutable job targets changed; register a new job"
        )
        validate_sealed_job(existing)
        return existing
    candidate.save(force_insert=True)
    created_targets = {}
    parent_keys = {}
    for ordinal, target in enumerate(targets):
        values = {"ordinal": ordinal, **target}
        parent_key = values.pop("parent_target_key", None)
        if "identifier_scope" in values:
            from core.identifier_namespaces import target_namespace_id
            values["identifier_scope_id"] = target_namespace_id(values)
            del values["identifier_scope"]
        created = CollectionJobTarget.objects.create(job=candidate, **values)
        created_targets[created.target_key] = created
        if parent_key is not None:
            parent_keys[created.target_key] = parent_key
    for target_key, parent_key in parent_keys.items():
        require(parent_key in created_targets, "parent target is missing")
        created = created_targets[target_key]
        created.parent_target = created_targets[parent_key]
        created.save(update_fields=["parent_target"])
    candidate.relational_sha256 = relational_identity(candidate)
    candidate.instructions_sealed_at = timezone.now()
    candidate.save(update_fields=["relational_sha256", "instructions_sealed_at"])
    validate_sealed_job(candidate)
    return candidate
