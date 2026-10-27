from __future__ import annotations

import json
import os
import signal
import threading
import uuid
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from monitor.cycle import CycleRunner
from monitor.enrichment_budget import config_fingerprint
from scripts.database_lock import DatabaseLockError
from x_monitor.config import load_config


class Command(BaseCommand):
    help = "Drain the existing scheduled enrichment queue without collecting posts."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--json", action="store_true", dest="as_json")
        parser.add_argument("--pilot", action="store_true")
        parser.add_argument("--post-ids-file", type=Path)
        parser.add_argument("--max-batches", type=int)

    def handle(self, *args, **options):
        cfg = load_config(Path("config.yaml"))
        control = cfg.harvest.enrichment
        environment = os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT")
        if environment not in {"staging", "production"} or not os.environ.get(
            "DATABASE_URL"
        ):
            raise CommandError("enrichment worker database/environment is invalid")
        max_batches = options["max_batches"]
        if max_batches is not None and max_batches < 1:
            raise CommandError("--max-batches must be positive")
        ids = None
        if options["post_ids_file"]:
            ids = set(json.loads(options["post_ids_file"].read_text()))
            if not ids or any(not isinstance(value, str) or not value for value in ids):
                raise CommandError("post IDs must be a nonempty JSON list of strings")
        if options["pilot"] and (ids is None or len(ids) > 200 or max_batches is None):
            raise CommandError(
                "pilot requires at most 200 exact post IDs and --max-batches"
            )
        if control.provider_calls_active and (
            control.mode != "worker" or not control.budget_window_id
        ):
            raise CommandError(
                "active worker requires worker mode and an explicit budget window"
            )
        if cfg.synthesis.concurrency > control.other_gemma_concurrency:
            raise CommandError(
                "commentary concurrency exceeds its declared Gemma allowance"
            )
        if not control.provider_calls_active and options["once"]:
            raise CommandError("enrichment provider calls are disabled")

        stopped = threading.Event()
        previous = {}
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGTERM, signal.SIGINT):
                previous[signum] = signal.signal(signum, lambda *_: stopped.set())
        batches = 0
        try:
            self.stdout.write(
                json.dumps(
                    {
                        "enrichment_worker": "active"
                        if control.provider_calls_active
                        else "idle",
                        "revision": os.environ.get("RENDER_GIT_COMMIT", "local"),
                        "config_fingerprint": config_fingerprint(cfg),
                        "process_limit": control.max_worker_processes,
                        "translation_slots": control.translation_concurrency,
                        "classification_slots": control.classification_concurrency,
                    },
                    sort_keys=True,
                )
            )
            while not stopped.is_set():
                if not control.provider_calls_active:
                    stopped.wait(control.poll_seconds)
                    continue
                from x_monitor.reattribute import (
                    build_classifier_client_from_env,
                    build_translator_client_from_env,
                )

                purpose = (
                    {"deepinfra_key_env": "DEEPINFRA_ON_DEMAND"}
                    if options["pilot"]
                    else {}
                )
                clients = {
                    "translation": build_translator_client_from_env(cfg, **purpose),
                    "classification": build_classifier_client_from_env(cfg, **purpose),
                }
                if any(client is None for client in clients.values()):
                    raise CommandError("enrichment provider credential unavailable")
                runner = CycleRunner(
                    cfg=cfg,
                    cycle_kind="enrichment",
                    _post_fetch_clients=clients,
                    _max_llm_calls=control.max_calls_per_batch,
                )
                result = runner._run_post_fetch(
                    [],
                    run_id=f"enrichment-{uuid.uuid4().hex}",
                    fair_queue=True,
                    post_ids=ids,
                    scope="pilot" if options["pilot"] else "scheduled",
                    stop_event=stopped,
                )
                batches += 1
                self.stdout.write(json.dumps(result, sort_keys=True, default=str))
                close_old_connections()
                reason = result.get("enrichment_stop_reason")
                if reason and reason not in {
                    "enrichment_batch_budget_exhausted",
                    "enrichment_stopping",
                }:
                    raise CommandError(reason)
                if options["once"] or (
                    max_batches is not None and batches >= max_batches
                ):
                    return
                if not result.get("n_enrichment_claimed"):
                    stopped.wait(control.poll_seconds)
        except DatabaseLockError as exc:
            raise CommandError(str(exc)) from exc
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
