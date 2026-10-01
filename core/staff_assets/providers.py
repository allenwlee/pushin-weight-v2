"""Opt-in SerpApi/Baidu discovery. Results are candidates, never verified portraits."""

import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests


def sanitized(value):
    if isinstance(value, dict):
        return {
            k: sanitized(v)
            for k, v in value.items()
            if k.lower()
            not in {"api_key", "api_token", "authorization", "access_token"}
        }
    if isinstance(value, list):
        return [sanitized(item) for item in value]
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        url = urlsplit(value)
        query = [
            (k, v)
            for k, v in parse_qsl(url.query, keep_blank_values=True)
            if k.lower() not in {"api_key", "token", "api_token", "access_token"}
        ]
        return urlunsplit(
            (url.scheme, url.netloc, url.path, urlencode(query), url.fragment)
        )
    return value


class SerpApiBaidu:
    name = "serpapi_baidu"

    def __init__(self, *, api_key):
        if not api_key:
            raise ValueError("Explicit SerpApi credential required")
        self.api_key = api_key

    def search(self, parameters):
        if (
            set(parameters) != {"engine", "q", "rn", "pn"}
            or parameters["engine"] != "baidu"
            or parameters["rn"] != 50
            or parameters["pn"] != 0
        ):
            raise ValueError("Only the bounded first Baidu page is supported")
        with requests.get(
            "https://serpapi.com/search.json",
            params={**parameters, "api_key": self.api_key},
            timeout=(5, 25),
            stream=True,
            allow_redirects=False,
        ) as response:
            if response.status_code != 200:
                raise ValueError(f"Provider HTTP status {response.status_code}")
            data = bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data) > 6 * 1024 * 1024:
                    raise ValueError("Provider response exceeded size limit")
            payload = json.loads(data)
        if not isinstance(payload, dict) or payload.get("error"):
            raise ValueError("Provider did not return a successful result")
        return sanitized(payload)


def media_candidates(payload):
    for section in ("organic_results", "inline_videos"):
        for result in payload.get(section, []):
            if not isinstance(result, dict) or not result.get("link"):
                continue
            thumbnail = result.get("thumbnail")
            if isinstance(thumbnail, dict):
                thumbnail = thumbnail.get("src") or thumbnail.get("url")
            if isinstance(thumbnail, str) and thumbnail.startswith(
                ("http://", "https://")
            ):
                yield {
                    "source_url": result["link"],
                    "original_url": thumbnail,
                    "source_kind": "search_thumbnail",
                    "discovery_provider": "SerpApi · Baidu",
                    "kind": "image",
                    "evidence": {
                        "title": result.get("title", ""),
                        "snippet": result.get("snippet", ""),
                        "candidate_only": True,
                    },
                }
            if section == "inline_videos":
                yield {
                    "source_url": result["link"],
                    "original_url": "",
                    "source_kind": "video_page",
                    "discovery_provider": "SerpApi · Baidu",
                    "kind": "video",
                    "evidence": {"title": result.get("title", ""), "downloaded": False},
                }
