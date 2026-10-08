"""Frozen canonical identities and deliberately explicit provider mappings."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from core.hf_metadata_client import REPO_ID

SCHEMA_VERSION = 1


def require(condition, message):
    if not condition:
        raise ValueError(message)


def day(value):
    require(isinstance(value, str), "date must be YYYY-MM-DD")
    result = date.fromisoformat(value)
    require(result.isoformat() == value, "date must be YYYY-MM-DD")
    return result


def timestamp(value):
    require(isinstance(value, str), "timestamp must be an ISO string")
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None, "timestamp must have a timezone")
    return result


def days(start, end):
    first, last = day(start), day(end)
    require(0 <= (last - first).days < 366, "date range must contain 1–366 days")
    return [
        (first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)
    ]


def count(value):
    require(type(value) is int and value >= 0, "count must be a nonnegative integer")
    return value


def indexed(rows, key):
    require(isinstance(rows, list), f"{key} records must be a list")
    result = {}
    for row in rows:
        require(isinstance(row, dict), f"{key} record must be an object")
        value = row.get(key)
        require(isinstance(value, str) and 0 < len(value) <= 256, f"invalid {key}")
        require(value not in result, f"duplicate {key}: {value}")
        result[value] = row
    return result


def validate_inputs(catalog, mapping):
    require(
        isinstance(catalog, dict) and isinstance(mapping, dict),
        "inputs must be objects",
    )
    require(
        catalog.get("schema_version") == SCHEMA_VERSION, "unsupported catalog version"
    )
    require(
        mapping.get("schema_version") == SCHEMA_VERSION, "unsupported mapping version"
    )
    timestamp(catalog.get("exported_at"))
    brands = indexed(catalog.get("brands"), "id")
    companies = indexed(catalog.get("companies"), "id")
    products = indexed(catalog.get("products"), "product_key")
    require(bool(brands), "select at least one brand")
    for brand in brands.values():
        require(
            isinstance(brand.get("company_ids"), list), "brand requires company_ids"
        )
        require(set(brand["company_ids"]) <= companies.keys(), "unknown brand company")
    repos = set()
    for key, product in products.items():
        require(str(UUID(key)) == key, "product_key must be a canonical UUID")
        require(product.get("brand_id") in brands, "unknown product brand")
        repo = product.get("repo_id")
        if repo is not None:
            require(
                isinstance(repo, str) and REPO_ID.fullmatch(repo), "invalid HF repo_id"
            )
            require(repo.casefold() not in repos, "duplicate HF repository")
            repos.add(repo.casefold())
    hf_keys = mapping.get("hf_product_keys")
    require(
        isinstance(hf_keys, list) and all(isinstance(k, str) for k in hf_keys),
        "invalid HF selection",
    )
    require(len(set(hf_keys)) == len(hf_keys), "duplicate HF selection")
    for key in hf_keys:
        require(key in products, "unknown HF product")
        product = products[key]
        repo = product.get("repo_id")
        require(bool(repo), "HF selection needs a repository")
        namespace = product.get("hf_namespace")
        require(
            isinstance(namespace, str)
            and repo.split("/")[0].casefold() == namespace.casefold(),
            "HF namespace mismatch",
        )
        require(
            product.get("hf_confirmed") is True, "HF namespace ownership is unconfirmed"
        )
        require(
            product.get("hf_company_id") in brands[product["brand_id"]]["company_ids"],
            "HF company does not own this brand",
        )
    rows = mapping.get("mappings")
    require(isinstance(rows, list), "mappings must be a list")
    seen = set()
    for row in rows:
        require(isinstance(row, dict), "mapping must be an object")
        require(
            row.get("source") in {"arena", "openrouter", "opencode"},
            "unknown mapping source",
        )
        if row["source"] == "opencode":
            from .sources import opencode_url

            opencode_url(row.get("endpoint_path"))
        source_id = row.get("source_id")
        require(
            isinstance(source_id, str)
            and 0 < len(source_id) <= 256
            and source_id.strip() == source_id,
            "invalid source_id",
        )
        require(source_id != "other", "OpenRouter other cannot be mapped")
        key = (row["source"], source_id)
        require(key not in seen, "duplicate source mapping")
        seen.add(key)
        require(row.get("product_key") in products, "unknown mapped product")
        evidence = row.get("evidence")
        require(isinstance(evidence, str), "mapping needs an evidence URL")
        url = urlsplit(evidence)
        require(
            url.scheme in {"https", "http"} and bool(url.hostname) and not url.username,
            "invalid evidence URL",
        )
    posts = catalog.get("posts")
    require(
        isinstance(posts, dict) and posts.get("scope") == "collected_postbrand",
        "unsupported post counting scope",
    )
    window = set(days(posts.get("start_date"), posts.get("end_date")))
    require(isinstance(posts.get("counts"), list), "post counts must be a list")
    seen = set()
    for row in posts["counts"]:
        require(
            isinstance(row, dict)
            and row.get("brand_id") in brands
            and row.get("date") in window,
            "post count outside exported scope",
        )
        key = row["brand_id"], row["date"]
        require(key not in seen, "duplicate post count")
        seen.add(key)
        count(row.get("count"))
    return brands, products


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def taxonomy_digest(catalog):
    # Refreshing post counts/export time does not change the frozen identities.
    return digest(
        {
            key: catalog[key]
            for key in ("schema_version", "brands", "companies", "products")
        }
    )


def read_json(path):
    path = Path(path)
    require(path.stat().st_size <= 64 * 1024 * 1024, "input exceeds 64 MiB")
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path, value):
    """Atomic, exclusive publication: readers never see half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    fd, temporary = tempfile.mkstemp(prefix=".collector-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)  # Fails if another run already published this name.
    finally:
        os.unlink(temporary)
