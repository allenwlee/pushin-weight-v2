"""Deterministic, database-first evidence gathering for ranked original trends."""

import importlib
import re
import unicodedata
from collections import Counter
from datetime import datetime, timedelta
from functools import reduce
from operator import and_, or_
from typing import Literal
from uuid import uuid4

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from core.models import (
    Brand,
    BrandAccount,
    BrandSearchTerm,
    CollectionRun,
    EditorialStory,
    OriginalContentCall,
    OriginalContentRun,
    PersonAccount,
    PersonName,
    Post,
)
from monitor.original_content import digest
from x_monitor.queries import assert_under_length_cap
from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose

from .chatter_history import (
    attach_sources,
    freeze_sources,
    locked_run,
    project_post,
    resolved_sources,
    save_query,
)
from .chatter_sources import SourceSession
from .chatter_trends import TRENDS_SCOPE, checkpoint, read_ranked_batch

RECIPE = "chatter-original-headline-terms-v1"
# Generic headline framing supplies no names or story facts.
STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "at",
        "for",
        "with",
        "by",
        "is",
        "are",
        "was",
        "were",
        "as",
        "from",
        "its",
        "it",
        "s",
        "after",
        "amid",
        "new",
        "news",
        "says",
        "said",
        "story",
        "tale",
        "draws",
        "faces",
        "loses",
        "linked",
        "updates",
        "questions",
        "shares",
        "captures",
        "founder",
        "ceo",
        "chief",
        "executive",
        "director",
        "president",
        "researcher",
        "researchers",
        "company",
        "companies",
        "offers",
        "push",
    ]
)


def term_root(value):
    """Small English inflection view; factual names/numbers remain in the originals."""
    for suffix, replacement in (
        ("ies", "y"),
        ("ation", ""),
        ("ment", ""),
        ("ing", ""),
        ("ed", ""),
        ("s", ""),
    ):
        if value.endswith(suffix) and len(value) - len(suffix) >= 4:
            return value[: -len(suffix)] + replacement
    return value


def _headline_words(member):
    return {
        term_root(word)
        for word in normalized_headline(member["trend_name"]).split()
        if word not in STOP_WORDS
    }


def episode_terms(lead, context):
    """Score original terms by within-group recurrence and cross-group specificity."""
    documents = [
        [_headline_words(member) for member in group["headlines"]] for group in context
    ]
    own = [_headline_words(member) for member in lead["headlines"]]
    frequency = Counter(word for words in own for word in words)
    return {
        word: (count / len(own))
        / (
            1
            + sum(
                any(word in row for row in group)
                for group, original in zip(documents, context, strict=True)
                if original["headlines"] != lead["headlines"]
            )
        )
        for word, count in frequency.items()
    }


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Recipe(Closed):
    schema_version: Literal[1]
    recipe: Literal["chatter-original-headline-terms-v1"]
    original_headlines: list[str] = Field(min_length=1)
    anchor_basis: Literal["saved_entity_alias", "original_prefix"]
    episode_terms: list[str]
    numeric_terms: list[str]
    # OR across member headlines; AND across groups; OR across saved aliases.
    clauses: list[list[list[str]]] = Field(min_length=1)
    start: AwareDatetime
    end_exclusive: AwareDatetime
    query: str
    query_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    query_bytes: int = Field(ge=1, le=512)


class SourceGap(Closed):
    post_id: str
    code: Literal[
        "source_clock_missing",
        "outside_window",
        "query_not_matched",
        "quote_after_cutoff",
        "quote_clock_missing",
        "quote_author_missing",
        "author_missing",
    ]


class Lead(Closed):
    rank: int = Field(ge=1, le=10)
    headline_ids: list[int]
    recipe: Recipe | None
    existing_ids: list[str] = Field(default_factory=list)
    missing_ids: list[str] = Field(default_factory=list)
    raw_ids: list[str | None] = Field(default_factory=list)
    qualified_ids: list[str] = Field(default_factory=list)
    background_ids: list[str] = Field(default_factory=list)
    source_gaps: list[SourceGap] = Field(default_factory=list)
    coverage: Literal[
        "pending", "saved_support", "query_drained", "partial", "held"
    ] = "pending"
    error_code: str = ""
    source_observed_at: str | None = None
    query_state: Literal["unqueried", "drained", "partial", "held"] = "unqueried"


class Gathering(Closed):
    schema_version: Literal[1]
    recipe: Literal["chatter-original-headline-terms-v1"]
    batch_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    cutoff: AwareDatetime
    leads: list[Lead] = Field(max_length=10)


def document(model, value):
    import json

    return model.model_validate_json(
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    ).model_dump(mode="json")


def normalized_headline(value):
    return " ".join(
        re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", value).casefold())
    )


def literal(value):
    # All operators and Boolean-looking input remain inside a literal phrase.
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _render(clauses, start, end):
    expressions = [
        "("
        + " ".join(
            "(" + " OR ".join(literal(v) for v in alternatives) + ")"
            for alternatives in clause
        )
        + ")"
        for clause in clauses
    ]
    return (
        "("
        + " OR ".join(expressions)
        + f") since_time:{int(start.timestamp())} until_time:{int(end.timestamp())}"
    )


def compile_recipe(lead, cutoff, *, context_leads=None):
    cutoff = cutoff.replace(microsecond=0)
    originals = [member["trend_name"] for member in lead["headlines"]]
    clauses = []
    aliases = list(
        BrandSearchTerm.objects.order_by("brand_id", "term").values_list(
            "brand_id", "term"
        )
    )
    for brand in Brand.objects.filter(is_sentinel=False).order_by("pk"):
        aliases.extend(
            (brand.pk, value)
            for value in (
                brand.pk,
                brand.display_name,
                brand.display_name_en,
                brand.display_name_zh_cn,
            )
            if value
        )
    for brand, handle in BrandAccount.objects.filter(
        account__data_source_id="x", account__normalized_handle__isnull=False
    ).values_list("brand_id", "account__normalized_handle"):
        aliases.append((brand, "@" + handle))
    aliases.extend(
        ("person:" + str(person), name)
        for person, name in PersonName.objects.filter(person__merged_into__isnull=True)
        .exclude(review_status="rejected")
        .values_list("person_id", "full_name")
    )
    aliases.extend(
        ("person:" + str(person), "@" + handle)
        for person, handle in PersonAccount.objects.filter(
            person__merged_into__isnull=True,
            account__data_source_id="x",
            account__normalized_handle__isnull=False,
        )
        .exclude(resolution_status="rejected")
        .values_list("person_id", "account__normalized_handle")
    )
    registry = sorted(
        {
            (brand, alias, tuple(normalized_headline(alias).split()))
            for brand, alias in aliases
            if normalized_headline(alias)
        },
        key=lambda row: (-len(row[2]), row[0], row[1]),
    )
    anchors, entity_words = set(), set()
    for original in originals:
        words = normalized_headline(original).split()
        for _, _, tokens in registry:
            if any(
                tuple(words[index : index + len(tokens)]) == tokens
                for index in range(len(words))
            ):
                brands = {brand for brand, _, other in registry if other == tokens}
                anchors.update(alias for brand, alias, _ in registry if brand in brands)
                entity_words.update(term_root(word) for word in tokens)
    basis = "saved_entity_alias" if anchors else "original_prefix"
    if not anchors:
        for original in originals:
            words = [
                word
                for word in normalized_headline(original).split()
                if word not in STOP_WORDS
            ]
            if not words:
                raise ValueError("headline_has_no_search_terms")
            prefix = words[:2] if len(words) > 1 else words
            anchors.add(" ".join(prefix))
            entity_words.update(term_root(word) for word in prefix)
    numeric = sorted(
        {
            number
            for original in originals
            for number in re.findall(r"(?<!\w)\d+(?:\.\d+)*(?!\w)", original)
        }
    )
    scores = episode_terms(lead, context_leads or [lead])
    scores = {
        word: score
        for word, score in scores.items()
        if word not in entity_words and not word.isdigit()
    }
    ceiling = max(scores.values(), default=0)
    episodes = sorted(word for word, score in scores.items() if score > ceiling / 2)
    # Keep both supplied inflections and their deterministic matching roots.
    terms = sorted(
        set(episodes)
        | {
            word
            for original in originals
            for word in normalized_headline(original).split()
            if term_root(word) in episodes
        }
    )
    clause = [sorted(anchors)]
    if terms:
        clause.append(terms)
    if numeric:
        clause.append(numeric)
    if not terms and not numeric and basis == "saved_entity_alias":
        raise ValueError("headline_has_no_episode_terms")
    clauses = [clause]
    start = cutoff - timedelta(hours=24)
    query = _render(clauses, start, cutoff)
    assert_under_length_cap(query)
    return document(
        Recipe,
        {
            "schema_version": 1,
            "recipe": RECIPE,
            "original_headlines": originals,
            "anchor_basis": basis,
            "episode_terms": terms,
            "numeric_terms": numeric,
            "clauses": clauses,
            "start": start.isoformat(),
            "end_exclusive": cutoff.isoformat(),
            "query": query,
            "query_sha256": digest(query),
            "query_bytes": len(query.encode("utf-8")),
        },
    )


def validated_recipe(value):
    recipe = document(Recipe, value)
    rendered = _render(
        recipe["clauses"],
        datetime.fromisoformat(recipe["start"]),
        datetime.fromisoformat(recipe["end_exclusive"]),
    )
    if (
        rendered != recipe["query"]
        or digest(rendered) != recipe["query_sha256"]
        or len(rendered.encode("utf-8")) != recipe["query_bytes"]
        or datetime.fromisoformat(recipe["end_exclusive"])
        - datetime.fromisoformat(recipe["start"])
        != timedelta(hours=24)
    ):
        raise ValueError("gathering_recipe_changed")
    assert_under_length_cap(rendered)
    return recipe


def numeric_pattern(term):
    return r"(?<![\w.])" + re.escape(term) + r"(?![\w.])"


def _term_filter(field, term, recipe):
    return (
        Q(**{field + "__iregex": numeric_pattern(term)})
        if term in recipe["numeric_terms"]
        else Q(**{field + "__icontains": term})
    )


def _term_matches(text, term, recipe):
    return (
        bool(re.search(numeric_pattern(term), text, re.IGNORECASE))
        if term in recipe["numeric_terms"]
        else term.casefold() in text.casefold()
    )


def recipe_predicate(value):
    recipe = validated_recipe(value)

    def field_predicate(field):
        return reduce(
            or_,
            [
                reduce(
                    and_,
                    [
                        reduce(
                            or_,
                            [
                                _term_filter(field, term, recipe)
                                for term in alternatives
                            ],
                        )
                        for alternatives in clause
                    ],
                )
                for clause in recipe["clauses"]
            ],
        )

    quote_clock = (
        Q(quoted_status_id__isnull=True)
        | Q(quoted_status_id__created_at__isnull=True)
        | Q(quoted_status_id__created_at__lt=recipe["end_exclusive"])
    )
    return (
        field_predicate("text") | (field_predicate("quoted_text") & quote_clock)
    ) & Q(created_at__gte=recipe["start"], created_at__lt=recipe["end_exclusive"])


def _matches(item, recipe):
    from monitor.cycle import _item_created_epoch

    created = _item_created_epoch(item)
    if created is None or not int(
        datetime.fromisoformat(recipe["start"]).timestamp()
    ) <= created < int(datetime.fromisoformat(recipe["end_exclusive"]).timestamp()):
        return False
    texts = [item.get("text") or ""]
    quote_date = item.get("quoted_created_at")
    quote_epoch = (
        _item_created_epoch({"created_at": quote_date}) if quote_date else None
    )
    if (
        not quote_date
        or quote_epoch is not None
        and quote_epoch
        < int(datetime.fromisoformat(recipe["end_exclusive"]).timestamp())
    ):
        texts.append(item.get("quoted_text") or "")
    return any(
        all(
            any(_term_matches(text, term, recipe) for term in alternatives)
            for alternatives in clause
        )
        for text in texts
        for clause in recipe["clauses"]
    )


def source_gaps(item, recipe):
    from monitor.cycle import _item_created_epoch

    gaps = []
    if not _matches(item, recipe):
        created = _item_created_epoch(item)
        quote = _item_created_epoch({"created_at": item.get("quoted_created_at")})
        code = (
            "source_clock_missing"
            if created is None
            else "quote_after_cutoff"
            if quote is not None
            and quote
            >= int(datetime.fromisoformat(recipe["end_exclusive"]).timestamp())
            else "outside_window"
            if not int(datetime.fromisoformat(recipe["start"]).timestamp())
            <= created
            < int(datetime.fromisoformat(recipe["end_exclusive"]).timestamp())
            else "query_not_matched"
        )
        gaps.append(code)
    if item.get("quoted_text"):
        if not item.get("quoted_created_at"):
            gaps.append("quote_clock_missing")
        if not item.get("quoted_author_id") and not item.get("quoted_author_handle"):
            gaps.append("quote_author_missing")
    if not item.get("author_id") and not item.get("author_handle"):
        gaps.append("author_missing")
    return [{"post_id": item["id"], "code": code} for code in gaps]


def publication_evidence(post_id):
    """The reviewed reader alone decides pending versus completed-no-release."""
    try:
        reader = importlib.import_module(
            "core.classified_product_releases"
        ).read_publication_findings
    except ModuleNotFoundError as exc:
        if exc.name != "core.classified_product_releases":
            raise
        return {"state": "pending", "findings": []}
    findings = reader(post_id)
    return {
        "state": "pending"
        if findings is None
        else "completed_no_release"
        if not findings
        else "completed",
        "findings": list(findings or ()),
    }


def _source_identity(post):
    from x_monitor.tweet_entities import mention_id

    quote = post.quoted_status_id
    roles = {}
    if post.native_author_id:
        roles.setdefault(post.native_author_id, set()).add("author")
    if quote and quote.native_author_id:
        roles.setdefault(quote.native_author_id, set()).add("quoted_author")
    mentions = (
        (post.entities or {}).get("user_mentions", [])
        if isinstance(post.entities, dict)
        else []
    )
    for mention in mentions:
        if identity := mention_id(mention):
            roles.setdefault(identity, set()).add("mentioned")
    people = (
        list(
            PersonAccount.objects.filter(
                account__data_source_id="x",
                account__author_id__in=roles,
                person__merged_into__isnull=True,
            ).values("person_id", "account__author_id", "resolution_status")
        )
        if roles
        else []
    )
    return {
        "post_id": post.pk,
        "author_id": post.native_author_id,
        "quoted_post_id": quote.pk if quote else None,
        "person_ids": sorted({str(row["person_id"]) for row in people}),
        "person_links": [
            {
                "person_id": str(row["person_id"]),
                "native_account_id": row["account__author_id"],
                "resolution_status": row["resolution_status"],
                "role": role,
            }
            for row in people
            for role in sorted(roles[row["account__author_id"]])
        ],
        "release_evidence": publication_evidence(post.pk),
    }


@transaction.atomic
def _save(run, gathering):
    current = locked_run(run.pk, run.fence)
    current.outcome = {**current.outcome, "gathering": document(Gathering, gathering)}
    current.save(update_fields=["outcome", "updated_at"])
    run.outcome = current.outcome


def _freeze_saved(run, posts):
    current = resolved_sources(OriginalContentRun.objects.get(pk=run.pk).snapshot)
    additions = []
    for post in posts:
        if (
            post.pk in current
            or not post.text
            or not post.created_at
            or post.created_at >= run.facts_as_of
        ):
            continue
        source = project_post(post)
        if (
            post.quoted_status_id
            and post.quoted_status_id.created_at
            and post.quoted_status_id.created_at >= run.facts_as_of
        ):
            source["stored_quote"] = ""
        additions.append(source)
    if additions:
        freeze_sources(run, additions, fence=run.fence)


def gather_trends(run_id, *, cfg=None, x_client=None, enqueue=None, resume=False):
    """Gather independently supported leads, then use the existing evidence selector."""
    from .chatter_chain import _borrow, _consider, _history, _saved_config, _update

    run = OriginalContentRun.objects.get(pk=run_id, scope_key=TRENDS_SCOPE)
    cfg = _saved_config(run, cfg)
    if cfg is None:
        return {"status": "disabled"}
    with transaction.atomic():
        run = OriginalContentRun.objects.select_for_update().get(pk=run.pk)
        if run.outcome.get("phase") in {
            "discovered",
            "selected",
            "writing",
            "complete",
        } and not (resume and run.outcome.get("phase") == "discovered"):
            if enqueue and run.outcome.get("phase") == "discovered":
                enqueue("select", run.pk)
            return {"status": "already_discovered", "run_id": run.pk}
        if run.claim_owner and run.lease_until and run.lease_until > timezone.now():
            return {"status": "already_dispatched", "run_id": run.pk}
        run.fence += 1
        run.claim_owner = str(uuid4())
        run.lease_until = timezone.now() + timedelta(minutes=10)
        run.execution_state = "running"
        run.save(
            update_fields=["fence", "claim_owner", "lease_until", "execution_state"]
        )
    session = None
    try:
        state = checkpoint(run)
        if state.phase == "empty":
            from .chatter_trends import _headlines, _saved_observation

            _, observation = _saved_observation(run, state)
            if (
                _headlines(observation)
                or state.observation.http_status != 200
                or state.observation.headline_count != 0
            ):
                raise ValueError("invalid_empty_observation")
            _update(
                run, phase="complete", healthy_at=timezone.now().isoformat(), selected=0
            )
            OriginalContentRun.objects.filter(pk=run.pk, fence=run.fence).update(
                discovery_state="complete", execution_state="completed"
            )
            return {"status": "empty", "run_id": run.pk}
        batch = read_ranked_batch(run.pk)
        gathering = run.outcome.get("gathering")
        if gathering is None:
            leads = []
            for lead in batch["leads"]:
                entry = {
                    "rank": lead["rank"],
                    "headline_ids": lead["headline_ids"],
                    "recipe": None,
                }
                try:
                    entry["recipe"] = compile_recipe(
                        lead, run.facts_as_of, context_leads=batch["leads"]
                    )
                    entry["existing_ids"] = list(
                        Post.objects.filter(recipe_predicate(entry["recipe"]))
                        .order_by("pk")
                        .values_list("pk", flat=True)
                    )
                except ValueError:
                    entry.update(coverage="held", error_code="query_recipe_invalid")
                leads.append(entry)
            gathering = document(
                Gathering,
                {
                    "schema_version": 1,
                    "recipe": RECIPE,
                    "batch_sha256": batch["batch_sha256"],
                    "cutoff": batch["cutoff"],
                    "leads": leads,
                },
            )
            _save(run, gathering)  # Freeze every recipe/window before any source I/O.
        gathering = document(Gathering, gathering)
        if gathering["batch_sha256"] != batch["batch_sha256"] or datetime.fromisoformat(
            gathering["cutoff"]
        ) != datetime.fromisoformat(batch["cutoff"]):
            raise ValueError("gathering_batch_changed")
        previous, incumbents, history = _history(
            run.facts_as_of, lane="personalized-trends-v1"
        )
        producing = OriginalContentCall.objects.get(pk=batch["rank_call_id"], run=run)
        for prior in previous.values():
            borrowed = _borrow(run, prior)
            roles = {
                source.post_id
                or f"dossier-source:{source.dossier_source_id}": source.usage
                for source in prior.consideration_sources.all()
            }
            carried = _consider(
                run,
                prior.development,
                prior.selection,
                [
                    identity
                    for identity in borrowed
                    if roles[identity] == "consideration"
                ],
                "memory_only",
                producing,
            )
            background = [
                identity for identity in borrowed if roles[identity] == "background"
            ]
            if background:
                attach_sources(carried, background, fence=run.fence, usage="background")
        for lead, entry in zip(batch["leads"], gathering["leads"], strict=True):
            if (
                entry["rank"] != lead["rank"]
                or entry["headline_ids"] != lead["headline_ids"]
            ):
                raise ValueError("gathering_membership_changed")
            if entry["recipe"] is None:
                continue
            if (
                resume
                and entry["coverage"] == "held"
                and entry["error_code"]
                not in {"no_attributable_support", "query_recipe_invalid"}
            ):
                entry["coverage"], entry["error_code"] = "pending", ""
            recipe = validated_recipe(entry["recipe"])
            if datetime.fromisoformat(
                recipe["end_exclusive"]
            ) != run.facts_as_of.replace(microsecond=0):
                raise ValueError("gathering_window_changed")
            if recipe["original_headlines"] != [
                member["trend_name"] for member in lead["headlines"]
            ]:
                raise ValueError("gathering_headlines_changed")
            try:
                if entry["coverage"] == "pending":
                    if entry["existing_ids"]:
                        entry["qualified_ids"] = list(entry["existing_ids"])
                        entry["coverage"] = "saved_support"
                    else:
                        if session is None:
                            prior_collection = (
                                CollectionRun.objects.filter(content_run=run)
                                .exclude(
                                    job__job_key__startswith="chatter-personalized-trends:"
                                )
                                .exists()
                            )
                            session = SourceSession(
                                run,
                                cfg,
                                purpose=TwitterApiCredentialPurpose(
                                    state.credential_purpose
                                ),
                                client=x_client,
                                resume=prior_collection,
                            )
                        try:
                            entry["coverage"] = "query_drained"
                            entry["query_state"] = "drained"
                            for page in session.search_pages(recipe["query"]):
                                entry["raw_ids"].extend(page.raw_post_ids)
                                items = session.source_items(page.items)
                                entry["source_gaps"].extend(
                                    gap
                                    for item in items
                                    for gap in source_gaps(item, recipe)
                                )
                                qualified = [
                                    item for item in items if _matches(item, recipe)
                                ]
                                expected_quotes = [
                                    item["quoted_status_id"]
                                    for item in qualified
                                    if item.get("quoted_status_id")
                                ]
                                entry["missing_ids"] = list(
                                    dict.fromkeys(
                                        entry["missing_ids"] + expected_quotes
                                    )
                                )
                                session.ingest(qualified)
                                entry["qualified_ids"] = list(
                                    dict.fromkeys(
                                        entry["qualified_ids"]
                                        + [item["id"] for item in qualified]
                                    )
                                )
                                entry["source_observed_at"] = (
                                    session.last_receipt_at.isoformat()
                                    if session.last_receipt_at
                                    else None
                                )
                                if (
                                    page.has_more
                                    or page.clipped
                                    or page.continuation_invalid
                                ):
                                    entry["coverage"] = "partial"
                                    entry["query_state"] = "partial"
                                else:
                                    entry["coverage"] = "query_drained"
                                    entry["query_state"] = "drained"
                                _save(run, gathering)
                        except Exception as exc:  # noqa: BLE001 - preserve paid prefix and its gap
                            entry["coverage"] = (
                                "partial" if entry["qualified_ids"] else "held"
                            )
                            entry["error_code"] = type(exc).__name__
                            entry["query_state"] = (
                                "partial" if entry["raw_ids"] else "held"
                            )
                posts = list(
                    Post.objects.filter(pk__in=entry["qualified_ids"])
                    .filter(recipe_predicate(recipe))
                    .select_related("quoted_status_id")
                    .order_by("pk")
                )
                entry["qualified_ids"] = [post.pk for post in posts]
                entry["missing_ids"] = [
                    key
                    for key in entry["missing_ids"]
                    if not Post.objects.filter(pk=key).exists()
                ]
                if not posts:
                    entry.update(
                        coverage="held",
                        error_code=entry["error_code"] or "no_attributable_support",
                    )
                    continue
                quotes = {
                    post.quoted_status_id.pk: post.quoted_status_id
                    for post in posts
                    if post.quoted_status_id
                    and post.quoted_status_id.text
                    and post.quoted_status_id.created_at
                    and post.quoted_status_id.created_at < run.facts_as_of
                }
                _freeze_saved(run, posts + list(quotes.values()))
                source_ids = [post.pk for post in posts] + [
                    key
                    for key, quote in quotes.items()
                    if quote.created_at >= datetime.fromisoformat(recipe["start"])
                ]
                entry["background_ids"] = [
                    key for key in quotes if key not in source_ids
                ]
                headlines = sorted(
                    normalized_headline(value) for value in recipe["original_headlines"]
                )
                identity = {
                    "original_headlines": headlines,
                    "source_ids": sorted(post.pk for post in posts),
                }
                old = next(
                    (
                        row
                        for row in previous.values()
                        if row.selection.get("gathered_identity", {}).get(
                            "original_headlines"
                        )
                        == headlines
                        and set(row.selection["gathered_identity"]["source_ids"])
                        & set(identity["source_ids"])
                    ),
                    None,
                )
                story = (
                    old.development
                    if old
                    else EditorialStory.objects.get_or_create(
                        development_key="chatter-trend:" + digest(identity),
                        defaults={"anchor_ids": identity["source_ids"]},
                    )[0]
                )
                pitch = {
                    "schema_version": 1,
                    "subject": lead["title"],
                    "angle": lead["reason"],
                    "story_ref": None,
                    "original_headlines": recipe["original_headlines"],
                    "headline_ids": lead["headline_ids"],
                    "gathered_identity": identity,
                    "query_sha256": recipe["query_sha256"],
                    "source_identities": [_source_identity(post) for post in posts],
                }
                row = _consider(
                    run,
                    story,
                    pitch,
                    source_ids,
                    "personalized_trend",
                    producing,
                    lead["rank"],
                )
                if entry["background_ids"]:
                    attach_sources(
                        row,
                        entry["background_ids"],
                        fence=run.fence,
                        usage="background",
                    )
                save_query(recipe["query"], development=story)
            except Exception as exc:  # noqa: BLE001 - isolate held leads from supported siblings
                entry["coverage"] = "partial" if entry["qualified_ids"] else "held"
                entry["error_code"] = type(exc).__name__
            finally:
                _save(run, gathering)
        if session:
            session.close(
                success=not any(row["error_code"] for row in gathering["leads"])
            )
            session = None
        _update(
            run,
            phase="discovered",
            incumbent_refs={
                pool: str(row.development_id) for pool, row in incumbents.items()
            },
            history_coverage={
                "board_may_be_capped": history["board_may_be_capped"],
                "history_requests": [],
            },
            tool_detail_visibility="saved_sources_and_compact_provider_receipts",
            lookup_omitted=0,
            gathering_incomplete=any(
                entry["error_code"] for entry in gathering["leads"]
            ),
        )
        OriginalContentRun.objects.filter(pk=run.pk, fence=run.fence).update(
            discovery_state="complete"
        )
        if enqueue:
            enqueue("select", run.pk)
        return {"status": "discovered", "run_id": run.pk}
    except Exception as exc:  # noqa: BLE001 - queued boundary records a safe hold
        from .chatter_chain import _failure

        return _failure(run, "gathering", exc)
    finally:
        if session:
            session.close(success=False)
        OriginalContentRun.objects.filter(pk=run.pk, fence=run.fence).update(
            claim_owner=""
        )
