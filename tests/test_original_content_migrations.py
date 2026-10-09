"""Populated compatibility migration preserves real keys and legacy copy."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]
BASE = ("core", "0074_official_company_generic_accounts")
EXPAND = ("core", "0076_original_content_expand")


def test_populated_expand_and_pre_cutover_reverse_preserve_text_and_keys():
    executor = MigrationExecutor(connection)
    final = executor.loader.graph.leaf_nodes()
    executor.migrate([BASE])
    apps = executor.loader.project_state([BASE]).apps
    now = timezone.now()
    run = apps.get_model("core", "TrendNarrativeRun").objects.create(
        source_cycle_id="migration-seven-day",
        window_days=7,
        facts_as_of=now,
        packet_schema_version=3,
        snapshot={},
    )
    outcome = apps.get_model("core", "BrandTrendNarrative").objects.create(
        run=run,
        brand_key_snapshot="preserved",
        status="approved",
        brand_name_en_snapshot="Saved brand",
        brand_name_zh_cn_snapshot="保存品牌",
        headline_en="Saved headline",
        headline_zh_cn="保存标题",
        secondary_en="Saved secondary",
        secondary_zh_cn="保存副标题",
        verified_at=now,
        attempted_at=now,
    )
    text = apps.get_model("core", "BrandTrendNarrativeText").objects.create(
        narrative=outcome,
        locale="en",
        headline="Saved headline",
        secondary="Saved secondary",
    )
    apps.get_model("core", "TrendNarrativeVisibleRun").objects.create(
        window_days=7,
        run=run,
        facts_as_of=now,
        activated_at=now,
    )
    before = set(connection.introspection.table_names())
    try:
        executor = MigrationExecutor(connection)
        executor.migrate([EXPAND])
        new = executor.loader.project_state([EXPAND]).apps
        assert (
            new.get_model("core", "OriginalContent")
            .objects.get(pk=outcome.pk)
            .headline_en
            == "Saved headline"
        )
        assert (
            new.get_model("core", "OriginalContentText")
            .objects.get(pk=text.pk)
            .secondary
            == "Saved secondary"
        )
        pointer = new.get_model("core", "OriginalContentSelection").objects.get(
            window_days=7
        )
        assert pointer.pk == 7 and pointer.run_id == run.pk
        assert set(connection.introspection.table_names()) - before == {
            "original_content_sources"
        }
        MigrationExecutor(connection).migrate([BASE])
        old = MigrationExecutor(connection).loader.project_state([BASE]).apps
        assert (
            old.get_model("core", "BrandTrendNarrativeText")
            .objects.get(pk=text.pk)
            .headline
            == "Saved headline"
        )
        assert (
            old.get_model("core", "TrendNarrativeVisibleRun").objects.get(pk=7).run_id
            == run.pk
        )
    finally:
        MigrationExecutor(connection).migrate(final)
