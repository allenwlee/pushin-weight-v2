"""Bounded manual collection; no catalog refresh and no scheduler activation."""

import json
import os
import uuid

import httpx
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError

from core.benchmark_metric_store import persist_source
from core.measurement_taxonomy import digest
from core.models import MetricCollectionContract
from scripts.benchmark_download_collector import sources
from scripts.benchmark_download_collector.identity import days


class Command(BaseCommand):
    help = "Collect a reviewed source into shared metric history; requires --apply."

    def add_arguments(self, parser):
        parser.add_argument("--contract", required=True)
        parser.add_argument(
            "--source", required=True, choices=["hf", "openrouter", "arena"]
        )
        parser.add_argument("--start-date", required=True)
        parser.add_argument("--end-date", required=True)
        parser.add_argument("--batch-id", default=None)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--max-requests", type=int, default=20)
        parser.add_argument("--max-seconds", type=int, default=120)
        parser.add_argument("--max-bytes", type=int, default=8 * 1024 * 1024)
        parser.add_argument(
            "--openrouter-key-env", default="BENCHMARK_OPENROUTER_API_KEY"
        )

    def handle(self, *args, **options):
        try:
            contract = MetricCollectionContract.objects.get(pk=options["contract"])
            source = options["source"]
            days(options["start_date"], options["end_date"])
            if source not in contract.source_configuration:
                raise ValueError("source outside contract")
            if (
                not 1 <= options["max_requests"] <= 100
                or not 1 <= options["max_seconds"] <= 300
                or not 1 <= options["max_bytes"] <= 32 * 1024 * 1024
            ):
                raise ValueError("resource budget outside allowed range")
            for key in ("max_requests", "max_seconds", "max_bytes"):
                options[key] = min(
                    options[key],
                    contract.source_configuration[source].get(key, options[key]),
                )
            if not options["apply"]:
                self.stdout.write(
                    json.dumps(
                        {
                            "applied": False,
                            "source": source,
                            "selected_subjects": contract.mappings.filter(
                                source_id=source
                            ).count(),
                        }
                    )
                )
                return
            batch = (
                uuid.UUID(options["batch_id"]) if options["batch_id"] else uuid.uuid4()
            )
            params = {
                "start_date": options["start_date"],
                "end_date": options["end_date"],
            }
            key = digest([contract.contract_hash, source, str(batch), params])
            with httpx.Client() as client:
                budget = sources.Budget(
                    client,
                    max_requests=options["max_requests"],
                    max_seconds=options["max_seconds"],
                    max_bytes=options["max_bytes"],
                )

                def fetch():
                    try:
                        return fetch_source()
                    except sources.SourceError:
                        return {
                            "status": "error",
                            "rows": [],
                            "request_count": options["max_requests"] - budget.remaining,
                        }

                def fetch_source():
                    if source == "hf":
                        selected = [
                            {
                                "product_key": str(m.subject.product_id),
                                "repo_id": m.external_identifier,
                            }
                            for m in contract.mappings.filter(
                                source_id="hf"
                            ).select_related("subject")
                        ]
                        result = sources.hf(budget, selected)
                    elif source == "openrouter":
                        result = sources.openrouter(
                            budget,
                            params["start_date"],
                            params["end_date"],
                            key=os.environ.get(options["openrouter_key_env"]),
                        )
                    else:
                        result = sources.arena(
                            budget, params["start_date"], params["end_date"]
                        )
                    result["request_count"] = options["max_requests"] - budget.remaining
                    return result

                run = persist_source(
                    contract,
                    source,
                    key,
                    request_params=params,
                    source_metadata={
                        "ingestion_mode": "direct",
                        "adapter_version": contract.source_configuration[source][
                            "adapter_key"
                        ],
                        "batch_id": str(batch),
                    },
                    fetch=fetch,
                    batch_id=batch,
                )
            self.stdout.write(
                json.dumps(
                    {
                        "run_id": str(run.pk),
                        "status": run.status,
                        "selected_count": run.selected_count,
                        "success_count": run.success_count,
                        "request_count": run.request_count,
                    }
                )
            )
            if run.status in {"failed", "aborted"}:
                raise CommandError(
                    f"Collection {run.status}: {run.error_code or 'no usable selected subjects'}"
                )
        except (ValueError, KeyError, ObjectDoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
