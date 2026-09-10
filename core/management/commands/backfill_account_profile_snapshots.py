"""Build compressed profile history from already-persisted account facts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Account, Post, TwitterListMembership
from core.profile_snapshots import (
    build_brand_reference_index,
    classify_affiliation_signals,
    persist_affiliation_candidates,
    profile_observation_from_account,
    profile_observation_from_post,
    record_profile_snapshot,
)

COMMAND_VERSION = "account-profile-backfill-v1"


class Command(BaseCommand):
    help = (
        "Build deterministic profile snapshots and unreviewed affiliation "
        "candidates from local database facts; makes no provider calls."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--after-author-id")
        parser.add_argument("--limit-accounts", type=int)
        parser.add_argument("--checkpoint", type=Path)
        parser.add_argument("--report", type=Path)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options) -> None:
        if options["limit_accounts"] is not None and options["limit_accounts"] < 1:
            raise CommandError("--limit-accounts must be positive")

        checkpoint_path: Path | None = options["checkpoint"]
        checkpoint = self._read_checkpoint(checkpoint_path)
        after_author_id = options["after_author_id"]
        if after_author_id is None and checkpoint is not None:
            after_author_id = checkpoint.get("last_completed_author_id")

        accounts = (
            Account.objects.filter(posts__isnull=False).distinct().order_by("author_id")
        )
        if after_author_id:
            accounts = accounts.filter(author_id__gt=str(after_author_id))
        if options["limit_accounts"] is not None:
            accounts = accounts[: options["limit_accounts"]]

        references = build_brand_reference_index()
        report: dict[str, Any] = {
            "command_version": COMMAND_VERSION,
            "dry_run": bool(options["dry_run"]),
            "resumed_after_author_id": after_author_id,
            "accounts_processed": 0,
            "observations_processed": 0,
            "snapshots_created": 0,
            "snapshots_changed": 0,
            "snapshots_unchanged": 0,
            "candidate_counts": {
                "staff": 0,
                "community": 0,
                "unknown": 0,
                "official": 0,
            },
            "call_a": {
                "active_accounts_processed": 0,
                "with_brand_role": 0,
                "missing_brand_role": 0,
                "unmatched_brand": 0,
            },
            "last_completed_author_id": None,
        }

        for account in accounts.iterator(chunk_size=100):
            account_report = self._process_account(
                account=account,
                references=references,
                dry_run=options["dry_run"],
            )
            report["accounts_processed"] += 1
            report["observations_processed"] += account_report["observations"]
            for key in (
                "snapshots_created",
                "snapshots_changed",
                "snapshots_unchanged",
            ):
                report[key] += account_report[key]
            for key, value in account_report["candidate_counts"].items():
                report["candidate_counts"][key] += value
            for key, value in account_report["call_a"].items():
                report["call_a"][key] += value
            report["last_completed_author_id"] = str(account.pk)
            if checkpoint_path is not None and not options["dry_run"]:
                self._write_json(checkpoint_path, report)

        report_path: Path | None = options["report"]
        if report_path is not None:
            self._write_json(report_path, report)
        self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))

    @staticmethod
    def _process_account(*, account, references, dry_run: bool) -> dict[str, Any]:
        result: dict[str, Any] = {
            "observations": 0,
            "snapshots_created": 0,
            "snapshots_changed": 0,
            "snapshots_unchanged": 0,
            "candidate_counts": {
                "staff": 0,
                "community": 0,
                "unknown": 0,
                "official": 0,
            },
            "call_a": {
                "active_accounts_processed": 0,
                "with_brand_role": 0,
                "missing_brand_role": 0,
                "unmatched_brand": 0,
            },
        }
        active_call_a = TwitterListMembership.objects.filter(
            account=account, active=True, source="call_a"
        ).exists()
        has_brand_role = account.brands.exists()
        if active_call_a:
            result["call_a"]["active_accounts_processed"] = 1
            key = "with_brand_role" if has_brand_role else "missing_brand_role"
            result["call_a"][key] = 1

        observations = []
        posts = Post.objects.filter(author=account).order_by("fetched_at", "tweet_id")
        for post in posts.iterator(chunk_size=500):
            observation = profile_observation_from_post(post)
            if observation.present_fields:
                observations.append((post.fetched_at, "post", post, observation))
        account_observation = profile_observation_from_account(account)
        if account_observation.present_fields:
            observations.append(
                (
                    account.last_seen_at,
                    "account",
                    None,
                    account_observation,
                )
            )
        observations.sort(key=lambda value: (value[0], value[1], str(value[2] or "")))
        result["observations"] = len(observations)

        if dry_run:
            prior_hash = None
            for _observed_at, _kind, _post, observation in observations:
                if observation.profile_hash == prior_hash:
                    result["snapshots_unchanged"] += 1
                else:
                    result["snapshots_created"] += 1
                    result["snapshots_changed"] += int(prior_hash is not None)
                    prior_hash = observation.profile_hash
                signals = classify_affiliation_signals(
                    account=account,
                    observation=observation,
                    references=references,
                )
                for signal in signals:
                    result["candidate_counts"][signal.candidate_role] += 1
            if (
                active_call_a
                and not has_brand_role
                and not any(result["candidate_counts"].values())
            ):
                result["call_a"]["unmatched_brand"] = 1
            return result

        with transaction.atomic():
            for observed_at, source_kind, post, observation in observations:
                snapshot, created, changed = record_profile_snapshot(
                    account=account,
                    observation=observation,
                    observed_at=observed_at,
                    source_kind=source_kind,
                    source_post=post,
                    source_run=(COMMAND_VERSION if post is None else None),
                )
                result["snapshots_created"] += int(created)
                result["snapshots_changed"] += int(changed)
                result["snapshots_unchanged"] += int(not created)
                signals = classify_affiliation_signals(
                    account=account,
                    observation=observation,
                    references=references,
                )
                counts = persist_affiliation_candidates(
                    account=account,
                    snapshot=snapshot,
                    signals=signals,
                    observed_at=observed_at,
                )
                for key, value in counts.items():
                    result["candidate_counts"][key] += value
            if (
                active_call_a
                and not has_brand_role
                and not any(result["candidate_counts"].values())
            ):
                result["call_a"]["unmatched_brand"] = 1
        return result

    @staticmethod
    def _read_checkpoint(path: Path | None) -> dict[str, Any] | None:
        if path is None or not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CommandError(f"could not read checkpoint: {path}") from exc
        if value.get("command_version") != COMMAND_VERSION:
            raise CommandError("checkpoint command_version is incompatible")
        return value

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_name(f".{path.name}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise CommandError(f"could not write output: {path}") from exc
