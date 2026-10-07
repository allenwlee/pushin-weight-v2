"""Import published overall Arena history for an explicit organization cohort."""

import hashlib
import json
from pathlib import Path

import httpx
from django.core.management.base import BaseCommand, CommandError

from core.benchmark_metric_store import persist_source
from core.measurement_taxonomy import digest
from core.models import MetricCollectionContract
from scripts.benchmark_download_collector.history import date_chunks
from scripts.benchmark_download_collector.sources import Budget


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--contract", required=True)
        parser.add_argument("--organization", action="append", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--isolated-review", action="store_true")

    def handle(self, *args, **opts):
        import pyarrow.parquet as pq

        contract = MetricCollectionContract.objects.get(pk=opts["contract"])
        from core.benchmark_attribution import enforce_source_collection

        enforce_source_collection(
            contract,
            "arena",
            dataset="lmarena-ai/leaderboard-dataset",
            isolated_review=opts["isolated_review"],
        )
        config = contract.source_configuration["arena"].get(
            "config", "text_style_control"
        )
        organizations = set(opts["organization"])
        if not organizations or len(organizations) > 100:
            raise CommandError("invalid organization cohort")
        root = Path(opts["output"])
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{config}-full.parquet"
        receipt = root / f"{config}-full.json"
        if not path.exists():
            with httpx.Client(trust_env=False) as client:
                content = Budget(
                    client, max_requests=8, max_seconds=180, max_bytes=80 * 1024 * 1024
                ).arena_asset(config=config, split="full")
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(content)
            tmp.replace(path)
            receipt.write_text(
                json.dumps({"sha256": hashlib.sha256(content).hexdigest()})
            )
        binary_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if json.loads(receipt.read_text())["sha256"] != binary_hash:
            raise CommandError("Arena archive hash mismatch")
        f = pq.ParquetFile(path)
        if f.metadata.num_rows > 3000000:
            raise CommandError("Arena row budget exceeded")
        rows = []
        publications = set()
        for batch in f.iter_batches(batch_size=10000):
            for row in batch.to_pylist():
                if row["category"] == "overall":
                    publications.add(row["leaderboard_publish_date"])
                    if row["organization"] in organizations:
                        rows.append(row)
        if not publications:
            raise CommandError("No overall publications")
        report = {
            "source": "arena",
            "config": config,
            "organizations": sorted(organizations),
            "rows": len(rows),
            "earliest": min(publications),
            "latest": max(publications),
            "publication_dates": sorted(publications),
            "chunks": [],
            "complete": False,
        }
        for first, last in date_chunks(min(publications), max(publications)):
            selected = [
                r for r in rows if first <= r["leaderboard_publish_date"] <= last
            ]
            payload = {
                "status": "ok",
                "config": config,
                "coverage": "publication_window",
                "rows": selected,
            }
            (root / f"{first}-{last}.json").write_text(json.dumps(payload))
            result = {"start": first, "end": last, "rows": len(selected)}
            if opts["apply"]:
                run = persist_source(
                    contract,
                    "arena",
                    digest(
                        [
                            contract.contract_hash,
                            config,
                            binary_hash,
                            first,
                            last,
                            sorted(organizations),
                        ]
                    ),
                    payload,
                    isolated_review=opts["isolated_review"],
                    source_metadata={
                        "ingestion_mode": "historical_import",
                        "history_basis": "observed_snapshot",
                        "dataset_id": "lmarena-ai/leaderboard-dataset",
                        "upstream_sha256": binary_hash,
                        "publication_dates": sorted(
                            d for d in publications if first <= d <= last
                        ),
                        "selected_organizations": sorted(organizations),
                    },
                )
                result.update(run_id=str(run.pk), status=run.status)
                if selected and run.status not in {"success", "partial"}:
                    report["chunks"].append(result)
                    (root / "coverage.json").write_text(json.dumps(report, indent=2))
                    raise CommandError("Arena history import incomplete")
            report["chunks"].append(result)
        report["complete"] = True
        (root / "coverage.json").write_text(json.dumps(report, indent=2))
        self.stdout.write(
            json.dumps(
                {
                    "rows": len(rows),
                    "earliest": min(publications),
                    "latest": max(publications),
                }
            )
        )
