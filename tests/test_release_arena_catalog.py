import hashlib

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.benchmark_download_collector.sources import (
    ARENA_LATEST,
    AmbiguousCatalogMatch,
)


def published_model(name, organization, **changes):
    return {
        "model_name": name,
        "organization": organization,
        "category": "overall",
        "leaderboard_publish_date": "2026-09-11",
        "rating": 1442.53,
        "rating_lower": 1435.12,
        "rating_upper": 1451.13,
        "variance": 13.1,
        "vote_count": 5872,
        "rank": 3,
        **changes,
    }


def document(rows):
    stream = pa.BufferOutputStream()
    pq.write_table(pa.Table.from_pylist(rows), stream)
    return stream.getvalue().to_pybytes()


def test_arena_discovery_returns_owned_model_and_exact_published_coordinate():
    from core.release_arena_catalog import arena_candidates

    alias = "deepseek-v4-pro-0813 (thinking)"
    body = document(
        [
            published_model(alias, "DeepSeek"),
            published_model("deepseek-v4-pro-0813", "DeepSeek"),
            published_model(
                "deepseek-v4-pro-0813 (thinking)", "DeepSeek", category="coding"
            ),
        ]
    )
    requested = []

    def fetch(url):
        requested.append(url)
        return body

    candidates = arena_candidates(fetch, alias.__eq__, "DeepSeek".__eq__)
    assert requested == [ARENA_LATEST]
    [(identifier, scope, evidence_url, metadata)] = candidates
    assert identifier == alias and scope == "arena_model_name"
    assert (
        evidence_url
        == "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset/viewer/text/latest"
    )
    proof = metadata["release_endpoint"]
    assert proof["url"] == ARENA_LATEST
    assert proof["artifact_sha256"] == hashlib.sha256(body).hexdigest()
    assert proof["source_fields"] == {
        "config": "text",
        "category": "overall",
        "model_name": alias,
        "organization": "DeepSeek",
        "leaderboard_publish_date": "2026-09-11",
    }


@pytest.mark.parametrize(
    "target, issuer",
    [
        ("deepseek-v4-pro-0813 (thinking)", "unrelated"),
        ("deepseek-v4-pro", "DeepSeek"),
        ("deepseek-v4-pro-0813", "DeepSeek"),
        ("muse wonder (max)", "Meta"),
    ],
)
def test_arena_discovery_preserves_publisher_version_and_board(target, issuer):
    from core.release_arena_catalog import arena_candidates

    published = document(
        [
            published_model("deepseek-v4-pro-0813 (thinking)", "DeepSeek"),
            published_model("muse wonder (max)", "Meta", category="coding"),
        ]
    )
    assert arena_candidates(lambda _: published, target.__eq__, issuer.__eq__) == []


def test_multiple_matching_native_names_are_unresolved():
    from core.release_arena_catalog import arena_candidates

    body = document(
        [
            published_model("GLM-5.4", "Z.ai"),
            published_model("GLM 5.4", "Z.ai"),
        ]
    )
    with pytest.raises(AmbiguousCatalogMatch):
        arena_candidates(
            lambda _: body, lambda name: name.startswith("GLM"), lambda issuer: True
        )


@pytest.mark.parametrize(
    "source", ["bad_parquet", "missing_publisher", "conflicting_dates", "fetch_failed"]
)
def test_incomplete_arena_evidence_remains_retryable(source):
    from core.release_arena_catalog import arena_candidates

    row = published_model("GLM-5.4", "Z.ai")

    def fetch(url):
        if source == "fetch_failed":
            raise ValueError("unavailable")
        if source == "bad_parquet":
            return b"upstream returned html"
        if source == "missing_publisher":
            row.pop("organization")
            return document([row])
        return document(
            [row, published_model("Other", "B", leaderboard_publish_date="2026-09-10")]
        )

    with pytest.raises(ValueError):
        arena_candidates(fetch, lambda name: True, lambda issuer: True)


def test_concurrent_lookups_decode_one_publication_and_refresh_on_change(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from core import release_arena_catalog as catalog

    model = "GLM-5.4 (High)"
    first = document([published_model(model, "Z.ai")])
    second = document([published_model("new model", "Z.ai")])
    decode = catalog.read_arena_latest
    seen = []
    entered = Barrier(3)

    def recording_decode(load):
        seen.append(1)
        return decode(load)

    def lookup():
        entered.wait(timeout=5)
        return catalog.arena_candidates(lambda _: first, model.__eq__, "Z.ai".__eq__)

    monkeypatch.setattr(catalog, "read_arena_latest", recording_decode)
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert all(
            result[0][0] == model for result in pool.map(lambda _: lookup(), range(3))
        )
    assert len(seen) == 1
    assert catalog.arena_candidates(lambda _: second, model.__eq__, "Z.ai".__eq__) == []
    assert len(seen) == 2
