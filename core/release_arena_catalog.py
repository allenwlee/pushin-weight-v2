"""Discover the exact Arena identity for a released model on the overall text board."""

from functools import lru_cache
from threading import Lock

from scripts.benchmark_download_collector.sources import (
    ARENA_CONFIG,
    ARENA_DATASET,
    ARENA_LATEST,
    AmbiguousCatalogMatch,
    read_arena_latest,
)

_publication_lock = Lock()


@lru_cache(maxsize=1)
def _publication_index(content):
    """Keep only the most recent decoded board's model/publisher pairs."""
    publication = read_arena_latest(lambda: content)
    models = tuple(
        (row["model_name"], row.get("organization")) for row in publication["rows"]
    )
    return publication["artifact_sha256"], publication["as_of"], models


def arena_candidates(fetch, matches, owns):
    content = fetch(ARENA_LATEST)
    # Concurrent cache misses must not each inflate a full Parquet board.
    with _publication_lock:
        checksum, published, models = _publication_index(content)
    matched = []
    for name, organization in models:
        if matches(name):
            if not isinstance(organization, str) or not organization.strip():
                raise ValueError("Arena has no publisher for the matching model")
            if owns(organization):
                matched.append((name, organization))
    if len(matched) > 1:
        raise AmbiguousCatalogMatch("multiple Arena identifiers")
    if not matched:
        return []

    name, organization = matched[0]
    endpoint = {
        "url": ARENA_LATEST,
        "artifact_sha256": checksum,
        "source_fields": {
            "config": ARENA_CONFIG,
            "category": "overall",
            "model_name": name,
            "organization": organization,
            "leaderboard_publish_date": published,
        },
    }
    evidence = (
        f"https://huggingface.co/datasets/{ARENA_DATASET}/viewer/{ARENA_CONFIG}/latest"
    )
    return [(name, "arena_model_name", evidence, {"release_endpoint": endpoint})]
