"""Recover the publisher of an active, model-specific release finding from its original source."""

from __future__ import annotations

import json
import logging
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
    repo: str | None
    profile: str | None = None


class _ArticlePage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.hf_profiles = set()
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
            if "me" in attrs.get("rel", "").casefold().split() or (
                "social-link" in classes
                and "hugging face" in attrs.get("aria-label", "").casefold()
            ):
                profile = _hf_profile(attrs["href"])
                if profile:
                    self.hf_profiles.add(profile)

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


def _hf_profile(url):
    """A publisher's social-profile link must point to the root of a Hub namespace."""
    from core.hf_metadata_client import NAMESPACE

    if not isinstance(url, str):
        return None
    match = re.fullmatch(r"https://huggingface\.co/([^/?#]+)/?", url, re.IGNORECASE)
    if not match or not NAMESPACE.fullmatch(match[1]):
        return None
    namespace = match[1].casefold()
    if namespace in {
        "api",
        "models",
        "datasets",
        "spaces",
        "collections",
        "docs",
        "papers",
        "organizations",
        "users",
        "settings",
        "join",
        "login",
        "pricing",
        "blog",
        "tasks",
        "learn",
        "enterprise",
        "chat",
        "buckets",
        "kernels",
    }:
        return None
    return namespace


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


def _model_repo(links, product, publisher_handle, *other_namespaces):
    matching = set()
    owners = {name.casefold() for name in (publisher_handle, *other_namespaces)}
    for url in links:
        repo = _repo_from_hf_url(url)
        if repo:
            owner, slug = repo.split("/")
            if owner.casefold() in owners and _offering_key(slug) == _offering_key(
                product
            ):
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
    profile = next(iter(page.hf_profiles)) if len(page.hf_profiles) == 1 else None
    repo = _model_repo(page.links, product, profile or handle)
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
        matches.add(PublisherArticle(title, day, repo, profile))
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
    text = raw.get("text") or ""
    urls = re.findall(r"https://[^\s<>\"']+", text)
    text_urls = set(urls)
    entities = raw.get("entities") or {}
    for obj in entities.get("urls", ()) if isinstance(entities, dict) else ():
        if (
            isinstance(obj, dict)
            and obj.get("url") in text_urls
            and isinstance(obj.get("expanded_url"), str)
        ):
            urls.append(obj["expanded_url"])
    return list(dict.fromkeys(u.rstrip(".,;!?)]}") for u in urls))


def _host(url, *, profile=False):
    if not isinstance(url, str):
        return ""
    try:
        parsed = urlsplit(url or "")
        if (
            (parsed.scheme == "https" or profile and parsed.scheme == "http")
            and not parsed.username
            and not parsed.password
            and parsed.port in (None, 443 if parsed.scheme == "https" else 80)
        ):
            return (parsed.hostname or "").casefold().removeprefix("www.")
    except ValueError:
        pass
    return ""


def _issuer_article(page, product, handle, publisher, url):
    """A publisher can announce a closed model without offering downloadable weights."""
    host = _host(url)

    def same_page(value):
        if not isinstance(value, str) or _host(value) != host:
            return False
        candidate, source = urlsplit(value), urlsplit(url)
        return (candidate.path.rstrip("/"), candidate.query) == (
            source.path.rstrip("/"),
            source.query,
        )

    owner_ids = {
        doc["@id"]
        for doc in page.documents
        if isinstance(doc, dict)
        and doc.get("@type") == "Organization"
        and isinstance(doc.get("@id"), str)
        and _host(doc["@id"]) == host
        and _host(doc.get("url")) == host
        and isinstance(doc.get("name"), str)
        and doc["name"].casefold() == publisher.casefold()
    }
    if len(owner_ids) != 1 or not any(
        link.rstrip("/").casefold()
        in {f"https://x.com/{handle}", f"https://twitter.com/{handle}"}
        for link in page.links
    ):
        return None

    owner_id = next(iter(owner_ids))
    matches = set()
    for doc in page.documents:
        if not isinstance(doc, dict) or doc.get("@type") not in (
            "Article",
            "BlogPosting",
            "NewsArticle",
        ):
            continue
        owner, topics, title = (
            doc.get("publisher"),
            doc.get("about"),
            doc.get("headline"),
        )
        if not (
            isinstance(owner, dict)
            and owner.get("@id") == owner_id
            and same_page(doc.get("mainEntityOfPage"))
            and isinstance(topics, list)
            and product in topics
            and isinstance(title, str)
        ):
            continue
        # Keep the exact offering at the start of a Chinese launch headline.
        # A comparison, benchmark result or review title cannot create a release.
        chinese_launch = re.fullmatch(
            re.escape(product)
            + r"\s*(?:本地\s*)?(?:Agent\s*)?(?:模型\s*)?(?:正式)?发布[！!]?",
            title.strip(),
            re.IGNORECASE,
        )
        if not (_announcement_title(title, product) or chinese_launch):
            continue
        try:
            day = datetime.fromisoformat(doc["datePublished"]).date()
        except (TypeError, ValueError, KeyError):
            continue
        profile = next(iter(page.hf_profiles)) if len(page.hf_profiles) == 1 else None
        matches.add(
            PublisherArticle(
                title, day, _model_repo(page.links, product, profile or handle), profile
            )
        )
    return matches.pop() if len(matches) == 1 else None


def _publisher_page(raw, product, handle, budget, *, publisher_name=None):
    from urllib3.exceptions import HTTPError

    from core.product_verification import _walk_strings
    from core.staff_assets.public_fetch import fetch_before_deadline

    profile = raw.get("author_profile_bio") or {}
    profile_entities = profile.get("entities") if isinstance(profile, dict) else None
    hosts = {_host(raw.get("author_url"), profile=True)}
    for entities in (profile_entities, raw.get("author_entities")):
        if isinstance(entities, dict):
            hosts.update(
                _host(url, profile=True) for url in _walk_strings(entities.get("url"))
            )
    platforms = {
        "",
        "t.co",
        "bit.ly",
        "tinyurl.com",
        "ow.ly",
        "lnkd.in",
        "twitter.com",
        "x.com",
        "huggingface.co",
        "hf.co",
        "github.com",
        "linkedin.com",
    }
    hosts -= platforms
    publisher_label = re.sub(r"[^a-z0-9]", "", (publisher_name or "").casefold())
    articles = []
    for url in _urls(raw):
        host = _host(url)
        if host in platforms:
            continue
        if hosts:
            if host not in hosts:
                continue
        else:
            # Without a profile website, require a link from the genuine issuer
            # naming this product on a domain bearing the independently cited
            # publisher name. Only the target's own title, date, social backlink
            # and exact model link can complete the proof.
            if not (
                _original_post(raw, handle, product)
                and publisher_label
                and re.fullmatch(re.escape(publisher_label) + r"\.[a-z]{2,63}", host)
                and re.search(
                    r"(?<![a-z0-9])"
                    + re.escape(_offering_key(product))
                    + r"(?![a-z0-9])",
                    _offering_key(urlsplit(url).path),
                )
            ):
                continue
        articles.append(url)
    verify_issuer_article = False
    request_count = 1
    if not articles and publisher_label and _original_post(raw, handle, product):
        # An old post can have only its original t.co URL. Fetch a single cited
        # link with the existing bounded public reader, then verify the final
        # domain, the article's declared owner and its link back to this account.
        posted = _urls({"text": raw.get("text", "")})
        if len(posted) != 1:
            return None
        expanded = [link for link in _urls(raw) if link != posted[0]]
        if len(expanded) > 1:
            return None
        url = expanded[0] if expanded else posted[0]
        if _host(url) != "t.co" and not re.fullmatch(
            re.escape(publisher_label) + r"\.[a-z]{2,63}", _host(url)
        ):
            return None
        request_count = 3 if _host(url) == "t.co" else 1
        verify_issuer_article = True
    elif len(articles) == 1:
        url = articles[0]
    else:
        return None
    host = _host(url)
    budget.check()
    if budget.remaining < request_count:
        return None
    budget.remaining -= request_count
    cap = min(1024 * 1024, budget.max_bytes - budget.total_bytes_read)
    if cap <= 0:
        return None
    try:
        body, final, mime = fetch_before_deadline(
            url, max_bytes=cap, deadline=budget.deadline, max_requests=request_count
        )
    except (ValueError, OSError, HTTPError):
        return None
    budget.total_bytes_read += len(body)
    if _host(final) == host and "html" in mime and not verify_issuer_article:
        page = publisher_article(body, product, handle)
        if page:
            return final, page
    if publisher_label and "html" in mime:
        final_host = _host(final)
        if (hosts and final_host not in hosts) or not re.fullmatch(
            re.escape(publisher_label) + r"\.[a-z]{2,63}", final_host
        ):
            return None
        document = _ArticlePage()
        document.feed(body.decode("utf-8", errors="replace"))
        proof = _issuer_article(
            document, product, handle.casefold(), publisher_name, final
        )
        return (final, proof) if proof else None
    return None


def _search_publisher(handle, product, budget, report_id=None):
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
    # One deliberately selected source can retry the changed article parser
    # within this same pilot budget. The retry has its own single-use slot.
    if (
        report_id
        and os.environ.get("PULSE_STAGING_PUBLISHER_RETRY_POST_ID") == str(report_id)
        and SearchQuery.objects.filter(query_id=query_id).exists()
    ):
        query_id += ":article-v2"
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
    from core.publisher_accounts import cited_x_account

    if (
        report.author_id
        and (report.author_handle or "").casefold() == handle.casefold()
    ):
        account_id = report.author_id
    else:
        account = cited_x_account(report, handle)
        if account is None:
            return
        account_id = account.pk
    rows = (
        Post.objects.filter(
            author_id=account_id,
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
                            "author_entities",
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
        yield from (
            (None, row) for row in _search_publisher(handle, product, budget, report.pk)
        )


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


def _record_source(
    anchor, finding, source_post, raw, article, repo, now, *, budget=None
):
    from django.db import transaction

    from core.classified_product_releases import (
        read_publication_findings,
        replay_saved_publisher,
    )
    from core.event_dossiers import add_claim, attach_source
    from core.models import EventDossier, EventDossierClaim, Product
    from core.product_identity import resolve_saved_release_finding
    from core.publisher_accounts import resolve_release_publisher
    from core.release_provider_identity import (
        bind_hf_model,
        bind_hf_publisher,
        lookup_release_hf_model,
    )
    from monitor.cycle import persist_x_post

    report = anchor.event_dossier_source.post
    # A verified announcing account's website field is also first-party evidence.
    from core.product_verification import _walk_strings

    profile_urls = [raw.get("author_url") or ""]
    profile_bio = raw.get("author_profile_bio")
    for fields in (
        raw.get("author_entities"),
        profile_bio.get("entities") if isinstance(profile_bio, dict) else None,
    ):
        if isinstance(fields, dict):
            profile_urls.extend(_walk_strings(fields.get("url")))
    profiles = {name for url in profile_urls if (name := _hf_profile(url))}
    if article and article[1].profile:
        profiles.add(article[1].profile)
    profile = next(iter(profiles)) if len(profiles) == 1 else None
    if profile and repo and profile.casefold() != repo.split("/")[0].casefold():
        # The post and the publisher article point to different owners. Keep
        # the verified profile and require fresh proof for the model repository.
        repo = None
    source_repo = repo
    payload = None
    if budget is not None and len(profiles) <= 1:
        payload = lookup_release_hf_model(
            raw, finding["observed_name"], profile, repo, budget
        )
    if payload:
        repo = payload[1]["id"]
    with transaction.atomic():
        dossier = EventDossier.objects.select_for_update().get(
            pk=anchor.event_dossier_source.event_dossier_id
        )
        if (
            dossier.merged_into_id
            or dossier.current_review_id
            or not any(
                row["anchor_claim_id"] == str(anchor.pk)
                and replay_saved_publisher(row["finding"], report) == finding
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
            if _original_post(raw, source_post.author_handle, finding["observed_name"])
            else None
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
        profile_account = bind_hf_publisher(owner, profile, url) if profile else None
        bound = False
        if payload and (not profile or profile_account is not None):
            try:
                bound = bind_hf_model(product, payload, url)
            except ValueError as exc:
                # bind_hf_model rolls back just the disputed mapping.
                logging.getLogger(__name__).info(
                    "HF model mapping deferred for product %s: %s", product.pk, exc
                )
        if repo and (source_repo or bound):
            repo_url = f"https://huggingface.co/{repo}"
            add_claim(
                linked.pk,
                claim_kind="release_context",
                scope_key=f"official-hf-model:{repo}",
                assertion_text=repo_url,
                source_excerpt=repo_url if source_repo else repo,
                extraction_version="pulse-publisher-source-v1",
                **(
                    common
                    if source_repo
                    else {
                        **common,
                        "source_locator": "https://huggingface.co/api/models/" + repo,
                    }
                ),
            )
        return True


def recover_release_publisher(
    dossier, *, client, now, budget, revisit_saved_articles=False
):
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

        histories = claims.filter(
            extraction_version="pulse-historical-announcement-v1",
            reported_product__isnull=False,
        )
        dated_sources = list(
            histories.values_list("event_dossier_source__post_id", "source_locator")
        )
        existing_dates = {post_id for post_id, _ in dated_sources}
        verified_articles = {
            post_id
            for post_id, url in dated_sources
            if _host(url) not in ("", "x.com", "twitter.com")
        }
        fallback = None
        for saved, raw in _originals(handle, product, report, issuer, budget):
            if not _publisher_post(raw, handle):
                continue
            original = _original_post(raw, handle, product)
            article = None
            if revisit_saved_articles or not saved or saved.pk not in verified_articles:
                article = _publisher_page(
                    raw,
                    product,
                    handle,
                    budget,
                    publisher_name=issuer.get("observed_name"),
                )
            urls = _urls(raw)
            repo = None
            if any(_repo_from_hf_url(url) for url in urls):
                from core.models import BrandAccount, PostBrandProduct

                # P2 can already have confirmed a first-party release even when
                # its announcement did not begin with an English launch formula.
                confirmed = (
                    PostBrandProduct.objects.filter(
                        post=report,
                        product__display_name__iexact=product,
                        brand__in=BrandAccount.objects.filter(
                            account_id=report.author_id, role_id="official"
                        ).values("brand_id"),
                    )
                    .values_list("brand_id", flat=True)
                    .distinct()[:2]
                    if saved
                    and saved.pk == report.pk
                    and issuer.get("relation") == "source_author"
                    else ()
                )
                brands = list(confirmed)
                namespaces = (
                    BrandAccount.objects.filter(
                        brand_id=brands[0],
                        role_id="official",
                        account__data_source_id="hf",
                    ).values_list("account__external_identifier", flat=True)
                    if len(brands) == 1
                    else ()
                )
                if original or len(brands) == 1:
                    repo = _model_repo(urls, product, handle, *namespaces)
            if not (original or article or repo):
                continue
            if article and article[1].repo and repo and repo != article[1].repo:
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
                (article[1].repo or repo) if article else repo,
                now,
                budget=budget if client is not None else None,
            ):
                return True
        if fallback and _record_source(
            anchor,
            finding,
            *fallback,
            None,
            None,
            now,
            budget=budget if client is not None else None,
        ):
            return True
    return False
