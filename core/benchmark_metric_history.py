"""Bounded historical replay, preserving archive dates separately from import time."""

from __future__ import annotations

import copy
import re

from core.benchmark_metric_store import native_date, persist_source, safe_payload
from core.measurement_taxonomy import digest, require
from core.models import MetricCollectionContract

ARCHIVES = {
    "hf": {
        "cfahlgren1/hub-stats": "cfahlgren1",
        "hfmlsoc/hub_weekly_snapshots": "hfmlsoc",
    },
    "arena": {"lmarena-ai/leaderboard-dataset": "lmarena-ai"},
    "openrouter": {"openrouter/rankings-daily": "openrouter"},
}


def prepare_history(manifest):
    safe_payload(manifest)
    require(manifest.get("schema_version") == 1, "unsupported history schema")
    source = manifest["source"]
    dataset = manifest["dataset_id"]
    publisher = manifest["archive_publisher"]
    require(
        ARCHIVES.get(source, {}).get(dataset) == publisher,
        "unreviewed archive/provider",
    )
    require(
        manifest.get("artifact_kind") == "selected_json",
        "history expects hashed selected JSON; binary hashes must remain separate evidence",
    )
    start = native_date(manifest["start_date"])
    end = native_date(manifest["end_date"])
    require(0 <= (end - start).days < 366, "history date budget exceeded")
    snapshots = manifest["snapshots"]
    require(
        isinstance(snapshots, list) and 0 < len(snapshots) <= 366,
        "snapshot budget exceeded",
    )
    contract = MetricCollectionContract.objects.get(pk=manifest["contract_id"])
    require(
        source in contract.source_configuration, "historical source outside contract"
    )
    rows = []
    revisions = []
    as_of = []
    for snap in snapshots:
        day = native_date(snap["date"])
        require(start <= day <= end, "snapshot outside history range")
        revision = snap["immutable_revision"]
        require(
            re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", revision or ""),
            "immutable revision/hash required",
        )
        require(
            snap.get("file_path")
            and not snap["file_path"].startswith("/")
            and ".." not in snap["file_path"].split("/"),
            "relative source artifact path required",
        )
        payload = snap["payload"]
        require(
            digest(payload) == snap["raw_artifact_sha256"],
            "selected JSON artifact hash mismatch",
        )
        require(
            payload.get("status") in {"ok", "partial"},
            "archive retrieval not successful",
        )
        if source == "openrouter":
            require(
                payload.get("meta", {}).get("version") == "v1",
                "unknown OpenRouter history version",
            )
            if payload.get("as_of"):
                as_of.append(payload["as_of"])
        if source == "arena":
            require(
                payload.get("config") == "text_style_control",
                "Arena history configuration mismatch",
            )
        for row in payload["rows"]:
            item = copy.deepcopy(row)
            # Import time belongs to this run; the archive's timestamp is provenance.
            original_observed = item.pop("observed_at", None)
            item["_source_metadata"] = {
                "archive_snapshot_date": day.isoformat(),
                "archive_snapshot_precision": "date",
                "archive_snapshot_timezone": snap.get("snapshot_timezone", "unknown"),
                "archive_publisher": publisher,
                "dataset_id": dataset,
                "immutable_revision": revision,
                "file_path": snap["file_path"],
                "raw_artifact_sha256": snap["raw_artifact_sha256"],
                "artifact_kind": "selected_json",
                "original_retrieved_at": original_observed,
                "secondary_source": source == "hf",
            }
            upstream_hash = snap.get("upstream_binary_sha256")
            if upstream_hash is not None:
                require(
                    re.fullmatch(r"[0-9a-f]{64}", upstream_hash),
                    "invalid upstream binary hash",
                )
                item["_source_metadata"]["upstream_binary_sha256"] = upstream_hash
            if snap.get("upstream_retrieval_coordinates"):
                item["_source_metadata"]["upstream_retrieval_coordinates"] = snap[
                    "upstream_retrieval_coordinates"
                ]
            if source == "arena":
                require(
                    start <= native_date(item["leaderboard_publish_date"]) <= end,
                    "Arena publication outside range",
                )
            if source == "openrouter":
                require(
                    start <= native_date(item["date"]) <= end,
                    "usage date outside range",
                )
            rows.append(item)
        revisions.append(
            {
                k: snap[k]
                for k in (
                    "date",
                    "immutable_revision",
                    "file_path",
                    "raw_artifact_sha256",
                )
            }
        )
    require(len(rows) <= 25000, "historical row budget exceeded")
    payload = {"status": "ok", "rows": rows}
    if source == "arena":
        payload["config"] = "text_style_control"
    if source == "openrouter":
        require(len(snapshots) == 1, "one complete OpenRouter revision per import")
        payload.update(meta={"version": "v1"}, as_of=max(as_of) if as_of else None)
    metadata = {
        "ingestion_mode": "historical_import",
        "measurement_provider": source,
        "archive_publisher": publisher,
        "dataset_id": dataset,
        "revisions": revisions,
        "adapter_version": contract.source_configuration[source]["adapter_key"],
        "coverage": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "snapshot_count": len(snapshots),
            "missing_dates_are_unavailable": True,
        },
        "secondary_source": source == "hf",
    }
    key = digest([contract.contract_hash, source, metadata, digest(payload)])
    return contract, source, key, payload, metadata


def import_history(manifest, *, apply=False):
    contract, source, key, payload, metadata = prepare_history(manifest)
    if not apply:
        from core.benchmark_metric_store import prepare_rows

        prepared = prepare_rows(contract, source, payload)
        return {
            "applied": False,
            "ingestion_key": key,
            "observations": len(prepared),
            "values": sum(len(values) for _, values in prepared),
        }
    return persist_source(contract, source, key, payload, source_metadata=metadata)
