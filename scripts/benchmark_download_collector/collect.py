"""Immutable local snapshots, independent of Django and the live catalog."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from . import sources
from .identity import (
    digest,
    read_json,
    require,
    taxonomy_digest,
    validate_inputs,
    write_new,
)


def contract(catalog, mapping):
    return {
        "schema_version": 1,
        "taxonomy_digest": taxonomy_digest(catalog),
        "mapping_digest": digest(mapping),
    }


def ensure_contract(directory, catalog, mapping):
    """Freeze identity/cohort choices before spending any network budget."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    expected = contract(catalog, mapping)
    path = directory / "contract.json"
    try:
        write_new(path, expected)
    except FileExistsError:
        require(
            read_json(path) == expected,
            "catalog/mapping changed; start a new collection directory",
        )
    return expected


def collect(
    catalog,
    mapping,
    directory,
    budget,
    *,
    start_date,
    end_date,
    selected=("arena", "hf", "openrouter"),
    openrouter_key=None,
    max_pages=50,
    arena_history=False,
):
    _, products = validate_inputs(catalog, mapping)
    require(
        bool(selected)
        and set(selected) <= sources.SOURCE_URLS.keys()
        and len(set(selected)) == len(selected),
        "invalid source selection",
    )
    frozen = ensure_contract(directory, catalog, mapping)
    snapshot = {
        **frozen,
        "observed_at": datetime.now(UTC).isoformat(),
        "catalog": catalog,
        "mapping": mapping,
        "sources": {},
    }
    readers = {
        "arena": lambda: sources.arena(
            budget, start_date, end_date, max_pages=max_pages, history=arena_history
        ),
        "openrouter": lambda: sources.openrouter(
            budget, start_date, end_date, key=openrouter_key
        ),
        "hf": lambda: sources.hf(
            budget, [products[key] for key in mapping["hf_product_keys"]]
        ),
        "opencode": lambda: sources.opencode(
            budget,
            [
                {
                    "external_identifier": item["source_id"],
                    "endpoint_path": item["endpoint_path"],
                }
                for item in mapping["mappings"]
                if item["source"] == "opencode"
            ],
        ),
    }
    for source, reader in readers.items():
        if source == "opencode" and source not in selected:
            continue
        result = {"status": "not_requested", "rows": []}
        if source in selected:
            try:
                result = reader()
            except (ValueError, TypeError, KeyError) as exc:
                result = {
                    "status": "error",
                    "error": sources.safe_error(exc),
                    "rows": [],
                }
        result["source_url"] = sources.SOURCE_URLS[source]
        snapshot["sources"][source] = result
    snapshot["completed_at"] = datetime.now(UTC).isoformat()
    path = (
        Path(directory)
        / f"snapshot-{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}-{uuid4().hex[:8]}.json"
    )
    write_new(path, snapshot)
    return path, snapshot


def load_snapshots(directory):
    paths = sorted(Path(directory).glob("snapshot-*.json"))
    require(bool(paths), "no snapshots in collection directory")
    require(
        len(paths) <= 1000
        and sum(p.stat().st_size for p in paths) <= 128 * 1024 * 1024,
        "report input exceeds 1000 snapshots / 128 MiB; use a smaller directory",
    )
    return [read_json(path) for path in paths]
