"""Deterministic source records for the General reader and browser tests."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256

from core.classification_contract import (
    CONTRACT_VERSION,
    PROMPT_VERSION,
    TAXONOMY_VERSION,
)
from core.models import (
    Brand,
    Post,
    PostBrandClassificationState,
    PostBrandSignal,
    PostSynthesisArtifact,
    PostSynthesisText,
    PostTypeKey,
    SentimentKey,
)

NOW = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)


def classified_post(
    key, category="job_listings", *, brand="qwen", age=1, taxonomy=TAXONOMY_VERSION
):
    owner, _ = Brand.objects.get_or_create(
        nickname=brand, defaults={"display_name": brand.title()}
    )
    post_type, _ = PostTypeKey.objects.get_or_create(key=category)
    sentiment, _ = SentimentKey.objects.get_or_create(key="neutral")
    post, _ = Post.objects.get_or_create(
        tweet_id=str(key),
        defaults={
            "text": f"Original source {key}",
            "commentary_en": f"Saved commentary {key}",
            "author_handle": "source_author",
            "tweet_url": f"https://x.com/source_author/status/{key}",
        },
    )
    Post.objects.filter(pk=post.pk).update(
        fetched_at=NOW - timedelta(hours=age), created_at=NOW - timedelta(days=10)
    )
    post.refresh_from_db()
    PostBrandSignal.objects.get_or_create(
        post=post, brand=owner, post_type=post_type, defaults={"sentiment": sentiment}
    )
    PostBrandClassificationState.objects.update_or_create(
        post=post,
        brand=owner,
        defaults={
            "contract_version": CONTRACT_VERSION,
            "taxonomy_version": taxonomy,
            "prompt_version": PROMPT_VERSION,
            "model": "fixture",
            "input_context_fingerprint": sha256(str(key).encode()).hexdigest(),
            "outcome": "classified",
        },
    )
    return post


def saved_commentary(post, *, current=True, revision="one", texts=None):
    artifact = PostSynthesisArtifact.objects.create(
        post=post,
        input_context_fingerprint=sha256(revision.encode()).hexdigest(),
        prompt_version="fixture-v1",
        model="fixture",
        provider_role="fixture",
        state="succeeded",
        is_current=current,
        started_at=NOW - timedelta(hours=2),
        completed_at=NOW - timedelta(hours=1),
    )
    values = texts if texts is not None else {
        "en": "Normalized commentary",
        "zh-cn": "已保存的评论",
        "ja": "保存された解説",
    }
    for locale, text in values.items():
        PostSynthesisText.objects.create(artifact=artifact, locale=locale, text=text)
    return artifact


def complete_general_feed(section, *, locale="en", brands=None, limit=20, cursor=None, as_of=NOW):
    """Small-fixture oracle: qualify all Posts, hydrate all facts, then sort.

    Deliberately independent of candidate windows/cohorts and SQL pagination.
    Shared display helpers keep this focused on membership and page selection.
    """
    from django.core import signing

    from monitor import general_readers as readers

    brands = sorted(set(brands)) if brands is not None else None
    filters = {"section": section, "locale": locale, "brands": brands, "version": 1}
    last = None
    if cursor:
        payload = signing.loads(cursor, salt=readers.CURSOR_SALT, max_age=86400)
        assert payload["filters"] == filters
        as_of = datetime.fromisoformat(payload["as_of"])
        last = payload["last"]
    signals = readers.current_signals().filter(post_type_id=readers.SECTIONS[section])
    if brands is not None:
        signals = signals.filter(brand_id__in=brands)
    posts = list(readers.public_posts().filter(pk__in=signals.values("post_id"), fetched_at__lte=as_of))
    facts = readers.temporal_facts([p.pk for p in posts], section, as_of=as_of) if section in {"calendar", "free"} else {}
    timing, ordered = {}, []
    for post in posts:
        prefix = []
        if post.pk in facts:
            timing[post.pk] = readers.timing_anchor(facts[post.pk])
            if timing[post.pk] is None:
                continue
            fact = next((f for f in facts[post.pk] if f["id"] == timing[post.pk]["fact_id"]), None)
            prefix = list(readers._fact_order(fact)[:2]) if fact else [2, 0]
        key = [*prefix, -post.fetched_at.timestamp(), str(post.pk)]
        if last is None or key > last:
            ordered.append((key, post))
    ordered.sort(key=lambda item: item[0])
    page = ordered[:limit]
    documents = readers.post_documents([post for _, post in page], locale=locale, section=section)
    if section in {"jobs", "moving"}:
        facts = readers.jobs_people_facts(list(documents), section, as_of=as_of, locale=locale)
    for _, post in page:
        document = documents[post.pk]
        document["facts"] = facts.get(post.pk, [])
        document["timing"] = timing.get(post.pk)
        document["age_seconds"] = max(0, (as_of - post.fetched_at).total_seconds())
        document["recent"] = section == "jobs" and document["age_seconds"] < 86400
    continuation = signing.dumps({"filters": filters, "as_of": as_of.isoformat(), "last": page[-1][0]}, salt=readers.CURSOR_SALT, compress=True) if len(ordered) > limit else None
    return {"section": section, "locale": locale, "as_of": as_of.isoformat(), "items": [documents[post.pk] for _, post in page], "next_cursor": continuation}
