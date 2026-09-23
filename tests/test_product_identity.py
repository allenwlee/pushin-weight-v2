from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]

BEFORE = [("core", "0051_profile_movement_token_evidence")]
AFTER = [("core", "0052_alter_product_options_product_product_key_and_more")]


def test_populated_products_receive_distinct_keys_and_keep_ids_and_hf_metadata():
    executor = MigrationExecutor(connection)
    try:
        executor.migrate(BEFORE)
        old_apps = executor.loader.project_state(BEFORE).apps
        Product = old_apps.get_model("core", "Product")
        first = Product.objects.create(repo_id="org/one", sha="sha-one")
        second = Product.objects.create(repo_id="org/two", sha="sha-two")

        executor = MigrationExecutor(connection)
        executor.migrate(AFTER)
        apps = executor.loader.project_state(AFTER).apps
        Product = apps.get_model("core", "Product")
        rows = list(Product.objects.filter(id__in=[first.id, second.id]).order_by("id"))
        assert [row.id for row in rows] == [first.id, second.id]
        assert [row.repo_id for row in rows] == ["org/one", "org/two"]
        assert [row.sha for row in rows] == ["sha-one", "sha-two"]
        assert rows[0].product_key != rows[1].product_key
        x_only = Product.objects.create(repo_id=None, display_name="X-only Product")
        assert x_only.product_key
    finally:
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )
