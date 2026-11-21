"""Provider-independent X data operations and capability declarations.

Adapters return the established XClient shapes; a provider must raise
UnsupportedOperation for an unavailable operation rather than fabricate data.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Protocol


class XDataOperation(str, Enum):
    SEARCH = "search"
    TWEETS_BY_IDS = "tweets_by_ids"
    USER_INFO = "user_info"
    USER_ABOUT = "user_about"
    QUOTES = "quotes"
    FOLLOWERS = "followers"
    LIST_MEMBERS = "list_members"
    ARTICLE = "article"


class UnsupportedOperation(NotImplementedError):
    pass


class XDataProvider(Protocol):
    name: str
    capabilities: frozenset[XDataOperation]

    def search_page(self, query: str, cursor: str | None, **options: Any) -> Any: ...
    def normalize_page(self, response: Any, *, page_number: int, max_results: int) -> Any: ...
    def tweets_by_ids(self, ids: list[str]) -> Any: ...
    def user_info(self, handle: str) -> Any: ...
    def user_about(self, handle: str) -> Any: ...
    def quotes(self, tweet_id: str, **options: Any) -> Any: ...
    def followers(self, handle: str, **options: Any) -> Any: ...
    def list_members(self, list_id: str, **options: Any) -> Any: ...
    def article(self, tweet_id: str) -> Any: ...


def parse_provider_order(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ("twitterapi", "twexapi")
    names = tuple(part.strip().lower() for part in value.split(","))
    if not names or any(name not in {"twitterapi", "twexapi"} for name in names) or len(set(names)) != len(names):
        raise ValueError("X_DATA_PROVIDER_ORDER must list distinct known providers")
    return names


class _ProviderBase:
    """Explicitly unsupported methods remain so until their adapter is verified."""

    def tweets_by_ids(self, ids): raise UnsupportedOperation("tweets_by_ids")
    def user_info(self, handle): raise UnsupportedOperation("user_info")
    def user_about(self, handle): raise UnsupportedOperation("user_about")
    def quotes(self, tweet_id, **options): raise UnsupportedOperation("quotes")
    def followers(self, handle, **options): raise UnsupportedOperation("followers")
    def list_members(self, list_id, **options): raise UnsupportedOperation("list_members")
    def article(self, tweet_id): raise UnsupportedOperation("article")


class TwitterAPIProvider(_ProviderBase):
    name = "twitterapi"
    capabilities = frozenset({XDataOperation.SEARCH, XDataOperation.TWEETS_BY_IDS,
                              XDataOperation.USER_INFO, XDataOperation.QUOTES,
                              XDataOperation.FOLLOWERS, XDataOperation.LIST_MEMBERS,
                              XDataOperation.ARTICLE})

    def __init__(self, client): self.client = client
    def search_page(self, query, cursor=None, **options):
        from x_monitor.x_client import SEARCH_PATH
        params = {"query": query, "queryType": "Latest", "limit": options.pop("limit", 20)}
        if cursor: params["cursor"] = cursor
        return self.client._get(SEARCH_PATH, params, **options)
    def normalize_page(self, response, *, page_number, max_results):
        from x_monitor.x_client import search_page_from_response
        return search_page_from_response(response, page_number=page_number, max_results=max_results)
    def tweets_by_ids(self, ids): return self.client.get_tweets_by_ids(ids)
    def user_info(self, handle): return self.client.user_info(handle)
    def quotes(self, tweet_id, **options): return self.client.get_quote_tweets(tweet_id, **options)
    def followers(self, handle, **options): return self.client.run_followers(handle, **options)
    def list_members(self, list_id, **options): return self.client.run_list_members(list_id, **options)
    def article(self, tweet_id): return self.client.get_article(tweet_id)


class TwexAPIProvider(_ProviderBase):
    name = "twexapi"
    capabilities = frozenset({XDataOperation.SEARCH})

    def __init__(self, client): self.client = client
    def search_page(self, query, cursor=None, **options):
        return self.client._twex_guarded_search(query, cursor, **options)
    def normalize_page(self, response, *, page_number, max_results):
        from x_monitor.x_client import twexapi_search_page
        return twexapi_search_page(response, page_number=page_number, max_results=max_results)
