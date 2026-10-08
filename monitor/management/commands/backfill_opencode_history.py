"""One bounded capture of all exposed dates for a reviewed product cohort."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
from django.core.management.base import BaseCommand, CommandError

from core.benchmark_attribution import enforce_source_collection
from core.benchmark_metric_history import import_history
from core.measurement_taxonomy import digest
from core.models import MetricCollectionContract
from scripts.benchmark_download_collector.identity import write_new
from scripts.benchmark_download_collector.sources import Budget, opencode


class Command(BaseCommand):
    help = "Capture every exposed OpenCode day for reviewed mappings; import only with --apply."

    def add_arguments(self, parser):
        parser.add_argument("--contract", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--isolated-review", action="store_true")

    def handle(self, *args, **opts):
        try:
            contract = MetricCollectionContract.objects.get(pk=opts["contract"])
            if "opencode" not in contract.source_configuration:
                raise ValueError("OpenCode outside contract")
            enforce_source_collection(
                contract,
                "opencode",
                dataset="opencode/model-daily",
                isolated_review=opts["isolated_review"],
            )
            config = contract.source_configuration["opencode"]
            selected = [
                {
                    "external_identifier": m.external_identifier,
                    "endpoint_path": m.identifier_metadata["endpoint_path"],
                }
                for m in contract.mappings.filter(source_id="opencode")
            ]
            with httpx.Client(trust_env=False) as client:
                budget = Budget(
                    client,
                    **{
                        k: config[k]
                        for k in ("max_requests", "max_seconds", "max_bytes")
                    },
                )
                payload = opencode(budget, selected)
                payload["request_count"] = config["max_requests"] - budget.remaining
            labels = sorted(
                {row["date"] for row in payload["rows"] if row.get("status") != "error"}
            )
            if not labels:
                raise ValueError("no usable exposed history")
            revision = digest(payload)
            observed = datetime.now(UTC).isoformat()
            manifest = {
                "schema_version": 1,
                "source": "opencode",
                "dataset_id": "opencode/model-daily",
                "archive_publisher": "opencode",
                "artifact_kind": "selected_json",
                "contract_id": str(contract.pk),
                "start_date": labels[0],
                "end_date": labels[-1],
                "retrieved_at": observed,
                "selection": "reviewed_tracked_products",
                "snapshots": [
                    {
                        "date": labels[-1],
                        "immutable_revision": revision,
                        "file_path": f"model-daily-{revision}.json",
                        "raw_artifact_sha256": revision,
                        "snapshot_timezone": "UTC",
                        "payload": payload,
                    }
                ],
            }
            root = Path(opts["output"])
            root.mkdir(parents=True, exist_ok=True)
            path = root / f"opencode-{revision}.json"
            if path.exists():
                if json.loads(path.read_text())["snapshots"] != manifest["snapshots"]:
                    raise ValueError("history artifact collision")
            else:
                write_new(path, manifest)
            result = import_history(
                manifest, apply=opts["apply"], isolated_review=opts["isolated_review"]
            )
            report = {
                "artifact": str(path),
                "start_date": labels[0],
                "end_date": labels[-1],
                "exposed_dates": len(labels),
                "request_count": payload["request_count"],
                "cohort_complete": payload["status"] == "ok",
                "applied": opts["apply"],
            }
            if opts["apply"]:
                report.update(run_id=str(result.pk), status=result.status)
            else:
                report.update(result)
            self.stdout.write(json.dumps(report))
            if payload["status"] != "ok" or (
                opts["apply"] and result.status != "success"
            ):
                raise CommandError(
                    "OpenCode history incomplete; successful subject evidence retained"
                )
        except (
            ValueError,
            KeyError,
            OSError,
            MetricCollectionContract.DoesNotExist,
        ) as exc:
            raise CommandError(str(exc)) from exc
