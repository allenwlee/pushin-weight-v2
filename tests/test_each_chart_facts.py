"""Saved and live Each facts must match the frozen per-post reader."""

from datetime import UTC, datetime, timedelta

import pytest
from django.db import connection

from core.classification_contract import CONTRACT_VERSION, TAXONOMY_VERSION
from core.models import (
    Brand,
    MaterializationState,
    Post,
    PostBrand,
    PostBrandClassificationState,
    PostBrandSignal,
    PostTypeKey,
    SentimentKey,
)
from monitor.views import _each_chart_payload, _each_tab_entries
from tests.each_reference import reference_each_chart_payload

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]
NOW = datetime(2026, 11, 19, 12, tzinfo=UTC)
DATASET = "each.brand_post_facts.v1"


@pytest.fixture
def fact_brand():
    brand = Brand.objects.create(
        nickname="each-facts-oracle", display_name="Facts", accent_color="#0089f4"
    )
    for key in ("positive", "negative", "neutral", "mixed"):
        SentimentKey.objects.get_or_create(key=key)
    for key in (
        "releases_updates",
        "performance_comparisons",
        "results_evaluations",
        "events_opportunities",
    ):
        PostTypeKey.objects.get_or_create(key=key)
    for i, age in enumerate(
        (
            timedelta(minutes=2),
            timedelta(days=1),
            timedelta(days=2),
            timedelta(days=5),
            timedelta(days=20),
            timedelta(days=200),
        )
    ):
        post = Post.objects.create(
            tweet_id=f"each-facts-{i}",
            created_at=NOW - age,
            lang="en",
            lang_detected=("zh-Hans", None, "xx", "EN", "ja", "")[i],
        )
        PostBrand.objects.create(post=post, brand=brand)
        for j, key in enumerate(
            ("performance_comparisons", "results_evaluations")
            if i % 2
            else ("releases_updates",)
        ):
            PostBrandSignal.objects.create(
                post=post,
                brand=brand,
                post_type_id=key,
                sentiment_id="positive" if j == 0 else "negative",
            )
        if i != 2:
            PostBrandClassificationState.objects.create(
                post=post,
                brand=brand,
                contract_version=CONTRACT_VERSION if i != 3 else "unknown",
                taxonomy_version=TAXONOMY_VERSION,
                prompt_version="oracle",
                model="fixture",
                input_context_fingerprint="a" * 64,
                outcome="classified" if i != 4 else "context_missing",
                sentiment_id="mixed" if i != 5 else None,
            )
    from core.models import (
        AudienceTopicConcept,
        AudienceTopicScheme,
        GeopoliticalModeKey,
        PostBrandAudienceTopic,
        PostBrandGeopoliticalMode,
        PostBrandProductLabel,
        PostUntrackedBrandPromotion,
        ProductLabelKey,
    )

    posts = list(
        Post.objects.filter(tweet_id__startswith="each-facts-").order_by("tweet_id")
    )
    for key in ("product_request", "ideas_requests", "bug", "unknown-fact-label"):
        ProductLabelKey.objects.get_or_create(key=key)
    for key in ("product_request", "ideas_requests", "unknown-fact-label"):
        PostBrandProductLabel.objects.create(
            post=posts[0], brand=brand, product_label_id=key
        )
    # A missing current state must not inherit otherwise valid label edges.
    PostBrandProductLabel.objects.create(
        post=posts[2], brand=brand, product_label_id="bug"
    )
    scheme, _ = AudienceTopicScheme.objects.get_or_create(
        key="ai_audience_topics/v1", defaults={"manifest_hash": "a" * 64}
    )
    scheme.revision = 2
    scheme.save(update_fields=["revision"])
    for i, key in enumerate(("local_inference", "agents_tools")):
        concept, _ = AudienceTopicConcept.objects.get_or_create(scheme=scheme, key=key)
        PostBrandAudienceTopic.objects.create(
            post=posts[i],
            brand=brand,
            concept=concept,
            scheme=scheme,
            scheme_revision=2 if i == 0 else 1,
        )
    for i, version in enumerate(
        ("stage1-taxonomy-v3", "stage1-taxonomy-v4", "u18a-experimental")
    ):
        GeopoliticalModeKey.objects.get_or_create(key="reporting")
        PostBrandGeopoliticalMode.objects.create(
            post=posts[i],
            brand=brand,
            geopolitical_mode_id="reporting",
            taxonomy_version=version,
        )
    for i, raw in enumerate(
        (["general", "unknown-fact-promotion"], {"general": True}, ["spam"])
    ):
        PostUntrackedBrandPromotion.objects.create(post=posts[i], promotion_keys=raw)
    MaterializationState.objects.get_or_create(pk=DATASET)
    return brand


def populate():
    cutoff = NOW.replace(hour=0) - timedelta(days=1)
    with connection.cursor() as c:
        c.execute("REFRESH MATERIALIZED VIEW each_brand_post_facts")
    MaterializationState.objects.filter(pk=DATASET).update(
        cutoff=cutoff,
        refreshed_at=NOW,
        published_generation=0,
        source_generation=0,
        dirty_since=None,
    )


@pytest.mark.parametrize("publication", ["unpopulated", "saved", "dirty"])
@pytest.mark.parametrize(
    "zone", ["UTC", "Asia/Tokyo", "America/Los_Angeles", "Asia/Kolkata"]
)
def test_all_tabs_windows_and_timezones_equal_reference(fact_brand, publication, zone):
    if publication != "unpopulated":
        populate()
    if publication == "dirty":
        Post.objects.filter(pk="each-facts-5").update(lang="ja", lang_detected=None)
    for tab in _each_tab_entries("en"):
        for days in (1, 3, 7, 30, 365):
            options = {"now": NOW, "bucket_timezone": zone, "_rank": False}
            assert _each_chart_payload(
                fact_brand.pk, tab, days, "en", **options
            ) == reference_each_chart_payload(fact_brand.pk, tab, days, "en", **options)


def test_grouped_reader_count_does_not_scale_with_posts(fact_brand):
    from django.test.utils import CaptureQueriesContext

    from monitor.each_chart_facts import read_each_fact_groups

    args = (
        fact_brand.pk,
        "sentiment",
        NOW - timedelta(days=365),
        NOW,
        "day",
        "UTC",
        NOW,
    )
    with CaptureQueriesContext(connection) as queries:
        read_each_fact_groups(*args)
    reads = [
        q
        for q in queries
        if "FROM materialization_state WHERE dataset_key=" in q["sql"]
        or "WITH facts AS" in q["sql"]
    ]
    assert len(reads) == 2


def test_role_uses_account_uuid(fact_brand):
    from core.models import Account, BrandAccount, DataSource, Role

    DataSource.objects.get_or_create(
        pk="x", defaults={"name": "X", "source_type": "social"}
    )
    Role.objects.get_or_create(key="official")
    account = Account.objects.create(data_source_id="x", author_id="native-oracle-role")
    BrandAccount.objects.create(brand=fact_brand, account=account, role_id="official")
    Post.objects.filter(pk="each-facts-0").update(author=account)
    result = _each_chart_payload(fact_brand.pk, "role", 7, "en", now=NOW, _rank=False)
    assert sum(result["series"]["official"]) == 1


def test_historical_concept_rename_resolves_current_key_without_invalidation(
    fact_brand,
):
    from core.models import AudienceTopicConcept, PostBrandAudienceTopic

    concept = AudienceTopicConcept.objects.get(
        scheme_id="ai_audience_topics/v1", key="local_inference"
    )
    PostBrandAudienceTopic.objects.create(
        post_id="each-facts-5",
        brand=fact_brand,
        concept=concept,
        scheme_id="ai_audience_topics/v1",
        scheme_revision=2,
    )
    populate()
    generation = MaterializationState.objects.get(pk=DATASET).source_generation
    before = _each_chart_payload(
        fact_brand.pk, "audience_topics", 365, "en", now=NOW, _rank=False
    )
    AudienceTopicConcept.objects.filter(pk=concept.pk).update(
        key="unknown-renamed-concept"
    )
    after = _each_chart_payload(
        fact_brand.pk, "audience_topics", 365, "en", now=NOW, _rank=False
    )
    reference = reference_each_chart_payload(
        fact_brand.pk, "audience_topics", 365, "en", now=NOW, _rank=False
    )
    assert after == reference
    assert sum(after["series"]["local_inference"]) < sum(
        before["series"]["local_inference"]
    )
    assert MaterializationState.objects.get(pk=DATASET).source_generation == generation


@pytest.mark.parametrize("update", ["brand", "sentiment"])
def test_saved_binary_state_change_invalidates_exact_ownership(fact_brand, update):
    populate()
    state = PostBrandClassificationState.objects.get(
        post_id="each-facts-4", brand=fact_brand
    )
    if update == "brand":
        PostBrandClassificationState.objects.filter(pk=state.pk).update(
            brand_id=fact_brand.pk.upper()
        )
    else:
        PostBrandClassificationState.objects.filter(pk=state.pk).update(
            sentiment_id="POSITIVE"
        )
    assert MaterializationState.objects.get(pk=DATASET).source_generation > 0
    for brand in (fact_brand.pk, fact_brand.pk.upper()):
        for tab in ("sentiment", "post_types"):
            arguments = {"now": NOW, "_rank": False}
            assert _each_chart_payload(
                brand, tab, 365, "en", **arguments
            ) == reference_each_chart_payload(brand, tab, 365, "en", **arguments)


def test_absent_saved_relation_uses_live_facts(fact_brand):
    populate()
    with connection.cursor() as c:
        c.execute(
            "ALTER MATERIALIZED VIEW each_brand_post_facts RENAME TO each_brand_post_facts_unavailable"
        )
    try:
        result = _each_chart_payload(
            fact_brand.pk, "sentiment", 365, "en", now=NOW, _rank=False
        )
        assert result == reference_each_chart_payload(
            fact_brand.pk, "sentiment", 365, "en", now=NOW, _rank=False
        )
    finally:
        with connection.cursor() as c:
            c.execute(
                "ALTER MATERIALIZED VIEW each_brand_post_facts_unavailable RENAME TO each_brand_post_facts"
            )


@pytest.mark.parametrize(('detected', 'source'), [
    (None, '\tja\t'), (None, '\nja\n'), (None, ' JA '),
    ('  ', 'en'), ('\t', 'en'), ('', 'en'), ('\tja\t', 'en'),
])
def test_language_preserves_exact_sql_empty_and_trim_rules(fact_brand, detected, source):
    Post.objects.filter(tweet_id='each-facts-0').update(lang_detected=detected, lang=source)
    actual = _each_chart_payload(fact_brand.pk, 'lang', 7, 'en', now=NOW, _rank=False)
    expected = reference_each_chart_payload(fact_brand.pk, 'lang', 7, 'en', now=NOW, _rank=False)
    assert actual == expected


@pytest.fixture
def positive_fact_cohort(fact_brand):
    """Give both publication halves independently observable positive categories."""
    from core.models import (
        Account,
        AudienceTopicConcept,
        AudienceTopicScheme,
        BrandAccount,
        DataSource,
        PostBrandAudienceTopic,
        PostBrandProductLabel,
        PostUntrackedBrandPromotion,
        ProductLabelKey,
        Role,
    )

    DataSource.objects.get_or_create(
        pk="x", defaults={"name": "X", "source_type": "social"}
    )
    DataSource.objects.get_or_create(
        pk="each-facts-nonx", defaults={"name": "Other", "source_type": "social"}
    )
    accounts = {}
    for role in ("official", "staff"):
        Role.objects.get_or_create(key=role)
        account = Account.objects.create(
            data_source_id="x", author_id=f"native-positive-{role}"
        )
        assert str(account.pk) != account.author_id
        accounts[role] = account
        BrandAccount.objects.create(brand=fact_brand, account=account, role_id=role)
    for key in ("bug", "complaint", "product_request", "ideas_requests"):
        ProductLabelKey.objects.get_or_create(key=key)
    scheme = AudienceTopicScheme.objects.get(pk="ai_audience_topics/v1")
    concept = AudienceTopicConcept.objects.get(scheme=scheme, key="agents_tools")

    def add_positive(post_id, created_at, *, brand=fact_brand, account=None):
        post = Post.objects.create(
            tweet_id=post_id, created_at=created_at, author=account, lang_detected="en"
        )
        PostBrand.objects.create(post=post, brand=brand)
        PostBrandClassificationState.objects.create(
            post=post, brand=brand, contract_version=CONTRACT_VERSION,
            taxonomy_version=TAXONOMY_VERSION, prompt_version="positive-oracle",
            model="fixture", input_context_fingerprint="b" * 64,
            outcome="classified", sentiment_id="positive",
        )
        PostBrandProductLabel.objects.create(post=post, brand=brand, product_label_id="bug")
        PostBrandAudienceTopic.objects.create(
            post=post, brand=brand, concept=concept, scheme=scheme,
            scheme_revision=scheme.revision,
        )
        PostUntrackedBrandPromotion.objects.create(post=post, promotion_keys=["general"])
        return post

    times = {"history": NOW - timedelta(days=5), "live": NOW - timedelta(hours=2)}
    cohort = {}
    for half, created_at in times.items():
        for role, account in accounts.items():
            post = add_positive(f"positive-{half}-{role}", created_at, account=account)
            cohort[(half, role)] = post
            # Two historical aliases represent one assignment per post.
            for key in ("product_request", "ideas_requests"):
                PostBrandProductLabel.objects.create(
                    post=post, brand=fact_brand, product_label_id=key
                )

    other = Brand.objects.create(nickname="each-facts-second", display_name="Other")
    add_positive("positive-other-brand-only", NOW - timedelta(days=6), brand=other)
    shared = cohort[("history", "official")]
    PostBrand.objects.create(post=shared, brand=other)
    PostBrandClassificationState.objects.create(
        post=shared, brand=other, contract_version=CONTRACT_VERSION,
        taxonomy_version=TAXONOMY_VERSION, prompt_version="other-brand",
        model="fixture", input_context_fingerprint="c" * 64,
        outcome="classified", sentiment_id="negative",
    )
    PostBrandProductLabel.objects.create(post=shared, brand=other, product_label_id="complaint")
    # Non-X official mappings may exist, while X posts require X authors.
    # An unmapped X UUID must remain Other despite that unrelated mapping.
    nonx = Account.objects.create(
        data_source_id="each-facts-nonx", author_id=None,
        external_identifier="native-nonx", identifier_kind="provider_id",
    )
    BrandAccount.objects.create(brand=fact_brand, account=nonx, role_id="official")
    boundary_author = Account.objects.create(
        data_source_id="x", author_id="native-unmapped-boundary",
    )
    start = NOW.replace(hour=0) - timedelta(days=29)
    for label, created_at in (
        ("before-start", start - timedelta(microseconds=1)),
        ("at-start", start),
        ("at-end", NOW),
    ):
        add_positive(f"positive-{label}", created_at, account=boundary_author)
    return cohort


@pytest.mark.parametrize("publication", ["unpopulated", "saved", "dirty"])
def test_saved_and_live_positive_categories_brand_isolation_and_window_edges(
    fact_brand, positive_fact_cohort, publication,
):
    from core.models import (
        AudienceTopicConcept,
        PostBrandAudienceTopic,
        PostBrandProductLabel,
        PostUntrackedBrandPromotion,
    )

    if publication != "unpopulated":
        populate()
        # These positive rows are actually in the saved prefix, while equally
        # useful live controls remain outside it; a zero-valued parity pass fails.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT post_id FROM each_brand_post_facts WHERE brand_id=%s "
                "AND post_id LIKE 'positive-history-%%' ORDER BY post_id",
                [fact_brand.pk],
            )
            assert cursor.fetchall() == [
                ("positive-history-official",), ("positive-history-staff",),
            ]
            cursor.execute(
                "SELECT count(*) FROM each_brand_post_facts WHERE brand_id=%s "
                "AND post_id LIKE 'positive-live-%%'", [fact_brand.pk],
            )
            assert cursor.fetchone()[0] == 0
    if publication == "dirty":
        # Each update changes an asserted historical category. Live controls
        # stay positive, so broad all-live or empty-prefix comparisons cannot
        # silently stand in for a correct saved-prefix/dirty-tail combination.
        official = positive_fact_cohort[("history", "official")]
        staff = positive_fact_cohort[("history", "staff")]
        PostBrandProductLabel.objects.filter(
            post=official, brand=fact_brand, product_label_id="bug",
        ).update(product_label_id="complaint")
        local = AudienceTopicConcept.objects.get(
            scheme_id="ai_audience_topics/v1", key="local_inference",
        )
        PostBrandAudienceTopic.objects.filter(post=official, brand=fact_brand).update(
            concept=local,
        )
        PostUntrackedBrandPromotion.objects.filter(post=staff).update(promotion_keys=["spam"])
        state = MaterializationState.objects.get(pk=DATASET)
        assert state.source_generation > state.published_generation
        assert state.dirty_since == NOW - timedelta(days=5)

    charts = {}
    for tab in ("product_labels", "audience_topics", "untracked_brand_promotions", "role"):
        options = {"now": NOW, "_rank": False, "bucket_timezone": "UTC"}
        chart = _each_chart_payload(fact_brand.pk, tab, 30, "en", **options)
        assert chart == reference_each_chart_payload(fact_brand.pk, tab, 30, "en", **options)
        # Five original in-window rows + four positive controls + exactly the
        # inclusive start row. Other-brand-only, start−1µs and end are excluded.
        assert sum(chart["totals"]) == 10
        charts[tab] = chart

    def total(tab, key):
        return sum(charts[tab]["series"][key])

    dirty = publication == "dirty"
    assert total("product_labels", "bug") == (4 if dirty else 5)
    assert total("product_labels", "complaint") == (1 if dirty else 0)
    assert total("product_labels", "ideas_requests") == 5
    assert total("audience_topics", "agents_tools") == (4 if dirty else 5)
    assert total("audience_topics", "local_inference") == (2 if dirty else 1)
    assert total("untracked_brand_promotions", "general") == (5 if dirty else 6)
    assert total("untracked_brand_promotions", "spam") == (2 if dirty else 1)
    assert total("role", "official") == 2
    assert total("role", "staff") == 2
    assert total("role", "other") == 6
    for half, at in (("history", NOW - timedelta(days=5)), ("live", NOW)):
        index = charts["product_labels"]["days"].index(at.date().isoformat())
        expected = 1 if dirty and half == "history" else 2
        assert charts["product_labels"]["series"]["bug"][index] == expected
        assert charts["audience_topics"]["series"]["agents_tools"][index] == expected
    # The shared post has another brand's opposite state/complaint, and an
    # additional other-brand-only positive row; neither leaks into this brand.
    other_chart = _each_chart_payload(
        "each-facts-second", "product_labels", 30, "en", now=NOW, _rank=False,
    )
    assert sum(other_chart["totals"]) == 2
    assert sum(other_chart["series"]["bug"]) == 1
    assert sum(other_chart["series"]["complaint"]) == 1
