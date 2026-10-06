"""Explicit operator entry point for model-lab discovery and coverage."""

import json
import os
import time
import uuid
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from core.models import Account, OfficialCompanyAccountState, OfficialCompanyListIntent
from core.official_company_accounts import enqueue_account, register_account
from core.official_company_discovery import (
    build_discovery_call,
    coverage,
    drain_accounts,
    enqueue_incremental,
    scan_initial_batch,
)
from monitor.run_lock import harvest_writer_lock
from x_monitor.config import load_config


class Command(BaseCommand):
    help = "Inspect or explicitly run bounded official AI model-lab account discovery."

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            choices=[
                "inspect",
                "initial-scan",
                "incremental",
                "enqueue",
                "drain",
                "register",
                "retry",
                "suppress",
                "sync",
                "provision-owner",
                "refresh-owner",
                "resume-model",
            ],
        )
        parser.add_argument("--account-id", action="append", default=[])
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--seconds", type=int, default=45)
        parser.add_argument("--initial", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--config", default="config.yaml")
        parser.add_argument("--replace-owner-credential", action="store_true")

    def handle(self, *args, **opts):
        action = opts["action"]
        limit = opts["limit"]
        ids = opts["account_id"]
        if not 1 <= limit <= 500 or not 5 <= opts["seconds"] <= 120:
            raise CommandError("limit must be 1..500 and seconds 5..120")
        if action in {"enqueue", "retry", "suppress", "register"} and not ids:
            raise CommandError("this action requires explicit --account-id bounds")
        if len(ids) > limit:
            raise CommandError("account set exceeds limit")
        if opts["dry_run"] or action == "inspect":
            result = coverage()
            result["all_outcomes"] = dict(
                OfficialCompanyAccountState.objects.values("status")
                .annotate(n=Count("pk"))
                .values_list("status", "n")
            )
            result["list_outcomes"] = dict(
                OfficialCompanyListIntent.objects.values("status")
                .annotate(n=Count("pk"))
                .values_list("status", "n")
            )
            if ids:
                result["accounts"] = list(
                    OfficialCompanyAccountState.objects.filter(
                        account_id__in=ids
                    ).values("account_id", "status", "last_error", "decision")
                )
            self.stdout.write(json.dumps(result))
            return
        cfg = load_config(Path(opts["config"])).official_company
        if not cfg.enabled:
            raise CommandError("official company discovery is disabled")
        run_id = "official-co-" + uuid.uuid4().hex
        with harvest_writer_lock(
            execution_mode="manual",
            entrypoint="official_co_account_extraction",
            run_id=run_id,
        ) as lease:
            if not lease.acquired:
                self.stdout.write(
                    json.dumps({"status": "writer_busy", "run_id": run_id})
                )
                return
            deadline = time.monotonic() + opts["seconds"]
            if action in {"provision-owner", "refresh-owner"}:
                from core.official_company_credentials import OwnerTokenStore
                from core.official_company_lists import XListError

                try:
                    store = OwnerTokenStore.from_env()
                    if action == "provision-owner":
                        store.provision(
                            access_token=os.environ.get(
                                "PUSHINWEIGHT_X_LIST_ACCESS_TOKEN"
                            ),
                            refresh_token=os.environ.get(
                                "PUSHINWEIGHT_X_LIST_REFRESH_TOKEN"
                            ),
                            replace=opts["replace_owner_credential"],
                        )
                    else:
                        store.refresh()
                    result = {"status": "ready", "action": action}
                except XListError as exc:
                    raise CommandError(str(exc)) from None
            elif action == "resume-model":
                from core.models import OfficialCompanyProviderState

                result = {
                    "resumed": OfficialCompanyProviderState.objects.filter(
                        key="deepinfra"
                    ).update(blocked_reason="")
                }
            elif action == "initial-scan":
                result = scan_initial_batch(limit=limit, deadline=deadline)
            elif action == "incremental":
                result = {
                    "enqueued": enqueue_incremental(
                        limit=min(100, limit), deadline=deadline
                    )
                }
            elif action == "enqueue":
                result = {
                    "enqueued": sum(
                        1
                        for account in Account.objects.filter(pk__in=ids)
                        if enqueue_account(account)
                    )
                }
            elif action == "drain":
                call = build_discovery_call(cfg)
                if call is None:
                    raise CommandError("official company model client unavailable")
                result = drain_accounts(
                    cfg=cfg,
                    call=call,
                    limit=limit,
                    budget_scope=run_id,
                    initial=opts["initial"],
                    deadline=deadline,
                )
            elif action == "register":
                result = {
                    "registered": sum(
                        int(register_account(pk, cfg=cfg) is not None)
                        for pk in OfficialCompanyAccountState.objects.filter(
                            account_id__in=ids
                        ).values_list("pk", flat=True)
                    )
                }
            elif action in {"retry", "suppress"}:
                with transaction.atomic():
                    states = (
                        OfficialCompanyAccountState.objects.select_for_update().filter(
                            account_id__in=ids
                        )
                    )
                    for state in states:
                        if action == "retry" and state.status == "suppressed":
                            raise CommandError(
                                "suppression requires a separately reviewed evidence decision"
                            )
                        state.status = (
                            "suppressed"
                            if action == "suppress"
                            else (
                                "registered"
                                if state.status == "registered"
                                else "pending"
                            )
                        )
                        state.claim_token = ""
                        state.claim_expires_at = None
                        state.next_attempt_at = None
                        state.attempts = 0
                        state.save()
                    changed = (
                        OfficialCompanyListIntent.objects.filter(account_id__in=ids)
                        .exclude(status="confirmed")
                        .update(
                            status="suppressed"
                            if action == "suppress"
                            else "verify_needed",
                            claim_token="",
                            claim_expires_at=None,
                            next_attempt_at=None,
                            attempts=0,
                        )
                    )
                result = {"accounts": len(ids), "list_intents": changed}
            else:
                from core.official_company_lists import (
                    build_owner_list_client,
                    sync_intents,
                )

                result = sync_intents(
                    cfg=cfg, client=build_owner_list_client(cfg), deadline=deadline
                )
        self.stdout.write(json.dumps({"run_id": run_id, **result}))
