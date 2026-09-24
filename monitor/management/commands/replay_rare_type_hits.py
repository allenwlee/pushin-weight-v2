"""Explicit, bounded local replay of already-persisted rare-type hits."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.models import PostEnrichmentState, RareTypeSearchHit


class Command(BaseCommand):
    help = "Replay explicit saved rare-type hit IDs; dry-run by default."

    def add_arguments(self, parser):
        parser.add_argument("hit_ids", nargs="+", type=int)
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--max-hits", type=int, default=20)
        parser.add_argument("--max-llm-calls", type=int, default=None)
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        hit_ids = set(options["hit_ids"])
        if len(hit_ids) != len(options["hit_ids"]):
            raise CommandError("hit IDs must be unique")
        if (
            not hit_ids
            or len(hit_ids) > options["max_hits"]
            or options["max_hits"] > 20
        ):
            raise CommandError(
                "explicit hit count exceeds bounded --max-hits (maximum 20)"
            )
        found = set(
            RareTypeSearchHit.objects.filter(pk__in=hit_ids).values_list(
                "pk", flat=True
            )
        )
        missing = sorted(hit_ids - found)
        if missing:
            raise CommandError(f"unknown hit IDs: {missing}")
        if not options["commit"]:
            preview = {
                "schema_version": "rare-type-replay/v1",
                "mode": "dry-run",
                "hit_ids": sorted(hit_ids),
                "writes": 0,
                "provider_calls": 0,
            }
            self.stdout.write(
                json.dumps(preview, sort_keys=True)
                if options["as_json"]
                else f"dry-run: would replay hit IDs {sorted(hit_ids)}"
            )
            return
        if os.environ.get("RARE_TYPE_REPLAY_ENABLED") != "1":
            raise CommandError("committed replay is disabled in this environment")
        max_llm_calls = options["max_llm_calls"]
        if max_llm_calls is None:
            raise CommandError("committed replay requires explicit --max-llm-calls")
        if max_llm_calls < 0 or max_llm_calls > 20:
            raise CommandError("--max-llm-calls must be between 0 and 20")
        from core.rare_type_search import reconcile_classified_hits
        from core.targeted_extraction import build_targeted_extraction_calls
        from monitor.cycle import (
            CycleRunner,
            _build_brand_index,
            _load_brand_search_terms,
            _resolve_enabled_models,
        )
        from x_monitor.config import load_config
        from x_monitor.reattribute import build_relevancy_client_from_env

        cfg = load_config(Path("config.yaml"))
        enabled_models = _resolve_enabled_models(cfg, None)
        try:
            index = _build_brand_index(enabled_models)
        except Exception as exc:
            raise CommandError(
                f"attribution preflight failed: {type(exc).__name__}"
            ) from exc
        search_terms = _load_brand_search_terms()
        replay_run_id = f"rare-replay:{uuid.uuid4().hex[:12]}"
        runner = CycleRunner(
            cfg=cfg,
            dry_run=False,
            cycle_kind="manual",
            _max_llm_calls=max_llm_calls,
        )
        replay_deadline = cfg.harvest.start_deadline()
        drain = runner._drain_rare_type_hits(
            run_id=replay_run_id,
            index=index,
            search_terms=search_terms,
            hit_ids=hit_ids,
            allow_disabled=True,
            deadline=replay_deadline,
        )
        post_ids = set(
            RareTypeSearchHit.objects.filter(
                pk__in=hit_ids,
                gate_state=RareTypeSearchHit.GateState.KEPT,
                post_id__isnull=False,
            ).values_list("post_id", flat=True)
        )
        if (
            post_ids
            and cfg.targeted_extraction.enabled
            and cfg.targeted_extraction.max_calls_per_cycle > 0
        ):
            targeted_client = build_relevancy_client_from_env(cfg)
            runner._targeted_extraction_calls = build_targeted_extraction_calls(
                client=targeted_client,
                roles=cfg.targeted_extraction.roles,
                timeout_seconds=cfg.targeted_extraction.request_timeout_seconds,
            )
        previously_classified_post_ids = set(
            PostEnrichmentState.objects.filter(
                post_id__in=post_ids,
                classification_status=PostEnrichmentState.Status.SUCCEEDED,
            ).values_list("post_id", flat=True)
        )
        post_fetch = runner._run_post_fetch(
            [],
            run_id=replay_run_id,
            post_ids=post_ids,
            deadline=replay_deadline,
        )
        targeted_replay = runner._replay_targeted_extractions(
            post_ids=previously_classified_post_ids,
            deadline=replay_deadline,
        )
        reconciled = reconcile_classified_hits(
            now=runner._wall_now(),
            limit=len(hit_ids),
            hit_ids=hit_ids,
        )
        result = {
            "schema_version": "rare-type-replay/v1",
            "mode": "committed",
            "hit_ids": sorted(hit_ids),
            "post_ids": sorted(post_ids),
            "rare_type": drain,
            "post_fetch": post_fetch,
            "targeted_replay": targeted_replay,
            "classified_reconciled": reconciled,
            "twitterapi_calls": 0,
            "budgets": {
                "translation_and_classification_calls": max_llm_calls,
                "jev_normal_decisions": cfg.discovery.rare_types.jev.normal_decisions_per_cycle,
                "targeted_extraction_calls": cfg.targeted_extraction.max_calls_per_cycle,
                "hugging_face_requests": 0,
            },
        }
        self.stdout.write(
            json.dumps(result, sort_keys=True, default=str)
            if options["as_json"]
            else str(result)
        )
