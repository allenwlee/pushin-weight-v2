"""Acquire daily community archive snapshots for a reviewed HF repository cohort."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from django.core.management.base import BaseCommand, CommandError

from core.hf_metadata_client import HFMetadataClient
from core.measurement_taxonomy import digest
from scripts.benchmark_download_collector.hf_archive import (
    ArchiveBudget,
    select_snapshot,
)


class Command(BaseCommand):
    help = (
        "Save selected daily HF download/like history, preserving archive provenance."
    )

    def add_arguments(self, parser):
        parser.add_argument("cohort")
        parser.add_argument("--output", required=True)
        parser.add_argument("--max-seconds", type=int, default=7200)
        parser.add_argument("--max-requests", type=int, default=150000)
        parser.add_argument("--max-bytes", type=int, default=32 * 1024**3)

    def handle(self, *args, **opts):
        # Resolver redirects contain expiring public signatures; never log them.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        if (
            not 1 <= opts["max_seconds"] <= 14400
            or not 1 <= opts["max_requests"] <= 150000
            or not 1 <= opts["max_bytes"] <= 32 * 1024**3
        ):
            raise CommandError("invalid archive budget")
        cohort = json.loads(Path(opts["cohort"]).read_text())["repositories"]
        if (
            not cohort
            or len(cohort) > 5000
            or len({r["identifier"].casefold() for r in cohort}) != len(cohort)
        ):
            raise CommandError("invalid HF cohort")
        root = Path(opts["output"])
        root.mkdir(parents=True, exist_ok=True)
        report = {
            "source": "hf",
            "dataset_id": "cfahlgren1/hub-stats",
            "cohort_sha256": digest(cohort),
            "selected": len(cohort),
            "selection": "latest_model_revision_per_UTC_publication_day",
            "completed": [],
            "failed": [],
            "complete": False,
        }
        with httpx.Client(trust_env=False) as transport:
            client = HFMetadataClient(transport, max_requests=120, max_seconds=600)
            commits = []
            for page in range(100):
                path = root / f"commits-{page}.json"
                if path.exists():
                    batch = json.loads(path.read_text())
                    more = len(batch) == 100
                else:
                    result = client._get(
                        "/datasets/cfahlgren1/hub-stats/commits/main",
                        {"limit": 100, "p": page},
                    )
                    if result.outcome != "ok":
                        raise CommandError(
                            "archive revision list unavailable: " + result.outcome
                        )
                    batch = result.payload
                    path.write_text(json.dumps(batch))
                    more = 'rel="next"' in result.attempts[-1].get("link", "")
                commits.extend(batch)
                if not more:
                    break
            else:
                raise CommandError("archive revision page cap")
            revisions = {}
            for row in commits:
                if (
                    "models.parquet" in row["title"]
                    and row["date"][:10] not in revisions
                ):
                    revisions[row["date"][:10]] = {
                        k: row[k] for k in ["id", "date", "title"]
                    }
            if not revisions:
                raise CommandError("No model revisions")
            report.update(
                first_publication=min(revisions),
                last_publication=max(revisions),
                available_days=len(revisions),
            )
            budget = ArchiveBudget(
                transport,
                requests=opts["max_requests"],
                max_bytes=opts["max_bytes"],
                seconds=opts["max_seconds"],
            )

            def collect(pair):
                day, revision = pair
                path = root / f"snapshot-{day}.json"
                if path.exists():
                    saved = json.loads(path.read_text())
                    if (
                        saved.get("cohort_sha256") != report["cohort_sha256"]
                        or digest(saved["data"]) != saved.get("sha256")
                        or saved["data"]["revision"] != revision["id"]
                    ):
                        raise ValueError("archive checkpoint mismatch")
                else:
                    data = select_snapshot(budget, revision, cohort)
                    saved = {
                        "data": data,
                        "sha256": digest(data),
                        "cohort_sha256": report["cohort_sha256"],
                    }
                    tmp = path.with_suffix(".tmp")
                    tmp.write_text(json.dumps(saved))
                    tmp.replace(path)
                return {
                    "day": day,
                    "rows": len(saved["data"]["rows"]),
                    "artifact": path.name,
                    "sha256": saved["sha256"],
                }

            with ThreadPoolExecutor(max_workers=4) as pool:
                jobs = {
                    pool.submit(collect, pair): pair[0]
                    for pair in sorted(revisions.items(), reverse=True)
                }
                for future in as_completed(jobs):
                    try:
                        report["completed"].append(future.result())
                    except (
                        ValueError,
                        KeyError,
                        TypeError,
                        httpx.HTTPError,
                        OSError,
                    ) as exc:
                        report["failed"].append(
                            {
                                "day": jobs[future],
                                "reason": str(exc)[:150]
                                if isinstance(exc, ValueError)
                                else type(exc).__name__,
                            }
                        )
                    report.update(
                        requests_this_run=budget.requests, bytes_this_run=budget.bytes
                    )
                    (root / "coverage.json").write_text(json.dumps(report, indent=2))
                    self.stdout.write(
                        json.dumps(
                            {
                                "completed": len(report["completed"]),
                                "failed": len(report["failed"]),
                                "requests": budget.requests,
                                "bytes": budget.bytes,
                            }
                        )
                    )
                    self.stdout.flush()
        report["complete"] = len(report["completed"]) == len(revisions)
        (root / "coverage.json").write_text(json.dumps(report, indent=2))
        if not report["complete"]:
            raise CommandError(
                "HF archive acquisition incomplete; inspect coverage.json. Successful checkpoints are reusable."
            )
