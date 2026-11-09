"""Verify the historical chart lookup index is actually usable after migration."""

import pytest
from django.db import connection


@pytest.mark.django_db
@pytest.mark.requires_postgres
def test_chart_native_lookup_index_is_ready():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT i.indisvalid, i.indisready, pg_get_expr(i.indpred, i.indrelid)
            FROM pg_index i
            JOIN pg_class c ON c.oid = i.indexrelid
            WHERE c.relname = %s
            """,
            ["idx_obs_native_chart"],
        )
        row = cursor.fetchone()
    assert row is not None
    valid, ready, predicate = row
    assert valid and ready
    assert "mapping_id IS NULL" in predicate
    assert "model" in predicate and "repository" in predicate
