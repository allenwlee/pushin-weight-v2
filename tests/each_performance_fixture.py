"""Populate the combined candidate workload without synthesis-demand polling.

This is a preview/test fixture condition. Production behavior and its clock are
unchanged. The preview caller holds django.utils.timezone.now at the returned
anchor for every served request, as well as using it during this seed operation.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from django.utils import timezone

from core.models import Post, PostEnrichmentState
from tests import general_helpers
from tests.each_area_fixture import seed_each_area_orm
from tests.test_chart_harvest_coverage import record_harvest
from tests.v22_support import fixture_from_oracle, seed_real_home_orm

ROOT = Path(__file__).resolve().parents[1]


def seed_each_performance_orm(*, now=None):
    """Seed homepage + rich Each + General, returning their shared clock anchor."""
    anchor = now or timezone.now()
    assert timezone.is_aware(anchor)
    with patch("django.utils.timezone.now", return_value=anchor), patch.object(
        general_helpers, "NOW", anchor
    ):
        seed_real_home_orm(fixture_from_oracle())
        # Legacy base records contain EN/ZH commentary. Complete typed storage
        # with the same visible EN/ZH text and a deterministic Japanese fixture
        # so normal readers report ready and never enqueue missing-locale work.
        for post in Post.objects.filter(tweet_id__startswith="u3-post-"):
            assert post.commentary_en and post.commentary_zh_cn
            general_helpers.saved_commentary(post, texts={
                "en": post.commentary_en,
                "zh-cn": post.commentary_zh_cn,
                "ja": f"保存されたテスト用解説 {post.pk}",
            })
        # Terminal fixture condition keeps the declared processing-sprite cache
        # workload present without pending work, polling, or changing synthesis.
        PostEnrichmentState.objects.create(
            post_id="u3-post-0", translation_requested=True,
            translation_status=PostEnrichmentState.Status.FAILED,
            translation_attempts=3,
            translation_first_attempt_at=anchor, translation_last_attempt_at=anchor,
            translation_next_attempt_at=None,
            translation_error_code="fixture_terminal_translation_failure",
            classification_status=PostEnrichmentState.Status.SUCCEEDED,
            classification_attempts=1,
            classification_first_attempt_at=anchor, classification_last_attempt_at=anchor,
            classification_next_attempt_at=None,
        )
        seed = json.loads((ROOT / "tests/fixtures/ui_assurance/each-fixture.json").read_text())
        assert seed_each_area_orm(seed) == 62
        contract = json.loads((ROOT / "tests/fixtures/general_feed_contract.json").read_text())
        for post_id, category in contract["sections"].items():
            general_helpers.saved_commentary(general_helpers.classified_post(post_id, category))
        general_helpers.saved_commentary(general_helpers.classified_post(
            contract["closed_job"], brand="claude",
        ))
        record_harvest(anchor, finished_at=anchor, staggered=False)
    return anchor
