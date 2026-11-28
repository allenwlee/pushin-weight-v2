"""Find exact release identities in the providers' own public model inventories."""

import json
import re
from urllib.parse import urlsplit

from scripts.benchmark_download_collector.identity import require
from scripts.benchmark_download_collector.sources import (
    OPENROUTER_MODELS_URL,
    SOURCE_URLS,
    AmbiguousCatalogMatch,
    opencode_url,
)

_NATIVE_ID = re.compile(r"([a-zA-Z0-9][a-zA-Z0-9._-]*)/([a-zA-Z0-9][a-zA-Z0-9._-]*)")
_LAB_LINK = re.compile(
    r"^- \[([^\]\n]+)\]\(https://opencode\.ai/data/([a-z0-9][a-z0-9_-]{0,80})\.md\): (\d+) models?\s*$"
)
_OPEN_CODE = "https://opencode.ai"


def _native_id(value):
    return (
        _NATIVE_ID.fullmatch(value)
        if isinstance(value, str) and len(value) <= 256
        else None
    )


def _slug_key(value):
    # Providers spell the same version 4.1 and 4-1. Keep 4.1 distinct from 41.
    return re.sub(r"[\W_]+", "-", value.casefold()).strip("-")


def _matches_model(name, slug, matches):
    return matches(name) and (matches(slug) or _slug_key(slug) == _slug_key(name))


def _json_object(body):
    obj = json.loads(body)
    require(isinstance(obj, dict), "expected a provider catalog object")
    return obj


def _router_listing(row, matches, owns):
    identifier = row.get("id")
    model = _native_id(identifier)
    canonical = _native_id(row.get("canonical_slug"))
    if not model or not canonical or model[1].casefold() != canonical[1].casefold():
        return None
    if not owns(model[1]):
        return None
    name = row.get("name")
    if not isinstance(name, str):
        return None
    issuer, sep, label = name.partition(": ")
    if sep and not owns(issuer):
        return None
    if not _matches_model(label if sep else name, model[2], matches):
        return None
    # Public catalog IDs can name routers or moving aliases. A dated revision of
    # the same model is normal; a different variant behind the alias is not.
    current, resolved = _slug_key(model[2]), _slug_key(canonical[2])
    if re.search(r"(?:^|-)(?:latest|auto|free|fallback)(?:-|$)", current):
        return None
    if resolved != current and not re.fullmatch(
        re.escape(current) + r"-\d{8}", resolved
    ):
        return None
    return (
        identifier,
        "catalog_id",
        "https://openrouter.ai/" + identifier,
        {"canonical_slug": row["canonical_slug"]},
    )


def openrouter_candidates(fetch, matches, owns):
    """Only the catalog supplies catalog_id. Rankings use separate provider publications."""
    offset, limit = 0, 1000
    candidates = []
    # One request covers today's catalog. A partial page cannot rule out a
    # competing match, including when a continuation fails or the budget expires.
    while offset < 10000:
        doc = _json_object(
            fetch(OPENROUTER_MODELS_URL, {"offset": offset, "limit": limit})
        )
        rows = doc.get("data")
        if not isinstance(rows, list) or len(rows) > limit:
            raise ValueError("invalid OpenRouter model catalog page")
        for row in rows:
            require(
                isinstance(row, dict) and isinstance(row.get("id"), str),
                "invalid OpenRouter catalog row",
            )
            candidate = _router_listing(row, matches, owns)
            if candidate:
                candidates.append(candidate)
        offset += len(rows)
        total = doc.get("total_count")
        links = doc.get("links", {})
        if not isinstance(links, dict) or (
            total is not None and (type(total) is not int or total < offset)
        ):
            raise ValueError("inconsistent OpenRouter catalog pagination")
        more = bool(links.get("next")) or (
            offset < total if total is not None else len(rows) == limit
        )
        if not more:
            if len(candidates) > 1:
                raise AmbiguousCatalogMatch("multiple OpenRouter identifiers")
            return candidates
        if not rows:
            break
    raise ValueError("incomplete OpenRouter model catalog")


def _opencode_labs(body):
    text = body.decode("utf-8")
    section = re.search(
        r"^## Labs[ \t]*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    if not section:
        raise ValueError("missing OpenCode lab directory")
    labs = []
    for line in section[1].strip().splitlines():
        if not line.strip():
            continue
        lab = _LAB_LINK.fullmatch(line)
        if not lab:
            raise ValueError("invalid OpenCode lab directory")
        labs.append((lab[1], lab[2], int(lab[3])))
    if not labs:
        raise ValueError("empty OpenCode lab directory")
    return labs


def opencode_candidates(fetch, matches, owns):
    """Use the lab inventory (includes models outside the usage leaderboard)."""
    candidates = []
    for name, lab, count in _opencode_labs(fetch(SOURCE_URLS["opencode"])):
        if not (owns(lab) or owns(name)):
            continue
        lab_url = f"{_OPEN_CODE}/data/{lab}"
        doc = _json_object(fetch(lab_url + ".json"))
        owner, rows = doc.get("lab"), doc.get("models")
        if (
            doc.get("page") != lab_url
            or not isinstance(owner, dict)
            or owner.get("id") != lab
            or owner.get("name") != name
            or not isinstance(rows, list)
            or len(rows) != count
        ):
            raise ValueError("inconsistent OpenCode lab catalog")
        for row in rows:
            require(
                isinstance(row, dict) and isinstance(row.get("name"), str),
                "invalid OpenCode model listing",
            )
            native = _native_id(row.get("id"))
            if (
                not native
                or native[1] != lab
                or not _matches_model(row["name"], native[2], matches)
            ):
                continue
            page = row.get("page")
            require(isinstance(page, str), "missing OpenCode model page")
            path = urlsplit(page).path + ".json"
            url = opencode_url(path)
            if url != page + ".json" or not path.startswith(f"/data/{lab}/"):
                raise ValueError("invalid OpenCode model page")
            candidates.append((row, name, lab, path))
    if len(candidates) > 1:
        raise AmbiguousCatalogMatch("multiple OpenCode identifiers")
    if not candidates:
        return []
    row, name, lab, path = candidates[0]
    detail = _json_object(fetch(opencode_url(path)))
    model = detail.get("model")
    if (
        detail.get("page") != row["page"]
        or not isinstance(model, dict)
        or model.get("id") != row["id"]
        or model.get("name") != row["name"]
        or model.get("lab") != lab
        or model.get("labName") != name
    ):
        raise ValueError("OpenCode model detail disagrees with lab catalog")
    return [(row["id"], "model_id", row["page"], {"endpoint_path": path})]
