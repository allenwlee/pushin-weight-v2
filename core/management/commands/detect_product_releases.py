"""Bounded, resumable replay of canonical stored release evidence."""

import hashlib
import json
import time
from collections import Counter
from dataclasses import asdict

from django.core.management.base import BaseCommand, CommandError

from core.product_release_intake import RULE_VERSION, detect
from core.product_release_pipeline import persist_source
from core.product_release_replay import ReplayWindow
from core.product_release_sources import observation_page, post_page


class Command(BaseCommand):
    help = "Detect stored product releases without provider/model calls; dry-run unless --persist."

    def add_arguments(self, parser):
        parser.add_argument("--start", required=True)
        parser.add_argument("--end", required=True)
        parser.add_argument("--timezone")
        parser.add_argument(
            "--clock",
            choices=["collection", "publication", "first_storage"],
            default="collection",
        )
        parser.add_argument(
            "--source", choices=["post", "observation", "both"], default="both"
        )
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--max-batches", type=int, default=1)
        parser.add_argument(
            "--cursor", help="JSON next_cursor returned by the previous invocation"
        )
        parser.add_argument("--persist", action="store_true")

    def handle(self, *args, **options):
        try:
            window = ReplayWindow.parse(
                options["start"], options["end"], timezone=options["timezone"]
            )
            if (
                not 1 <= options["batch_size"] <= 2000
                or not 1 <= options["max_batches"] <= 1000
            ):
                raise ValueError("batch-size must be 1..2000 and max-batches 1..1000")
            selection = {
                "start": window.start.isoformat(),
                "end": window.end.isoformat(),
                "clock": options["clock"],
                "source": options["source"],
                "rule_version": RULE_VERSION,
            }
            selection_hash = hashlib.sha256(
                json.dumps(selection, sort_keys=True).encode()
            ).hexdigest()
            cursor = (
                json.loads(options["cursor"])
                if options["cursor"]
                else {
                    "selection": selection_hash,
                    "post": "",
                    "observation": 0,
                    "complete": [],
                }
            )
            if (
                set(cursor) != {"selection", "post", "observation", "complete"}
                or cursor["selection"] != selection_hash
            ):
                raise ValueError("Cursor does not match this selection/rule version")
            if (
                not isinstance(cursor["post"], str)
                or type(cursor["observation"]) is not int
                or cursor["observation"] < 0
                or not isinstance(cursor["complete"], list)
                or not set(cursor["complete"]) <= {"post", "observation"}
            ):
                raise ValueError("Invalid cursor values")
        except (ValueError, TypeError, KeyError) as error:
            raise CommandError(str(error)) from error
        counts, coverage, limitations = Counter(), Counter(), Counter()
        samples, nonmatches, digest = [], [], hashlib.sha256()
        started = time.monotonic()
        sources = (
            ["post", "observation"]
            if options["source"] == "both"
            else [options["source"]]
        )
        batches = 0
        for namespace in sources:
            if namespace in cursor["complete"]:
                continue
            loader = post_page if namespace == "post" else observation_page
            while batches < options["max_batches"]:
                rows = loader(
                    window,
                    clock=options["clock"],
                    after=cursor[namespace],
                    limit=options["batch_size"],
                )
                batches += 1
                for row in rows:
                    counts[f"{namespace}_read"] += 1
                    coverage[row.clock_basis] += 1
                    limitations.update(row.limitations)
                    digest.update(
                        json.dumps(asdict(row), sort_keys=True, default=str).encode()
                    )
                    candidate = detect(row.record)
                    if candidate is not None:
                        counts["candidates"] += 1
                        result = (
                            persist_source(row)
                            if options["persist"]
                            else {
                                "source": row.record.identity,
                                "disposition": candidate.disposition,
                                "dossier_ids": [],
                                "cautions": candidate.cautions,
                            }
                        )
                        counts["sources_persisted"] += int(options["persist"])
                        if len(samples) < 20:
                            samples.append(result)
                    elif len(nonmatches) < 20:
                        nonmatches.append(
                            {"source": row.record.identity, "url": row.source_url}
                        )
                    cursor[namespace] = (
                        row.post_id if namespace == "post" else row.observation_id
                    )
                if len(rows) < options["batch_size"]:
                    cursor["complete"].append(namespace)
                    break
        result = {
            "selection": selection,
            "mode": "persist" if options["persist"] else "dry_run",
            "counts": counts,
            "clock_coverage": coverage,
            "limitations": limitations,
            "enrichment_view": "current_saved_state_not_as_known_then",
            "input_hash": digest.hexdigest(),
            "sample_candidates": samples,
            "sample_nonmatches": nonmatches,
            "batches": batches,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "next_cursor": cursor,
            "complete": set(sources) <= set(cursor["complete"]),
            "additional_model_calls": 0,
            "provider_calls": 0,
        }
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
