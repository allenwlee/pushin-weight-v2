from __future__ import annotations

from copy import deepcopy

import pytest
from django.db import DatabaseError, connection

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _row(*, outcome: str = "classified", post_types: list[str] | None = None) -> dict:
    return {
        "outcome": outcome,
        "post_types": post_types if post_types is not None else ["other"],
        "product_labels": [],
        "sentiment": "neutral" if outcome == "classified" else None,
        "china_nationalism": None,
        "us_nationalism": None,
    }


def _trace(brand_id: str, *, final: dict | None = None) -> dict:
    primary = {brand_id: _row(post_types=["hands_on_usage"])}
    review = {brand_id: _row(post_types=["hands_on_usage"])}
    final_by_brand = final or review
    metadata = {
        "contract_version": "stage1-v1",
        "taxonomy_version": "stage1-taxonomy-v3",
        "prompt_version": "stage1-prompt-v22",
        "provider_role": "scheduled_classifier",
        "selector_version": "r79-test-selector-v1",
        "validation_state": "validated",
    }
    return {
        "metadata": metadata,
        "primary": {"by_brand": primary, **metadata, "changes": {}},
        "review": {
            "by_brand": review,
            **metadata,
            "changes": {
                "prompt": "must not persist",
                "source": {"text": "must not persist"},
            },
            "metadata_by_brand": {
                brand_id: {
                    "decision": "replace",
                    "change_reasons": ["missing_post_type"],
                    "evidence": [
                        {"source": "source", "quote": "classification source"}
                    ],
                    "prompt_version": "stage1-prompt-v22-completeness-review-repair-v1",
                }
            },
        },
        "final": {"by_brand": final_by_brand, **metadata, "changes": {}},
    }


def _publish_setup(suffix: str):
    from core.models import (
        Brand,
        Post,
        PostBrand,
        PostEnrichmentState,
        PostTypeKey,
        SentimentKey,
    )

    PostTypeKey.objects.get_or_create(key="hands_on_usage")
    PostTypeKey.objects.get_or_create(key="other")
    SentimentKey.objects.get_or_create(key="neutral")

    post = Post.objects.create(
        tweet_id=f"provenance-post-{suffix}",
        text="classification source",
        lang_detected="en",
    )
    brand = Brand.objects.create(
        nickname=f"provenance-brand-{suffix}", display_name="Provenance"
    )
    PostBrand.objects.create(post=post, brand=brand)
    PostEnrichmentState.objects.create(
        post=post, claim_run_id=f"provenance-run-{suffix}"
    )
    return post, brand


def _publish(post, result, *, run_id: str):
    from monitor.cycle import _publish_stage1_classification

    return _publish_stage1_classification(
        post_id=post.pk,
        result=result,
        tweet={"text": post.text, "context": []},
        model="deepseek-v4-flash",
        run_id=run_id,
    )


def test_judgment_history_links_lineage_and_reruns_idempotently():
    from core.models import (
        PostBrandClassificationJudgment,
        PostBrandClassificationState,
    )

    post, brand = _publish_setup("lineage")
    result = {
        "valid": True,
        "unsanctioned_flags": [],
        "by_brand": {brand.pk: _row(post_types=["hands_on_usage"])},
        "classification_trace": _trace(brand.pk),
    }

    assert _publish(post, result, run_id="provenance-run-lineage").outcome == "cleared"
    assert (
        _publish(post, deepcopy(result), run_id="provenance-run-lineage").outcome
        == "cleared"
    )

    rows = list(
        PostBrandClassificationJudgment.objects.filter(post=post).order_by("created_at")
    )
    assert [row.stage for row in rows] == ["primary", "review", "final"]
    assert rows[0].parent_judgment_id is None
    assert rows[1].parent_judgment_id == rows[0].pk
    assert rows[2].parent_judgment_id == rows[1].pk
    assert rows[1].parent_judgment.stage == "primary"
    assert rows[2].parent_judgment.stage == "review"
    assert {(row.post_id, row.brand_id, row.revision_id) for row in rows} == {
        (post.pk, brand.pk, rows[0].revision_id)
    }
    assert len({row.revision_id for row in rows}) == 1
    assert not any("prompt" in row.canonical_judgment for row in rows)
    assert rows[1].changes_json["decision"] == "replace"
    assert rows[1].changes_json["change_reasons"] == ["missing_post_type"]
    assert "prompt" not in rows[1].changes_json
    assert "source" not in rows[1].changes_json
    assert rows[1].prompt_version == "stage1-prompt-v22-completeness-review-repair-v1"
    state = PostBrandClassificationState.objects.get(post=post, brand=brand)
    assert state.selected_final_judgment_id == rows[2].pk
    assert PostBrandClassificationJudgment.objects.filter(post=post).count() == 3


def test_trace_final_mismatch_rejects_before_any_projection_write():
    from core.models import (
        PostBrandClassificationJudgment,
        PostBrandClassificationState,
    )

    post, brand = _publish_setup("mismatch")
    result = {
        "valid": True,
        "unsanctioned_flags": [],
        "by_brand": {brand.pk: _row(post_types=["hands_on_usage"])},
        "classification_trace": _trace(
            brand.pk, final={brand.pk: _row(post_types=["other"])}
        ),
    }

    with pytest.raises(ValueError, match="final_mismatch"):
        _publish(post, result, run_id="provenance-run-mismatch")
    assert not PostBrandClassificationJudgment.objects.filter(post=post).exists()
    assert not PostBrandClassificationState.objects.filter(post=post).exists()


def test_trace_requires_the_same_nonblank_selector_on_every_stage():
    from core.models import (
        PostBrandClassificationJudgment,
        PostBrandClassificationState,
    )

    post, brand = _publish_setup("selector")
    trace = _trace(brand.pk)
    trace.pop("metadata")
    trace.pop("selector_version", None)
    trace["review"]["selector_version"] = ""
    result = {
        "valid": True,
        "unsanctioned_flags": [],
        "by_brand": {brand.pk: _row(post_types=["hands_on_usage"])},
        "classification_trace": trace,
    }

    with pytest.raises(ValueError, match="selector_missing_or_conflicting"):
        _publish(post, result, run_id="provenance-run-selector")
    assert not PostBrandClassificationJudgment.objects.filter(post=post).exists()
    assert not PostBrandClassificationState.objects.filter(post=post).exists()


def test_trace_and_projection_roll_back_together_on_downstream_failure(monkeypatch):
    from core.models import (
        PostBrandClassificationJudgment,
        PostBrandClassificationState,
    )
    from monitor import unsanctioned_flags

    post, brand = _publish_setup("rollback")
    monkeypatch.setattr(
        unsanctioned_flags,
        "persist_classifier_flags",
        lambda **_kwargs: (_ for _ in ()).throw(DatabaseError("forced")),
    )
    result = {
        "valid": True,
        "unsanctioned_flags": [],
        "by_brand": {brand.pk: _row()},
        "classification_trace": _trace(brand.pk, final={brand.pk: _row()}),
    }

    with pytest.raises(DatabaseError):
        _publish(post, result, run_id="provenance-run-rollback")
    assert not PostBrandClassificationJudgment.objects.filter(post=post).exists()
    assert not PostBrandClassificationState.objects.filter(post=post).exists()


def test_legacy_call_keeps_selected_judgment_null_and_clears_stale_edges():
    from core.models import (
        PostBrandClassificationJudgment,
        PostBrandClassificationState,
        PostBrandProductLabel,
        PostBrandSignal,
        PostTypeKey,
        ProductLabelKey,
        SentimentKey,
    )

    post, brand = _publish_setup("legacy")
    PostTypeKey.objects.get_or_create(key="other")
    SentimentKey.objects.get_or_create(key="neutral")
    ProductLabelKey.objects.get_or_create(key="bug")
    PostBrandSignal.objects.create(
        post=post, brand=brand, post_type_id="other", sentiment_id="neutral"
    )
    PostBrandProductLabel.objects.create(post=post, brand=brand, product_label_id="bug")
    result = {
        "valid": True,
        "unsanctioned_flags": [],
        "by_brand": {brand.pk: _row(outcome="context_missing", post_types=[])},
    }

    assert _publish(post, result, run_id="provenance-run-legacy").outcome == "cleared"
    state = PostBrandClassificationState.objects.get(post=post, brand=brand)
    assert state.selected_final_judgment_id is None
    assert not PostBrandClassificationJudgment.objects.filter(post=post).exists()
    assert not PostBrandSignal.objects.filter(post=post).exists()
    assert not PostBrandProductLabel.objects.filter(post=post).exists()


def test_migration_has_history_table_and_nullable_projection_link():
    tables = connection.introspection.table_names()
    assert "posts_brands_classification_judgments" in tables
    columns = {
        column.name
        for column in connection.introspection.get_table_description(
            connection.cursor(), "posts_brands_classification_judgments"
        )
    }
    assert {
        "revision_id",
        "stage",
        "canonical_judgment",
        "provider_role",
        "selector_version",
        "validation_state",
        "changes_json",
        "parent_judgment_id",
    } <= columns
    state_columns = {
        column.name: column
        for column in connection.introspection.get_table_description(
            connection.cursor(), "posts_brands_classification_states"
        )
    }
    assert state_columns["selected_final_judgment_id"].null_ok is True
