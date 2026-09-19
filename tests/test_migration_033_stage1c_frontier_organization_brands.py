"""Upgrade proof for distinct organization-facing Stage 1C brands."""

from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_migration_seeds_anthropic_and_google_deepmind_without_gemini_aliasing():
    executor = MigrationExecutor(connection)
    try:
        executor.migrate([("core", "0032_stage1c_people_jobs_events")])
        old_apps = executor.loader.project_state(
            [("core", "0032_stage1c_people_jobs_events")]
        ).apps
        Brand = old_apps.get_model("core", "Brand")
        Brand.objects.create(nickname="gemini", display_name="Gemini")

        executor = MigrationExecutor(connection)
        executor.migrate([("core", "0033_stage1c_frontier_organization_brands")])
        apps = executor.loader.project_state(
            [("core", "0033_stage1c_frontier_organization_brands")]
        ).apps
        Brand = apps.get_model("core", "Brand")
        BrandCompany = apps.get_model("core", "BrandCompany")

        assert Brand.objects.filter(nickname="anthropic").exists()
        assert Brand.objects.filter(nickname="google_deepmind").exists()
        assert Brand.objects.filter(nickname="gemini").exists()
        assert BrandCompany.objects.filter(
            brand_id="google_deepmind", company_id="google"
        ).exists()
    finally:
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )
