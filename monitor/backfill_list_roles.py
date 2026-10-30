"""Copy production's Call A main-list members and X account roles into xbackfiller.

Planning a historical window freezes the Call A list members and their brand
roles from the database it runs in. The dedicated backfill database
(xbackfiller) learns neither by itself, so this module copies them from a saved,
read-only production export (``scripts/backfill_list_roles_production.sql``).

Operator flow:

1. On fuchitalee, run the export SQL against production with
   ``render psql ... -o json`` and save the full output.
2. Against xbackfiller, ``python manage.py sync_backfill_list_roles --export FILE``
   is a dry run: every write runs inside one transaction, the proofs run, and
   the transaction rolls back. ``--execute`` commits only when every proof passes.

Refusals happen before any write, in this order: an invalid export, a
non-backfill environment, any database other than xbackfiller, a live
historical lease, and a held harvest writer lock (the lease is checked again
once the lock is held).

The sync creates missing X accounts, creates or reactivates memberships with
source ``production_export``, deactivates main-list members absent from the
export, and creates or corrects roles whose brand and role key already exist.
It never creates or edits Brand, BrandKeyword, BrandSearchTerm, BrandHashtag,
Product or Role rows, never edits an existing account's handle, never deletes a
role and never writes ``TwitterListSyncState``. Skipped roles, xbackfiller-only
roles and differing handles are reported instead.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import (
    Account,
    Brand,
    BrandAccount,
    BrandHashtag,
    BrandKeyword,
    BrandSearchTerm,
    CollectionJob,
    CollectionRun,
    Product,
    Role,
    TwitterListMembership,
)
from monitor.account_geography_recovery import PRODUCTION_DATABASE_NAME
from monitor.backfill_staging import validate_staging
from monitor.cycle import (
    _classification_tracked_brand_catalog,
    _resolve_x_monitor_list_id,
)
from monitor.list_membership import (
    _upsert_account,
    _upsert_membership,
    resolve_call_a_author_contexts,
)
from monitor.run_lock import harvest_writer_lock
from x_monitor.attribution import _tracked_brand_catalog
from x_monitor.config import load_config

FORMAT = "x-backfill-list-roles/v1"
REPORT_FORMAT = "x-backfill-list-roles-report/v1"
MEMBERSHIP_SOURCE = "production_export"
RUN_ID_PREFIX = "production-export-sha256:"
BACKFILL_DATABASE = "xbackfiller"
ENTRYPOINT = "management.sync_backfill_list_roles"
CALL_A_ROLES = ("official", "staff")
# Rows the sync must never create, edit or delete.
PROTECTED_MODELS = (Brand, BrandKeyword, BrandSearchTerm, BrandHashtag, Product, Role)
COUNT_KEYS = (
    "accounts_created",
    "memberships_created",
    "memberships_reactivated",
    "memberships_unchanged",
    "memberships_deactivated",
    "roles_created",
    "roles_corrected",
    "roles_unchanged",
    "roles_skipped",
)


class SyncRefused(Exception):
    """A guard refused the sync; nothing was changed."""


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise SyncRefused(message)


# ---------------------------------------------------------------------------
# Reading the saved export (scans the render output once, never quadratically)
# ---------------------------------------------------------------------------


def _find_document(value: Any, expected_format: str, depth: int = 0) -> dict | None:
    if depth > 10:
        return None
    if isinstance(value, dict):
        if value.get("format") == expected_format:
            return value
        children: Iterable[Any] = value.values()
    elif isinstance(value, list):
        children = value
    elif isinstance(value, str) and expected_format in value:
        try:
            return _find_document(json.loads(value), expected_format, depth + 1)
        except ValueError:
            return None
    else:
        return None
    for child in children:
        found = _find_document(child, expected_format, depth + 1)
        if found is not None:
            return found
    return None


def load_document(text: str, expected_format: str) -> dict:
    """Find the export document in Render CLI output (JSON, CSV or plain text)."""
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    found = _find_document(parsed, expected_format) if parsed is not None else None
    if found is not None:
        return found
    # `render psql -o json` wraps psql's aligned table text in {"output": "..."}.
    # Scan only the strings inside parsed JSON. The raw JSON text is one long line
    # that names the format too, and retrying every "{" in it is quadratic.
    if parsed is None:
        texts = [text]
    elif isinstance(parsed, dict):
        texts = [value for value in parsed.values() if isinstance(value, str)]
    elif isinstance(parsed, list):
        texts = [value for value in parsed if isinstance(value, str)]
    else:
        texts = [parsed] if isinstance(parsed, str) else []
    decoder = json.JSONDecoder()
    for line in (line for candidate in texts for line in candidate.splitlines()):
        if expected_format not in line:
            continue
        for variant in (line, line.replace('""', '"')):
            start = variant.find("{")
            while start != -1:
                try:
                    value, _ = decoder.raw_decode(variant, start)
                except ValueError:
                    start = variant.find("{", start + 1)
                    continue
                found = _find_document(value, expected_format)
                if found is not None:
                    return found
                break
    raise ValueError(
        f"no {expected_format} document found; save the full output of the read-only query "
        "(psql must print the SELECT result, not only the last statement)"
    )


@dataclass(frozen=True)
class ProductionExport:
    path: str
    sha256: str
    database: str
    generated_at: datetime
    list_id: int
    members: tuple[dict[str, Any], ...]
    roles: tuple[dict[str, Any], ...]

    @property
    def source_run_id(self) -> str:
        return RUN_ID_PREFIX + self.sha256

    def summary(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "database": self.database,
            "generated_at": self.generated_at.isoformat(),
            "list_id": self.list_id,
            "members": len(self.members),
            "roles": len(self.roles),
        }


def _decimal_id(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = str(value).strip()
    return text if text.isascii() and text.isdecimal() else None


def _is_text_or_none(value: Any) -> bool:
    return value is None or isinstance(value, str)


def _clean_handle(value: str | None) -> str | None:
    return (value or "").strip() or None


def configured_list_id(config_path: Path = Path("config.yaml")) -> int:
    """The Call A list id exactly as planning resolves it."""
    list_id = _resolve_x_monitor_list_id(load_config(config_path))
    _require(list_id is not None, "the Call A list id is not configured")
    return int(list_id)


def read_export(path: Path | str, *, list_id: int) -> ProductionExport:
    """Validate a saved production export without touching any database."""
    path = Path(path)
    try:
        body = path.read_bytes()
        document = load_document(body.decode("utf-8"), FORMAT)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise SyncRefused(f"export unreadable: {exc}") from exc
    _require(document.get("database") == PRODUCTION_DATABASE_NAME, "export is not from production")
    exported_list = document.get("list_id")
    _require(type(exported_list) is int and exported_list == list_id, "export is for another list")
    try:
        generated_at = parse_datetime(document.get("generated_at") or "")
    except (TypeError, ValueError):
        generated_at = None
    _require(generated_at is not None and timezone.is_aware(generated_at),
             "export generated_at must be a timezone-aware time")

    raw_members = document.get("members")
    _require(isinstance(raw_members, list) and raw_members, "export has no members")
    members: list[dict[str, Any]] = []
    seen: set[str] = set()
    for member in raw_members:
        author_id = _decimal_id(member.get("author_id")) if isinstance(member, dict) else None
        _require(author_id is not None, "export member author_id must be decimal")
        _require(_is_text_or_none(member.get("handle")), "export member handle must be text or null")
        _require(author_id not in seen, f"export has a duplicate member: {author_id}")
        seen.add(author_id)
        members.append({"author_id": author_id, "handle": _clean_handle(member.get("handle"))})

    raw_roles = document.get("roles")
    _require(isinstance(raw_roles, list), "export roles must be a list")
    roles: list[dict[str, Any]] = []
    pairs: set[tuple[str, str]] = set()
    for role in raw_roles:
        valid = (
            isinstance(role, dict)
            and {"author_id", "handle", "brand_id", "role_id"} <= set(role)
            and _decimal_id(role["author_id"]) is not None
            and _is_text_or_none(role["handle"])
            and all(isinstance(role[key], str) and role[key] and role[key] == role[key].strip()
                    for key in ("brand_id", "role_id"))
        )
        _require(valid, "export has a malformed role")
        author_id = _decimal_id(role["author_id"])
        pair = (author_id, role["brand_id"])
        _require(pair not in pairs, f"export has a duplicate role: {author_id}:{role['brand_id']}")
        pairs.add(pair)
        roles.append({"author_id": author_id, "handle": _clean_handle(role["handle"]),
                      "brand_id": role["brand_id"], "role_id": role["role_id"]})

    return ProductionExport(
        path=str(path),
        sha256=hashlib.sha256(body).hexdigest(),
        database=document["database"],
        generated_at=generated_at,
        list_id=exported_list,
        members=tuple(members),
        roles=tuple(roles),
    )


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def require_backfill_environment() -> None:
    """Checked first so a non-backfill process never queries database identity."""
    _require(os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT") == "backfill",
             "dedicated backfill environment required")


def require_dedicated_database() -> dict[str, str]:
    """The same dedicated-database rule ``manifest()`` applies before planning."""
    try:
        validate_staging({"response_storage": "database",
                          "database_host": settings.DATABASES["default"].get("HOST")})
    except ValueError as exc:
        raise SyncRefused(str(exc)) from exc
    return {"name": BACKFILL_DATABASE, "user": BACKFILL_DATABASE}


def live_historical_leases() -> list[str]:
    """Job keys of historical X runs whose lease is missing or still live."""
    return list(
        CollectionRun.objects.filter(job__source_id="x", job__mode="historical", status="running")
        .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__gt=timezone.now()))
        .order_by("job__job_key")
        .values_list("job__job_key", flat=True)[:20]
    )


def require_no_live_lease() -> None:
    keys = live_historical_leases()
    _require(not keys, "historical backfill run holds a live lease: " + ", ".join(keys))


# ---------------------------------------------------------------------------
# Catalog digests and proofs (pure)
# ---------------------------------------------------------------------------


def _canonical(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """The classifier's canonical catalog and revision for these rows."""
    return _tracked_brand_catalog([], [{"tracked_brand_catalog": list(rows), "brand_ids": []}])


def projection_digest(rows: Iterable[dict[str, Any]]) -> str:
    """Catalog revision with account handles and roles removed.

    Roles change the classifier's revision by design, because the catalog
    hashes each brand's X handles and roles. Equal projections prove brands,
    aliases, keywords, domains, hashtags and products are untouched.
    """
    return _canonical({**row, "handles": [], "accounts": []} for row in rows)["revision"]


def catalog_digests(rows: list[dict[str, Any]]) -> dict[str, Any]:
    canonical = _canonical(rows)
    return {
        "revision": canonical["revision"],
        "projection_digest": projection_digest(rows),
        "brands": len(canonical["brands"]),
    }


def _sorted_rows(values: Iterable[tuple]) -> list[list[Any]]:
    return sorted(list(value) for value in values)


def _account_entries(rows: list[dict[str, Any]]) -> tuple[set, set, set]:
    accounts: set[tuple[str, str, str]] = set()
    handles: set[tuple[str, str]] = set()
    brands = _canonical(rows)["brands"]
    for brand in brands:
        accounts.update((brand["brand_id"], value["handle"], value["role"]) for value in brand["accounts"])
        handles.update((brand["brand_id"], value) for value in brand["handles"])
    return accounts, handles, {brand["brand_id"] for brand in brands}


def account_delta_proof(
    before_rows: list[dict[str, Any]], after_rows: list[dict[str, Any]], written: list[dict[str, Any]],
) -> dict[str, Any]:
    """Every catalog handle/role change is explained by a written role, and vice versa.

    A written role reaches the catalog only for a non-sentinel brand and an
    account with a handle. A correction may remove only its old role. Without
    any written role the whole revision must stay byte-identical.
    """
    before_accounts, before_handles, _ = _account_entries(before_rows)
    after_accounts, after_handles, brands = _account_entries(after_rows)
    expected_accounts: set[tuple[str, str, str]] = set()
    expected_handles: set[tuple[str, str]] = set()
    removable: set[tuple[str, str, str]] = set()
    for row in written:
        handle = str(row.get("handle") or "").strip().removeprefix("@").strip()
        if not handle or row["brand_id"] not in brands:
            continue
        expected_accounts.add((row["brand_id"], handle.casefold(), row["new_role"]))
        expected_handles.add((row["brand_id"], handle))
        if row.get("old_role"):
            removable.add((row["brand_id"], handle.casefold(), row["old_role"]))
    added_accounts, removed_accounts = after_accounts - before_accounts, before_accounts - after_accounts
    added_handles, removed_handles = after_handles - before_handles, before_handles - after_handles
    revision_unchanged = _canonical(before_rows)["revision"] == _canonical(after_rows)["revision"]
    failures = {
        "unexpected_added_accounts": added_accounts - expected_accounts,
        "missing_accounts": expected_accounts - after_accounts,
        "unexpected_removed_accounts": removed_accounts - removable,
        "unexpected_added_handles": added_handles - expected_handles,
        "missing_handles": expected_handles - after_handles,
    }
    passed = not any(failures.values()) and not removed_handles and (bool(written) or revision_unchanged)
    return {
        "passed": passed,
        "revision_unchanged": revision_unchanged,
        "added_accounts": _sorted_rows(added_accounts),
        "removed_accounts": _sorted_rows(removed_accounts),
        "added_handles": _sorted_rows(added_handles),
        "removed_handles": _sorted_rows(removed_handles),
        **{name: _sorted_rows(values) for name, values in failures.items()},
    }


def expected_contexts(
    member_ids: Iterable[str],
    before_edges: Iterable[tuple[str | None, str, str]],
    applied_roles: Iterable[tuple[str, str, str]],
) -> dict[str, dict[str, list[str]]]:
    """Call A roles each exported member should resolve to after the sync.

    Export roles that were written or already matched override the member's
    existing xbackfiller edges; edges the export does not name are kept.
    """
    final: dict[str, dict[str, str]] = {str(author): {} for author in member_ids}
    for edges in (before_edges, applied_roles):
        for author, brand, role in edges:
            if author in final:
                final[author][brand] = role
    return {
        author: {kind: sorted(brand for brand, role in roles.items() if role == kind) for kind in CALL_A_ROLES}
        for author, roles in final.items()
    }


def contexts_proof(
    contexts: dict[str, Any], expected: dict[str, dict[str, list[str]]], active_member_ids: Iterable[Any],
) -> dict[str, Any]:
    """One planning context per exported member, with the expected roles, and no other active member."""
    exported, resolved = set(expected), set(contexts)
    active = {str(author) for author in active_member_ids}
    mismatched = sorted(
        author for author in exported & resolved
        if {"official": sorted(contexts[author].official_brands),
            "staff": sorted(contexts[author].staff_brands)} != expected[author]
    )
    result = {
        "missing": sorted(exported - resolved),
        "unexpected": sorted(resolved - exported),
        "mismatched": mismatched,
        "active_not_exported": sorted(active - exported),
        "exported_not_active": sorted(exported - active),
    }
    return {"passed": not any(result.values()), "contexts": len(resolved), **result}


def extra_roles(export: ProductionExport, edges: Iterable[tuple]) -> list[dict[str, Any]]:
    """xbackfiller X roles production does not have; reported, never deleted."""
    exported = {(role["author_id"], role["brand_id"]) for role in export.roles}
    return sorted(
        ({"author_id": author, "brand_id": brand, "role_id": role, "handle": handle}
         for author, brand, role, handle in edges if (author, brand) not in exported),
        key=lambda row: (str(row["author_id"]), row["brand_id"]),
    )


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def _ensure_membership(*, list_id: int, account: Account, observed_at: datetime, source: str,
                       source_run_id: str) -> str:
    """Activate one list membership; return "unchanged", "created" or "reactivated"."""
    existing = TwitterListMembership.objects.filter(list_id=list_id, account=account).first()
    if existing is not None and existing.active:
        return "unchanged"
    _membership, created, _was_active = _upsert_membership(
        list_id=list_id, account=account, observed_at=observed_at, source=source,
        source_run_id=source_run_id, complete=False,
    )
    return "created" if created else "reactivated"


def apply_export(export: ProductionExport) -> dict[str, Any]:
    """Write memberships, missing accounts and roles; call only inside the guarded transaction."""
    run_id, observed_at = export.source_run_id, export.generated_at
    counts = dict.fromkeys(COUNT_KEYS, 0)
    degraded: list[str] = []
    accounts: dict[str, Account] = {}
    created_accounts: list[str] = []
    differs: dict[str, dict[str, Any]] = {}

    def account_for(author_id: str, handle: str | None) -> Account:
        account = accounts.get(author_id)
        if account is not None:
            return account
        account = Account.x.filter(author_id=author_id).first()
        if account is None:
            # Only a missing account is observed; an existing handle is never edited.
            account, created = _upsert_account({"author_id": author_id, "handle": handle},
                                               degraded=degraded, observed_at=observed_at)
            if created:
                created_accounts.append(author_id)
        accounts[author_id] = account
        if _clean_handle(account.handle) != handle:
            differs[author_id] = {"author_id": author_id, "xbackfiller": account.handle, "production": handle}
        return account

    member_ids = [member["author_id"] for member in export.members]
    for member in export.members:
        account = account_for(member["author_id"], member["handle"])
        outcome = _ensure_membership(list_id=export.list_id, account=account, observed_at=observed_at,
                                     source=MEMBERSHIP_SOURCE, source_run_id=run_id)
        counts["memberships_" + outcome] += 1
    absent = TwitterListMembership.objects.filter(list_id=export.list_id, active=True).exclude(
        account__author_id__in=member_ids)
    deactivated = sorted(str(author or account_key)
                         for author, account_key in absent.values_list("account__author_id", "account_id"))
    counts["memberships_deactivated"] = absent.update(active=False, source=MEMBERSHIP_SOURCE,
                                                      source_run_id=run_id)

    brands = set(Brand.objects.values_list("nickname", flat=True))
    role_keys = set(Role.objects.values_list("key", flat=True))
    written: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    applied: list[tuple[str, str, str]] = []
    for role in export.roles:
        author_id, brand_id, role_id = role["author_id"], role["brand_id"], role["role_id"]
        reason = ("brand_missing" if brand_id not in brands
                  else "role_missing" if role_id not in role_keys else None)
        if reason is not None:
            skipped.append({"author_id": author_id, "brand_id": brand_id, "role_id": role_id, "reason": reason})
            continue
        account = account_for(author_id, role["handle"])
        current = BrandAccount.objects.filter(brand_id=brand_id, account=account).first()
        entry = {"author_id": author_id, "brand_id": brand_id, "handle": account.handle,
                 "old_role": None, "new_role": role_id}
        if current is None:
            BrandAccount.objects.create(brand_id=brand_id, account=account, role_id=role_id)
            written.append({**entry, "action": "created"})
            counts["roles_created"] += 1
        elif current.role_id != role_id:
            BrandAccount.objects.filter(brand_id=brand_id, account=account).update(role_id=role_id)
            written.append({**entry, "old_role": current.role_id, "action": "corrected"})
            counts["roles_corrected"] += 1
        else:
            counts["roles_unchanged"] += 1
        applied.append((author_id, brand_id, role_id))
    counts["accounts_created"] = len(created_accounts)
    counts["roles_skipped"] = len(skipped)
    return {
        "counts": counts,
        "accounts_created": sorted(created_accounts),
        "memberships_deactivated": deactivated,
        "roles_written": sorted(written, key=lambda row: (row["author_id"], row["brand_id"])),
        "roles_skipped": sorted(skipped, key=lambda row: (row["author_id"], row["brand_id"])),
        "roles_applied": applied,
        "handle_differs": [differs[author] for author in sorted(differs)],
        "degraded": sorted(set(degraded)),
    }


def _snapshot(export: ProductionExport) -> dict[str, Any]:
    authors = {member["author_id"] for member in export.members} | {role["author_id"] for role in export.roles}
    return {
        "catalog": _classification_tracked_brand_catalog(),
        "jobs": dict(CollectionJob.objects.filter(source_id="x", mode="historical").values_list(
            "job_key", "definition_sha256")),
        "protected": {model.__name__: model.objects.count() for model in PROTECTED_MODELS},
        "handles": dict(Account.x.filter(author_id__in=authors).values_list("author_id", "handle")),
        "edges": list(BrandAccount.objects.filter(account__data_source_id="x").values_list(
            "account__author_id", "brand_id", "role_id", "account__handle")),
    }


def apply_and_prove(export: ProductionExport, *, execute: bool) -> dict[str, Any]:
    """Write and prove in one transaction; roll back on a dry run or any failed proof."""
    with transaction.atomic():
        before = _snapshot(export)
        applied = apply_export(export)
        after = _snapshot(export)
        member_ids = [member["author_id"] for member in export.members]
        contexts, context_degraded = resolve_call_a_author_contexts(
            list_id=export.list_id, items=[{"author_id": author} for author in member_ids])
        active = TwitterListMembership.objects.filter(list_id=export.list_id, active=True).values_list(
            "account__author_id", flat=True)
        expected = expected_contexts(member_ids, [edge[:3] for edge in before["edges"]], applied["roles_applied"])
        changed_handles = sorted(author for author, handle in before["handles"].items()
                                 if after["handles"].get(author) != handle)
        proofs = {
            "catalog_projection_unchanged": {
                "passed": projection_digest(before["catalog"]) == projection_digest(after["catalog"])},
            "account_delta_matches_written_roles": account_delta_proof(
                before["catalog"], after["catalog"], applied["roles_written"]),
            "contexts_match_export": contexts_proof(contexts, expected, list(active)),
            "historical_jobs_unchanged": {"passed": before["jobs"] == after["jobs"], "jobs": len(after["jobs"])},
            "protected_rows_unchanged": {"passed": before["protected"] == after["protected"],
                                         "counts": after["protected"]},
            "existing_handles_unchanged": {"passed": not changed_handles, "changed": changed_handles},
        }
        passed = all(proof.get("passed") is True for proof in proofs.values())
        committed = bool(execute and passed)
        if not committed:
            transaction.set_rollback(True)
    extras = extra_roles(export, before["edges"])
    return {
        "format": REPORT_FORMAT,
        "status": "committed" if committed else "dry_run" if passed else "proof_failed",
        "committed": committed,
        "execute": bool(execute),
        "source": MEMBERSHIP_SOURCE,
        "source_run_id": export.source_run_id,
        "counts": {**applied["counts"], "extra_roles": len(extras),
                   "handle_differs": len(applied["handle_differs"])},
        "accounts_created": applied["accounts_created"],
        "memberships_deactivated": applied["memberships_deactivated"],
        "roles_written": applied["roles_written"],
        "roles_skipped": applied["roles_skipped"],
        "extra_roles": extras,
        "handle_differs": applied["handle_differs"],
        "degraded": applied["degraded"],
        "context_degraded": sorted(context_degraded),
        "catalog": {"before": catalog_digests(before["catalog"]), "after": catalog_digests(after["catalog"])},
        "proofs": proofs,
    }


def sync(export_path: Path | str, *, execute: bool = False) -> dict[str, Any]:
    """Run every guard in order, then the single write-and-prove transaction."""
    export = read_export(export_path, list_id=configured_list_id())
    require_backfill_environment()
    database = require_dedicated_database()
    require_no_live_lease()
    with harvest_writer_lock(execution_mode="list_membership", entrypoint=ENTRYPOINT) as lease:
        _require(lease.acquired, "harvest writer lock is held; nothing was changed")
        require_no_live_lease()
        report = apply_and_prove(export, execute=execute)
    return {**report, "database": database, "export": export.summary()}
