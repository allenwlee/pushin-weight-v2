"""Public GitHub metadata, pinned small files and checked pagination only."""

from __future__ import annotations

import base64
import json
import re
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, quote, urlsplit

import httpx

from core.measurement_taxonomy import require
from scripts.benchmark_download_collector.sources import Budget, SourceError

API = "https://api.github.com"
API_VERSION = "2026-03-10"  # Verified retained primary REST documentation.
METADATA_FILES = frozenset(
    {"README.md", "config.json", "model_index.json", "generation_config.json"}
)
NAME = r"[A-Za-z0-9_.-]{1,100}"
ENDPOINT = re.compile(
    rf"/(?:users/{NAME}|(?:orgs|users)/{NAME}/repos|repos/{NAME}/{NAME}(?:/(?:releases|tags|commits|git/trees/[0-9a-f]{{40,64}}|contents/(?:README\.md|config\.json|model_index\.json|generation_config\.json)))?)"
)


@dataclass(frozen=True)
class GitHubResponse:
    status: int
    payload: dict | list | None
    url: str
    next_url: str | None = None
    etag: str | None = None
    retry_at: datetime | None = None
    observed_at: datetime | None = None


class GitHubMetadataClient:
    def __init__(self, budget: Budget, *, key=None):
        self.budget, self.key = budget, key

    @staticmethod
    def checked_url(url):
        parsed = urlsplit(url)
        require(
            parsed.scheme == "https"
            and parsed.hostname == "api.github.com"
            and parsed.port in (None, 443)
            and not parsed.username
            and not parsed.password
            and not parsed.fragment
            and ENDPOINT.fullmatch(parsed.path),
            "untrusted GitHub endpoint",
        )
        query = parse_qs(parsed.query, strict_parsing=True)
        require(
            set(query)
            <= {
                "page",
                "per_page",
                "sort",
                "direction",
                "type",
                "ref",
                "since",
                "until",
            },
            "untrusted GitHub query",
        )
        for key in ("page", "per_page"):
            if key in query:
                require(
                    len(query[key]) == 1
                    and query[key][0].isascii()
                    and query[key][0].isdigit()
                    and 0
                    < int(query[key][0])
                    <= (100 if key == "per_page" else 100000),
                    "invalid GitHub page",
                )
        return url

    def get(self, url, *, params=None, etag=None):
        self.checked_url(url)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
        }
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        if etag:
            require(
                isinstance(etag, str)
                and len(etag) <= 256
                and "\r" not in etag
                and "\n" not in etag,
                "invalid ETag",
            )
            headers["If-None-Match"] = etag
        request = self.budget.public_request(url, params, headers=headers)
        self.checked_url(str(request.url))
        try:
            with closing(
                self.budget.client.send(
                    request, stream=True, auth=None, follow_redirects=False
                )
            ) as response:
                now = datetime.now(UTC)
                status = response.status_code
                if status == 200:
                    body = self.budget.response_bytes(response, cumulative=True)
                    try:
                        payload = json.loads(body)
                    except (ValueError, UnicodeDecodeError) as exc:
                        raise SourceError("malformed_json") from exc
                    require(
                        isinstance(payload, (dict, list)), "malformed GitHub payload"
                    )
                else:
                    payload = None
                next_url = response.links.get("next", {}).get("url")
                if next_url:
                    require(
                        urlsplit(next_url).path == urlsplit(url).path,
                        "untrusted pagination path",
                    )
                    try:
                        self.checked_url(next_url)
                    except ValueError as exc:
                        raise ValueError("untrusted pagination URL") from exc
                retry_at = None
                if status in {403, 429}:
                    delay = response.headers.get("retry-after")
                    reset = response.headers.get("x-ratelimit-reset")
                    candidates = [now + timedelta(minutes=15)]
                    if delay and delay.isdigit():
                        candidates.append(
                            now + timedelta(seconds=min(int(delay), 86400))
                        )
                    if reset and reset.isdigit():
                        try:
                            candidates.append(datetime.fromtimestamp(int(reset), UTC))
                        except (OverflowError, ValueError, OSError):
                            pass
                    retry_at = max(candidates)
                return GitHubResponse(
                    status,
                    payload,
                    str(request.url),
                    next_url,
                    response.headers.get("etag"),
                    retry_at,
                    now,
                )
        except httpx.HTTPError as exc:
            raise SourceError("request_error") from exc

    def owner(self, login):
        require(
            isinstance(login, str) and re.fullmatch(NAME, login), "invalid GitHub owner"
        )
        return self.get(f"{API}/users/{quote(login, safe='')}")

    def repositories(
        self, login, account_kind, *, next_url=None, etag=None, per_page=100
    ):
        require(
            isinstance(login, str) and re.fullmatch(NAME, login), "invalid GitHub owner"
        )
        require(
            account_kind in {"organization", "individual"},
            "reviewed account kind required",
        )
        endpoint = f"{API}/{'orgs' if account_kind == 'organization' else 'users'}/{login}/repos"
        require(
            next_url is None or urlsplit(next_url).path == urlsplit(endpoint).path,
            "pagination scope mismatch",
        )
        return self.get(
            next_url or endpoint,
            params=None
            if next_url
            else {
                "type": "public" if account_kind == "organization" else "owner",
                "sort": "created",
                "direction": "desc",
                "per_page": per_page,
            },
            etag=etag,
        )

    def repository(self, full_name):
        return self.get(self.repo_url(full_name))

    @staticmethod
    def repo_url(full_name):
        require(
            isinstance(full_name, str) and re.fullmatch(rf"{NAME}/{NAME}", full_name),
            "invalid GitHub repository",
        )
        return f"{API}/repos/{full_name}"

    def events(self, full_name, kind, *, next_url=None, per_page=100):
        require(
            kind in {"releases", "tags", "commits"}, "unsupported GitHub evidence kind"
        )
        endpoint = self.repo_url(full_name) + "/" + kind
        require(
            next_url is None or urlsplit(next_url).path == urlsplit(endpoint).path,
            "pagination scope mismatch",
        )
        return self.get(
            next_url or endpoint, params=None if next_url else {"per_page": per_page}
        )

    def tree(self, full_name, revision):
        self.revision(revision)
        return self.get(self.repo_url(full_name) + "/git/trees/" + revision)

    @staticmethod
    def revision(value):
        require(
            isinstance(value, str)
            and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value),
            "pinned revision required",
        )

    def file(self, full_name, filename, revision):
        self.revision(revision)
        require(filename in METADATA_FILES, "small metadata file required")
        result = self.get(
            self.repo_url(full_name) + "/contents/" + filename, params={"ref": revision}
        )
        if result.status == 200:
            data = result.payload
            require(
                isinstance(data, dict)
                and data.get("type") == "file"
                and data.get("encoding") == "base64"
                and type(data.get("size")) is int
                and 0 <= data["size"] <= 128 * 1024,
                "small metadata response required",
            )
            try:
                text = base64.b64decode(data["content"], validate=False)
                require(
                    len(text) == data["size"] and len(text) <= 128 * 1024,
                    "metadata byte size mismatch",
                )
                text.decode("utf-8")
            except (ValueError, KeyError, UnicodeDecodeError) as exc:
                raise SourceError("malformed_metadata_file") from exc
        return result
