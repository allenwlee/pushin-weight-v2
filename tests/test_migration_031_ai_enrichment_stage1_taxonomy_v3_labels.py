"""Additive taxonomy-v3 lookup and label migration proof."""

from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from core.classification_contract import (
    CANONICAL_POST_TYPE_KEYS,
    STAGE1_TAXONOMY_V2_POST_TYPE_KEYS,
)
from core.classification_labels import POST_TYPE_LABELS

BEFORE = [("core", "0030_ai_enrichment_stage1_taxonomy_v2_edges")]
TARGET = [("core", "0031_ai_enrichment_stage1_taxonomy_v3_labels")]
V3_ONLY_KEYS = tuple(
    key
    for key in CANONICAL_POST_TYPE_KEYS
    if key not in STAGE1_TAXONOMY_V2_POST_TYPE_KEYS
)


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_taxonomy_v3_labels_are_additive_and_preserve_v2_rows():
    executor = MigrationExecutor(connection)
    try:
        executor.recorder.record_unapplied("core", TARGET[0][1])
        apps = executor.loader.project_state(BEFORE).apps
        PostTypeKey = apps.get_model("core", "PostTypeKey")
        PostTypeLabel = apps.get_model("core", "PostTypeLabel")
        State = apps.get_model("core", "PostBrandClassificationState")

        PostTypeLabel.objects.filter(post_type_id__in=V3_ONLY_KEYS).delete()
        PostTypeKey.objects.filter(key__in=V3_ONLY_KEYS).delete()
        before_v2_labels = list(
            PostTypeLabel.objects.filter(
                post_type_id="events_opportunities"
            ).values_list("lang", "label")
        )
        before_state_count = State.objects.count()

        MigrationExecutor(connection).migrate(TARGET)
        migrated_apps = MigrationExecutor(connection).loader.project_state(TARGET).apps
        MigratedLabel = migrated_apps.get_model("core", "PostTypeLabel")

        assert V3_ONLY_KEYS == (
            "events",
            "opportunities",
            "job_listings",
            "personnel_changes",
        )
        for key in V3_ONLY_KEYS:
            assert (
                dict(
                    MigratedLabel.objects.filter(post_type_id=key).values_list(
                        "lang", "label"
                    )
                )
                == POST_TYPE_LABELS[key]
            )
        assert (
            list(
                MigratedLabel.objects.filter(
                    post_type_id="events_opportunities"
                ).values_list("lang", "label")
            )
            == before_v2_labels
        )
        assert (
            migrated_apps.get_model(
                "core", "PostBrandClassificationState"
            ).objects.count()
            == before_state_count
        )
    finally:
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )
