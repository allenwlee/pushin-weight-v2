"""PostgreSQL contracts for the narrative-ledger expansion schema."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.db import IntegrityError, connection, transaction

import core.models as core_models

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def _restore_current_core_schema() -> None:
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    targets = [
        node
        for node in executor.loader.graph.leaf_nodes()
        if node[0] == "core"
    ]
    executor.migrate(targets)


def test_canonical_parent_and_subject_models_use_physical_table_names():
    narrative_model = core_models.TrendNarrative
    subject_model = core_models.TrendNarrativeSubject

    assert narrative_model._meta.db_table == "trend_narratives"
    assert subject_model._meta.db_table == "trend_narrative_subjects"
    assert not hasattr(core_models, "TrendNarrativeVersion")
    assert {
        "body_zh_cn",
        "llm_model_name",
        "output_schema_version",
        "observations_en",
        "observations_zh_cn",
        "selected_candidate_ids",
        "claims",
        "consecutive_failures",
    } <= {field.name for field in narrative_model._meta.fields}

    legacy_row = narrative_model(
        body_zh_hans="旧版中文",
        body_zh_cn=None,
        model_name="deepseek-v4-pro",
        llm_model_name=None,
    )
    assert legacy_row.resolved_body_zh_cn == "旧版中文"
    assert legacy_row.resolved_llm_model_name == "deepseek-v4-pro"


def test_physical_parent_table_and_writable_legacy_view_coexist():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT relname, relkind
            FROM pg_class
            WHERE relname IN (
                'trend_narratives',
                'trend_narrative_versions',
                'trend_narrative_subjects'
            )
            ORDER BY relname
            """
        )
        assert cursor.fetchall() == [
            ("trend_narrative_subjects", "r"),
            ("trend_narrative_versions", "v"),
            ("trend_narratives", "r"),
        ]
    from django.db.migrations.executor import MigrationExecutor

    old_apps = MigrationExecutor(connection).loader.project_state(
        [("core", "0013_trend_narrative_version")]
    ).apps
    old_model = old_apps.get_model("core", "TrendNarrativeVersion")
    old_row = old_model.objects.create(
        source_cycle_id="old-revision-write",
        window_days=1,
        status="checked",
        facts_as_of=NOW,
    )
    row_id = old_row.pk
    old_row.error_code = "legacy_update"
    old_row.save(update_fields=["error_code", "updated_at"])
    assert old_model.objects.get(pk=row_id).error_code == "legacy_update"

    old_brand = old_apps.get_model("core", "Brand").objects.create(
        nickname="late-legacy-brand",
        display_name="Late Legacy Brand",
        display_name_en="Late Legacy Brand",
        display_name_zh_cn="迟来旧品牌",
    )
    late_published = old_model.objects.create(
        source_cycle_id="old-revision-published-write",
        window_days=7,
        status="published",
        facts_as_of=NOW,
        semantic_fingerprint="late-legacy-fingerprint",
        is_current=True,
        primary_brand=old_brand,
        primary_brand_key="late-legacy-brand",
        primary_brand_name_en="Late Legacy Brand",
        primary_brand_name_zh_hans="迟来旧品牌",
        body_en="Late legacy headline",
        body_zh_hans="迟来旧标题",
        output_hash="late-legacy-output-hash",
        call_slot_consumed=True,
        claim_owner="late-legacy-worker",
        claim_fence=1,
        claimed_at=NOW,
        claim_expires_at=NOW + timedelta(minutes=5),
        transport_started_at=NOW,
        transport_completed_at=NOW,
        generated_at=NOW,
        published_at=NOW,
        model_name="deepseek-v4-pro",
    )
    canonical = core_models.TrendNarrative.objects.get(pk=late_published.pk)
    assert canonical.body_zh_cn is None
    assert canonical.llm_model_name is None
    assert canonical.resolved_body_zh_cn == "迟来旧标题"
    assert canonical.resolved_llm_model_name == "deepseek-v4-pro"
    assert not canonical.subjects.exists()

    late_published.body_zh_hans = "旧版更新标题"
    late_published.model_name = "deepseek-v4-pro-late-write"
    late_published.save(update_fields=["body_zh_hans", "model_name", "updated_at"])
    canonical.refresh_from_db()
    assert canonical.resolved_body_zh_cn == "旧版更新标题"
    assert canonical.resolved_llm_model_name == "deepseek-v4-pro-late-write"

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT source_cycle_id FROM trend_narratives WHERE id = %s",
            [row_id],
        )
        assert cursor.fetchone()[0] == "old-revision-write"
    deleted, _ = old_model.objects.filter(pk=row_id).delete()
    assert deleted == 1
    deleted, _ = old_model.objects.filter(pk=late_published.pk).delete()
    assert deleted == 1


def test_subject_identity_and_support_unions_are_database_enforced():
    narrative_model = core_models.TrendNarrative
    subject_model = core_models.TrendNarrativeSubject
    narrative = narrative_model.objects.create(
        source_cycle_id="subject-shapes",
        window_days=1,
        status=narrative_model.Status.CHECKED,
        facts_as_of=NOW,
    )

    valid = subject_model.objects.create(
        trend_narrative=narrative,
        position=0,
        support_type=subject_model.SupportType.MEASURED_CANDIDATE,
        entity_type=subject_model.EntityType.BRAND,
        identity_type=subject_model.IdentityType.BRAND,
        canonical_key_snapshot="minimax",
        name_en_snapshot="MiniMax",
        name_zh_cn_snapshot="MiniMax",
        candidate_id="minimax:full_window",
    )
    assert valid.pk

    with transaction.atomic(), pytest.raises(IntegrityError):
        subject_model.objects.create(
            trend_narrative=narrative,
            position=1,
            support_type=subject_model.SupportType.EVIDENCE_ONLY,
            entity_type=subject_model.EntityType.MODEL,
            identity_type=subject_model.IdentityType.UNRESOLVED,
            observed_name="OffListModel",
            canonical_key_snapshot="synthetic-key-is-forbidden",
            name_en_snapshot="OffListModel",
            name_zh_cn_snapshot="OffListModel",
            candidate_id="off-list:fake-series",
            evidence_ids=[],
        )

    evidence_only_narrative = narrative_model.objects.create(
        source_cycle_id="evidence-only-primary",
        window_days=7,
        status=narrative_model.Status.CHECKED,
        facts_as_of=NOW,
    )
    with transaction.atomic(), pytest.raises(IntegrityError):
        subject_model.objects.create(
            trend_narrative=evidence_only_narrative,
            position=0,
            support_type=subject_model.SupportType.EVIDENCE_ONLY,
            entity_type=subject_model.EntityType.MODEL,
            identity_type=subject_model.IdentityType.UNRESOLVED,
            observed_name="OffListModel",
            name_en_snapshot="OffListModel",
            name_zh_cn_snapshot="OffListModel",
            evidence_ids=["e_one", "e_two"],
        )


def test_subject_position_is_unique_and_bounded():
    narrative_model = core_models.TrendNarrative
    subject_model = core_models.TrendNarrativeSubject
    narrative = narrative_model.objects.create(
        source_cycle_id="subject-positions",
        window_days=1,
        status=narrative_model.Status.CHECKED,
        facts_as_of=NOW,
    )
    values = {
        "trend_narrative": narrative,
        "support_type": subject_model.SupportType.MEASURED_CANDIDATE,
        "entity_type": subject_model.EntityType.BRAND,
        "identity_type": subject_model.IdentityType.BRAND,
        "canonical_key_snapshot": "minimax",
        "name_en_snapshot": "MiniMax",
        "name_zh_cn_snapshot": "MiniMax",
        "candidate_id": "minimax:full_window",
    }
    subject_model.objects.create(position=0, **values)
    with transaction.atomic(), pytest.raises(IntegrityError):
        subject_model.objects.create(position=0, **values)
    with transaction.atomic(), pytest.raises(IntegrityError):
        subject_model.objects.create(position=2, **values)


def test_u2_normalized_persistence_tables_constraints_and_indexes_exist():
    assert {
        "TrendNarrativeRun",
        "TrendNarrativeProviderCall",
        "BrandTrendNarrative",
        "TrendNarrativeVisibleRun",
    } <= set(dir(core_models))
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT relname
            FROM pg_class
            WHERE relname IN (
                'trend_narrative_runs',
                'trend_narrative_provider_calls',
                'brand_trend_narratives',
                'trend_narrative_visible_runs'
            )
              AND relkind = 'r'
            ORDER BY relname
            """
        )
        assert [row[0] for row in cursor.fetchall()] == [
            "brand_trend_narratives",
            "trend_narrative_provider_calls",
            "trend_narrative_runs",
            "trend_narrative_visible_runs",
        ]
        cursor.execute(
            """
            SELECT conname
            FROM pg_constraint
            WHERE conname IN (
                'uq_tnr_source_window', 'uq_tnpc_run_stage_batch',
                'uq_tnpc_request_identity', 'uq_btn_run_brand',
                'ck_tnpc_sent_shape', 'ck_btn_held_last_good',
                'ck_btn_critic_decision', 'ck_btn_narrative_kind',
                'ck_btn_confidence'
            )
            ORDER BY conname
            """
        )
        assert [row[0] for row in cursor.fetchall()] == [
            "ck_btn_confidence",
            "ck_btn_critic_decision",
            "ck_btn_held_last_good",
            "ck_btn_narrative_kind",
            "ck_tnpc_sent_shape",
            "uq_btn_run_brand",
            "uq_tnpc_request_identity",
            "uq_tnpc_run_stage_batch",
            "uq_tnr_source_window",
        ]
        cursor.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE indexname IN (
                'idx_tnr_window_facts', 'idx_tnpc_claim_due',
                'idx_btn_brand_attempt'
            )
            ORDER BY indexname
            """
        )
        assert [row[0] for row in cursor.fetchall()] == [
            "idx_btn_brand_attempt",
            "idx_tnpc_claim_due",
            "idx_tnr_window_facts",
        ]

    brand_fields = {
        field.name for field in core_models.BrandTrendNarrative._meta.fields
    }
    assert {"critic_decision", "narrative_kind", "confidence"} <= brand_fields


def test_u2_migration_round_trip_preserves_legacy_narrative_rows():
    from django.db.migrations.executor import MigrationExecutor

    legacy = core_models.TrendNarrative.objects.create(
        source_cycle_id="u2-migration-preserves-legacy",
        window_days=7,
        status=core_models.TrendNarrative.Status.CHECKED,
        facts_as_of=NOW,
        error_code="existing_legacy_check",
    )
    try:
        executor = MigrationExecutor(connection)
        executor.migrate([("core", "0016_post_commentary_fields")])
        old_apps = executor.loader.project_state(
            [("core", "0016_post_commentary_fields")]
        ).apps
        old_row = old_apps.get_model("core", "TrendNarrative").objects.get(
            pk=legacy.pk
        )
        assert old_row.source_cycle_id == "u2-migration-preserves-legacy"
        assert old_row.error_code == "existing_legacy_check"

        executor = MigrationExecutor(connection)
        executor.migrate([("core", "0017_per_brand_trend_narratives")])
        new_apps = executor.loader.project_state(
            [("core", "0017_per_brand_trend_narratives")]
        ).apps
        new_row = new_apps.get_model("core", "TrendNarrative").objects.get(
            pk=legacy.pk
        )
        assert new_row.source_cycle_id == "u2-migration-preserves-legacy"
        assert new_row.error_code == "existing_legacy_check"
    finally:
        _restore_current_core_schema()


def test_product_subject_snapshot_survives_future_product_catalog_deletion():
    product = core_models.Product.objects.create(
        repo_id="vendor/FutureModel",
        display_name="FutureModel",
    )
    narrative = core_models.TrendNarrative.objects.create(
        source_cycle_id="product-subject",
        window_days=1,
        status=core_models.TrendNarrative.Status.CHECKED,
        facts_as_of=NOW,
    )
    subject = core_models.TrendNarrativeSubject.objects.create(
        trend_narrative=narrative,
        position=0,
        support_type="measured_candidate",
        entity_type="model",
        identity_type="product",
        product=product,
        canonical_key_snapshot="vendor/FutureModel",
        name_en_snapshot="FutureModel",
        name_zh_cn_snapshot="FutureModel",
        candidate_id="vendor/FutureModel:full_window",
    )

    product.delete()
    subject.refresh_from_db()

    assert subject.product_id is None
    assert subject.canonical_key_snapshot == "vendor/FutureModel"
    assert subject.name_en_snapshot == "FutureModel"


def test_upgrade_from_0013_backfills_canonical_fields_and_subjects():
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    try:
        executor.migrate([("core", "0013_trend_narrative_version")])
        old_apps = executor.loader.project_state(
            [("core", "0013_trend_narrative_version")]
        ).apps
        old_brand = old_apps.get_model("core", "Brand").objects.create(
            nickname="legacy-brand",
            display_name="Legacy Brand",
            display_name_en="Legacy Brand",
            display_name_zh_cn="旧品牌",
        )
        old_model = old_apps.get_model("core", "TrendNarrativeVersion")
        old_row = old_model.objects.create(
            source_cycle_id="legacy-row",
            window_days=1,
            status="published",
            facts_as_of=NOW,
            semantic_fingerprint="legacy-fingerprint",
            is_current=True,
            primary_brand=old_brand,
            primary_brand_key="legacy-brand",
            primary_brand_name_en="Legacy Brand",
            primary_brand_name_zh_hans="旧品牌",
            body_en="Legacy headline",
            body_zh_hans="旧标题",
            output_hash="legacy-output-hash",
            call_slot_consumed=True,
            claim_owner="legacy-worker",
            claim_fence=1,
            claimed_at=NOW,
            claim_expires_at=NOW + timedelta(minutes=5),
            transport_started_at=NOW,
            transport_completed_at=NOW,
            generated_at=NOW,
            published_at=NOW,
            model_name="deepseek-v4-pro",
        )

        executor = MigrationExecutor(connection)
        executor.migrate([("core", "0014_expand_trend_narrative")])
        new_apps = executor.loader.project_state(
            [("core", "0014_expand_trend_narrative")]
        ).apps
        narrative = new_apps.get_model("core", "TrendNarrative").objects.get(
            source_cycle_id="legacy-row"
        )
        subject_model = new_apps.get_model("core", "TrendNarrativeSubject")

        assert narrative.pk == old_row.pk
        assert narrative.body_en == "Legacy headline"
        assert narrative.body_zh_hans == "旧标题"
        assert narrative.body_zh_cn == "旧标题"
        assert narrative.model_name == "deepseek-v4-pro"
        assert narrative.llm_model_name == "deepseek-v4-pro"
        assert narrative.output_schema_version == 1
        subject = subject_model.objects.get(
            trend_narrative_id=narrative.pk
        )
        assert subject.position == 0
        assert subject.support_type == "measured_candidate"
        assert subject.identity_type == "brand"
        assert subject.brand_id == "legacy-brand"
        assert subject.canonical_key_snapshot == "legacy-brand"
        assert subject.name_en_snapshot == "Legacy Brand"
        assert subject.name_zh_cn_snapshot == "旧品牌"
        assert subject.candidate_id == "legacy-brand:legacy"
    finally:
        _restore_current_core_schema()


def test_reverse_refuses_expansion_only_data_before_any_destructive_step():
    from django.db.migrations.executor import MigrationExecutor

    narrative = core_models.TrendNarrative.objects.create(
        source_cycle_id="canonical-only-row",
        window_days=1,
        status=core_models.TrendNarrative.Status.CHECKED,
        facts_as_of=NOW,
        output_schema_version=2,
        selected_candidate_ids=["minimax:full_window"],
    )

    with pytest.raises(RuntimeError, match="cannot reverse"):
        MigrationExecutor(connection).migrate(
            [("core", "0013_trend_narrative_version")]
        )

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relkind FROM pg_class WHERE relname = 'trend_narratives'"
        )
        assert cursor.fetchone()[0] == "r"
        cursor.execute(
            "SELECT relkind FROM pg_class WHERE relname = 'trend_narrative_versions'"
        )
        assert cursor.fetchone()[0] == "v"
    assert core_models.TrendNarrative.objects.filter(pk=narrative.pk).exists()
