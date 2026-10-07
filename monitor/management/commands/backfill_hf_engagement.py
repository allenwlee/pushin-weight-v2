"""Acquire timestamp-based HF history without retaining personal profile records."""

import json
import time
from pathlib import Path

import httpx
from django.core.management.base import BaseCommand, CommandError

from core.hf_metadata_client import HFMetadataClient
from core.measurement_taxonomy import digest
from scripts.benchmark_download_collector.history import hf_relationship_history


class Command(BaseCommand):
    help = "Save current HF counters and reconstructed engagement for an explicit reviewed cohort."

    def add_arguments(self, parser):
        parser.add_argument("cohort")
        parser.add_argument("--contract", required=True)
        parser.add_argument("--isolated-review", action="store_true")
        parser.add_argument("--output", required=True)
        parser.add_argument("--max-requests", type=int, default=10000)
        parser.add_argument("--max-seconds", type=int, default=3600)

    def handle(self, *args, **opts):
        from core.benchmark_attribution import enforce_source_collection
        from core.models import MetricCollectionContract

        contract = MetricCollectionContract.objects.get(pk=opts["contract"])
        enforce_source_collection(
            contract, "hf", dataset=None, isolated_review=opts["isolated_review"]
        )

        if (
            not 1 <= opts["max_requests"] <= 20000
            or not 1 <= opts["max_seconds"] <= 14400
        ):
            raise CommandError("budget out of range")
        cohort = json.loads(Path(opts["cohort"]).read_text())
        selected = cohort["accounts"] + cohort["repositories"]
        if len(selected) > 5000 or len(
            {(r["identifier"], r["kind"]) for r in selected}
        ) != len(selected):
            raise CommandError("invalid cohort")
        root = Path(opts["output"])
        root.mkdir(parents=True, exist_ok=True)
        report = {
            "cohort_sha256": digest(cohort),
            "selected": len(selected),
            "completed": [],
            "failed": [],
            "complete": False,
        }
        with httpx.Client(trust_env=False) as transport:
            client = HFMetadataClient(
                transport,
                max_requests=opts["max_requests"],
                max_seconds=opts["max_seconds"],
                max_bytes=16 * 1024 * 1024,
            )
            last_attempt = [0.0]

            def pace(_):
                delay = max(0, 0.7 - (time.monotonic() - last_attempt[0]))
                if delay:
                    time.sleep(delay)
                last_attempt[0] = time.monotonic()

            client.on_attempt = pace
            for row in selected:
                key = digest([row["kind"], row["identifier"]])
                path = root / (key + ".json")
                if path.exists():
                    saved = json.loads(path.read_text())
                    if saved.get("sha256") != digest(saved.get("data")):
                        raise CommandError("checkpoint hash mismatch")
                    report["completed"].append(
                        {
                            "identifier": row["identifier"],
                            "kind": row["kind"],
                            "artifact": path.name,
                        }
                    )
                    continue
                try:
                    if client.stop_reason:
                        raise ValueError(client.stop_reason)
                    current = (
                        client.download_counts(row["identifier"])
                        if row["kind"] == "repository"
                        else client.account_counts(row["identifier"], row["kind"])
                    )
                    if current.outcome != "ok":
                        raise ValueError("current_" + current.outcome)
                    data = hf_relationship_history(
                        client, row["identifier"], kind=row["kind"]
                    )
                    data["current"] = {
                        k: v
                        for k, v in current.payload.items()
                        if k
                        in {
                            "id",
                            "_id",
                            "downloads",
                            "downloadsAllTime",
                            "likes",
                            "numFollowers",
                        }
                    }
                    data["observed_at"] = current.attempts[-1]["observed_at"]
                    tmp = path.with_suffix(".tmp")
                    tmp.write_text(json.dumps({"data": data, "sha256": digest(data)}))
                    tmp.replace(path)
                    report["completed"].append(
                        {
                            "identifier": row["identifier"],
                            "kind": row["kind"],
                            "artifact": path.name,
                        }
                    )
                except (ValueError, KeyError, TypeError) as exc:
                    report["failed"].append(
                        {
                            "identifier": row["identifier"],
                            "kind": row["kind"],
                            "reason": str(exc)[:120],
                        }
                    )
                    if "throttled" in str(exc):
                        break
                if (len(report["completed"]) + len(report["failed"])) % 25 == 0:
                    (root / "coverage.json").write_text(json.dumps(report, indent=2))
                    self.stdout.write(
                        json.dumps(
                            {
                                "completed": len(report["completed"]),
                                "failed": len(report["failed"]),
                                "requests": client.requests,
                            }
                        )
                    )
                    self.stdout.flush()
                if client.stop_reason:
                    break
            report["requests_this_run"] = client.requests
        report["complete"] = len(report["completed"]) == len(selected)
        (root / "coverage.json").write_text(json.dumps(report, indent=2))
        self.stdout.write(
            json.dumps(
                {
                    "complete": report["complete"],
                    "completed": len(report["completed"]),
                    "failed": len(report["failed"]),
                }
            )
        )
        if not report["complete"]:
            raise CommandError(
                "HF acquisition incomplete; see coverage.json. Successful checkpoints are reusable."
            )
