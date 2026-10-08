"""Replay verified HF backfill checkpoints through the shared metric writer."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.benchmark_metric_history import import_history
from core.benchmark_metric_store import persist_source
from core.measurement_taxonomy import digest
from core.models import MetricCollectionContract


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("directory")
        parser.add_argument("--kind", choices=["archive", "engagement"], required=True)
        parser.add_argument("--contract", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--isolated-review", action="store_true")
        parser.add_argument("--allow-incomplete", action="store_true")

    def handle(self, *args, **opts):
        root = Path(opts["directory"])
        coverage = json.loads((root / "coverage.json").read_text())
        if not coverage["complete"] and not opts["allow_incomplete"]:
            raise CommandError(
                "Acquisition incomplete; explicit --allow-incomplete required to import available checkpoints"
            )
        contract = MetricCollectionContract.objects.get(pk=opts["contract"])
        report = {
            "contract": str(contract.pk),
            "kind": opts["kind"],
            "acquisition_complete": coverage["complete"],
            "apply": opts["apply"],
            "files": 0,
            "rows": 0,
            "runs": [],
            "complete": False,
        }
        for entry in coverage["completed"]:
            name = entry["artifact"]
            if Path(name).name != name:
                raise CommandError("Invalid checkpoint path")
            path = root / name
            if path.stat().st_size > 32 * 1024**2:
                raise CommandError("Checkpoint byte cap")
            saved = json.loads(path.read_text())
            data = saved["data"]
            if digest(data) != saved["sha256"]:
                raise CommandError("Checkpoint hash mismatch")
            if entry.get("sha256", saved["sha256"]) != saved["sha256"]:
                raise CommandError("Coverage checkpoint hash mismatch")
            if opts["kind"] == "archive":
                day = entry["day"]
                if data["archive_published_at"][:10] != day or saved.get(
                    "cohort_sha256"
                ) != coverage.get("cohort_sha256"):
                    raise CommandError("Archive checkpoint identity mismatch")
                payload = {
                    "status": "ok",
                    "rows": [{"repo_id": r["id"], "raw": r} for r in data["rows"]],
                }
                manifest = {
                    "schema_version": 1,
                    "source": "hf",
                    "contract_id": str(contract.pk),
                    "dataset_id": "cfahlgren1/hub-stats",
                    "archive_publisher": "cfahlgren1",
                    "artifact_kind": "selected_json",
                    "start_date": day,
                    "end_date": day,
                    "snapshots": [
                        {
                            "date": day,
                            "immutable_revision": data["revision"],
                            "file_path": data["file_path"],
                            "snapshot_timezone": "UTC",
                            "raw_artifact_sha256": digest(payload),
                            "upstream_retrieval_coordinates": {
                                "archive_published_at": data["archive_published_at"],
                                "retrieved_at": data["retrieved_at"],
                                "file_size": data["upstream_file_size"],
                                "selected_ranges_sha256": digest(
                                    data["selected_ranges"]
                                ),
                                "selected_ranges_count": len(data["selected_ranges"]),
                                "acquisition_artifact": name,
                                "acquisition_artifact_sha256": saved["sha256"],
                            },
                            "payload": payload,
                        }
                    ],
                }
                if payload["rows"]:
                    result = import_history(
                        manifest,
                        apply=opts["apply"],
                        isolated_review=opts["isolated_review"],
                    )
                    if opts["apply"]:
                        self.check_run(result)
                        report["runs"].append(str(result.pk))
                report["rows"] += len(payload["rows"])
            else:
                if (
                    data["kind"] not in {"repository", "organization", "individual"}
                    or entry.get("identifier", data["identifier"]) != data["identifier"]
                    or entry.get("kind", data["kind"]) != data["kind"]
                ):
                    raise CommandError("Engagement checkpoint identity mismatch")
                identity = (
                    {"repo_id": data["identifier"]}
                    if data["kind"] == "repository"
                    else {
                        "account_identifier": data["identifier"],
                        "account_kind": data["kind"],
                    }
                )
                current = {
                    "status": "ok",
                    "rows": [
                        {
                            **identity,
                            "raw": data["current"],
                            "observed_at": data["observed_at"],
                        }
                    ],
                }
                wire = "likes" if data["kind"] == "repository" else "numFollowers"
                rows = [
                    {
                        **identity,
                        "raw": {wire: value},
                        "_source_metadata": {
                            "history_basis": "reconstructed_current_relationships",
                            "includes_removed_relationships": False,
                            "reconstruction_date": day,
                            "reconstruction_timezone": "UTC",
                            "retrieved_at": data["retrieved_at"],
                            "raw_artifact_sha256": saved["sha256"],
                        },
                    }
                    for day, value in data["counts"].items()
                ]
                report["rows"] += 1 + len(rows)
                for mode, payload in [
                    ("observed_snapshot", current),
                    (
                        "reconstructed_current_relationships",
                        {"status": "ok", "rows": rows},
                    ),
                ]:
                    if not payload["rows"]:
                        continue
                    if opts["apply"]:
                        result = persist_source(
                            contract,
                            "hf",
                            digest([contract.contract_hash, saved["sha256"], mode]),
                            payload,
                            isolated_review=opts["isolated_review"],
                            source_metadata={
                                "ingestion_mode": "direct"
                                if mode == "observed_snapshot"
                                else "historical_reconstruction",
                                "history_basis": mode,
                                "artifact_sha256": saved["sha256"],
                                "endpoint": data["endpoint"],
                                "page_sha256": data["page_sha256"],
                                "retrieved_at": data["retrieved_at"],
                            },
                        )
                        self.check_run(result)
                        report["runs"].append(str(result.pk))
                    else:
                        from core.benchmark_metric_store import prepare_rows

                        prepared = prepare_rows(contract, "hf", payload)
                        if any(row["status"] == "error" for row, _ in prepared):
                            raise CommandError(
                                "HF checkpoint contains invalid observation"
                            )
            report["files"] += 1
            if report["files"] % 25 == 0:
                (root / f"import-{contract.pk}.json").write_text(
                    json.dumps(report, indent=2)
                )
                self.stdout.write(
                    json.dumps({"files": report["files"], "rows": report["rows"]})
                )
                self.stdout.flush()
        report["complete"] = True
        (root / f"import-{contract.pk}.json").write_text(json.dumps(report, indent=2))
        self.stdout.write(
            json.dumps(
                {
                    "files": report["files"],
                    "rows": report["rows"],
                    "acquisition_complete": coverage["complete"],
                }
            )
        )

    def check_run(self, run):
        if (
            run.status not in {"success", "partial"}
            or run.observations.filter(status="error").exists()
        ):
            raise CommandError("HF import failed: " + str(run.pk))
