from __future__ import annotations

import pytest

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_u9_migration_seeds_exact_classifier_flag_vocabulary():
    from core.models import UnsanctionedFlagKey

    assert set(UnsanctionedFlagKey.objects.values_list("key", flat=True)) == {
        "marketing_spam",
        "scam",
        "crypto",
        "unauthorized",
    }


def test_u9_state_tables_exist_on_postgresql():
    from django.db import connection

    table_names = set(connection.introspection.table_names())
    assert {
        "harvest_backlog_windows",
        "twitter_list_memberships",
        "post_enrichment_states",
    } <= table_names


@pytest.mark.django_db(transaction=True)
def test_u9_reverse_migration_preserves_existing_posts_flags_and_vocabulary():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    from core.models import Post, PostUnsanctionedFlag

    post = Post.objects.create(tweet_id="migration-safe-post")
    PostUnsanctionedFlag.objects.create(post=post, flags='["scam"]')

    executor = MigrationExecutor(connection)
    try:
        executor.migrate([("core", "0010_post_metrics_refreshed_at")])
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM posts WHERE tweet_id = %s",
                ["migration-safe-post"],
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "SELECT count(*) FROM posts_unsanctioned_flags WHERE post_id = %s",
                ["migration-safe-post"],
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute("SELECT key FROM unsanctioned_flag_keys ORDER BY key")
            assert {row[0] for row in cursor.fetchall()} == {
                "marketing_spam",
                "scam",
                "crypto",
                "unauthorized",
            }
    finally:
        MigrationExecutor(connection).migrate(
            [("core", "0011_harvester_state_primitives")]
        )
