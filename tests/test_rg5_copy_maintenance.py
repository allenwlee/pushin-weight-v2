"""Index maintenance must not lengthen Post row-lock transactions."""

import importlib

import pytest
from django.db import connection

from core.models import Post
from core.source_vocabulary import reference_id

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


@pytest.mark.parametrize(
    "migration_rehearsal_schema",
    [("core", "0166_rg5_reference_source_guards")],
    indirect=True,
)
def test_post_copy_commits_before_maintenance_and_resumes_without_overwriting(
    migration_rehearsal_schema, monkeypatch,
):
    mapping = importlib.import_module("core.migrations._rg5_reference_mapping_v2")
    maintenance = importlib.import_module(
        "core.migrations._rg4_geography_write_performance_v1"
    )
    keys = [f"rg5-maintenance-{index:04}" for index in range(501)]
    Post.objects.bulk_create([Post(tweet_id=key) for key in keys])
    bridge = mapping.bridge_name("posts", "author_verified_type")
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE posts DISABLE TRIGGER {bridge}")
        cursor.execute("UPDATE posts SET author_verified_type='Business'")
        cursor.execute(f"ALTER TABLE posts ENABLE TRIGGER {bridge}")

    real_prepare = maintenance.prepare_post_index
    calls = []

    def interrupt_after_commit(conn, table, *, phase="initial"):
        assert not conn.in_atomic_block
        calls.append(phase)
        if phase == "batch" and calls.count("batch") == 1:
            assert Post.objects.filter(author_verified_type__isnull=False).count() == 500
            raise RuntimeError("maintenance interrupted after committed copy")
        return real_prepare(conn, table, phase=phase)

    monkeypatch.setattr(mapping, "prepare_post_index", interrupt_after_commit)
    monkeypatch.setattr(maintenance, "prepare_post_index", interrupt_after_commit)

    def verify_write_budget(execute, sql, params, many, context):
        if sql.startswith("UPDATE posts SET author_verified_type_id="):
            assert connection.in_atomic_block
            assert connection.connection.execute(
                "SHOW gin_pending_list_limit"
            ).fetchone() == ("64MB",)
        return execute(sql, params, many, context)

    def copy():
        with connection.execute_wrapper(verify_write_budget):
            mapping.install_and_map(
                connection,
                table="posts",
                old="author_verified_type",
                new="author_verified_type_id",
                catalogue="account_verification_types",
                pk="tweet_id",
                source_sql="'x'",
            )

    with pytest.raises(RuntimeError, match="maintenance interrupted"):
        copy()
    assert Post.objects.filter(author_verified_type__isnull=False).count() == 500
    corrected = reference_id("account_verification_types", "x", "Government")
    Post.objects.filter(pk=keys[0]).update(author_verified_type_id=corrected)
    copy()
    assert Post.objects.get(pk=keys[0]).author_verified_type_id == corrected
    assert Post.objects.filter(author_verified_type__code="Business").count() == 500
    assert Post.objects.count() == 501
    assert calls == ["rg5-reference-initial", "batch", "rg5-reference-initial", "batch"]
