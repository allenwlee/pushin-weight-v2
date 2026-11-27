import json
from hashlib import sha256
from urllib.parse import urlencode

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.models import (
    PostBrandClassificationState,
    PostSynthesisArtifact,
    PostSynthesisDemand,
)
from tests.general_helpers import NOW, classified_post, saved_commentary

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_exact_classification_deduplicates_brands_and_rejects_old_or_failed_state():
    from monitor.general_readers import general_feed

    post = classified_post("1101")
    classified_post("1101", brand="mistral")
    classified_post("1102", taxonomy="stage1-taxonomy-v2")
    failed = classified_post("1103")
    PostBrandClassificationState.objects.filter(post=failed).update(
        outcome="context_missing"
    )
    classified_post(
        "1104", category="events_opportunities", taxonomy="stage1-taxonomy-v2"
    )
    result = general_feed("jobs", as_of=NOW)
    assert [item["id"] for item in result["items"]] == [post.pk]
    assert {brand["id"] for brand in result["items"][0]["brands"]} == {
        "qwen",
        "mistral",
    }


def test_normalized_commentary_and_language_fallback_are_explicit_without_writes():
    from monitor.general_readers import general_feed

    post = classified_post("1201")
    revision = saved_commentary(post)
    classified_post("1202", age=2)
    result = general_feed("jobs", locale="ja", as_of=NOW)
    normalized, legacy = result["items"]
    assert normalized["commentary"]["text"] == "保存された解説"
    assert normalized["commentary"]["artifact_id"] == revision.pk
    assert not normalized["commentary"]["fallback"]
    assert legacy["commentary"]["locale"] == "en"
    assert legacy["commentary"]["fallback"]
    assert legacy["commentary"]["source"] == "legacy"
    assert PostSynthesisDemand.objects.count() == 0
    assert "input_context_fingerprint" not in json.dumps(result)
    assert "provider_role" not in json.dumps(result)


def test_bounded_signed_continuation_preserves_order_and_rejects_filter_changes():
    from monitor.general_readers import general_feed

    for index in range(4):
        classified_post(str(1300 + index), age=index + 1)
    first = general_feed("jobs", limit=2, as_of=NOW)
    second = general_feed("jobs", limit=2, cursor=first["next_cursor"], as_of=NOW)
    assert [item["id"] for item in first["items"] + second["items"]] == [
        "1300",
        "1301",
        "1302",
        "1303",
    ]
    assert not second["next_cursor"]
    with pytest.raises(ValueError):
        general_feed("calendar", cursor=first["next_cursor"], as_of=NOW)
    with pytest.raises(ValueError):
        general_feed("jobs", cursor="altered", as_of=NOW)
    with pytest.raises(ValueError):
        general_feed("jobs", limit=51, as_of=NOW)


def test_reader_query_count_does_not_grow_per_card():
    from monitor.general_readers import general_feed

    post = classified_post("1400")
    saved_commentary(post)
    with CaptureQueriesContext(connection) as one:
        general_feed("jobs", as_of=NOW)
    for index in range(1, 20):
        saved_commentary(classified_post(str(1400 + index), age=index + 1))
    with CaptureQueriesContext(connection) as many:
        page = general_feed("jobs", as_of=NOW)
    assert len(page["items"]) == 20
    assert len(many) == len(one)


def test_large_selection_continuation_fits_request_line_and_keeps_filter_binding():
    from monitor.general_readers import general_feed

    for index in range(3):
        classified_post(f"large-selection-{index}", age=index + 1)
    brands = ["qwen", *[sha256(str(i).encode()).hexdigest()[:28] for i in range(1734)]]
    first = general_feed("jobs", brands=brands, limit=1, as_of=NOW)
    url = "/general/feed/?" + urlencode({"section": "jobs", "cursor": first["next_cursor"]})
    assert len(url.encode()) < 2000
    second = general_feed("jobs", brands=list(reversed(brands)), limit=1, cursor=first["next_cursor"])
    assert [item["id"] for item in second["items"]] == ["large-selection-1"]
    assert second["as_of"] == first["as_of"]
    for different in (brands[:-1], None, []):
        with pytest.raises(ValueError, match="continuation"):
            general_feed("jobs", brands=different, cursor=first["next_cursor"])


def test_legacy_continuation_still_validates_exact_filters_and_clock():
    from django.core import signing

    from monitor.general_readers import CURSOR_SALT, general_feed

    first = classified_post("legacy-0", age=1)
    classified_post("legacy-1", age=2)
    cursor = signing.dumps({
        "filters": {"section": "jobs", "locale": "en", "brands": ["qwen"], "version": 1},
        "as_of": NOW.isoformat(), "last": [-first.fetched_at.timestamp(), first.pk],
    }, salt=CURSOR_SALT, compress=True)
    page = general_feed("jobs", brands=["qwen"], cursor=cursor)
    assert [item["id"] for item in page["items"]] == ["legacy-1"]
    assert page["as_of"] == NOW.isoformat()
    with pytest.raises(ValueError, match="continuation"):
        general_feed("jobs", brands=["mistral"], cursor=cursor)


def test_withdrawn_current_commentary_is_not_exposed_by_the_feed():
    from monitor.general_readers import general_feed

    post = classified_post("1501")
    revision = saved_commentary(post)
    PostSynthesisArtifact.objects.filter(pk=revision.pk).update(
        review_state="withdrawn"
    )
    item = general_feed("jobs", as_of=NOW)["items"][0]
    assert item["commentary"]["text"] == ""
    assert item["commentary"]["artifact_id"] is None
