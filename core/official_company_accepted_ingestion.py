"""Freeze saved evaluator acceptances without making provider calls."""

import json
from pathlib import Path

from django.db import connection, transaction

from core.models import OfficialCompanyAttempt
from core.official_company_accounts import digest
from core.official_company_queue_pass import (
    _database_identity,
    _environment,
    _write_new_private_file,
)


def _valid_checksum(value):
    return value.get("sha256") == digest(
        {k: v for k, v in value.items() if k != "sha256"}
    )


def freeze_accepted(*, queue, path):
    """Capture the latest accepted completed attempt per frozen queue member."""
    if not _valid_checksum(queue):
        raise ValueError("queue checksum mismatch")
    environment = _environment(queue, allow_isolated_fixture=True)
    if connection.in_atomic_block:
        raise ValueError("snapshot requires an outermost transaction")
    members = {item["state_id"]: item for item in queue["members"]}
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SELECT transaction_timestamp()")
            cutoff = cursor.fetchone()[0]
        database = _database_identity()
        attempts = (
            OfficialCompanyAttempt.objects.filter(
                state_id__in=members,
                status="completed",
                completed_at__isnull=False,
                decision__outcome="accepted",
                budget_keys__contains=["queue-pass:" + queue["run_id"]],
            )
            .order_by("state_id", "-created_at", "-pk")
            .distinct("state_id")
            .select_related("state")
        )
        selected = {}
        for attempt in attempts.iterator(chunk_size=500):
            source = members[attempt.state_id]
            selected[attempt.state_id] = {
                "state_id": attempt.state_id,
                "account_key": source["account_key"],
                "native_identifier": (
                    attempt.evidence.get("external_identifier")
                    if isinstance(attempt.evidence, dict)
                    else None
                ),
                "attempt_id": attempt.pk,
                "evidence_hash": attempt.evidence_hash,
                "attempt_content_sha256": digest(
                    {"evidence": attempt.evidence, "decision": attempt.decision}
                ),
                "model": attempt.model,
                "policy_version": attempt.policy_version,
                "attempt_created_at": attempt.created_at.isoformat(),
                "state_status": attempt.state.status,
            }
    value = {
        "version": 1,
        "queue_run_id": queue["run_id"],
        "queue_sha256": queue["sha256"],
        "database": database,
        "lock_environment": environment,
        "cutoff": cutoff.isoformat(),
        "count": len(selected),
        "members": [selected[key] for key in sorted(selected)],
    }
    value["sha256"] = digest(value)
    _write_new_private_file(path, value, prefix=".accepted-")
    return value


def _validate_accepted(value, *, queue):
    if not isinstance(value, dict) or not _valid_checksum(value):
        raise ValueError("accepted manifest checksum mismatch")
    if not isinstance(queue, dict) or not _valid_checksum(queue):
        raise ValueError("queue checksum mismatch")
    _environment(queue, allow_isolated_fixture=True)
    if (
        value.get("version") != 1
        or value.get("queue_run_id") != queue["run_id"]
        or value.get("queue_sha256") != queue["sha256"]
        or value.get("database") != _database_identity()
        or value.get("lock_environment") != queue["lock_environment"]
        or not isinstance(value.get("members"), list)
        or value.get("count") != len(value["members"])
    ):
        raise ValueError("accepted manifest does not match queue or database")
    original = {item["state_id"]: item["account_key"] for item in queue["members"]}
    seen = set()
    for item in value["members"]:
        if not isinstance(item, dict):
            raise ValueError("invalid queue membership")  # noqa: TRY004
        state_id = item.get("state_id")
        if (
            not isinstance(state_id, int)
            or state_id in seen
            or original.get(state_id) != item.get("account_key")
            or not isinstance(item.get("attempt_id"), int)
            or not (
                item.get("native_identifier") is None
                or isinstance(item.get("native_identifier"), str)
            )
            or not isinstance(item.get("evidence_hash"), str)
            or not isinstance(item.get("attempt_content_sha256"), str)
            or not isinstance(item.get("model"), str)
            or not isinstance(item.get("policy_version"), str)
            or not isinstance(item.get("attempt_created_at"), str)
        ):
            raise ValueError("invalid queue membership")
        seen.add(state_id)
    return value


def read_accepted(path, *, queue):
    return _validate_accepted(json.loads(Path(path).read_text()), queue=queue)


_NOT_LOADED = object()


def _verify_identity_collations():
    """Fail closed if matching columns no longer use the expected database rules."""
    expected = {
        ("brands", "nickname", "case_insensitive"),
        ("brands", "display_name", "default"),
        ("companies", "nickname", "case_insensitive"),
        ("company_labels", "label", "default"),
    }
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT r.relname, a.attname, c.collname FROM pg_attribute a "
            "JOIN pg_class r ON r.oid = a.attrelid "
            "JOIN pg_collation c ON c.oid = a.attcollation "
            "WHERE (a.attrelid, a.attname) IN "
            "((to_regclass('brands'), 'nickname'), (to_regclass('brands'), 'display_name'), "
            "(to_regclass('companies'), 'nickname'), (to_regclass('company_labels'), 'label'))"
        )
        if set(cursor.fetchall()) != expected:
            raise ValueError("organization identity column collation mismatch")


def _batch_reservation_classes(values):
    """Assign database-equivalent nickname/name classes in one query."""
    if not values:
        return []
    _verify_identity_collations()
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT dense_rank() OVER (ORDER BY slug COLLATE "case_insensitive"), '
            "dense_rank() OVER (ORDER BY UPPER(name::text)) "
            "FROM unnest(%s::text[], %s::text[]) WITH ORDINALITY AS v(slug, name, ord) "
            "ORDER BY ord",
            [[value[0] for value in values], [value[1] for value in values]],
        )
        return cursor.fetchall()


def _reservation_conflicts(reservations, slug, name):
    """Use the same database comparisons as the scheduled registration path."""
    if not reservations:
        return False
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM unnest(%s::text[], %s::text[]) AS r(slug, name) "
            'WHERE r.slug COLLATE "case_insensitive" = %s COLLATE "case_insensitive" '
            "OR UPPER(r.name) = UPPER(%s::text))",
            [[r[0] for r in reservations], [r[1] for r in reservations], slug, name],
        )
        return cursor.fetchone()[0]


def _preview_member(
    member,
    reserved_brands,
    reserved_companies,
    *,
    queue_run_id,
    reservation_class=None,
    role_exists=_NOT_LOADED,
    und_locale_exists=_NOT_LOADED,
    state=_NOT_LOADED,
    attempt=_NOT_LOADED,
):
    from django.db.models import Q

    from core.models import (
        BrandAccount,
        BrandCompany,
        CompanyAccount,
        Locale,
        OfficialCompanyAccountState,
        Role,
    )
    from core.official_company_accounts import (
        RegistrationIdentityConflict,
        registration_identity,
        x_account_identifier,
    )

    row = {
        "state_id": member["state_id"],
        "attempt_id": member["attempt_id"],
        "account_key": member["account_key"],
    }
    if state is _NOT_LOADED:
        state = (
            OfficialCompanyAccountState.objects.filter(pk=member["state_id"])
            .select_related("account")
            .first()
        )
    if attempt is _NOT_LOADED:
        attempt = OfficialCompanyAttempt.objects.filter(pk=member["attempt_id"]).first()
    if state is not None:
        row["current_status"] = state.status
    if not state or not attempt or attempt.state_id != member["state_id"]:
        row.update(disposition="unresolved", reason="missing_state_or_attempt")
    elif str(state.account_id) != member["account_key"]:
        row.update(disposition="unresolved", reason="account_changed")
    elif (
        not isinstance(member["native_identifier"], str)
        or not member["native_identifier"].isdecimal()
        or not isinstance(attempt.evidence, dict)
        or attempt.evidence.get("provider") != "x"
        or attempt.evidence.get("external_identifier") != member["native_identifier"]
        or state.account.data_source_id != "x"
        or state.account.author_id != member["native_identifier"]
        or state.account.external_identifier != member["native_identifier"]
    ):
        row.update(disposition="unresolved", reason="native_account_changed")
    elif (
        attempt.status != "completed"
        or attempt.completed_at is None
        or attempt.model != member["model"]
        or attempt.policy_version != member["policy_version"]
        or attempt.created_at.isoformat() != member["attempt_created_at"]
        or not isinstance(attempt.budget_keys, list)
        or "queue-pass:" + queue_run_id not in attempt.budget_keys
        or not isinstance(attempt.decision, dict)
        or attempt.evidence_hash != member["evidence_hash"]
        or digest({"evidence": attempt.evidence, "decision": attempt.decision})
        != member["attempt_content_sha256"]
        or attempt.decision.get("outcome") != "accepted"
    ):
        row.update(disposition="unresolved", reason="evidence_or_decision_changed")
    elif state.status in {"suppressed", "rejected"}:
        row.update(disposition="unresolved", reason="state_" + state.status)
    elif (
        state.evidence_hash != member["evidence_hash"]
        or attempt.decision != state.decision
    ):
        row.update(disposition="unresolved", reason="evidence_or_decision_changed")
    elif (
        OfficialCompanyAttempt.objects.filter(state=state)
        .filter(
            Q(created_at__gt=attempt.created_at)
            | Q(created_at=attempt.created_at, pk__gt=attempt.pk)
        )
        .exclude(
            Q(status="failed", evidence_hash=attempt.evidence_hash)
            | Q(
                status="completed",
                decision=attempt.decision,
                evidence_hash=attempt.evidence_hash,
            )
        )
        .exists()
    ):
        row.update(disposition="unresolved", reason="newer_attempt")
    elif state.status == "registered":
        try:
            resolved_brand, resolved_company, _, _ = registration_identity(
                state, state.account
            )
        except (RegistrationIdentityConflict, ValueError) as exc:
            row.update(disposition="conflict", reason=str(exc))
            return row
        if (
            resolved_brand is not None
            and resolved_company is not None
            and resolved_brand.pk == state.registered_brand_id
            and resolved_company.pk == state.registered_company_id
            and state.registered_brand_id
            and state.registered_company_id
            and BrandAccount.objects.filter(
                account=state.account,
                brand_id=state.registered_brand_id,
                role_id="official",
            ).exists()
            and CompanyAccount.objects.filter(
                account=state.account,
                company_id=state.registered_company_id,
                role_id="official",
            ).exists()
        ):
            row.update(
                disposition="already_registered",
                frozen_state_matches=(
                    state.evidence_hash == member["evidence_hash"]
                    and state.decision == attempt.decision
                ),
                brand=state.registered_brand_id,
                company=state.registered_company_id,
                brand_action="reuse",
                company_action="reuse",
                brand_account_action="retain",
                company_account_action="retain",
                brand_company_action="retain"
                if BrandCompany.objects.filter(
                    brand_id=state.registered_brand_id,
                    company_id=state.registered_company_id,
                ).exists()
                else "none",
            )
        else:
            row.update(disposition="unresolved", reason="registered_links_incomplete")
    elif state.status != "accepted" and not (
        state.status == "review_needed" and state.last_error == "human_review_required"
    ):
        row.update(disposition="unresolved", reason="state_not_eligible")
    else:
        try:
            x_account_identifier(state.account)
            brand, company, name, slug = registration_identity(state, state.account)
            if company is None:
                if und_locale_exists is _NOT_LOADED:
                    und_locale_exists = Locale.objects.filter(pk="und").exists()
                if not und_locale_exists:
                    row.update(disposition="unresolved", reason="missing_und_locale")
                    return row
            if reservation_class is None:
                brand_collision = brand is None and _reservation_conflicts(
                    reserved_brands, slug, name
                )
                company_collision = company is None and _reservation_conflicts(
                    reserved_companies, slug, name
                )
                reservation = (slug, name)
            else:
                reservation = {
                    ("slug", reservation_class[0]),
                    ("name", reservation_class[1]),
                }
                brand_collision = brand is None and not reserved_brands.isdisjoint(
                    reservation
                )
                company_collision = (
                    company is None and not reserved_companies.isdisjoint(reservation)
                )
            if brand_collision or company_collision:
                raise RegistrationIdentityConflict("planned_identity_collision")
            if brand is None:
                if reservation_class is None:
                    reserved_brands.append(reservation)
                else:
                    reserved_brands.update(reservation)
            if company is None:
                if reservation_class is None:
                    reserved_companies.append(reservation)
                else:
                    reserved_companies.update(reservation)
            brand_id = brand.pk if brand else slug
            company_id = company.pk if company else slug
            brand_link = bool(
                brand
                and BrandAccount.objects.filter(
                    brand=brand, account=state.account
                ).exists()
            )
            company_link = bool(
                company
                and CompanyAccount.objects.filter(
                    company=company, account=state.account
                ).exists()
            )
            edge = bool(
                brand
                and company
                and BrandCompany.objects.filter(brand=brand, company=company).exists()
            )
            if role_exists is _NOT_LOADED:
                role_exists = Role.objects.filter(pk="official").exists()
            row.update(
                disposition="eligible",
                official_role_action="retain" if role_exists else "create",
                company_label_action="none" if company else "create",
                name=name,
                slug=slug,
                brand=brand_id,
                brand_action="reuse" if brand else "create",
                company=company_id,
                company_action="reuse" if company else "create",
                brand_account_action="retain" if brand_link else "create",
                company_account_action="retain" if company_link else "create",
                brand_company_action="retain"
                if edge
                else ("create" if not brand and not company else "none"),
                native_account_id_after=state.account.author_id,
                automatically_updated_state_fields=["updated_at"],
                state_before={
                    "native_account_id": state.native_account_id,
                    "status": state.status,
                    "last_error": state.last_error,
                    "registered_brand": state.registered_brand_id,
                    "registered_company": state.registered_company_id,
                    "evidence_hash": state.evidence_hash,
                    "next_attempt_at": state.next_attempt_at.isoformat()
                    if state.next_attempt_at
                    else None,
                },
                state_fingerprint=digest(
                    {
                        "status": state.status,
                        "last_error": state.last_error,
                        "native_account_id": state.native_account_id,
                        "decision": state.decision,
                        "evidence_hash": state.evidence_hash,
                        "next_attempt_at": state.next_attempt_at.isoformat()
                        if state.next_attempt_at
                        else None,
                    }
                ),
            )
        except (RegistrationIdentityConflict, ValueError) as exc:
            row.update(disposition="conflict", reason=str(exc))
    return row


def preview_accepted(*, queue, manifest, path):
    """Predict registration from one consistent read-only database snapshot."""
    _validate_accepted(manifest, queue=queue)
    if connection.in_atomic_block:
        raise ValueError("preview requires an outermost transaction")
    rows = []
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SELECT transaction_timestamp()")
            cutoff = cursor.fetchone()[0]
        from core.models import Locale, OfficialCompanyAccountState, Role

        und_locale_exists = Locale.objects.filter(pk="und").exists()
        role_exists = Role.objects.filter(pk="official").exists()
        states = OfficialCompanyAccountState.objects.select_related("account").in_bulk(
            [member["state_id"] for member in manifest["members"]]
        )
        attempts = OfficialCompanyAttempt.objects.in_bulk(
            [member["attempt_id"] for member in manifest["members"]]
        )
        from core.official_company_accounts import (
            registration_slug,
            x_account_identifier,
        )

        candidates = []
        for member in manifest["members"]:
            state = states.get(member["state_id"])
            if state is None or not isinstance(state.decision, dict):
                continue
            name = state.decision.get("organization_name")
            if not isinstance(name, str) or not name.strip():
                continue
            try:
                x_account_identifier(state.account)
                candidates.append(
                    (member["state_id"], registration_slug(name, state.account), name)
                )
            except ValueError:
                continue
        if len(candidates) <= 10000:
            classes = _batch_reservation_classes(
                [(slug, name) for _, slug, name in candidates]
            )
            class_by_id = {
                item[0]: value for item, value in zip(candidates, classes, strict=True)
            }
            reserved_brands, reserved_companies = set(), set()
        else:
            # Preserve exact comparisons without building an unbounded batch.
            _verify_identity_collations()
            class_by_id = None
            reserved_brands, reserved_companies = [], []
        for member in manifest["members"]:
            row = _preview_member(
                member,
                reserved_brands,
                reserved_companies,
                queue_run_id=manifest["queue_run_id"],
                reservation_class=class_by_id.get(member["state_id"])
                if class_by_id is not None
                else None,
                role_exists=role_exists,
                und_locale_exists=und_locale_exists,
                state=states.get(member["state_id"]),
                attempt=attempts.get(member["attempt_id"]),
            )
            rows.append(row)
            if row["disposition"] == "eligible":
                role_exists = True
    eligible = [row for row in rows if row["disposition"] == "eligible"]
    existing = [row for row in rows if row["disposition"] == "already_registered"]
    accounted = eligible + existing
    counts = {
        "state_updates": len(eligible),
        "official_roles_created": sum(
            row["official_role_action"] == "create" for row in eligible
        ),
        "company_labels_created": len(
            {
                row["company"]
                for row in eligible
                if row["company_label_action"] == "create"
            }
        ),
        "already_registered": len(existing),
        "conflicts": sum(row["disposition"] == "conflict" for row in rows),
        "unresolved": sum(row["disposition"] == "unresolved" for row in rows),
        "suppressed": sum(row.get("current_status") == "suppressed" for row in rows),
        "rejected": sum(row.get("current_status") == "rejected" for row in rows),
        "native_identity_changed": sum(
            row.get("reason") == "native_account_changed" for row in rows
        ),
        "newer_attempt": sum(row.get("reason") == "newer_attempt" for row in rows),
        "missing": sum(row.get("reason") == "missing_state_or_attempt" for row in rows),
        "missing_prerequisite": sum(
            row.get("reason") == "missing_und_locale" for row in rows
        ),
        "changed_evidence_or_decision": sum(
            row.get("reason") == "evidence_or_decision_changed" for row in rows
        ),
        "new_brands": len(
            {r["brand"] for r in eligible if r["brand_action"] == "create"}
        ),
        "reused_brands": len(
            {r["brand"] for r in accounted if r["brand_action"] == "reuse"}
        ),
        "updated_brands": 0,
        "new_companies": len(
            {r["company"] for r in eligible if r["company_action"] == "create"}
        ),
        "reused_companies": len(
            {r["company"] for r in accounted if r["company_action"] == "reuse"}
        ),
        "updated_companies": 0,
    }
    for kind in ("brand_account", "company_account", "brand_company"):
        for action in ("create", "retain"):
            relevant = [r for r in accounted if r[f"{kind}_action"] == action]
            if kind == "brand_account":
                identities = {(r["brand"], r["account_key"]) for r in relevant}
            elif kind == "company_account":
                identities = {(r["company"], r["account_key"]) for r in relevant}
            else:
                identities = {(r["brand"], r["company"]) for r in relevant}
            counts[f"{kind}_{action}"] = len(identities)
    value = {
        "version": 1,
        "manifest_sha256": manifest["sha256"],
        "queue_sha256": queue["sha256"],
        "database": manifest["database"],
        "cutoff": cutoff.isoformat(),
        "members": rows,
        "counts": counts,
        "list_changes": 0,
        "rollback": (
            "Review each applied record and later references before undoing it; "
            "restore the captured state only if unchanged, and do not remove reused "
            "entities, shared links, evidence, attempts, or list intents."
        ),
    }
    value["sha256"] = digest(value)
    _write_new_private_file(path, value, prefix=".accepted-preview-")
    return value


def _registered_matches_preview(actual, planned):
    return (
        actual.get("disposition") == "already_registered"
        and actual.get("frozen_state_matches") is True
        and actual.get("brand") == planned["brand"]
        and actual.get("company") == planned["company"]
        and actual.get("brand_company_action")
        == (
            "retain"
            if planned["brand_company_action"] in {"create", "retain"}
            else "none"
        )
    )


def apply_preview(
    *,
    queue,
    manifest,
    preview,
    cfg,
    allow_production=False,
    frozen_list_path=None,
    max_writes=None,
):
    """Apply a reviewed preview to fixtures or explicitly authorized production."""
    from django.db import DatabaseError, IntegrityError, ProgrammingError

    from core.models import (
        Account,
        Company,
        CompanyLabel,
        OfficialCompanyAccountState,
    )
    from core.official_company_accounts import register_account
    from core.organization_identity_locks import (
        acquire_ingestion_identity_locks,
        organization_lock_keys,
    )
    from core.publisher_accounts import brand_name_candidates

    class IdentityBusy(Exception):
        pass

    environment = _environment(queue, allow_isolated_fixture=True)
    if max_writes is not None and (type(max_writes) is not int or max_writes <= 0):
        raise ValueError("max_writes must be a positive integer")
    if environment == "production":
        if not allow_production or not frozen_list_path:
            raise ValueError(
                "production apply requires --allow-production and a frozen-list file"
            )
        if read_accepted(frozen_list_path, queue=queue) != manifest:
            raise ValueError("frozen-list file does not match manifest")
    elif environment != "test":
        raise ValueError(
            "apply is available only for approved fixture databases or authorized production"
        )
    _validate_accepted(manifest, queue=queue)
    if (
        not isinstance(preview, dict)
        or not _valid_checksum(preview)
        or preview.get("version") != 1
        or preview.get("queue_sha256") != queue["sha256"]
        or not isinstance(preview.get("members"), list)
        or manifest.get("queue_sha256") != queue["sha256"]
        or preview.get("manifest_sha256") != manifest["sha256"]
        or preview.get("database") != _database_identity()
    ):
        raise ValueError("preview, manifest or database mismatch")
    allowed = {"eligible", "already_registered", "unresolved", "conflict"}
    if any(
        not isinstance(row, dict)
        or not isinstance(row.get("state_id"), int)
        or row.get("disposition") not in allowed
        for row in preview["members"]
    ):
        raise ValueError("invalid preview members")
    expected = {row["state_id"]: row for row in preview["members"]}
    if len(expected) != len(preview["members"]) or set(expected) != {
        m["state_id"] for m in manifest["members"]
    }:
        raise ValueError("preview does not cover the frozen cohort")
    for member in manifest["members"]:
        row = expected[member["state_id"]]
        if (
            row.get("attempt_id") != member["attempt_id"]
            or row.get("account_key") != member["account_key"]
        ):
            raise ValueError("invalid preview member identity")
        if row["disposition"] in {"unresolved", "conflict"}:
            if not isinstance(row.get("reason"), str) or not row["reason"]:
                raise ValueError("invalid preview member reason")
            continue
        if not all(
            isinstance(row.get(key), str) and row[key] for key in ("brand", "company")
        ):
            raise ValueError("invalid preview organization identity")
        if (
            row.get("brand_account_action") not in {"create", "retain"}
            or row.get("company_account_action") not in {"create", "retain"}
            or row.get("brand_company_action") not in {"create", "retain", "none"}
        ):
            raise ValueError("invalid preview relationship action")
        if row["disposition"] == "already_registered":
            if (
                row.get("brand_action") != "reuse"
                or row.get("company_action") != "reuse"
                or row.get("brand_account_action") != "retain"
                or row.get("company_account_action") != "retain"
                or row.get("brand_company_action") not in {"retain", "none"}
                or not isinstance(row.get("frozen_state_matches"), bool)
            ):
                raise ValueError("invalid preview registered member")
            continue
        if (
            not all(
                isinstance(row.get(key), str) and row[key]
                for key in (
                    "name",
                    "slug",
                    "state_fingerprint",
                    "native_account_id_after",
                )
            )
            or row.get("brand_action") not in {"create", "reuse"}
            or row.get("company_action") not in {"create", "reuse"}
            or row.get("official_role_action") not in {"create", "retain"}
            or row.get("company_label_action")
            != ("create" if row.get("company_action") == "create" else "none")
            or row.get("automatically_updated_state_fields") != ["updated_at"]
            or not isinstance(row.get("state_before"), dict)
        ):
            raise ValueError("invalid preview eligible member")
        if row["brand_company_action"] == "create" and (
            row["brand_action"] != "create" or row["company_action"] != "create"
        ):
            raise ValueError("invalid preview organization relationship")
    if connection.in_atomic_block:
        raise ValueError("apply requires an outermost transaction")
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW transaction_timeout")
            cursor.fetchone()
    except ProgrammingError as exc:
        raise ValueError("PostgreSQL transaction_timeout is required") from exc
    results = []
    write_attempts = 0
    for index, member in enumerate(manifest["members"]):
        if max_writes is not None and write_attempts >= max_writes:
            results.extend(
                {"state_id": pending["state_id"], "disposition": "not_attempted"}
                for pending in manifest["members"][index:]
            )
            break
        planned = expected[member["state_id"]]
        result = {"state_id": member["state_id"]}
        if planned["disposition"] == "already_registered":
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                    )
                actual = _preview_member(
                    member, [], [], queue_run_id=manifest["queue_run_id"]
                )
            result["disposition"] = (
                "already_registered" if actual == planned else "drift"
            )
            results.append(result)
            continue
        if planned["disposition"] != "eligible":
            result["disposition"] = planned["disposition"]
            results.append(result)
            continue
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # Revalidation must see commits made after earlier reads.
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                    cursor.execute("SET LOCAL transaction_timeout = '2000ms'")
                    cursor.execute("SET LOCAL lock_timeout = '250ms'")
                keys = organization_lock_keys(
                    name=planned["name"],
                    nickname=planned["slug"],
                    account=member["account_key"],
                    state=member["state_id"],
                    brand=planned["brand"],
                    company=planned["company"],
                )
                if not acquire_ingestion_identity_locks(keys):
                    raise IdentityBusy
                state = (
                    OfficialCompanyAccountState.objects.select_for_update(
                        skip_locked=True
                    )
                    .filter(pk=member["state_id"])
                    .first()
                )
                if (
                    state is None
                    or not Account.objects.select_for_update(skip_locked=True)
                    .filter(pk=state.account_id)
                    .exists()
                ):
                    result["disposition"] = "busy_or_missing"
                elif state.status == "registered":
                    actual = _preview_member(
                        member,
                        [],
                        [],
                        queue_run_id=manifest["queue_run_id"],
                        state=state,
                    )
                    correct = _registered_matches_preview(actual, planned)
                    result["disposition"] = "already_registered" if correct else "drift"
                else:
                    actual = _preview_member(
                        member, [], [], queue_run_id=manifest["queue_run_id"]
                    )
                    if actual != planned:
                        result["disposition"] = "drift"
                    else:
                        write_attempts += 1
                        if state.status == "review_needed":
                            state.status = "accepted"
                            state.last_error = ""
                            state.next_attempt_at = None
                            state.save(
                                update_fields=[
                                    "status",
                                    "last_error",
                                    "next_attempt_at",
                                    "updated_at",
                                ]
                            )
                        registered = register_account(
                            state.pk,
                            cfg=cfg,
                            preserve_list_intents=True,
                            propagate_conflicts=True,
                            expected_role_creation=planned["official_role_action"]
                            == "create",
                            expected_actions=planned,
                        )
                        if registered is None:
                            raise ValueError("registration did not run")
                        actual_registered = _preview_member(
                            member, [], [], queue_run_id=manifest["queue_run_id"]
                        )
                        if not _registered_matches_preview(actual_registered, planned):
                            raise ValueError("registered identity changed from preview")
                        if (
                            planned["brand_action"] == "create"
                            and brand_name_candidates(
                                planned["name"], nickname=planned["slug"]
                            )
                            .exclude(pk=planned["brand"])
                            .exists()
                        ):
                            raise ValueError(
                                "brand identity changed during registration"
                            )
                        if planned["company_action"] == "create" and (
                            Company.objects.exclude(pk=planned["company"])
                            .filter(nickname=planned["slug"])
                            .exists()
                            or CompanyLabel.objects.exclude(
                                company_id=planned["company"]
                            )
                            .filter(locale_id="und", label__iexact=planned["name"])
                            .exists()
                        ):
                            raise ValueError(
                                "company identity changed during registration"
                            )
                        # Recheck after the other identity reads as well: a writer
                        # outside this lock protocol can commit between checks.
                        if (
                            planned["brand_action"] == "create"
                            and brand_name_candidates(
                                planned["name"], nickname=planned["slug"]
                            )
                            .exclude(pk=planned["brand"])
                            .exists()
                        ):
                            raise ValueError(
                                "brand identity changed during registration"
                            )
                        result["disposition"] = "registered"
        except IdentityBusy:
            result["disposition"] = "busy_retry"
        except IntegrityError:
            result["disposition"] = "drift"
        except DatabaseError as exc:
            sqlstate = getattr(exc.__cause__, "sqlstate", None)
            if sqlstate == "55P03":
                result["disposition"] = "busy_retry"
            else:
                connection.close()
                result["disposition"] = "unknown_outcome"
                result["database_error_type"] = type(exc).__name__
                result["sqlstate"] = sqlstate
                results.append(result)
                results.extend(
                    {"state_id": pending["state_id"], "disposition": "not_attempted"}
                    for pending in manifest["members"][index + 1 :]
                )
                return results
        except ValueError:
            result["disposition"] = "drift"
        results.append(result)
    return results
