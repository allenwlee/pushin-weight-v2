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
    rf"/(?:users/{NAME}|(?:orgs|users)/{NAME}/repos|repos/{NAME}/{NAME}(?:/(?:releases(?:/[1-9][0-9]*/assets)?|tags|commits|git/trees/[0-9a-f]{{40,64}}|contents/(?:README\.md|config\.json|model_index\.json|generation_config\.json)))?|repositories/[1-9][0-9]*/(?:releases(?:/[1-9][0-9]*/assets)?|tags|commits))"
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
    collection_request_id: str | None = None


class GitHubMetadataClient:
    def __init__(self, budget: Budget, *, key=None):
        self.budget, self.key = budget, key
        self.capture = None
        self.collection_scope = None

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

    def get(self, url, *, params=None, etag=None, pagination_paths=None):
        self.checked_url(url)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "PushinWeight-public-metadata",
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
        receipt = (
            self.capture.start(self.collection_scope, str(request.url), etag=etag)
            if self.capture
            else None
        )
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
                        if receipt:
                            self.capture.received(
                                receipt,
                                body=None,
                                status=status,
                                response_bytes=len(body),
                                error_code="malformed_json",
                            )
                        raise SourceError("malformed_json") from exc
                    if receipt:
                        path = urlsplit(str(request.url)).path
                        reason = None
                        if path.endswith("/releases"):
                            reason = "awaiting_public_release_selection"
                        elif re.fullmatch(r"/repos/[^/]+/[^/]+", path) and (
                            not isinstance(payload, dict)
                            or payload.get("private") is not False
                        ):
                            reason = "repository_not_proven_public"
                        elif path.endswith("/repos") and (
                            not isinstance(payload, list)
                            or any(
                                not isinstance(row, dict)
                                or row.get("private") is not False
                                for row in payload
                            )
                        ):
                            reason = "inventory_not_proven_public"
                        self.capture.received(
                            receipt,
                            body=body if reason is None else None,
                            status=status,
                            response_bytes=len(body),
                            error_code=reason,
                        )
                    require(
                        isinstance(payload, (dict, list)), "malformed GitHub payload"
                    )
                else:
                    payload = None
                    if receipt:
                        self.capture.received(receipt, body=None, status=status)
                next_url = response.links.get("next", {}).get("url")
                if next_url:
                    require(
                        urlsplit(next_url).path
                        in (pagination_paths or {urlsplit(url).path}),
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
                if receipt:
                    self.capture.response_metadata(
                        receipt,
                        etag=response.headers.get("etag"),
                        cursor=next_url,
                        retry_after_at=retry_at,
                    )
                return GitHubResponse(
                    status,
                    payload,
                    str(request.url),
                    next_url,
                    response.headers.get("etag"),
                    retry_at,
                    now,
                    str(receipt.pk) if receipt else None,
                )
        except httpx.HTTPError as exc:
            if receipt:
                self.capture.failed(receipt)
            raise SourceError("request_error") from exc
        except SourceError as exc:
            if receipt:
                self.capture.failed(receipt, error_code=str(exc))
            raise

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

    def events(
        self, full_name, kind, *, repository_id=None, next_url=None, per_page=100
    ):
        require(
            kind in {"releases", "tags", "commits"}, "unsupported GitHub evidence kind"
        )
        endpoint = self.repo_url(full_name) + "/" + kind
        paths = {urlsplit(endpoint).path}
        if repository_id is not None:
            require(
                type(repository_id) is int and repository_id > 0,
                "native repository ID required",
            )
            # GitHub's Link header can switch from the name to its stable ID.
            paths.add(f"/repositories/{repository_id}/{kind}")
        require(
            next_url is None or urlsplit(next_url).path in paths,
            "pagination scope mismatch",
        )
        return self.get(
            next_url or endpoint,
            params=None if next_url else {"per_page": per_page},
            pagination_paths=paths,
        )

    def tree(self, full_name, revision):
        self.revision(revision)
        return self.get(self.repo_url(full_name) + "/git/trees/" + revision)

    def release_assets(
        self, full_name, release_id, *, repository_id, next_url=None, per_page=100
    ):
        """Metadata JSON only; never follow an asset's binary download URL."""
        require(
            type(release_id) is int
            and release_id > 0
            and type(repository_id) is int
            and repository_id > 0,
            "native repository and release IDs required",
        )
        require(type(per_page) is int and 1 <= per_page <= 100, "invalid page size")
        suffix = f"/releases/{release_id}/assets"
        endpoint = self.repo_url(full_name) + suffix
        paths = {urlsplit(endpoint).path, f"/repositories/{repository_id}{suffix}"}
        require(
            next_url is None or urlsplit(next_url).path in paths,
            "pagination scope mismatch",
        )
        return self.get(
            next_url or endpoint,
            params=None if next_url else {"per_page": per_page},
            pagination_paths=paths,
        )

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
