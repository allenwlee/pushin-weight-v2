"""Collect every reported historical top-50 cohort, including unmapped models."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from django.core.management.base import BaseCommand, CommandError

from core.benchmark_metric_store import persist_source
from core.measurement_taxonomy import digest
from core.models import MetricCollectionContract
from scripts.benchmark_download_collector.history import date_chunks
from scripts.benchmark_download_collector.sources import Budget, openrouter


class Command(BaseCommand):
    help = "Acquire all available OpenRouter daily rankings into an explicit artifact directory; import only with --apply."

    def add_arguments(self, parser):
        parser.add_argument("--contract", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--start-date", default="2025-01-01")
        parser.add_argument(
            "--end-date",
            default=(datetime.now(UTC).date() - timedelta(days=1)).isoformat(),
        )
        parser.add_argument("--key-env", default="BENCHMARK_OPENROUTER_API_KEY")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **opts):
        contract = MetricCollectionContract.objects.get(pk=opts["contract"])
        if "openrouter" not in contract.source_configuration:
            raise CommandError("OpenRouter is not in this contract")
        chunks = list(date_chunks(opts["start_date"], opts["end_date"]))
        if len(chunks) > 40:
            raise CommandError("history request budget exceeded")
        root = Path(opts["output"])
        root.mkdir(parents=True, exist_ok=True)
        report = {
            "source": "openrouter",
            "start": opts["start_date"],
            "end": opts["end_date"],
            "selection": "all_reported_models",
            "chunks": [],
            "complete": False,
        }
        with httpx.Client(trust_env=False) as client:
            budget = Budget(
                client, max_requests=120, max_seconds=600, max_bytes=16 * 1024 * 1024
            )
            for first, last in chunks:
                path = root / f"openrouter-{first}-{last}.json"
                try:
                    if path.exists():
                        saved = json.loads(path.read_text())
                        payload = saved["payload"]
                        if (
                            digest(payload) != saved["sha256"]
                            or payload["meta"]["start_date"] != first
                            or payload["meta"]["end_date"] != last
                        ):
                            raise ValueError("checkpoint mismatch")
                    else:
                        payload = openrouter(
                            budget, first, last, key=os.environ.get(opts["key_env"])
                        )
                        saved = {
                            "payload": payload,
                            "sha256": digest(payload),
                            "retrieved_at": datetime.now(UTC).isoformat(),
                        }
                        tmp = path.with_suffix(".tmp")
                        tmp.write_text(json.dumps(saved))
                        tmp.replace(path)
                    row = {
                        "start": first,
                        "end": last,
                        "sha256": saved["sha256"],
                        "rows": len(payload["rows"]),
                        "missing_dates": payload["missing_dates"],
                    }
                    if opts["apply"]:
                        run = persist_source(
                            contract,
                            "openrouter",
                            digest(
                                [
                                    contract.contract_hash,
                                    "openrouter_history",
                                    saved["sha256"],
                                ]
                            ),
                            payload,
                            source_metadata={
                                "ingestion_mode": "historical_import",
                                "history_basis": "observed_snapshot",
                                "dataset_id": "openrouter/rankings-daily",
                                "retrieved_at": saved["retrieved_at"],
                                "selection": "all_reported_models",
                            },
                        )
                        row.update(run_id=str(run.pk), status=run.status)
                        if run.status not in {"success", "partial"}:
                            raise ValueError("history import failed")
                    report["chunks"].append(row)
                    self.stdout.write(json.dumps(row))
                except (ValueError, KeyError, httpx.HTTPError) as exc:
                    report["error"] = type(exc).__name__
                    (root / "coverage.json").write_text(json.dumps(report, indent=2))
                    raise CommandError(
                        "History incomplete; inspect coverage.json and retained chunks"
                    ) from None
        report["complete"] = True
        report["rows"] = sum(r["rows"] for r in report["chunks"])
        report["missing_dates"] = [
            d for r in report["chunks"] for d in r["missing_dates"]
        ]
        (root / "coverage.json").write_text(json.dumps(report, indent=2))
        self.stdout.write(
            json.dumps(
                {
                    "complete": True,
                    "rows": report["rows"],
                    "missing_days": len(report["missing_dates"]),
                }
            )
        )
