from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from scripts.staging_refresh.policy import (
    DatabaseInspection,
    PolicyError,
    authorize,
    expected_confirmation,
    load_policy,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "config" / "staging_refresh.yaml"
RUNBOOK_PATH = REPO_ROOT / "docs" / "operations" / "staging-data-refresh.md"


def _inspection(
    policy,
    *,
    source: bool,
    database: str | None = None,
    role: str | None = None,
) -> DatabaseInspection:
    endpoint = policy.source if source else policy.target
    return DatabaseInspection(
        database=database or endpoint.database,
        role=role or endpoint.role,
        server_version=180000,
        tls=True,
        default_transaction_read_only=source,
        has_write_privileges=False,
        can_create_database=not source,
        readable_tables=policy.relations.copied_tables if source else frozenset(),
        maintainable_tables=(
            policy.relations.excluded_tables if source else frozenset()
        ),
        readable_sequences=policy.relations.sequences if source else frozenset(),
        base_tables=policy.relations.classified_tables if source else frozenset(),
        views=policy.relations.views if source else frozenset(),
        sequences=policy.relations.sequences if source else frozenset(),
    )


def _environment(policy) -> dict[str, str]:
    return {
        "RENDER_SERVICE_ID": policy.service.id,
        "RENDER_SERVICE_NAME": policy.service.name,
        policy.enable_environment: "true",
        policy.source.environment: (
            f"postgresql://{policy.source.role}:secret@{policy.source.host}:5432/"
            f"{policy.source.database}?sslmode=require"
        ),
        policy.target.environment: (
            f"postgresql://{policy.target.role}:secret@{policy.target.host}:5432/"
            f"{policy.target.database}"
        ),
    }


def test_release_detection_queue_is_environment_local() -> None:
    policy = load_policy(POLICY_PATH)
    table = "product_release_detection_states"
    assert table in policy.relations.excluded_tables
    assert table in policy.relations.optional_source_tables
    assert table in policy.scrub.truncate_tables
    assert table not in policy.relations.copied_tables


def test_release_claim_job_links_are_preserved_when_available() -> None:
    policy = load_policy(POLICY_PATH)
    table = "event_dossier_claim_collection_jobs"
    sequence = "event_dossier_claim_collection_jobs_id_seq"
    assert table in policy.relations.copied_tables
    assert table in policy.relations.optional_source_tables
    assert table in policy.validation.exact_count_tables
    assert sequence in policy.relations.sequences
    assert sequence in policy.relations.optional_source_sequences


def test_loads_the_tracked_exhaustive_policy() -> None:
    policy = load_policy(POLICY_PATH)

    assert policy.service.name == "pushinweight-staging-jobs"
    assert policy.source.role == "staging_refresh_reader"
    assert policy.source.database == "pushinweight_shadow"
    assert policy.target.database == "pushinweight_staging"
    assert policy.relations.copied_tables.isdisjoint(policy.relations.excluded_tables)
    assert "auth_user" in policy.relations.excluded_tables
    assert "posts" in policy.relations.copied_tables
    assert "trend_narrative_versions" in policy.relations.views
    aliases = {
        "brand_trend_narratives",
        "brand_trend_narrative_texts",
        "trend_narrative_runs",
        "trend_narrative_provider_calls",
        "trend_narrative_visible_runs",
        "editorial_pictures",
    }
    assert aliases <= policy.relations.views
    assert aliases.isdisjoint(policy.relations.classified_tables)
    assert aliases.isdisjoint(policy.scrub.truncate_tables)
    assert "original_content_sources" in policy.relations.excluded_tables
    assert "original_content_sources" in policy.scrub.truncate_tables
    assert policy.validation.forward_migration_count_deltas == {}
    assert policy.validation.forward_migration_translation_count_deltas == {}
    assert {"brands", "brands_companies", "companies"} <= set(
        policy.validation.exact_count_tables
    )


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_every_current_managed_table_has_an_explicit_refresh_disposition():
    from django.apps import apps
    from django.db import connection

    policy = load_policy(POLICY_PATH)
    models = [
        model for model in apps.get_models(include_auto_created=True)
        if model._meta.managed and not model._meta.proxy
    ]
    tables = {model._meta.db_table for model in models}
    assert not tables - policy.relations.classified_tables
    # PostgreSQL keeps sequence names across table renames. Inspect the actual
    # schema rather than deriving names that never existed.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname FROM pg_class WHERE relkind='S' "
            "AND relnamespace='public'::regnamespace"
        )
        sequences = {row[0] for row in cursor.fetchall()}
    assert not sequences - policy.relations.sequences


def test_pre_merge_source_is_authorized_without_reading_legacy_catalog():
    from scripts.staging_refresh.policy import (
        LEGACY_CATALOG_SEQUENCES,
        LEGACY_CATALOG_TABLES,
        LEGACY_COLLECTION_TABLES,
    )

    policy = load_policy(POLICY_PATH)
    current = _inspection(policy, source=True)
    shared = frozenset(
        {"collection_runs", "collection_observations", "collection_scope_runs"}
    )
    old_numeric = frozenset(LEGACY_COLLECTION_TABLES.values())
    old = replace(
        current,
        base_tables=(current.base_tables - shared)
        | LEGACY_CATALOG_TABLES
        | old_numeric,
        readable_tables=(current.readable_tables - shared) | old_numeric,
        maintainable_tables=current.maintainable_tables | LEGACY_CATALOG_TABLES,
        views=current.views - old_numeric,
        sequences=current.sequences | LEGACY_CATALOG_SEQUENCES,
        readable_sequences=current.sequences | LEGACY_CATALOG_SEQUENCES,
    )
    authorize(
        policy,
        action="preflight",
        environ=_environment(policy),
        source=old,
        target=_inspection(policy, source=False),
    )
    with pytest.raises(PolicyError, match="source_excluded_table_readable"):
        authorize(
            policy,
            action="preflight",
            environ=_environment(policy),
            source=replace(
                old, readable_tables=old.readable_tables | LEGACY_CATALOG_TABLES
            ),
            target=_inspection(policy, source=False),
        )
    with pytest.raises(PolicyError, match="source_collection_schema_mixed"):
        authorize(
            policy,
            action="preflight",
            environ=_environment(policy),
            source=replace(
                current, base_tables=current.base_tables | LEGACY_CATALOG_TABLES
            ),
            target=_inspection(policy, source=False),
        )


def test_rare_type_relations_have_explicit_copy_or_scrub_policy() -> None:
    policy = load_policy(POLICY_PATH)

    assert {
        "posts_brands_products",
        "rare_type_category_assignments",
    } <= policy.relations.copied_tables
    assert {
        "brand_discovery_candidate_token_evidence",
        "brand_discovery_candidate_tokens",
        "product_verification_proposals",
        "profile_movement_candidates",
        "rare_type_decision_attempts",
        "rare_type_decision_processing_cycles",
        "rare_type_decisions",
        "rare_type_search_daily_budgets",
        "rare_type_search_hits",
        "rare_type_search_runs",
    } <= policy.relations.excluded_tables
    assert {
        "brand_discovery_candidates",
        "posts_brands_products",
        "products",
        "rare_type_category_assignments",
    } <= set(policy.validation.exact_count_tables)
    rare_type_sequences = {
        "brand_discovery_candidate_token_evidence_id_seq",
        "brand_discovery_candidate_tokens_id_seq",
        "product_verification_proposals_id_seq",
        "profile_movement_candidates_id_seq",
        "rare_type_category_assignments_id_seq",
        "rare_type_decision_attempts_id_seq",
        "rare_type_decision_processing_cycles_id_seq",
        "rare_type_decisions_id_seq",
        "rare_type_search_daily_budgets_id_seq",
        "rare_type_search_hits_id_seq",
        "rare_type_search_runs_id_seq",
    }
    assert rare_type_sequences <= policy.relations.sequences
    assert rare_type_sequences <= policy.relations.optional_source_sequences


def test_migration_graph_tables_are_exhaustively_classified() -> None:
    from django.db.migrations.loader import MigrationLoader

    policy = load_policy(POLICY_PATH)
    state = MigrationLoader(None, ignore_no_migrations=True).project_state()
    migration_tables = {
        model.options.get("db_table") or f"{app_label}_{model_name}"
        for (app_label, model_name), model in state.models.items()
        if model.options.get("managed", True) and not model.options.get("proxy", False)
    }
    migration_tables.update(
        {
            "auth_group_permissions",
            "auth_user_groups",
            "auth_user_user_permissions",
            "django_migrations",
            "socialaccount_socialapp_sites",
        }
    )

    assert policy.relations.classified_tables == migration_tables


def test_per_brand_headline_graph_is_environment_local_state() -> None:
    policy = load_policy(POLICY_PATH)
    runtime_tables = {
        "original_content_runs",
        "provider_batches",
        "original_content",
        "trend_narrative_work_slots",
        "original_content_calls",
        "original_content_selections",
    }

    assert runtime_tables <= policy.relations.excluded_tables
    assert runtime_tables <= policy.scrub.truncate_tables
    assert {
        "trend_narrative_runs_id_seq",
        "brand_trend_narratives_id_seq",
        "trend_narrative_provider_calls_id_seq",
    } <= policy.relations.sequences
    assert policy.quiescence.harvest_environment == "staging"
    assert policy.quiescence.broker_environment == "CELERY_BROKER_URL"
    assert policy.quiescence.queue_name == "trend-narratives"
    assert policy.quiescence.queue_namespace_pattern == "trend-narratives*"
    assert policy.quiescence.unacked_index_key == "unacked_index"


def test_official_company_credentials_and_work_remain_environment_local() -> None:
    policy = load_policy(POLICY_PATH)
    runtime_tables = {
        "official_company_account_states",
        "official_company_attempts",
        "official_company_budgets",
        "official_company_list_intents",
        "official_company_owner_credentials",
        "official_company_provider_states",
        "official_company_scans",
    }
    sequences = {
        "official_company_account_states_id_seq",
        "official_company_attempts_id_seq",
        "official_company_list_intents_id_seq",
    }

    assert runtime_tables <= policy.relations.excluded_tables
    assert runtime_tables <= policy.scrub.truncate_tables
    assert runtime_tables <= policy.relations.optional_source_tables
    assert runtime_tables.isdisjoint(policy.relations.copied_tables)
    assert sequences <= policy.relations.sequences
    assert sequences <= policy.relations.optional_source_sequences
    assert {"brands_accounts", "companies_accounts"} <= policy.relations.copied_tables


def test_runbook_source_grants_cover_the_exhaustive_copy_policy() -> None:
    policy = load_policy(POLICY_PATH)
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")

    for relation in sorted(
        policy.relations.classified_tables | policy.relations.sequences
    ):
        assert relation in runbook
    assert "GRANT MAINTAIN ON" in runbook
    maintain_block = runbook.split("GRANT MAINTAIN ON", 1)[1].split(
        "TO staging_refresh_reader;", 1
    )[0]
    maintained_relations = frozenset(maintain_block.replace(",", " ").split())
    assert maintained_relations == policy.relations.excluded_tables
    assert "Do not add default privileges" in runbook
    assert "\\password staging_refresh_reader" in runbook


def test_home_count_publication_is_environment_local_after_data_refresh() -> None:
    policy = load_policy(POLICY_PATH)
    assert "materialization_state" in policy.relations.excluded_tables
    assert "materialization_state" in policy.relations.optional_source_tables
    assert "materialization_state" in policy.scrub.truncate_tables
    assert "materialization_state" not in policy.relations.copied_tables
    # pg_dump carries native materialized-view definitions, rather than COPY
    # rows. They must never enter a base-table TRUNCATE or SELECT grant list.
    assert "home_brand_time_counts" not in policy.relations.classified_tables


def test_policy_rejects_unknown_fields(tmp_path: Path) -> None:
    raw = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    raw["surprise"] = True
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(PolicyError, match="policy_unknown_fields:surprise"):
        load_policy(path)


def test_valid_staging_preflight_is_authorized() -> None:
    policy = load_policy(POLICY_PATH)

    result = authorize(
        policy,
        action="preflight",
        environ=_environment(policy),
        source=_inspection(policy, source=True),
        target=_inspection(policy, source=False),
    )

    assert result.source.database == "pushinweight_shadow"
    assert result.target.database == "pushinweight_staging"


def test_enrichment_allowances_cannot_cross_the_refresh_boundary() -> None:
    policy = load_policy(POLICY_PATH)
    table = "enrichment_budget_windows"
    assert table in policy.relations.excluded_tables
    assert table in policy.scrub.truncate_tables
    assert table in policy.relations.optional_source_tables
    assert table not in policy.relations.copied_tables

    source = _inspection(policy, source=True)
    with pytest.raises(PolicyError, match="source_excluded_table_readable:" + table):
        authorize(
            policy,
            action="preflight",
            environ=_environment(policy),
            source=replace(source, readable_tables=source.readable_tables | {table}),
            target=_inspection(policy, source=False),
        )

    # A source predating the allowance table is still supported; a new target
    # must provision its own spending authority instead of copying production's.
    authorize(
        policy,
        action="preflight",
        environ=_environment(policy),
        source=replace(
            source,
            base_tables=source.base_tables - {table},
            maintainable_tables=source.maintainable_tables - {table},
        ),
        target=_inspection(policy, source=False),
    )


def test_pre_rename_source_requires_separate_schema_preparation() -> None:
    policy = load_policy(POLICY_PATH)
    source = _inspection(policy, source=True)
    old = {
        "brand_trend_narratives",
        "brand_trend_narrative_texts",
        "trend_narrative_runs",
        "trend_narrative_provider_calls",
        "trend_narrative_visible_runs",
        "editorial_pictures",
    }
    canonical = {
        "original_content",
        "original_content_texts",
        "original_content_runs",
        "original_content_calls",
        "original_content_selections",
        "content_pictures",
    }
    source = replace(
        source,
        base_tables=(source.base_tables - canonical) | old,
        views=source.views - old,
    )
    with pytest.raises(PolicyError, match="source_unclassified_table:"):
        authorize(
            policy,
            action="preflight",
            environ=_environment(policy),
            source=source,
            target=_inspection(policy, source=False),
        )


def test_staging_first_preflight_accepts_declared_post_migration_relations_absent():
    policy = load_policy(POLICY_PATH)
    source = _inspection(policy, source=True)
    source = replace(
        source,
        base_tables=source.base_tables - policy.relations.optional_source_tables,
        readable_tables=(
            source.readable_tables - policy.relations.optional_source_tables
        ),
        maintainable_tables=(
            source.maintainable_tables - policy.relations.optional_source_tables
        ),
        sequences=source.sequences - policy.relations.optional_source_sequences,
        readable_sequences=(
            source.readable_sequences - policy.relations.optional_source_sequences
        ),
    )

    result = authorize(
        policy,
        action="preflight",
        environ=_environment(policy),
        source=source,
        target=_inspection(policy, source=False),
    )

    assert result.source.database == "pushinweight_shadow"


def test_optional_source_policy_covers_every_post_0027_relation() -> None:
    """Staging may migrate an exact production-0027 snapshot forward."""
    policy = load_policy(POLICY_PATH)

    assert {
        "currencies",
        "salary_periods",
        "job_functions",
        "seniority_levels",
        "employment_types",
        "workplace_types",
        "organization_ai_relationship_types",
        "role_ai_relationship_types",
        "job_function_assignments",
        "job_seniority_assignments",
        "job_employment_type_assignments",
        "job_workplace_type_assignments",
        "job_organization_ai_relationship_assignments",
        "job_role_ai_relationship_assignments",
        "time_zones",
        "languages",
        "locales",
        "measurement_units",
        "actors",
        "definition_versions",
        "service_providers",
        "inference_models",
        "workflow_stages",
        "event_dossiers",
        "event_dossier_sources",
        "event_dossier_claims",
        "event_dossier_reviews",
        "event_dossier_review_claims",
        "product_release_details",
        "personnel_change_details",
        "provider_batches",
        "materialization_state",
        "data_sources",
        "taxonomy_versions",
        "product_groups",
        "product_relationships",
        "product_group_memberships",
        "measurement_subjects",
        "subject_relationships",
        "post_subject_attributions",
        "metric_types",
        "metrics",
        "metric_collection_contracts",
        "source_subject_mappings",
        "collection_jobs",
        "collection_runs",
        "collection_observations",
        "metric_values",
        "editorial_assessments",
        "editorial_budgets",
        "editorial_calls",
        "editorial_editions",
        "editorial_heroes",
        "content_pictures",
        "editorial_stories",
        "official_company_account_states",
        "official_company_attempts",
        "official_company_budgets",
        "official_company_list_intents",
        "official_company_owner_credentials",
        "official_company_provider_states",
        "official_company_scans",
        "people_identity_corrections",
        "people_media",
        "people_names",
        "person_name_selections",
        "people_name_evidence",
        "people_texts",
        "people_text_translations",
        "staff_collection_work",
        "staff_intakes",
        "staff_media_objects",
        "staff_provider_requests",
        "account_profile_text_translations",
        "company_labels",
        "original_content_subject_labels",
        "trend_narrative_subject_labels",
        "product_label_keys",
        "collection_scope_runs",
        "collection_campaigns",
        "collection_job_targets",
        "collection_attempts",
        "collection_requests",
        "collection_evidence_archives",
        "collection_observation_inputs",
        "collection_resource_snapshots",
        "collection_metric_gaps",
        "collection_corrections",
        "product_label_labels",
        "audience_topic_concepts",
        "audience_topic_labels",
        "audience_topic_schemes",
        "geopolitical_mode_keys",
        "geopolitical_mode_labels",
        "national_stance_keys",
        "national_stance_labels",
        "untracked_brand_promotion_keys",
        "untracked_brand_promotion_labels",
        "posts_brands_classification_states",
        "posts_brands_classification_judgments",
        "posts_brands_audience_topics",
        "posts_brands_geopolitical_modes",
        "posts_brands_product_labels",
        "posts_brands_products",
        "posts_untracked_brand_promotions",
        "untracked_brand_promotion_evidence",
        "account_profile_snapshots",
        "brand_discovery_candidates",
        "brand_discovery_candidate_token_evidence",
        "brand_discovery_candidate_tokens",
        "events",
        "event_evidence",
        "job_discovery_runs",
        "job_listing_evidence",
        "job_listings",
        "job_source_states",
        "job_source_sync_runs",
        "opportunities",
        "people",
        "people_accounts",
        "people_brand_affiliation_evidence",
        "people_brand_affiliations",
        "personnel_discovery_runs",
        "targeted_extraction_attempts",
        "targeted_extraction_states",
        "trend_narrative_demands",
        "original_content_texts",
        "original_content_sources",
        "post_synthesis_artifacts",
        "post_synthesis_daily_budgets",
        "post_synthesis_demands",
        "post_synthesis_rate_limit_buckets",
        "post_synthesis_texts",
        "post_translation_artifacts",
        "post_translation_chunks",
        "post_translation_texts",
        "product_verification_proposals",
        "profile_movement_candidates",
        "rare_type_category_assignments",
        "rare_type_decision_attempts",
        "rare_type_decision_processing_cycles",
        "rare_type_decisions",
        "rare_type_search_daily_budgets",
        "rare_type_search_hits",
        "rare_type_search_runs",
    } <= policy.relations.optional_source_tables

    # Table renames retain owned sequence names; do not invent renamed sequences.
    sequence_prefix = {
        "metrics": "source_metrics",
        "collection_observations": "metric_observations",
        "collection_scope_runs": "hf_model_catalog_namespace_runs",
        "original_content_texts": "brand_trend_narrative_texts",
    }
    assert {
        f"{sequence_prefix.get(table, table)}_id_seq"
        for table in policy.relations.optional_source_tables
        if f"{sequence_prefix.get(table, table)}_id_seq" in policy.relations.sequences
    } == policy.relations.optional_source_sequences


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ("production_service", "service_identity_mismatch"),
        ("writable_source", "source_not_read_only"),
        ("source_database", "source_database_mismatch"),
        ("target_database", "target_database_mismatch"),
        ("production_target", "target_is_production"),
        ("excluded_readable", "source_excluded_table_readable:auth_user"),
        ("excluded_unlockable", "source_excluded_table_unlockable:auth_user"),
        (
            "unexpected_maintenance",
            "source_maintenance_privilege_unexpected:posts",
        ),
    ],
)
def test_guard_matrix_fails_closed(change: str, code: str) -> None:
    policy = load_policy(POLICY_PATH)
    environment = _environment(policy)
    source = _inspection(policy, source=True)
    target = _inspection(policy, source=False)

    if change == "production_service":
        environment["RENDER_SERVICE_ID"] = "srv-production"
    elif change == "writable_source":
        source = replace(source, default_transaction_read_only=False)
    elif change == "source_database":
        source = replace(source, database="other_source")
    elif change == "target_database":
        target = replace(target, database="other_target")
    elif change == "production_target":
        environment[policy.target.environment] = (
            f"postgresql://writer:secret@{policy.source.host}:5432/{policy.source.database}"
        )
    elif change == "excluded_readable":
        source = replace(source, readable_tables=source.readable_tables | {"auth_user"})
    elif change == "excluded_unlockable":
        source = replace(
            source, maintainable_tables=source.maintainable_tables - {"auth_user"}
        )
    elif change == "unexpected_maintenance":
        source = replace(
            source, maintainable_tables=source.maintainable_tables | {"posts"}
        )

    with pytest.raises(PolicyError, match=code):
        authorize(
            policy,
            action="preflight",
            environ=environment,
            source=source,
            target=target,
        )


def test_unknown_source_table_names_only_the_relation() -> None:
    policy = load_policy(POLICY_PATH)
    source = replace(
        _inspection(policy, source=True),
        base_tables=policy.relations.classified_tables | {"new_private_table"},
    )

    with pytest.raises(PolicyError) as exc_info:
        authorize(
            policy,
            action="preflight",
            environ=_environment(policy),
            source=source,
            target=_inspection(policy, source=False),
        )

    assert str(exc_info.value) == "source_unclassified_table:new_private_table"


@pytest.mark.parametrize("confirmation", ["yes", "refresh", "REFRESH production"])
def test_refresh_requires_the_exact_action_confirmation(confirmation: str) -> None:
    policy = load_policy(POLICY_PATH)

    with pytest.raises(PolicyError, match="confirmation_mismatch"):
        authorize(
            policy,
            action="refresh",
            environ=_environment(policy),
            source=_inspection(policy, source=True),
            target=_inspection(policy, source=False),
            confirmation=confirmation,
        )


def test_confirmation_cannot_be_replayed_for_another_action() -> None:
    policy = load_policy(POLICY_PATH)
    recovery = "pushinweight_staging_recovery_20260827t010203z"

    with pytest.raises(PolicyError, match="confirmation_mismatch"):
        authorize(
            policy,
            action="rollback",
            environ=_environment(policy),
            source=None,
            target=_inspection(policy, source=False),
            recovery=recovery,
            confirmation=expected_confirmation(policy, "prune", recovery=recovery),
        )


@pytest.mark.parametrize(
    "recovery",
    ["pushinweight_staging; DROP DATABASE x", "../recovery", "pushinweight_staging"],
)
def test_recovery_database_name_must_match_the_policy_grammar(recovery: str) -> None:
    policy = load_policy(POLICY_PATH)

    with pytest.raises(PolicyError, match="recovery_name_invalid"):
        expected_confirmation(policy, "rollback", recovery=recovery)


def test_benchmark_evidence_is_copied_with_optional_pre_migration_sources():
    policy = load_policy(POLICY_PATH)
    tables = {
        "data_sources",
        "taxonomy_versions",
        "product_groups",
        "product_relationships",
        "product_group_memberships",
        "measurement_subjects",
        "subject_relationships",
        "post_subject_attributions",
        "metric_types",
        "metrics",
        "metric_collection_contracts",
        "source_subject_mappings",
        "collection_runs",
        "collection_observations",
        "metric_values",
    }
    assert tables <= policy.relations.copied_tables
    assert tables <= policy.relations.optional_source_tables
    assert tables.isdisjoint(policy.relations.excluded_tables)
    # 0066 seeds X/HF into data_sources, so its pre-migration count may change.
    assert tables - {"data_sources"} <= set(policy.validation.exact_count_tables)
    sequences = {
        "source_metrics_id_seq",
        "metric_observations_id_seq",
        "collection_job_targets_id_seq",
        "collection_observation_inputs_id_seq",
        "collection_metric_gaps_id_seq",
        "metric_values_id_seq",
    }
    assert sequences <= policy.relations.sequences
    assert sequences <= policy.relations.optional_source_sequences


def test_shared_catalogues_are_preserved_and_pre_foundation_sources_remain_supported():
    policy = load_policy(POLICY_PATH)
    catalogues = frozenset(
        {
            "time_zones",
            "languages",
            "locales",
            "measurement_units",
            "actors",
            "definition_versions",
            "service_providers",
            "inference_models",
            "workflow_stages",
        }
    )
    assert catalogues <= policy.relations.copied_tables
    assert catalogues <= policy.relations.optional_source_tables
    assert catalogues.isdisjoint(policy.scrub.truncate_tables)
    current = _inspection(policy, source=True)
    old = replace(
        current,
        base_tables=current.base_tables - catalogues,
        readable_tables=current.readable_tables - catalogues,
    )
    authorize(
        policy,
        action="preflight",
        environ=_environment(policy),
        source=old,
        target=_inspection(policy, source=False),
    )


def test_post_drop_schema_contract_does_not_require_retired_identity_columns():
    policy = load_policy(POLICY_PATH)
    required = policy.validation.required_columns

    assert required["metrics"] >= {"unit_id", "window_unit_id", "source_timezone_id"}
    assert required["events"] >= {"source_timezone_id"}
    assert required["opportunities"] >= {"source_timezone_id"}
    assert required["geolocation_alternate_names"] >= {"geolocation_id", "locale_id", "name"}
    assert "unit" not in required["metrics"]
    assert "window_unit" not in required["metrics"]
    assert "source_timezone" not in required["metrics"]
    assert "source_timezone" not in required["events"]
    assert "source_timezone" not in required["opportunities"]
    for retired in ("countries", "regions", "country_labels", "region_labels", "country_codes_region",
                    "person_name_types", "release_disclosure_states"):
        assert retired not in required and retired not in policy.relations.classified_tables


def test_dossier_history_is_copied_and_pre_dossier_sources_remain_supported():
    policy = load_policy(POLICY_PATH)
    tables = frozenset({
        "event_dossiers", "event_dossier_sources", "event_dossier_claims",
        "event_dossier_reviews", "event_dossier_review_claims",
        "product_release_details", "personnel_change_details",
    })
    sequences = frozenset({
        "event_dossier_sources_id_seq", "event_dossier_review_claims_id_seq",
    })
    assert tables <= policy.relations.copied_tables
    assert tables <= policy.relations.optional_source_tables
    assert tables.isdisjoint(policy.scrub.truncate_tables)
    assert sequences <= policy.relations.sequences
    assert sequences <= policy.relations.optional_source_sequences
