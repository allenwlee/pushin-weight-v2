"""Bounded, relevance-led recall from stored posts after a story is selected."""

import re
from collections import Counter
from datetime import datetime, timedelta

from django.db import OperationalError, connection, transaction
from django.db.models import Case, F, IntegerField, Q, Value, When, Window
from django.db.models.functions import RowNumber, TruncMonth

from core.models import Brand, Company, Post

from .evidence import packet_bytes, post_evidence

# Distinctive names seed recall. Generic sentence openings and category words
# cannot send a six-month search off in an unrelated direction.
STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "but",
        "by",
        "can",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "is",
        "it",
        "its",
        "just",
        "new",
        "no",
        "not",
        "of",
        "on",
        "or",
        "our",
        "out",
        "post",
        "posts",
        "says",
        "said",
        "that",
        "the",
        "their",
        "then",
        "there",
        "these",
        "they",
        "this",
        "to",
        "today",
        "was",
        "we",
        "were",
        "what",
        "when",
        "which",
        "who",
        "will",
        "with",
        "you",
        "your",
        "ai",
        "api",
        "model",
        "models",
        "released",
        "release",
        "announced",
        "announcement",
        "available",
        "source",
        "report",
        "reports",
        "open",
        "weights",
        "breaking",
        "update",
        "now",
        "via",
        "using",
        "more",
        "all",
        "about",
        "after",
        "before",
        "first",
        "last",
        "one",
        "two",
        "three",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "localai",
        "meet",
        "working",
        "forged",
        "state-of-the-art",
    ]
)
PHRASE = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Z][a-z]+|[A-Z]{2,})(?:[ -](?:[A-Z][a-z]+|[A-Z]{2,})){1,3}(?:[ -][0-9]+(?:\.[0-9]+)*)?"
)
TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*")


def source_text(source):
    return re.sub(
        r"https?://\S+",
        "",
        " ".join(source.get(k, "") or "" for k in ("original_text", "stored_quote")),
    )


PROMOTION = re.compile(
    r"(?:\b(?:CA|contract address|ticker)\s*[:：=]|solana:)[ \t]*[A-Za-z0-9:]{20,}",
    re.IGNORECASE,
)


def phrases(text):
    for match in PHRASE.finditer(text):
        start = match.start()
        parts = list(re.finditer(r"[^ -]+", match.group()))
        while parts and parts[0].group().casefold() in STOP_WORDS:
            parts.pop(0)
        while parts and parts[-1].group().casefold() in STOP_WORDS:
            parts.pop()
        if len(parts) >= 2:
            yield start + parts[0].start(), start + parts[-1].end()


def words(source):
    return {
        t.casefold()
        for t in TOKEN.findall(source_text(source))
        if len(t) >= 3 and t.casefold() not in STOP_WORDS
    }


def names(sources, brands=()):
    counts = Counter()
    excluded = STOP_WORDS | {b.casefold() for b in brands}
    for source in sources:
        text = source_text(source)
        counts.update(
            {
                t.casefold()
                for t in TOKEN.findall(text)
                if len(t) >= 4
                and t.casefold() not in excluded
                and (any(c.isupper() for c in t) or any(c.isdigit() for c in t))
            }
        )
        counts.update(
            {
                text[start:end].casefold()
                for start, end in phrases(text)
                if any(
                    t.casefold() not in excluded for t in TOKEN.findall(text[start:end])
                )
            }
        )
    return counts


def term_filter(term):
    # PostgreSQL word boundaries are Unicode-aware; ASCII boundaries also find
    # Latin product/person names next to Chinese or Japanese prose.
    pattern = r"(^|[^A-Za-z0-9])" + re.escape(term) + r"([^A-Za-z0-9]|$)"
    return Q(text__iregex=pattern) | Q(quoted_text__iregex=pattern)


def retrieve(cutoff, terms, cfg, *, historical=False):
    if not terms:
        return [], False
    relevance = sum(
        (
            Case(
                When(
                    Q(
                        text__iregex=r"(^|[^A-Za-z0-9])"
                        + re.escape(t)
                        + r"([^A-Za-z0-9]|$)"
                    ),
                    then=Value(4),
                ),
                When(term_filter(t), then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
            for t in terms
        ),
        Value(0),
    )
    query = Post.objects.filter(created_at__lte=cutoff, fetched_at__lte=cutoff)
    if historical:
        query = query.filter(
            created_at__gte=cutoff - timedelta(days=cfg.context_history_days),
        )
    else:
        query = query.filter(created_at__gte=cutoff - timedelta(days=7))
    matches = Q()
    for term in terms:
        matches |= Q(text__icontains=term) | Q(quoted_text__icontains=term)
    query = query.filter(matches).annotate(relevance=relevance)
    if historical:
        # Sample each month so a busy recent week cannot hide an older meme.
        query = query.annotate(
            month_rank=Window(
                expression=RowNumber(),
                partition_by=[TruncMonth("created_at")],
                order_by=[
                    F("relevance").desc(),
                    F("created_at").desc(),
                    F("tweet_id").asc(),
                ],
            )
        ).filter(month_rank__lte=8)
    query = query.order_by("-relevance", "-created_at", "tweet_id")[:80]
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SHOW statement_timeout")
                previous = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT set_config('statement_timeout', %s, true)",
                    [f"{cfg.context_query_timeout_ms}ms"],
                )
            posts = list(query.prefetch_related("brands"))
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('statement_timeout', %s, true)", [previous]
                )
        return [post_evidence(p) for p in posts], False
    except OperationalError as exc:
        # Only query cancellation is optional recall failure. Connection errors
        # and other DB defects must retain their real failure semantics.
        if getattr(exc.__cause__, "sqlstate", None) != "57014":
            raise
        return [], True


def story_packet(event, packet, cfg):
    """Return anchors plus relevant background, without changing editor decisions."""
    anchors = list(
        {
            p["id"]: p
            for p in packet["posts"] + packet.get("context", [])
            if p["id"] in event.post_ids
        }.values()
    )
    cutoff = datetime.fromisoformat(packet["cutoff"])
    missing = set(event.post_ids) - {p["id"] for p in anchors}
    if missing:
        anchors.extend(
            post_evidence(p)
            for p in Post.objects.filter(
                pk__in=missing, created_at__lte=cutoff, fetched_at__lte=cutoff
            )
            .prefetch_related("brands")
            .order_by("tweet_id")
        )
    anchors.sort(key=lambda p: event.post_ids.index(p["id"]))
    if {p["id"] for p in anchors} != set(event.post_ids):
        raise ValueError("missing selected source")
    if packet_bytes(anchors) > cfg.max_story_bytes:
        raise ValueError("selected sources exceed story evidence cap")
    brand_names = set(event.brand_keys)
    for model in (Brand, Company):
        for row in model.objects.values_list(
            "nickname", "display_name", "display_name_en"
        ):
            for value in row:
                brand_names.update(t.casefold() for t in TOKEN.findall(value or ""))
    counts = names(anchors, brand_names)
    terms = sorted(counts, key=lambda t: (-counts[t], -len(t), t))[:8]
    anchor_words = set().union(*(words(p) for p in anchors))
    brands = set(event.brand_keys)

    def rank(source, search_terms):
        text = source_text(source).casefold()
        overlap = {
            t
            for t in search_terms
            if re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", text)
        }
        original = source.get("original_text", "").casefold()
        original_overlap = {
            t
            for t in overlap
            if re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", original)
        }
        shared = words(source) & anchor_words
        # A brand match alone, or an ambiguous name alone, is not story evidence.
        relevant = (
            any(" " in t for t in overlap)
            or len(overlap) >= 2
            or (bool(overlap) and len(shared - set(search_terms)) >= 2)
        )
        if PROMOTION.search(source.get("original_text", "")) and not any(
            PROMOTION.search(p.get("original_text", "")) for p in anchors
        ):
            relevant = False
        for term in terms:
            version = re.fullmatch(r"(.+) ([0-9]+(?:\.[0-9]+)*)", term)
            if version and term not in overlap:
                other_version = re.search(
                    re.escape(version[1]) + r" ([0-9]+(?:\.[0-9]+)*)", text
                )
                if (
                    other_version
                    and other_version[1] != version[2]
                    and not any(" " in t for t in overlap)
                ):
                    relevant = False
        return (
            int(relevant),
            len(original_overlap),
            len(overlap),
            len(shared),
            bool(brands & set(source.get("brand_keys", []))),
            source.get("created_at", ""),
            source["id"],
        )

    recent, recent_timeout = (
        retrieve(cutoff, terms, cfg) if cfg.max_story_context_posts else ([], False)
    )
    pool = {p["id"]: p for p in recent if p["id"] not in event.post_ids}
    relevant = [p for p in pool.values() if rank(p, terms)[0]]
    # One expansion round. Preserve the exact bridge passage that licenses
    # each new phrase; a nearby generic brand mention cannot create an alias.
    expansion_sources = [p for p in relevant if len(names([p], brand_names)) <= 16]
    repeated = names(anchors + expansion_sources, brand_names)
    introduced = []
    for source in expansion_sources:
        for field in ("original_text", "stored_quote"):
            text = source.get(field, "") or ""
            for start, end in phrases(text):
                term = text[start:end].casefold()
                if term in terms or not any(
                    t.casefold() not in STOP_WORDS | brand_names
                    for t in TOKEN.findall(term)
                ):
                    continue
                nearby = text[max(0, start - 160) : end + 160].casefold()
                links = [
                    t
                    for t in terms
                    if re.search(
                        r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", nearby
                    )
                ]
                if not links or not re.search(
                    r"\b(?:aka|called|named|nickname|alias|joke|meme|renamed|inspired|revives|revived|backstory|known as)\b|梗|别名|通称",
                    nearby,
                ):
                    continue
                introduced.append(
                    {
                        "linked_terms": links,
                        "term": term,
                        "post_id": source["id"],
                        "source_field": field,
                        "start": start,
                        "end": end,
                        "text": text[start:end],
                    }
                )
    additions = list(dict.fromkeys(p["term"] for p in introduced))[:2]
    if len(additions) < 2:
        additions += sorted(
            (
                t
                for t, n in repeated.items()
                if n >= 2 and t not in terms and t not in additions
            ),
            key=lambda t: (-repeated[t], -len(t), t),
        )[: 2 - len(additions)]
    history_terms = list(dict.fromkeys(terms + additions))[:10]
    older, history_timeout = (
        retrieve(cutoff, history_terms, cfg, historical=True)
        if cfg.max_story_context_posts
        else ([], False)
    )
    expanded = [
        p for p in older if p["id"] not in event.post_ids and rank(p, history_terms)[0]
    ]
    boundary = (cutoff - timedelta(days=7)).isoformat()
    historical = [p for p in expanded if p.get("created_at", "") < boundary]
    relevant = list(
        {
            p["id"]: p
            for p in relevant
            + [p for p in expanded if p.get("created_at", "") >= boundary]
        }.values()
    )
    linked_ids = {
        str(p.get(k))
        for p in anchors
        for k in ("parent_post_id", "quoted_post_id")
        if p.get(k)
    } - set(event.post_ids)
    linked = (
        [
            post_evidence(p)
            for p in Post.objects.filter(
                pk__in=linked_ids,
                created_at__lte=cutoff,
                fetched_at__lte=cutoff,
                created_at__gte=cutoff - timedelta(days=cfg.context_history_days),
            )
            .prefetch_related("brands")
            .order_by("tweet_id")[:8]
        ]
        if cfg.max_story_context_posts
        else []
    )
    historical.sort(key=lambda p: rank(p, history_terms), reverse=True)
    relevant.sort(key=lambda p: rank(p, history_terms), reverse=True)
    # Reserve up to a third of the slots for history; fill spare slots by relevance.
    reserved = historical[: cfg.max_story_context_posts // 3]
    candidates = linked + reserved + relevant + historical[len(reserved) :]
    selected = []
    seen = set(event.post_ids)
    seen_texts = {source_text(p).strip().casefold() for p in anchors}
    for source in candidates:
        text_key = source_text(source).strip().casefold()
        if (
            source["id"] in seen
            or text_key in seen_texts
            or len(selected) >= cfg.max_story_context_posts
        ):
            continue
        if packet_bytes(anchors + selected + [source]) > cfg.max_story_bytes:
            continue
        selected.append(source)
        seen.add(source["id"])
        seen_texts.add(text_key)
    return {
        **{k: v for k, v in packet.items() if k != "story_packets"},
        "posts": anchors,
        "context": selected,
        "story_context": {
            "anchor_ids": event.post_ids,
            "terms": terms,
            "history_terms": history_terms,
            "alias_bridges": [p for p in introduced if p["term"] in additions],
            "linked_ids": [p["id"] for p in linked],
            "history_days": cfg.context_history_days,
            "recent_candidates": len(recent),
            "history_candidates": len(older),
            "included_ids": [p["id"] for p in selected],
            "eligible_context": len({p["id"] for p in candidates}),
            "omitted_context": len({p["id"] for p in candidates}) - len(selected),
            "candidate_limit_per_query": 80,
            "max_context_posts": cfg.max_story_context_posts,
            "expansion_rounds": 1,
            "seed_scope": "Latin-script distinctive names and phrases",
            "evidence_bytes": packet_bytes(anchors + selected),
            "byte_limit": cfg.max_story_bytes,
            "query_timeout": recent_timeout or history_timeout,
        },
    }
