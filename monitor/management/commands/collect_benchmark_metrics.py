"""Bounded manual collection; no catalog refresh and no scheduler activation."""

import json
import os
import uuid
from contextlib import nullcontext
from datetime import date

import httpx
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError

from core.benchmark_metric_identity import SOURCE_STATISTICS_POLICY
from core.benchmark_metric_store import collection_lock, persist_source
from core.measurement_taxonomy import digest
from core.models import MetricCollectionContract
from scripts.benchmark_download_collector import sources
from scripts.benchmark_download_collector.identity import days


class Command(BaseCommand):
    help = "Collect a reviewed source into shared metric history; requires --apply."

    def add_arguments(self, parser):
        parser.add_argument("--contract", required=True)
        parser.add_argument(
            "--source",
            required=True,
            choices=["hf", "github", "openrouter", "arena", "opencode"],
        )
        parser.add_argument("--start-date", required=True)
        parser.add_argument("--end-date", required=True)
        parser.add_argument("--batch-id", default=None)
        parser.add_argument("--job", default=None)
        parser.add_argument("--slot", default=None)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--isolated-review", action="store_true")
        parser.add_argument("--max-requests", type=int, default=20)
        parser.add_argument("--max-seconds", type=int, default=120)
        parser.add_argument("--max-bytes", type=int, default=8 * 1024 * 1024)
        parser.add_argument(
            "--openrouter-key-env", default="BENCHMARK_OPENROUTER_API_KEY"
        )

    def handle(self, *args, **options):
        claim = None
        budget = None
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
                                purpose="metric", source_id=source
                            ).count(),
                        }
                    )
                )
                return
            if (
                contract.source_configuration[source].get("eligibility_policy")
                == SOURCE_STATISTICS_POLICY
            ):
                from core.models import CollectionJob
                from core.source_metric_projection import replay_saved_evidence

                if not options["job"]:
                    raise ValueError("source statistics require a reviewed source job")
                selected = CollectionJob.objects.get(pk=options["job"])
                if (
                    selected.contract_id != contract.pk
                    or selected.source_id != source
                    or selected.campaign_settings.get("phase") != "replay"
                ):
                    raise ValueError(
                        "source-statistics acquisition hook is unavailable; select a saved-evidence replay job"
                    )
                run = replay_saved_evidence(selected.pk)
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
                return
            if options["job"]:
                from core.benchmark_attribution import enforce_source_collection
                from core.collection_state import claim_job, fenced_run
                from core.models import CollectionJob

                job = CollectionJob.objects.get(pk=options["job"])
                enforce_source_collection(
                    contract, source, isolated_review=options["isolated_review"]
                )
                if (
                    job.contract_id != contract.pk
                    or job.source_id != source
                    or job.operation != "collect_metrics"
                ):
                    raise ValueError("metric job/contract/source mismatch")
                for flag, name in (
                    ("max_requests", "requests"),
                    ("max_seconds", "seconds"),
                    ("max_bytes", "bytes"),
                ):
                    options[flag] = min(options[flag], job.budgets[name])
                claim = claim_job(job.pk)
                with fenced_run(claim) as (_, active):
                    active.report = {**active.report, "schedule_slot": options["slot"]}
                    active.save(update_fields=["report", "updated_at"])
            batch = (
                uuid.UUID(options["batch_id"]) if options["batch_id"] else uuid.uuid4()
            )
            params = {
                "start_date": options["start_date"],
                "end_date": options["end_date"],
            }
            key = digest([contract.contract_hash, source, str(batch), params])
            if claim is not None:
                key = active.ingestion_key
            with (
                httpx.Client() as client,
                (
                    collection_lock(contract, source)
                    if claim is not None
                    else nullcontext()
                ),
            ):
                budget = sources.Budget(
                    client,
                    max_requests=options["max_requests"],
                    max_seconds=options["max_seconds"],
                    max_bytes=options["max_bytes"],
                    cumulative=claim is not None,
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
                                **(
                                    {
                                        "account_identifier": m.external_identifier,
                                        "account_kind": m.identifier_scope,
                                    }
                                    if m.source_subject_kind == "account"
                                    else {"repo_id": m.external_identifier}
                                ),
                            }
                            for m in contract.mappings.filter(
                                purpose="metric", source_id="hf"
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
                    elif source == "opencode":
                        result = sources.opencode(
                            budget,
                            [
                                {
                                    "external_identifier": m.external_identifier,
                                    "endpoint_path": m.identifier_metadata[
                                        "endpoint_path"
                                    ],
                                }
                                for m in contract.mappings.filter(
                                    purpose="metric", source_id=source
                                )
                            ],
                        )
                    else:
                        result = sources.arena(
                            budget,
                            params["start_date"],
                            params["end_date"],
                            config=contract.source_configuration[source].get(
                                "config", "text_style_control"
                            ),
                        )
                    result["request_count"] = options["max_requests"] - budget.remaining
                    return result

                fetched = None
                if claim is not None:
                    from core.collection_capture import capture_budget

                    with capture_budget(
                        claim,
                        budget,
                        scope_kind="metric_fetch",
                        scope_key="source",
                        ownership={"contract_id": str(contract.pk)},
                        requested_start_date=date.fromisoformat(params["start_date"]),
                        requested_end_date=date.fromisoformat(params["end_date"]),
                    ):
                        fetched = fetch()
                if (
                    claim is not None
                    and len(fetched.get("rows", [])) > job.budgets["items"]
                ):
                    raise ValueError("metric job item cap")
                run = persist_source(
                    contract,
                    source,
                    key,
                    isolated_review=options["isolated_review"],
                    request_params=params,
                    source_metadata={
                        "ingestion_mode": "direct",
                        "adapter_version": contract.source_configuration[source][
                            "adapter_key"
                        ],
                        "batch_id": str(batch),
                        "physical_bytes_received": budget.total_bytes_read,
                    },
                    payload=fetched,
                    fetch=fetch if claim is None else None,
                    batch_id=batch,
                    claim=claim,
                    transport_budget=budget,
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
            if claim is not None:
                from core.collection_state import StaleClaim, finish_run

                try:
                    finish_run(
                        claim,
                        status="failed",
                        error_code="invalid_metric_execution",
                        request_count=options["max_requests"] - budget.remaining
                        if budget
                        else 0,
                        report={
                            "physical_bytes_received": budget.total_bytes_read
                            if budget
                            else 0
                        },
                    )
                except StaleClaim:
                    pass
            raise CommandError(str(exc)) from exc
