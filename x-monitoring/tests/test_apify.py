# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.apify (TwitterAPI.io client)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from x_monitor.apify import (
    FOLLOWERS_MAX_PER_PAGE,
    TwitterApiAuthError,
    TwitterApiClient,
    TwitterApiRateLimitError,
    TwitterApiServerError,
    _normalize_follower,
    _normalize_tweet,
    _normalize_article,
)


# --- error mapping --------------------------------------------------------


def _mock_response(status: int, body: dict | list | str = {}) -> MagicMock:
    m = MagicMock()
    m.status_code = status
    m.text = json.dumps(body) if isinstance(body, (dict, list)) else body
    m.json.return_value = body
    m.raise_for_status = MagicMock()
    return m


def test_run_search_raises_auth_error_on_401():
    client = TwitterApiClient(api_key="x", max_retries=0)
    with patch.object(requests, "get", return_value=_mock_response(401, "unauth")):
        with pytest.raises(TwitterApiAuthError):
            client.run_search("from:x")


def test_run_search_raises_rate_limit_on_429():
    client = TwitterApiClient(api_key="x", max_retries=0)
    with patch.object(requests, "get", return_value=_mock_response(429, "rate")):
        with pytest.raises(TwitterApiRateLimitError):
            client.run_search("from:x")


def test_run_search_raises_server_error_on_500():
    client = TwitterApiClient(api_key="x", max_retries=0)
    with patch.object(requests, "get", return_value=_mock_response(500, "boom")):
        with pytest.raises(TwitterApiServerError):
            client.run_search("from:x")


def test_run_search_passes_query_as_param():
    """The new client must send `query` (not searchTerms/maxItems/mode)."""
    client = TwitterApiClient(api_key="x", max_retries=0)
    with patch.object(requests, "get", return_value=_mock_response(200, {"tweets": []})) as mock_get:
        client.run_search("from:MiniMaxAI lang:en", max_results=10)
        args, kwargs = mock_get.call_args
        assert kwargs["params"]["query"] == "from:MiniMaxAI lang:en"
        assert kwargs["params"]["limit"] == 10


def test_run_search_appends_since_if_provided():
    client = TwitterApiClient(api_key="x", max_retries=0)
    with patch.object(requests, "get", return_value=_mock_response(200, {"tweets": []})) as mock_get:
        client.run_search("from:MiniMaxAI", since="2026-06-01")
        args, kwargs = mock_get.call_args
        assert "since:2026-06-01" in kwargs["params"]["query"]


def test_run_search_does_not_double_since():
    """If user already wrote since: in the query, don't append a second one."""
    client = TwitterApiClient(api_key="x", max_retries=0)
    with patch.object(requests, "get", return_value=_mock_response(200, {"tweets": []})) as mock_get:
        client.run_search("from:x since:2026-06-01", since="2026-06-02")
        args, kwargs = mock_get.call_args
        # The user's since:2026-06-01 wins; we don't append.
        assert kwargs["params"]["query"].count("since:") == 1


def test_run_search_cookies_arg_is_ignored():
    """Backward-compat: old call sites still pass cookies= — must not error."""
    client = TwitterApiClient(api_key="x", max_retries=0)
    with patch.object(requests, "get", return_value=_mock_response(200, {"tweets": []})):
        out = client.run_search(
            "from:x",
            cookies={"auth_token": "ignored", "ct0": "ignored"},
        )
        assert out == []


def test_run_search_returns_empty_on_200_with_no_tweets():
    client = TwitterApiClient(api_key="x", max_retries=0)
    with patch.object(requests, "get", return_value=_mock_response(200, {"tweets": []})):
        assert client.run_search("from:x") == []


def test_run_search_normalizes_tweet_shape():
    """Output must have the keys our Store.insert_posts expects."""
    client = TwitterApiClient(api_key="x", max_retries=0)
    raw = {
        "tweets": [
            {
                "id": "123",
                "text": "hello",
                "lang": "en",
                "createdAt": "2026-06-01T00:00:00Z",
                "likeCount": 10,
                "retweetCount": 2,
                "replyCount": 1,
                "quoteCount": 0,
                "bookmarkCount": 0,
                "isReply": True,
                "isRetweet": False,
                "inReplyToUserId": "999",
                "author": {
                    "userName": "alice",
                    "name": "Alice",
                    "followers": 5000,
                    "isBlueVerified": True,
                },
            }
        ]
    }
    with patch.object(requests, "get", return_value=_mock_response(200, raw)):
        out = client.run_search("from:alice")
    assert len(out) == 1
    t = out[0]
    assert t["id"] == "123"
    assert t["favorite_count"] == 10
    assert t["retweet_count"] == 2
    assert t["author_handle"] == "alice"
    assert t["author_followers_count"] == 5000
    assert t["author_verified"] is True
    assert t["in_reply_to_user_id"] == "999"


# --- run_followers --------------------------------------------------------


def test_run_followers_single_page():
    client = TwitterApiClient(api_key="x", max_retries=0)
    body = {
        "followers": [
            {"userName": "alice", "name": "Alice", "followers": 100},
            {"userName": "bob", "name": "Bob", "followers": 50},
        ],
        "next_cursor": None,
    }
    with patch.object(requests, "get", return_value=_mock_response(200, body)):
        out = client.run_followers("MiniMaxAI", max_results=200)
    assert len(out) == 2
    assert out[0]["handle"] == "alice"
    assert out[0]["follower_count"] == 100
    assert out[1]["handle"] == "bob"
    assert out[1]["follower_count"] == 50


def test_run_followers_paginates_via_cursor():
    client = TwitterApiClient(api_key="x", max_retries=0)
    page1 = {
        "followers": [
            {"userName": f"user{i}", "name": f"User{i}", "followers": i}
            for i in range(FOLLOWERS_MAX_PER_PAGE)
        ],
        "next_cursor": "page2",
    }
    page2 = {
        "followers": [{"userName": "last", "name": "Last", "followers": 1}],
        "next_cursor": None,
    }
    with patch.object(requests, "get", side_effect=[
        _mock_response(200, page1),
        _mock_response(200, page2),
    ]) as mock_get:
        out = client.run_followers("MiniMaxAI", max_results=250)
    assert len(out) == FOLLOWERS_MAX_PER_PAGE + 1
    # Second call must carry the cursor
    second_call_params = mock_get.call_args_list[1].kwargs["params"]
    assert second_call_params.get("cursor") == "page2"


def test_run_followers_stops_at_max_results():
    """Even if the API keeps returning pages, we stop at max_results."""
    client = TwitterApiClient(api_key="x", max_retries=0)
    page1 = {
        "followers": [
            {"userName": f"u{i}", "name": f"U{i}", "followers": 1}
            for i in range(FOLLOWERS_MAX_PER_PAGE)
        ],
        "next_cursor": "more",
    }
    page2 = {
        "followers": [{"userName": "extra", "name": "X", "followers": 1}],
        "next_cursor": None,
    }
    with patch.object(requests, "get", side_effect=[
        _mock_response(200, page1),
        _mock_response(200, page2),
    ]):
        out = client.run_followers("MiniMaxAI", max_results=50)
    assert len(out) == 50


def test_run_followers_cookies_arg_is_ignored():
    client = TwitterApiClient(api_key="x", max_retries=0)
    body = {"followers": [], "next_cursor": None}
    with patch.object(requests, "get", return_value=_mock_response(200, body)):
        out = client.run_followers(
            "MiniMaxAI", cookies={"auth_token": "x", "ct0": "y"}
        )
        assert out == []


# --- probe_api ------------------------------------------------------------


def test_probe_api_returns_false_on_401():
    client = TwitterApiClient(api_key="x", max_retries=0)
    with patch.object(requests, "get", return_value=_mock_response(401, "unauth")):
        assert client.probe_api() is False


def test_probe_api_returns_true_on_success():
    client = TwitterApiClient(api_key="x", max_retries=0)
    with patch.object(requests, "get", return_value=_mock_response(200, {
        "status": "success", "data": {"userName": "MiniMaxAI"}
    })):
        assert client.probe_api() is True


def test_probe_api_returns_true_on_transient_5xx():
    client = TwitterApiClient(api_key="x", max_retries=0)
    with patch.object(requests, "get", return_value=_mock_response(500, "boom")):
        # Transient errors are NOT a liveness failure.
        assert client.probe_api() is True


# --- from_env -------------------------------------------------------------


def test_from_env_requires_key(monkeypatch):
    monkeypatch.delenv("TWITTERAPI_IO_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TWITTERAPI_IO_API_KEY"):
        TwitterApiClient.from_env()


def test_from_env_reads_key(monkeypatch):
    monkeypatch.setenv("TWITTERAPI_IO_API_KEY", "abc")
    c = TwitterApiClient.from_env()
    assert c.api_key == "abc"
    assert c.base_url == "https://api.twitterapi.io"


# --- normalizer unit tests -----------------------------------------------


def test_normalize_tweet_handles_missing_fields():
    out = _normalize_tweet({})
    assert out["id"] == ""
    assert out["favorite_count"] == 0
    assert out["author_handle"] == ""
    assert out["in_reply_to_user_id"] is None


def test_normalize_follower_handles_missing_fields():
    out = _normalize_follower({})
    assert out["handle"] == ""
    assert out["display_name"] == ""
    assert out["follower_count"] == 0



class TestNormalizeArticle:
    """_normalize_article trims the API response to title + plain text."""

    def test_minimal(self):
        out = _normalize_article({"title": "Hello", "preview_text": "World"})
        assert out["title"] == "Hello"
        assert out["preview_text"] == "World"
        assert out["plain_text"] is None

    def test_strips_empty_title(self):
        out = _normalize_article({"title": "  ", "preview_text": "P"})
        assert out["title"] is None  # whitespace-only -> None
        assert out["preview_text"] == "P"

    def test_flattens_content_blocks(self):
        out = _normalize_article({
            "title": "T",
            "contents": [
                {"type": "header-one", "text": "Intro"},
                {"type": "unstyled", "text": "Para 1"},
                {"type": "unordered-list-item", "text": "Item A"},
                {"type": "image"},  # ignored
                {"type": "divider"},  # ignored
            ],
        })
        assert out["title"] == "T"
        assert "Intro" in out["plain_text"]
        assert "Para 1" in out["plain_text"]
        assert "- Item A" in out["plain_text"]

    def test_preserves_cover_and_author(self):
        out = _normalize_article({
            "title": "T",
            "cover_media_img_url": "https://pbs.twimg.com/media/x.jpg",
            "author": {"userName": "@foo"},
            "createdAt": "Fri Mar 28 09:01:12 +0000 2025",
        })
        assert out["cover_media_img_url"] == "https://pbs.twimg.com/media/x.jpg"
        assert out["author"] == {"userName": "@foo"}
        assert out["created_at"] == "Fri Mar 28 09:01:12 +0000 2025"


class TestGetArticle:
    """TwitterApiClient.get_article() calls /twitter/article and normalizes."""

    def _client(self):
        from x_monitor.apify import TwitterApiClient
        return TwitterApiClient(api_key="test-key", base_url="https://api.example.com")

    def test_get_article_returns_normalized_dict(self):
        client = self._client()
        api_response = {
            "article": {
                "title": "Big AI News",
                "preview_text": "Short preview.",
                "contents": [
                    {"type": "header-one", "text": "Intro"},
                    {"type": "unstyled", "text": "Para 1"},
                ],
                "author": {"userName": "@ai"},
                "createdAt": "Fri Mar 28 09:01:12 +0000 2025",
            }
        }
        with patch.object(client, "_get", return_value=api_response) as mock_get:
            result = client.get_article("2064029478616182784")
        assert result is not None
        assert result["title"] == "Big AI News"
        assert result["preview_text"] == "Short preview."
        assert "Intro" in result["plain_text"]
        mock_get.assert_called_once()
        # Must pass tweet_id as the only required param.
        args, kwargs = mock_get.call_args
        # _get(path, params) is called with params as a positional arg.
        # args = (path, params), kwargs = {}.
        assert args[0] == "/twitter/article"  # ARTICLE_PATH
        assert args[1] == {"tweet_id": "2064029478616182784"}

    def test_get_article_returns_none_when_no_article_key(self):
        # API returns 200 but `article` is missing or null.
        client = self._client()
        with patch.object(client, "_get", return_value={"article": None}):
            assert client.get_article("123") is None
        with patch.object(client, "_get", return_value={}):
            assert client.get_article("123") is None

    def test_get_article_returns_none_for_empty_tweet_id(self):
        client = self._client()
        # Empty/None should not even call _get.
        with patch.object(client, "_get") as mock_get:
            assert client.get_article("") is None
            assert client.get_article(None) is None  # type: ignore[arg-type]
        mock_get.assert_not_called()

    def test_get_article_returns_none_for_non_dict_response(self):
        client = self._client()
        with patch.object(client, "_get", return_value="not a dict"):
            assert client.get_article("123") is None
        with patch.object(client, "_get", return_value=["list", "of", "stuff"]):
            assert client.get_article("123") is None

    def test_get_article_propagates_auth_error(self):
        from x_monitor.apify import TwitterApiAuthError
        client = self._client()
        with patch.object(
            client, "_get",
            side_effect=TwitterApiAuthError("bad key"),
        ):
            with pytest.raises(TwitterApiAuthError):
                client.get_article("123")

    def test_get_article_propagates_rate_limit(self):
        from x_monitor.apify import TwitterApiRateLimitError
        client = self._client()
        with patch.object(
            client, "_get",
            side_effect=TwitterApiRateLimitError("429"),
        ):
            with pytest.raises(TwitterApiRateLimitError):
                client.get_article("123")
