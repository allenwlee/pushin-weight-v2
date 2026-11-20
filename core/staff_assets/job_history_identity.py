"""Apply supported identity, names, language and prose from a prepared packet."""

import re
from datetime import datetime

from django.utils.dateparse import parse_datetime

from core.models import (
    Account,
    Person,
    PersonAccount,
    PersonNameEvidence,
    PersonNameSelection,
    StaffIntake,
)
from core.person_identity import (
    IdentityConflict,
    account_has_observed_handle,
    account_observation_person_ids,
    account_person,
)
from core.person_names import digest, record_name
from core.person_text import record_text
from core.staff_assets.intake import validate_record
from core.staff_assets.job_history_names import assess_fresh, load_lexicon


class IdentityHold(ValueError):
    pass


def _time(value):
    parsed = parse_datetime(value) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.utcoffset() is None:
        raise IdentityHold("A timezone-aware saved observation is required")
    return parsed


def _source_observed(person, text, reference, observed, source_keys=None):
    """Check the quote, clock, and account/post reference as a single observation."""
    if not isinstance(text, str) or not isinstance(reference, str):
        return False
    name = person.get("name_source") or {}
    if (
        source_keys is None
        and text == name.get("source_text")
        and reference == name.get("source_reference")
        and name.get("observed_at")
        and _time(observed) == _time(name["observed_at"])
    ):
        return True
    if source_keys is not None and (
        not isinstance(source_keys, list) or not source_keys
    ):
        return False
    selected = set(source_keys or [])
    for source in person.get("sources", []):
        if selected and source.get("key") not in selected:
            continue
        if source_keys is None and text not in source.get("text", ""):
            continue
        for observation in source.get("observations", []):
            handle = observation.get("handle") or person.get("handle")
            post_id = (
                observation.get("post_id")
                or source.get("native_post_id")
                or source.get("post_id")
                or source.get("tweet_id")
            )
            expected = source.get("url") or (
                f"https://x.com/{handle}" + (f"/status/{post_id}" if post_id else "")
            )
            if (
                expected.casefold() == reference.casefold()
                and observation.get("observed")
                and _time(observed) == _time(observation["observed"])
            ):
                return True
    return False


def _marker(person, native_id, observed, *, purpose, details=None):
    """Persist source-only provenance without establishing staff eligibility."""
    source_key = f"save-person-job:{purpose}:{native_id}"
    payload = {
        "source_key": source_key,
        "display_name": str(person.pk),
        "eligibility": "db_staff",
        "observed_at": observed.isoformat(),
        "collection_mode": "evidence_only",
        "evidence_only": {"schema": "staff-evidence-only/v1", "claims": []},
        "save_person_job": {
            "version": "record-job-history/v1",
            "purpose": purpose,
            **(details or {}),
        },
    }
    validate_record(payload)
    StaffIntake.objects.get_or_create(
        source_key=source_key,
        fingerprint=digest(payload),
        defaults={
            "person": person,
            "eligibility": "db_staff",
            "payload": payload,
            "observed_at": observed,
        },
    )


def apply_identity_records(item, actions, review_provenance):
    """Apply only non-held records for a single verified native account.

    The caller must wrap the complete person in an atomic transaction. A stale
    or ambiguous identity raises IdentityHold so the caller rolls all work back.
    """
    native, handle = item.get("native_id"), item.get("handle")
    if (
        not isinstance(native, str)
        or not native.isascii()
        or not native.isdigit()
        or str(int(native)) != native
        or int(native) <= 0
    ):
        raise IdentityHold("Stable native account identity is missing or invalid")
    if (
        not isinstance(handle, str)
        or not handle
        or not handle.isascii()
        or len(handle) > 15
        or not all(c.isalnum() or c == "_" for c in handle)
    ):
        raise IdentityHold("Saved account handle is invalid")
    identity = item.get("identity") or {}
    if identity.get("account_action") not in {"create", "reuse"} or identity.get(
        "person_action"
    ) not in {"create", "reuse"}:
        raise IdentityHold("Prepared identity is held")
    source_time = (item.get("name_source") or {}).get("observed_at")
    if not source_time:
        raise IdentityHold("Account identity has no saved observation clock")
    name_source = item.get("name_source") or {}
    if name_source.get("native_id") not in {None, native}:
        raise IdentityHold("Name source belongs to another account")
    if (
        name_source.get("source_reference")
        and name_source["source_reference"].casefold()
        != f"https://x.com/{handle}".casefold()
    ):
        raise IdentityHold("Name source references a different account")
    observed = _time(source_time)
    account = Account.x.select_for_update().filter(author_id=native).first()
    account_created = False
    person_created = False
    if account is None:
        if identity["account_action"] != "create":
            raise IdentityHold("Prepared account no longer exists")
        if Account.x.filter(handle__iexact=handle).exists():
            raise IdentityHold("Handle is attached to another account")
        account = Account.x.create(author_id=native, handle=handle)
        account_created = True
    else:
        if account.handle and account.handle.casefold() != handle.casefold():
            # Handles change; accept a historical spelling only when the saved
            # name identifies this native account and persisted evidence binds
            # the old spelling to the same account. Never rename the live row.
            historical = (
                name_source.get("native_id") == native
                and account_has_observed_handle(account, handle)
            )
            if not historical:
                raise IdentityHold("Saved handle conflicts with current account")
        if identity["account_action"] == "reuse" and str(account.pk) != str(
            identity.get("account_key")
        ):
            raise IdentityHold("Prepared account identity changed")
        if (
            identity["account_action"] == "create"
            and not StaffIntake.objects.filter(
                source_key=f"save-person-job:identity:{native}"
            ).exists()
        ):
            raise IdentityHold("Account appeared since preview")
    try:
        resolved = account_person(account, create=False)
    except IdentityConflict as exc:
        raise IdentityHold(str(exc)) from exc
    action = identity["person_action"]
    if action == "reuse":
        if resolved is None or str(resolved.pk) != str(identity.get("person_id")):
            raise IdentityHold("Prepared person identity changed")
        if (
            not PersonAccount.objects.filter(person=resolved, account=account)
            .exclude(resolution_status="rejected")
            .exists()
        ):
            raise IdentityHold("Prepared person-account link is absent")
        person = Person.objects.select_for_update().get(pk=resolved.pk)
    else:
        marker_key = f"save-person-job:identity:{native}"
        if resolved is not None:
            if not StaffIntake.objects.filter(
                person=resolved, source_key=marker_key
            ).exists():
                raise IdentityHold("Account gained another person since preview")
            if (
                not PersonAccount.objects.filter(person=resolved, account=account)
                .exclude(resolution_status="rejected")
                .exists()
            ):
                raise IdentityHold("Previously imported account link is absent")
            person = Person.objects.select_for_update().get(pk=resolved.pk)
        else:
            if (
                PersonAccount.objects.filter(account=account)
                .exclude(resolution_status="rejected")
                .exists()
            ):
                raise IdentityHold("Account has an unresolved person link")
            person, person_created = Person.objects.get_or_create(
                pk=account_observation_person_ids(native)[0]
            )
            if not person_created:
                raise IdentityHold(
                    "Derived person already exists without a source link"
                )
            person = Person.objects.select_for_update().get(pk=person.pk)
            try:
                resolved = account_person(account, create=True, observed_at=observed)
            except IdentityConflict as exc:
                raise IdentityHold(str(exc)) from exc
            if resolved.pk != person.pk:
                raise IdentityHold("Account resolved to an unexpected person")
            _marker(
                person,
                native,
                observed,
                purpose="identity",
                details={"native_id": native},
            )
    counts = {
        "accounts_created": int(account_created),
        "accounts_reused": int(not account_created),
        "people_created": int(person_created),
        "people_reused": int(not person_created),
        "names_created": 0,
        "names_reused": 0,
        "names_held": 0,
        "name_evidence_held": 0,
        "language_updated": 0,
        "language_retained": 0,
        "language_held": 0,
        "language_excluded": 0,
        "texts_created": 0,
        "texts_reused": 0,
        "texts_held": 0,
    }
    name_actions = [a for a in actions if a.get("table") == "people_names"]
    name_evidence = [a for a in actions if a.get("table") == "people_name_evidence"]
    counts["name_evidence_held"] = sum(
        action.get("action") == "hold" for action in name_evidence
    )
    selections = [a for a in actions if a.get("table") == "person_name_selections"]
    for action in name_actions:
        if action.get("action") not in {"create", "compare_or_create", "reuse"}:
            counts["names_held"] += 1
            continue
        f = action.get("fields") or {}
        full = f.get("full_name")
        related = [
            e
            for e in name_evidence
            if (e.get("fields") or {}).get("name_id") == action.get("key")
            and e.get("action") in {"create", "compare_or_create", "reuse"}
        ]
        if (
            not isinstance(full, str)
            or not full.strip()
            or f.get("locale_id", "und") != "und"
            or not related
        ):
            counts["names_held"] += 1
            continue
        row = None
        name_created = False
        for evidence in related:
            e = evidence.get("fields") or {}
            quote, ref, time = (
                e.get("source_text"),
                e.get("source_reference"),
                e.get("observed_at"),
            )
            if (
                not isinstance(quote, str)
                or full not in quote
                or not time
                or not _source_observed(item, quote, ref, time)
            ):
                counts["name_evidence_held"] += 1
                continue
            before = person.names.count()
            row = record_name(
                person,
                full_name=full,
                language="und",
                source_kind=e.get("source_kind") or "saved_account_name",
                source_reference=ref,
                source_text=quote,
                collection_method=e.get("collection_method")
                or "record-job-history-saved-review-v1",
                observed_at=_time(time),
                name_type=f.get("name_type", "professional"),
                origin=f.get("origin", "source"),
            )
            # The shared legacy fingerprint omits the observation clock. Keep
            # additional dated observations instead of silently collapsing them.
            source_fields = {
                "source_kind": e.get("source_kind") or "saved_account_name",
                "source_reference": ref,
                "source_text": quote,
                "supports_fields": ["full_name"],
                "collection_method": e.get("collection_method")
                or "record-job-history-saved-review-v1",
                "review_reason": "",
            }
            primary = PersonNameEvidence.objects.get(
                name=row, evidence_hash=digest(source_fields)
            )
            original_time = _time(time)
            if primary.observed_at != original_time:
                PersonNameEvidence.objects.get_or_create(
                    name=row,
                    evidence_hash=digest(
                        {**source_fields, "observed_at": original_time.isoformat()}
                    ),
                    defaults={**source_fields, "observed_at": original_time},
                )
            name_created = name_created or person.names.count() > before
        if row:
            counts["names_created" if name_created else "names_reused"] += 1
        else:
            counts["names_held"] += 1
        if (
            row
            and action.get("action") == "create"
            and identity["person_action"] == "create"
            and any(
                s.get("action") == "create"
                and (s.get("fields") or {}).get("name_id") == action["key"]
                for s in selections
            )
        ):
            PersonNameSelection.objects.get_or_create(
                person=person, display_locale_id="und", defaults={"name": row}
            )
    language = item.get("language_proposal") or {}
    counts["language_held"] = int(language.get("action") == "hold")
    counts["language_excluded"] = int(language.get("action") == "excluded")
    if language.get("action") == "propose":
        trusted_name = name_source.get("source_text")
        trusted_names = [trusted_name] if trusted_name in item.get("names", []) else []
        assessed = assess_fresh({**item, "names": trusted_names}, load_lexicon())
        if (
            assessed["outcome"] != "assign"
            or language.get("value") != "zh-Hans"
            or language.get("exclusion_reason")
            or not isinstance(review_provenance, dict)
            or any(
                not isinstance(review_provenance.get(key), str)
                or not re.fullmatch(r"[0-9a-f]{64}", review_provenance[key])
                for key in ("review_sha256", "source_audit_sha256", "name_audit_sha256")
            )
            or not isinstance(review_provenance.get("authorized_by"), str)
            or not review_provenance["authorized_by"].strip()
            or not review_provenance.get("reviewed_at")
        ):
            raise IdentityHold(
                "Language proposal is not supported by the selected reviewed rules"
            )
        if not person.primary_language:
            person.primary_language = "zh-Hans"
            person.save(update_fields=["primary_language", "updated_at"])
            _marker(
                person,
                native,
                _time(review_provenance["reviewed_at"]),
                purpose="language",
                details={
                    "review_sha256": review_provenance["review_sha256"],
                    "source_audit_sha256": review_provenance["source_audit_sha256"],
                    "name_audit_sha256": review_provenance["name_audit_sha256"],
                    "authorized_by": review_provenance["authorized_by"],
                    "value": "zh-Hans",
                },
            )
            counts["language_updated"] += 1
        else:
            counts["language_retained"] += 1
    for action in actions:
        if action.get("table") != "people_texts":
            continue
        f = action.get("fields") or {}
        if (
            action.get("action") != "compare_or_create"
            or f.get("action") != "compare_or_create"
        ):
            counts["texts_held"] += 1
            continue
        if (
            f.get("kind") != "biography"
            or f.get("origin") != "summary"
            or f.get("language") != "und"
            or f.get("review_status") != "pending"
            or not f.get("text")
            or not f.get("observed_at")
            or not _source_observed(
                item,
                f["text"],
                f.get("source_reference"),
                f["observed_at"],
                f.get("source_keys"),
            )
        ):
            counts["texts_held"] += 1
            continue
        observation_times = f.get("observation_times", [f["observed_at"]])
        if (
            not isinstance(observation_times, list)
            or not observation_times
            or any(
                not time
                or not _source_observed(
                    item, f["text"], f["source_reference"], time, f.get("source_keys")
                )
                for time in observation_times
            )
        ):
            counts["texts_held"] += 1
            continue
        before = person.texts.count()
        record_text(
            person,
            kind="biography",
            language="und",
            text=f["text"],
            source_reference=f["source_reference"],
            observed_at=_time(f["observed_at"]),
            origin="summary",
            review_status="pending",
        )
        counts[
            "texts_created" if person.texts.count() > before else "texts_reused"
        ] += 1
        _marker(
            person,
            native,
            _time(f["observed_at"]),
            purpose="text:" + digest([f["source_reference"], f["text"]]),
            details={
                "source_reference": f["source_reference"],
                "source_keys": f["source_keys"],
                "observation_times": observation_times,
            },
        )
    return person, account, counts
