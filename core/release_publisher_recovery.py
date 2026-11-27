"""Recover the publisher of an active, model-specific release finding from its original source."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

from core.product_verification import _repo_from_hf_url


@dataclass(frozen=True)
class PublisherArticle:
    title: str
    day: date
    repo: str


class _ArticlePage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.documents = []
        self._script = None
        self.headings = []
        self.byline_dates = []
        self._capture = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if tag == "h1" and "blog_header_title" in classes:
            self._capture = (tag, self.headings, [])
        elif tag == "div" and "resources_featured_meta-text" in classes:
            self._capture = (tag, self.byline_dates, [])
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        elif tag == "script" and attrs.get("type") == "application/ld+json":
            self._script = []

    def handle_data(self, data):
        if self._capture:
            self._capture[2].append(data)
        if self._script is not None:
            self._script.append(data)

    def handle_endtag(self, tag):
        if self._capture and self._capture[0] == tag:
            self._capture[1].append("".join(self._capture[2]).strip())
            self._capture = None
        if tag != "script" or self._script is None:
            return
        raw = "".join(self._script)
        self._script = None
        try:
            data = json.loads(raw)
        except (ValueError, RecursionError):
            return
        entries = data if isinstance(data, list) else [data]
        for item in entries:
            if isinstance(item, dict):
                graph = item.get("@graph")
                self.documents.extend(graph if isinstance(graph, list) else [item])


def _offering_key(value):
    # Keep meaningful version punctuation; HF slugs replace spaces with hyphens.
    return re.sub(r"[\s_-]+", "-", value.strip()).casefold()


def _announcement_title(title, product):
    if not isinstance(title, str):
        return False
    separator = r"[\s_-]+"
    literal = separator.join(
        re.escape(word) for word in re.split(separator, product) if word
    )
    return bool(
        literal
        and re.match(
            rf"^(?:(?:we(?:['’]re| are)?\s+)?(?:introduc(?:ing|e)|announc(?:ing|e)|releas(?:ing|ed)|launch(?:ing|ed))"
            rf"\s*[:—-]?\s+{literal}(?=$|[,!:—]|\.(?:\s|$)|\s+(?:today|on |weights|model|is |a |[-—:]))|{literal}\s+(?:is (?:now )?(?:available|live)|launches)\b)",
            title.strip(),
            re.IGNORECASE,
        )
    )


def _model_repo(links, product, publisher_handle):
    matching = set()
    for url in links:
        repo = _repo_from_hf_url(url)
        if repo:
            owner, slug = repo.split("/")
            if owner.casefold() == publisher_handle.casefold() and _offering_key(
                slug
            ) == _offering_key(product):
                matching.add(repo)
    return matching.pop() if len(matching) == 1 else None


def publisher_article(body, product, handle):
    page = _ArticlePage()
    page.feed(body.decode("utf-8", errors="replace"))
    socials = {
        f"https://{host}/{handle.casefold()}" for host in ("x.com", "twitter.com")
    }
    if not any(url.rstrip("/").casefold() in socials for url in page.links):
        return None
    repo = _model_repo(page.links, product, handle)
    if not repo:
        return None
    matches = set()
    for doc in page.documents:
        if not isinstance(doc, dict) or doc.get("@type") not in (
            "Article",
            "BlogPosting",
            "NewsArticle",
        ):
            continue
        title = doc.get("headline")
        if not _announcement_title(title, product):
            continue
        try:
            day = datetime.fromisoformat(doc["datePublished"]).date()
        except (ValueError, TypeError, KeyError):
            continue
        matches.add(PublisherArticle(title, day, repo))
    # CMS pages may put dates in the visible article byline instead of JSON-LD.
    if len(page.headings) == 1 and _announcement_title(page.headings[0], product):
        for byline in page.byline_dates:
            try:
                day = datetime.strptime(byline, "%B %d, %Y").date()  # noqa: DTZ007 - civil byline date
            except ValueError:
                continue
            matches.add(PublisherArticle(page.headings[0], day, repo))
    return matches.pop() if len(matches) == 1 else None


def _publisher_post(raw, handle):
    return (
        str(raw.get("author_id") or "").isdecimal()
        and (raw.get("author_handle") or "").casefold() == handle.casefold()
        and not any(
            raw.get(k)
            for k in (
                "is_retweet",
                "is_quote",
                "quoted_status_id",
                "retweeted_status_id",
            )
        )
    )


def _original_post(raw, handle, product):
    return _publisher_post(raw, handle) and _announcement_title(
        (raw.get("text") or "").lstrip("🚀🎉 \n").split("\n", 1)[0], product
    )


def _urls(raw):
    from core.product_verification import _walk_strings

    return list(
        dict.fromkeys(
            url.rstrip(".,;!?)]}")
            for field in (raw.get("entities"), raw.get("text"))
            for value in _walk_strings(field)
            for url in re.findall(r"https://[^\s<>\"']+", value)
        )
    )


def _host(url):
    try:
        parsed = urlsplit(url or "")
        if (
            parsed.scheme == "https"
            and not parsed.username
            and not parsed.password
            and parsed.port in (443, None)
        ):
            return (parsed.hostname or "").casefold().removeprefix("www.")
    except ValueError:
        pass
    return ""


def _publisher_page(raw, product, handle, budget):
    from urllib3.exceptions import HTTPError

    from core.product_verification import _walk_strings
    from core.staff_assets.public_fetch import fetch_before_deadline

    profile = raw.get("author_profile_bio") or {}
    profile_entities = profile.get("entities") if isinstance(profile, dict) else None
    websites = (
        (profile_entities or {}).get("url")
        if isinstance(profile_entities, dict)
        else None
    )
    hosts = {_host(url) for url in [raw.get("author_url"), *_walk_strings(websites)]}
    hosts -= {"", "t.co", "twitter.com", "x.com", "huggingface.co", "github.com"}
    for url in _urls(raw):
        host = _host(url)
        if host not in hosts:
            continue
        budget.check()
        budget.remaining -= 1
        cap = min(1024 * 1024, budget.max_bytes - budget.total_bytes_read)
        if cap <= 0:
            return None
        try:
            body, final, mime = fetch_before_deadline(
                url, max_bytes=cap, deadline=budget.deadline, max_requests=1
            )
        except (ValueError, OSError, HTTPError):
            return None
        budget.total_bytes_read += len(body)
        if _host(final) == host and "html" in mime:
            page = publisher_article(body, product, handle)
            if page:
                return final, page
        break
    return None


def _search_publisher(handle, product, budget):
    """A single separately reserved X lookup in the explicitly guarded pilot window."""
    import hashlib
    import os
    from decimal import Decimal
    from pathlib import Path

    from django.db import transaction
    from requests import RequestException

    from core.models import SearchQuery
    from monitor.enrichment_budget import config_fingerprint, reserve_charge
    from monitor.staging_acceptance import MAX_RARE_TYPE_SEARCH_CREDITS
    from x_monitor.config import load_config
    from x_monitor.twitterapi_credentials import (
        TwitterApiCredentialPurpose,
        get_twitterapi_api_key,
    )
    from x_monitor.x_client import (
        XClient,
        XClientAuthError,
        XClientRateLimitError,
        XClientServerError,
    )

    window = os.environ.get("PULSE_STAGING_BUDGET_WINDOW_ID")
    key = get_twitterapi_api_key(TwitterApiCredentialPurpose.ON_DEMAND)
    if (
        not key
        or not window
        or os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT") != "staging"
        or not re.fullmatch(r"[\w .-]{2,100}", product)
        or not re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle)
    ):
        return []
    budget.check()
    timeout = min(8, budget.deadline - budget.clock())
    cfg = load_config(Path("config.yaml"))

    # Reserve a named search instruction and its cost together. A timeout or
    # process exit after dispatch still consumes the same single pilot slot.
    query = f'from:{handle} "{product}"'
    digest = hashlib.sha256(query.casefold().encode()).hexdigest()
    query_id = f"pulse-publisher-search-v1:{window}:{digest}"
    if SearchQuery.objects.filter(query_id=query_id).exists():
        return []

    @transaction.atomic
    def charge(_timeout):
        budget.check()
        _, created = SearchQuery.objects.get_or_create(
            query_id=query_id,
            defaults={"query_text": query, "plan_calls_run_id": window},
        )
        if not created:
            raise ValueError("publisher_lookup_already_reserved")
        reserve_charge(
            window_id=window,
            fingerprint=config_fingerprint(cfg),
            scope="pilot",
            cost=Decimal(MAX_RARE_TYPE_SEARCH_CREDITS) / 100_000,
            window_ceiling=Decimal(20),
        )
        budget.remaining -= 1

    cap = min(512 * 1024, budget.max_bytes - budget.total_bytes_read)
    if cap <= 0:
        return []
    api = XClient(
        api_key=key,
        provider_order=("twitterapi",),
        timeout_s=timeout,
        search_timeout_s=timeout,
        max_retries=0,
        search_max_retries=0,
        max_response_bytes=cap,
        before_request=charge,
    )
    # Charge the full allowed response allowance, including an interrupted response.
    try:
        rows, _ = api.run_search(
            f'from:{handle} "{product}"', max_results=20, max_pages=1
        )
    except (
        RequestException,
        TimeoutError,
        XClientServerError,
        XClientRateLimitError,
        XClientAuthError,
    ):
        return []
    finally:
        if api.exchanges_started:
            budget.total_bytes_read += cap
    return rows


def _saved_originals(handle, product, report):
    from core.models import Post

    rows = (
        Post.objects.filter(
            author_handle__iexact=handle,
            text__icontains=product,
            created_at__lte=report.created_at,
        )
        .select_related("author")
        .order_by("created_at", "pk")[:24]
    )
    for row in rows:
        if row.author_id:
            yield (
                row,
                {
                    **{
                        key: getattr(row, key)
                        for key in (
                            "author_handle",
                            "text",
                            "entities",
                            "author_url",
                            "author_profile_bio",
                            "is_quote",
                            "is_retweet",
                            "quoted_status_id",
                        )
                    },
                    "author_id": row.author.author_id,
                },
            )


def _originals(handle, product, report, issuer, budget):
    yield from _saved_originals(handle, product, report)
    if issuer.get("relation") == "attributed_party":
        yield from ((None, row) for row in _search_publisher(handle, product, budget))


def _announcement_effective(text, published_at):
    from core.product_release_milestones import extract_milestones

    dates = {
        row.effective_date
        for row in extract_milestones(text, published_at=published_at)
        if row.kind == "source_stated_release" and row.effective_date
    }
    if len(dates) == 1 and next(iter(dates)) <= published_at.date():
        return {"effective_precision": "day", "effective_date": next(iter(dates))}
    # The time of a retrospective post cannot supply an unstated launch day.
    if dates or re.search(
        r"\b(?:on\s+(?:[A-Z][a-z]+\s+\d+|\d+)|last|yesterday|ago|previously|back in|earlier)\b",
        text,
        re.IGNORECASE,
    ):
        return None
    return {"effective_precision": "datetime", "effective_at": published_at}


def _record_source(anchor, finding, source_post, raw, article, repo, now):
    from django.db import transaction

    from core.classified_product_releases import (
        read_publication_findings,
        replay_saved_publisher,
    )
    from core.event_dossiers import add_claim, attach_source
    from core.models import EventDossier, EventDossierClaim, Product
    from core.product_identity import resolve_saved_release_finding
    from core.publisher_accounts import resolve_release_publisher
    from monitor.cycle import persist_x_post

    report = anchor.event_dossier_source.post
    with transaction.atomic():
        dossier = EventDossier.objects.select_for_update().get(
            pk=anchor.event_dossier_source.event_dossier_id
        )
        if (
            dossier.merged_into_id
            or dossier.current_review_id
            or not any(
                row["anchor_claim_id"] == str(anchor.pk) and replay_saved_publisher(row["finding"], report) == finding
                for row in read_publication_findings(report.pk) or ()
            )
        ):
            return False
        if source_post is None:
            source_post, _ = persist_x_post(raw)
        if (
            not source_post
            or not source_post.author_id
            or not source_post.created_at
            or source_post.created_at > min(report.created_at, now)
            or (article and article[1].day > min(report.created_at, now).date())
        ):
            transaction.set_rollback(True)
            return False
        owner = resolve_release_publisher(
            post=report,
            finding=finding,
            verified_account=source_post.author if article or repo else None,
        )
        if not owner:
            transaction.set_rollback(True)
            return False
        result = resolve_saved_release_finding(claim_id=anchor.pk)
        if not result["product_id"]:
            transaction.set_rollback(True)
            return False
        product = Product.objects.get(pk=result["product_id"])
        if product.brand_id != owner:
            transaction.set_rollback(True)
            return False
        linked = attach_source(result["dossier_id"], post_id=source_post.pk)
        url = (
            source_post.tweet_url
            or f"https://x.com/{source_post.author_handle}/status/{source_post.pk}"
        )
        title = (raw["text"] or "").strip().splitlines()[0][:512]
        if article:
            url, page = article
            title = page.title
        common = {
            "source_locator": url,
            "reported_product_id": product.pk,
            "reported_brand_id": owner,
        }
        effective = (
            {"effective_precision": "day", "effective_date": article[1].day}
            if article
            else _announcement_effective(title, source_post.created_at)
        )
        existing_date = EventDossierClaim.objects.filter(
            event_dossier_source__event_dossier_id=result["dossier_id"],
            scope_key=f"pulse-history-v1:{product.product_key}",
            reported_product=product,
            extraction_version="pulse-historical-announcement-v1",
        )
        # A later X announcement can add a repository without establishing
        # another launch timestamp. Explicit publisher-stated days retain provenance.
        if effective and (
            article or effective.get("effective_date") or not existing_date.exists()
        ):
            add_claim(
                linked.pk,
                claim_kind="announcement",
                scope_key=f"pulse-history-v1:{product.product_key}",
                assertion_text=title,
                source_excerpt=title,
                extraction_version="pulse-historical-announcement-v1",
                **effective,
                **common,
            )
        if repo:
            repo_url = f"https://huggingface.co/{repo}"
            add_claim(
                linked.pk,
                claim_kind="release_context",
                scope_key=f"official-hf-model:{repo}",
                assertion_text=repo_url,
                source_excerpt=repo_url,
                extraction_version="pulse-publisher-source-v1",
                **common,
            )
        return True


def recover_release_publisher(dossier, *, client, now, budget):
    from core.classified_product_releases import (
        read_publication_findings,
        replay_saved_publisher,
    )
    from core.models import EventDossierClaim
    from core.product_release_findings import discussion_only_reason

    if dossier.current_review_id or dossier.merged_into_id:
        return False
    claims = EventDossierClaim.objects.filter(
        event_dossier_source__event_dossier=dossier
    )
    if claims.filter(extraction_version="pulse-publisher-source-v1").exists():
        return False
    anchors = claims.filter(
        scope_key__startswith="pulse-finding-v1:",
        event_dossier_source__post__isnull=False,
    )
    for anchor in anchors.select_related("event_dossier_source__post").order_by("pk")[
        :4
    ]:
        report = anchor.event_dossier_source.post
        finding = next(
            (
                row["finding"]
                for row in read_publication_findings(report.pk) or ()
                if row["anchor_claim_id"] == str(anchor.pk)
            ),
            None,
        )
        if (
            not finding
            or finding["category"] not in {"model-llm", "model-other"}
            or finding["novelty"]
            not in {"new_release", "historical_release", "availability_update"}
            or discussion_only_reason(finding)
            or not report.created_at
        ):
            continue
        finding = replay_saved_publisher(finding, report)
        issuer = finding.get("issuer_evidence") or {}
        handle = (
            report.author_handle
            if issuer.get("relation") == "source_author"
            else issuer.get("observed_handle")
            if issuer.get("relation") == "attributed_party"
            else None
        )
        product = finding.get("observed_name")
        if not handle or not product or len(product) < 2:
            continue

        existing_dates = set(
            claims.filter(
                extraction_version="pulse-historical-announcement-v1",
                reported_product__isnull=False,
            ).values_list("event_dossier_source__post_id", flat=True)
        )
        fallback = None
        for saved, raw in _originals(handle, product, report, issuer, budget):
            if not _publisher_post(raw, handle):
                continue
            original = _original_post(raw, handle, product)
            article = _publisher_page(raw, product, handle, budget)
            if not (original or article):
                continue
            repo = _model_repo(_urls(raw), product, handle) if original else None
            if article and repo and repo != article[1].repo:
                continue
            if issuer.get("relation") == "attributed_party" and not (article or repo):
                continue
            if not (article or repo):
                if (
                    fallback is None
                    and not existing_dates
                    and saved
                    and saved.created_at
                    and _announcement_effective(
                        raw["text"].splitlines()[0], saved.created_at
                    )
                ):
                    fallback = (saved, raw)
                continue
            if _record_source(
                anchor,
                finding,
                saved,
                raw,
                article,
                article[1].repo if article else repo,
                now,
            ):
                return True
        if fallback and _record_source(anchor, finding, *fallback, None, None, now):
            return True
    return False
