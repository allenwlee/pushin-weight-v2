"""Release A compatibility tests for canonical dashboard taxonomy surfaces."""

from __future__ import annotations

import html
import json
import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from core.classification_contract import CONTRACT_VERSION
from core.models import (
    Brand,
    Post,
    PostBrand,
    PostBrandClassificationState,
    PostBrandProductLabel,
    PostBrandSignal,
    PostTypeKey,
    ProductLabelKey,
    SentimentKey,
)
from monitor import views

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]

OLD_TYPE = "buzz_releases"
CANONICAL_TYPE = "releases_updates"
OLD_PRODUCT = "product_request"
CANONICAL_PRODUCT = "ideas_requests"


@pytest.fixture
def compatible_taxonomy_rows():
    brand = Brand.objects.create(
        nickname="taxonomy-surface", display_name="Taxonomy Surface"
    )
    for key in (OLD_TYPE, CANONICAL_TYPE):
        PostTypeKey.objects.get_or_create(key=key)
    for key in (OLD_PRODUCT, CANONICAL_PRODUCT):
        ProductLabelKey.objects.get_or_create(key=key)
    SentimentKey.objects.get_or_create(key="positive")
    now = timezone.now()
    posts = []
    for index in range(2):
        post = Post.objects.create(
            tweet_id=f"taxonomy-surface-{index}",
            created_at=now - timedelta(minutes=index + 1),
            text=f"taxonomy source {index}",
            text_en=f"taxonomy translation {index}",
            text_zh_cn=f"分类翻译 {index}",
            commentary_en=f"taxonomy commentary {index}",
            commentary_zh_cn=f"分类评论 {index}",
            lang_detected="en",
        )
        PostBrand.objects.create(post=post, brand=brand)
        PostBrandClassificationState.objects.create(
            post=post,
            brand=brand,
            contract_version=CONTRACT_VERSION,
            taxonomy_version="stage1-taxonomy-v1",
            prompt_version="stage1-prompt-v2",
            model="compatibility-test",
            source_language="en",
            input_context_fingerprint=str(index) * 64,
            outcome="classified",
            sentiment_id="positive",
        )
        PostBrandSignal.objects.bulk_create(
            [
                PostBrandSignal(
                    post=post,
                    brand=brand,
                    post_type_id=key,
                    sentiment_id="positive",
                )
                for key in (OLD_TYPE, CANONICAL_TYPE)
            ]
        )
        PostBrandProductLabel.objects.bulk_create(
            [
                PostBrandProductLabel(
                    post=post, brand=brand, product_label_id=key
                )
                for key in (OLD_PRODUCT, CANONICAL_PRODUCT)
            ]
        )
        posts.append(post)
    views._clear_home_pulse_cache()
    yield brand, posts
    views._clear_home_pulse_cache()


def _filters(post_type: str, product_label: str) -> dict[str, object]:
    return {
        "post_types": [post_type],
        "product_labels": [product_label],
        "unsanctioned": "any",
        "window": 1,
    }


def _embedded_payload(response, attribute: str) -> dict[str, object]:
    body = response.content.decode("utf-8")
    match = re.search(rf"{attribute}='([^']*)'", body)
    assert match is not None
    return json.loads(html.unescape(match.group(1)))


def test_alias_and_canonical_filters_share_cache_identity():
    alias = views._normalize_home_filters(_filters(OLD_TYPE, OLD_PRODUCT))
    canonical = views._normalize_home_filters(
        _filters(CANONICAL_TYPE, CANONICAL_PRODUCT)
    )

    assert alias == canonical
    assert views._home_chart_cache_key(1, alias, "en") == (
        views._home_chart_cache_key(1, canonical, "en")
    )


def test_feed_aliases_emit_canonical_keys_and_keep_cursor_results_equivalent(
    client, compatible_taxonomy_rows
):
    alias_filters = _filters(OLD_TYPE, OLD_PRODUCT)
    canonical_filters = _filters(CANONICAL_TYPE, CANONICAL_PRODUCT)

    alias_first = client.get(
        "/feed/",
        {"filters": json.dumps(alias_filters), "window": 1, "limit": 1},
        secure=True,
    ).json()
    canonical_first = client.get(
        "/feed/",
        {"filters": json.dumps(canonical_filters), "window": 1, "limit": 1},
        secure=True,
    ).json()

    assert alias_first == canonical_first
    assert alias_first["applied_filters"] == canonical_filters
    assert alias_first["rows"][0]["post_type_keys"] == [CANONICAL_TYPE]
    assert alias_first["rows"][0]["product_label_keys"] == [CANONICAL_PRODUCT]
    assert alias_first["next_cursor"] is not None

    alias_second = client.get(
        "/feed/",
        {
            "filters": json.dumps(alias_filters),
            "window": 1,
            "limit": 1,
            "cursor": alias_first["next_cursor"],
        },
        secure=True,
    ).json()
    canonical_second = client.get(
        "/feed/",
        {
            "filters": json.dumps(canonical_filters),
            "window": 1,
            "limit": 1,
            "cursor": canonical_first["next_cursor"],
        },
        secure=True,
    ).json()
    assert alias_second == canonical_second
    assert len(alias_second["rows"]) == 1

    comma = client.get(
        "/feed/",
        {
            "post_types": OLD_TYPE,
            "product_labels": OLD_PRODUCT,
            "window": 1,
        },
        secure=True,
    ).json()
    assert comma["applied_filters"]["post_types"] == [CANONICAL_TYPE]
    assert comma["applied_filters"]["product_labels"] == [CANONICAL_PRODUCT]


def test_chart_endpoints_emit_canonical_filters_and_reuse_one_cache_entry(
    client, django_user_model, compatible_taxonomy_rows
):
    brand, _posts = compatible_taxonomy_rows
    alias_filters = _filters(OLD_TYPE, OLD_PRODUCT)
    canonical_filters = _filters(CANONICAL_TYPE, CANONICAL_PRODUCT)

    alias = client.get(
        "/chart/",
        {"filters": json.dumps(alias_filters), "window": 1, "locale": "en"},
        secure=True,
    ).json()
    canonical = client.get(
        "/chart/",
        {"filters": json.dumps(canonical_filters), "window": 1, "locale": "en"},
        secure=True,
    ).json()
    assert alias == canonical
    assert alias["applied_filters"] == canonical_filters
    assert alias["totals"][brand.nickname] == 2
    assert len(views._HOME_CHART_CACHE) == 1

    chart_html = client.get(
        "/chart.html",
        {"post_types": OLD_TYPE, "product_labels": OLD_PRODUCT, "window": 1},
        secure=True,
    )
    embedded = _embedded_payload(chart_html, "data-home")
    assert embedded["applied_filters"]["post_types"] == [CANONICAL_TYPE]
    assert embedded["applied_filters"]["product_labels"] == [CANONICAL_PRODUCT]

    user = django_user_model.objects.create_user(
        username="taxonomy-brand-chart", password="test-only"
    )
    client.force_login(user)
    for route, attribute in (
        (f"/brand-chart/{brand.nickname}/", None),
        (f"/brand-chart/{brand.nickname}.html", "data-brand-chart"),
    ):
        response = client.get(
            route,
            {"filters": json.dumps(alias_filters), "window": 1},
            secure=True,
        )
        assert response.status_code == 200
        payload = response.json() if attribute is None else _embedded_payload(
            response, attribute
        )
        assert payload["applied_filters"] == canonical_filters


def test_static_icon_and_order_contract_uses_only_canonical_renamed_keys():
    root = Path(__file__).resolve().parents[1]
    icons = (root / "monitor/static/pw-icons.js").read_text(encoding="utf-8")
    feed = (root / "monitor/static/pw-feed.js").read_text(encoding="utf-8")
    for key in (
        "releases_updates",
        "results_evaluations",
        "questions_requests",
        "events_opportunities",
        "ideas_requests",
    ):
        assert key in icons
        assert key in feed
    for alias in (
        "buzz_releases",
        "performance_comparisons",
        "feedback_questions",
        "event_announcement",
        "product_request",
    ):
        assert alias not in icons
        assert alias not in feed
