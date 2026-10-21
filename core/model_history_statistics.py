"""Prepare explicit immutable statistics instructions before job registration."""

import copy

from django.db import transaction

from core.benchmark_metric_identity import SOURCE_STATISTICS_POLICY
from core.measurement_taxonomy import configure_taxonomy, require, resolve_subject_id
from core.models import DataSource, Product, SourceSubjectMapping
from core.source_metric_projection import configure_source_statistics


@transaction.atomic
def prepare_history_statistics_scope(*, source, scope, reviewed_by, use_policy=None):
    """Return a draft scope with a pinned contract; never modify an existing job.

    Only reviewed catalog crosswalks can become canonical metric mappings. HF
    model-registry qualification does not classify an unknown model as text/LLM.
    """
    source = DataSource.objects.get(pk=source) if isinstance(source, str) else source
    selected = copy.deepcopy(scope)
    require(
        not selected.get("numeric_contract_id"), "scope already pins a numeric contract"
    )
    require(
        reviewed_by and selected.get("cohort_hash"), "reviewed frozen cohort required"
    )
    models = selected.get("models", [])
    require(
        isinstance(models, list) and len(models) <= 100,
        "bounded model selection required",
    )
    subjects, mappings, publishers = {}, [], {}
    for model in models:
        product = Product.objects.select_related("publisher_account").get(
            product_key=model["product_key"]
        )
        for pin in model.get("provider_pins", []):
            if pin["source"] != source.pk:
                continue
            reviewed = SourceSubjectMapping.objects.select_related(
                "publisher_account"
            ).get(pk=pin["mapping_id"], purpose="catalog", source=source)
            require(
                reviewed.mapping_hash == pin["mapping_hash"]
                and reviewed.subject.subject_kind == "product"
                and reviewed.subject.product_id == product.product_key,
                "frozen catalog crosswalk changed",
            )
            if source.pk in {"arena", "openrouter"} and reviewed.identifier_scope != (
                "arena_model_name" if source.pk == "arena" else "rankings_permaslug"
            ):
                continue
            account = reviewed.publisher_account
            require(account is not None, "reviewed publisher required")
            if source.pk in {"hf", "github"}:
                publishers[str(account.pk)] = account
            entry = {"kind": "product", "key": str(product.product_key)}
            if isinstance(model.get("qualification"), dict):
                entry["model_kind_qualification"] = model["qualification"]
            subjects[str(product.product_key)] = entry
            mappings.append(
                {
                    "source": source.pk,
                    "source_subject_kind": reviewed.source_subject_kind,
                    "identifier_scope": reviewed.identifier_scope,
                    "external_identifier": reviewed.external_identifier,
                    "subject_id": str(reviewed.subject_id),
                    "publisher_account_key": str(account.pk),
                    "evidence_url": reviewed.evidence_url,
                    "identifier_metadata": {
                        "role": reviewed.identity_snapshot.get("role"),
                        "catalog_mapping_id": str(reviewed.pk),
                        "catalog_mapping_hash": reviewed.mapping_hash,
                    },
                }
            )
        if source.pk == "hf" and product.publisher_account_id:
            publishers[str(product.publisher_account_id)] = product.publisher_account
    for account in publishers.values():
        subjects["account:" + str(account.pk)] = {
            "kind": "account",
            "key": str(account.pk),
        }
        mappings.append(
            {
                "source": source.pk,
                "source_subject_kind": "account",
                "identifier_scope": account.account_kind,
                "external_identifier": account.normalized_identifier,
                "subject_id": str(resolve_subject_id("account", account.pk)),
                "publisher_account_key": str(account.pk),
                "evidence_url": account.provider_metadata.get("ownership_evidence")
                or (
                    "https://huggingface.co/" + account.normalized_identifier
                    if source.pk == "hf"
                    else "https://api.github.com/user/" + account.normalized_identifier
                ),
            }
        )
    taxonomy = configure_taxonomy(
        {"reviewed_by": reviewed_by, "subjects": list(subjects.values())}
    )
    metrics = {
        "hf": ["downloads", "downloads_all_time", "likes", "trending_score"],
        "github": [
            "stars",
            "forks",
            "open_issues",
            "subscribers",
            "repository_size_kb",
            "asset_downloads",
            "asset_size_bytes",
        ],
        "openrouter": ["total_tokens"],
        "arena": [
            "rating",
            "rating_lower",
            "rating_upper",
            "vote_count",
            "rank",
            "variance",
        ],
    }[source.pk]
    settings = {"metrics": metrics, "native_resources": True}
    if source.pk == "arena":
        config = selected.get("arena_config", "text")
        settings["config"] = config
        if config == "agent":
            settings["metrics"] = [
                "agent_score",
                "agent_score_ci_lower",
                "agent_score_ci_upper",
                "observation_count",
                "session_count",
                "rank",
            ]
        else:
            settings["metric_versions"] = {
                key: 2 for key in ("rating_lower", "rating_upper", "vote_count")
            }
    if source.pk in {"arena", "openrouter"}:
        settings["publication_provenance"] = {
            "dataset_id": "openrouter/rankings-daily"
            if source.pk == "openrouter"
            else "lmarena-ai/leaderboard-dataset",
            "source_url": "https://openrouter.ai/rankings"
            if source.pk == "openrouter"
            else "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset",
            "reviewed_by": reviewed_by,
        }
    if use_policy is not None:
        settings["use_policy"] = copy.deepcopy(use_policy)
    contract = configure_source_statistics(
        {
            "reviewed_by": reviewed_by,
            "taxonomy_version": str(taxonomy.pk),
            "source_configuration": {source.pk: settings},
            "mappings": mappings,
        }
    )
    selected["numeric_contract_id"] = str(contract.pk)
    selected["numeric_projection_policy"] = SOURCE_STATISTICS_POLICY
    if source.pk in {"openrouter", "arena"}:
        selected.setdefault("publication_window_days", 7)
        require(
            type(selected["publication_window_days"]) is int
            and 1 <= selected["publication_window_days"] <= 90,
            "publication windows must be between 1 and 90 days",
        )
    if source.pk == "arena":
        selected.setdefault("arena_config", "text")
        selected.setdefault("arena_carry_in_days", 0)
        require(
            selected["arena_carry_in_days"] == 0,
            "statistics history has no synthetic carry-in",
        )
    return selected


def history_statistics_contract(job):
    """Resolve an existing pin; legacy catalog-only instructions stay catalog-only."""
    from core.models import MetricCollectionContract

    scope = job.scope
    contract_id = scope.get("numeric_contract_id")
    require(
        contract_id or not scope.get("numeric_projection_policy"),
        "history statistics contract pin required",
    )
    if not contract_id:
        return None
    contract = MetricCollectionContract.objects.get(pk=contract_id)
    require(
        job.source_id in contract.source_configuration,
        "numeric contract source mismatch",
    )
    policy = scope.get("numeric_projection_policy")
    require(
        policy in {None, SOURCE_STATISTICS_POLICY},
        "unsupported history statistics policy",
    )
    require(
        not policy
        or contract.source_configuration[job.source_id].get("eligibility_policy")
        == policy,
        "history statistics policy/contract mismatch",
    )
    return contract
