# {{AGENT_ATTRIBUTION}}
"""Thin wrapper around TwitterAPI.io (https://twitterapi.io).

Migrated 2026-06-08 from automation-lab/twitter-scraper (Apify) to
TwitterAPI.io. Rationale:
  - search mode on automation-lab required user cookies; TwitterAPI.io
    search is cookie-free and cheaper ($0.15/1k vs $3/1k)
  - followers mode on automation-lab required cookies; TwitterAPI.io
    get_user_followers is cookie-free ($0.01/1k)
  - no more cookie probe, cookie file, or cookie rot failure mode
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import requests

log = logging.getLogger(__name__)


TWITTERAPI_BASE = "https://api.twitterapi.io"
SEARCH_PATH = "/twitter/tweet/advanced_search"
FOLLOWERS_PATH = "/twitter/user/followers"
# Per docs TwitterAPI.io caps each advanced_search response at 20 tweets.
# We paginate via next_cursor to retrieve up to max_results.
SEARCH_MAX_PER_PAGE = 20
USER_INFO_PATH = "/twitter/user/info"
# v1.4: long-form X article body. Cost: 100 credits per article.
ARTICLE_PATH = "/twitter/article"

# Pagination caps per the TwitterAPI.io pricing page:
#   followers/following: 20-99 returned = 3cr each, 100-199 = 2cr, 200 = 1cr.
#   Always ask for 200 — the price-per-item is the cheapest.
FOLLOWERS_MAX_PER_PAGE = 200


class TwitterApiAuthError(RuntimeError):
    """Raised on HTTP 401 (X-API-Key missing or invalid)."""


class TwitterApiRateLimitError(RuntimeError):
    """Raised on HTTP 429."""


class TwitterApiServerError(RuntimeError):
    """Raised on HTTP 5xx."""


@dataclass
class TwitterApiClient:
    """REST client for TwitterAPI.io.

    Replaces the previous ApifyClient. The shape (run_search, run_followers,
    from_env) is preserved so call sites in run.py / __main__.py / tests
    only need to rename the class.
    """

    api_key: str
    base_url: str = TWITTERAPI_BASE
    timeout_s: int = 60
    max_retries: int = 2

    @classmethod
    def from_env(cls) -> "TwitterApiClient":
        api_key = os.environ.get("TWITTERAPI_IO_API_KEY")
        if not api_key:
            raise RuntimeError("TWITTERAPI_IO_API_KEY not in environment")
        return cls(api_key=api_key)

    # --- low-level HTTP --------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
        }

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                r = requests.get(
                    url,
                    params=params,
                    headers=self._headers(),
                    timeout=self.timeout_s,
                )
            except requests.RequestException as e:
                last_exc = e
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise
            if r.status_code == 401:
                raise TwitterApiAuthError(
                    f"TwitterAPI.io auth failed: {r.text[:200]}"
                )
            if r.status_code == 429:
                if attempt < self.max_retries:
                    time.sleep(2 ** (attempt + 2))
                    continue
                raise TwitterApiRateLimitError(
                    f"TwitterAPI.io rate limit: {r.text[:200]}"
                )
            if 500 <= r.status_code < 600:
                last_exc = TwitterApiServerError(
                    f"TwitterAPI.io 5xx: {r.status_code}"
                )
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise last_exc
            if r.status_code >= 400:
                raise RuntimeError(
                    f"TwitterAPI.io error {r.status_code}: {r.text[:200]}"
                )
            return r.json()
        if last_exc:
            raise last_exc
        raise RuntimeError("TwitterAPI.io call failed without a recorded exception")

    def _walk_followers(self, handle: str, max_results: int) -> list[dict[str, Any]]:
        """Paginate get_user_followers via cursor. Returns normalized list."""
        out: list[dict[str, Any]] = []
        cursor: str | None = None
        # Hard cap on pages so a runaway pagination can't run forever.
        max_pages = max(1, (max_results + FOLLOWERS_MAX_PER_PAGE - 1) // FOLLOWERS_MAX_PER_PAGE)
        for _ in range(max_pages):
            params: dict[str, Any] = {
                "userName": handle,
                "page_size": FOLLOWERS_MAX_PER_PAGE,
            }
            if cursor:
                params["cursor"] = cursor
            data = self._get(FOLLOWERS_PATH, params)
            # Response shape (per TwitterAPI.io docs):
            #   { "followers": [ {...}, ... ], "next_cursor": "..."|null,
            #     "status": "success" }
            followers = data.get("followers") or data.get("users") or []
            for f in followers:
                if len(out) >= max_results:
                    break
                out.append(_normalize_follower(f))
            if len(out) >= max_results:
                break
            cursor = data.get("next_cursor")
            if not cursor:
                break
        return out

    # --- public surface (mirrors the old ApifyClient) --------------------

    def _walk_search(
        self,
        query: str,
        max_results: int,
        *,
        max_pages: int = 5,
    ) -> list[dict[str, Any]]:
        """Paginate advanced_search via next_cursor. Returns up to max_results.

        TwitterAPI.io caps each response at SEARCH_MAX_PER_PAGE tweets and
        signals more results via `has_next_page` + `next_cursor`. We follow
        the cursor until either the user's max_results ceiling is hit or
        has_next_page is false. The defensive max_pages cap (default 5)
        guards against a runaway cursor draining the credit budget — at 20
        tweets/page × 5 pages = 100 tweets, which covers all current
        max_results=50 calls with headroom.
        """
        out: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(max_pages):
            if len(out) >= max_results:
                break
            params: dict[str, Any] = {
                "query": query,
                "queryType": "Latest",
                "limit": min(SEARCH_MAX_PER_PAGE, max_results - len(out)),
            }
            if cursor:
                params["cursor"] = cursor
            data = self._get(SEARCH_PATH, params)
            tweets = data.get("tweets") or data.get("data") or []
            for t in tweets:
                out.append(_normalize_tweet(t))
                if len(out) >= max_results:
                    return out
            if not data.get("has_next_page"):
                break
            cursor = data.get("next_cursor")
            if not cursor:
                break
        return out

    def run_search(
        self,
        query: str,
        max_results: int = 50,
        since: str | None = None,
        cookies: dict[str, str] | None = None,  # noqa: ARG002 — kept for compat
    ) -> list[dict[str, Any]]:
        """Run an X advanced-search query via TwitterAPI.io.

        `query` is a raw advanced-search string (e.g., 'from:MiniMaxAI lang:en
        min_faves:5'). TwitterAPI.io accepts the same X operators.

        `since` is an ISO date string (YYYY-MM-DD). If provided, we pass it as
        a `since:` operator suffix — TwitterAPI.io does not expose a separate
        `since` param. We only inject it if the caller didn't already include
        a `since:` operator in the query.

        `cookies` is accepted for backward compatibility with the old
        ApifyClient signature but is ignored (TwitterAPI.io does not require
        user cookies).

        Returns up to max_results tweets, paginated via next_cursor (see
        _walk_search).
        """
        effective_query = query
        if since and "since:" not in query:
            effective_query = f"{query} since:{since}"
        return self._walk_search(effective_query, max_results, max_pages=5)

    def run_followers(
        self,
        handle: str,
        max_results: int = 200,
        cookies: dict[str, str] | None = None,  # noqa: ARG002 — kept for compat
    ) -> list[dict[str, Any]]:
        """Fetch the followers list for a handle. Paginated up to max_results.

        `cookies` is accepted for backward compatibility but is ignored.
        """
        return self._walk_followers(handle, max_results)

    def user_info(self, handle: str) -> dict[str, Any] | None:
        """Fetch a single user's public profile info.

        Used by the v1.2 `relevance audit-handles` subcommand to verify
        canonical_handles in data/filters/<model>.yaml.

        Returns a normalized dict with at least: handle, name, description,
        followers_count, verified. Returns None if the user is not found
        (HTTP 200 but no `data`).

        Raises TwitterApiAuthError on 401, TwitterApiRateLimitError on 429,
        TwitterApiServerError on 5xx, RuntimeError on other 4xx.
        """
        data = self._get(USER_INFO_PATH, {"userName": handle})
        # TwitterAPI.io shape: { "data": { ...user... }, "status": "success" }
        # or { "user": { ... } } on some endpoints. Fall back to the whole
        # response if neither key is present (defensive against future shape
        # changes — caller still gets a dict back).
        if isinstance(data, dict):
            user = data.get("data") or data.get("user") or data
        else:
            user = None
        if not user or not isinstance(user, dict):
            return None
        return _normalize_user(user)

    def get_article(self, tweet_id: str) -> dict[str, Any] | None:
        """Fetch the long-form X article body for a given tweet_id.

        The tweet_id is the integer id of the tweet that links to the
        article (not the article's own internal id). For URLs like
        `x.com/i/article/2064029478616182784`, the trailing path segment
        IS the tweet_id.

        Returns a normalized dict with at least: title, preview_text,
        contents (list of content blocks). Returns None if the article
        is not found (HTTP 200 but no `article` key) or if the
        underlying tweet has no long-form article attached.

        Raises TwitterApiAuthError on 401, TwitterApiRateLimitError on
        429, TwitterApiServerError on 5xx, RuntimeError on other 4xx.
        Cost: 100 credits per call.
        """
        if not tweet_id:
            return None
        data = self._get(ARTICLE_PATH, {"tweet_id": str(tweet_id)})
        if not isinstance(data, dict):
            return None
        article = data.get("article")
        if not article or not isinstance(article, dict):
            return None
        return _normalize_article(article)

    def probe_api(self) -> bool:
        """Lightweight liveness check: hit user/info on a known handle.

        Returns True iff the call succeeds with a non-empty response. Used by
        tests and operator diagnostics. Replaces the old cookie probe.
        """
        try:
            data = self._get(USER_INFO_PATH, {"userName": "MiniMaxAI"})
        except TwitterApiAuthError:
            return False
        except (TwitterApiRateLimitError, TwitterApiServerError, requests.RequestException):
            return True  # transient — not a liveness failure
        except Exception:
            return False
        return bool(data) and data.get("status") != "error"


# --- normalizers -----------------------------------------------------------


def _normalize_tweet(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize TwitterAPI.io tweet to the shape our Store.insert_posts expects.

    TwitterAPI.io tweet shape (per docs):
      { "id": "...", "text": "...", "createdAt": "...", "lang": "...",
        "likeCount": N, "retweetCount": N, "replyCount": N, "quoteCount": N,
        "bookmarkCount": N, "isReply": bool, "isRetweet": bool, "isQuote": bool,
        "inReplyToUserId": "...", "author": { "userName": "...", "name": "...",
          "followers": N, ..., "isBlueVerified": bool }, ... }

    Our store expects: id, text, lang, created_at, like_count,
    retweet_count, author_handle, in_reply_to_user_id, entities.
    """
    author = item.get("author") or {}
    return {
        "id": str(item.get("id") or ""),
        "text": item.get("text") or "",
        "lang": item.get("lang"),
        "created_at": item.get("createdAt") or item.get("created_at"),
        "like_count": int(item.get("likeCount") or 0),
        "retweet_count": int(item.get("retweetCount") or 0),
        "reply_count": int(item.get("replyCount") or 0),
        "quote_count": int(item.get("quoteCount") or 0),
        "bookmark_count": int(item.get("bookmarkCount") or 0),
        "is_reply": bool(item.get("isReply")),
        "is_retweet": bool(item.get("isRetweet")),
        "is_quote": bool(item.get("isQuote")),
        "in_reply_to_user_id": item.get("inReplyToUserId") or None,
        "author_handle": (
            author.get("userName")
            or author.get("screen_name")
            or item.get("userName")
            or ""
        ),
        "author_name": author.get("name") or "",
        "author_followers_count": int(author.get("followers") or 0),
        "author_verified": bool(
            author.get("isBlueVerified") or author.get("verified")
        ),
        # The store ignores unknown keys, so we leave the raw object too.
        "raw": item,
    }


def _normalize_follower(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize TwitterAPI.io follower to {handle, display_name, follower_count}.

    TwitterAPI.io follower shape (per docs):
      { "id": "...", "userName": "...", "name": "...", "followers": N, ... }
    """
    handle = item.get("userName") or item.get("screen_name") or item.get("handle") or ""
    display_name = item.get("name") or item.get("display_name") or ""
    follower_count = int(
        item.get("followers")
        or item.get("followers_count")
        or item.get("followerCount")
        or 0
    )
    return {
        "handle": str(handle),
        "display_name": str(display_name),
        "follower_count": follower_count,
    }


def _normalize_user(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize TwitterAPI.io user/info response to a flat dict.

    TwitterAPI.io user/info shape (per docs):
      { "id": "...", "userName": "...", "name": "...",
        "description": "...", "followers": N, "verified": bool, ... }
    """
    return {
        "handle": str(
            item.get("userName")
            or item.get("screen_name")
            or item.get("handle")
            or ""
        ),
        "name": str(item.get("name") or item.get("display_name") or ""),
        "description": str(item.get("description") or item.get("bio") or ""),
        "followers_count": int(
            item.get("followers")
            or item.get("followers_count")
            or item.get("followerCount")
            or 0
        ),
        "verified": bool(
            item.get("isBlueVerified")
            or item.get("verified")
            or False
        ),
        "id": str(item.get("id") or ""),
    }


def _normalize_article(article: dict[str, Any]) -> dict[str, Any]:
    """Trim the TwitterAPI.io article response to what we need.

    The API returns the full content tree (headers, lists, images,
    markdown blocks). For v1.4 we only store the title + preview_text
    + a flattened plain-text projection of the contents, since the
    dashboard headline column is a single short string.
    """
    contents = article.get("contents") or []
    plain_parts: list[str] = []
    for block in contents:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")
        btext = block.get("text", "")
        if not btext:
            continue
        if btype in {"header-one", "header-two", "header-three"}:
            plain_parts.append(btext.strip())
        elif btype in {"unstyled", "markdown"}:
            plain_parts.append(btext.strip())
        elif btype in {"unordered-list-item", "ordered-list-item"}:
            plain_parts.append(f"- {btext.strip()}")
        # image / gif / divider: no text contribution
    return {
        "title": (article.get("title") or "").strip() or None,
        "preview_text": (article.get("preview_text") or "").strip() or None,
        "plain_text": "\n\n".join(p for p in plain_parts if p) or None,
        "cover_media_img_url": article.get("cover_media_img_url"),
        "author": article.get("author"),
        "created_at": article.get("createdAt"),
    }
