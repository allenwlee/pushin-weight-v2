"""Record evidence and deliberate display selections without guessing name parts."""

from __future__ import annotations

import hashlib
import json

from django.db import transaction
from django.utils import timezone

from core.models import Person, PersonName, PersonNameEvidence


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


@transaction.atomic
def record_name(
    person,
    *,
    full_name,
    language,
    source_kind,
    source_reference,
    source_text,
    collection_method,
    given_name=None,
    family_name=None,
    name_type="professional",
    name_order="unknown",
    origin="source",
    derived_from=None,
    supports_fields=None,
    observed_at=None,
    review_reason="",
):
    if not full_name.strip() or not source_reference.strip():
        raise ValueError("A full name and source reference are required")
    fields = supports_fields or ["full_name"]
    for field, value in (("given_name", given_name), ("family_name", family_name)):
        if value is not None and field not in fields:
            raise ValueError(f"supports_fields must explicitly support {field}")
    if derived_from and derived_from.person_id != person.pk:
        raise ValueError("Derived name must belong to the same person")
    representation = {
        "full_name": full_name,
        "language": language,
        "name_type": name_type,
        "origin": origin,
        "derived_from_id": derived_from.pk if derived_from else None,
    }
    row, _ = PersonName.objects.get_or_create(
        person=person,
        fingerprint=digest(representation),
        defaults={
            **representation,
            "given_name": given_name,
            "family_name": family_name,
            "name_order": name_order,
        },
    )
    # A later conflicting component is another observation, never a silent rewrite.
    if (given_name and row.given_name not in (None, given_name)) or (
        family_name and row.family_name not in (None, family_name)
    ):
        raise ValueError("Conflicting name components require a reviewed correction")
    updates = {}
    for field, value in (("given_name", given_name), ("family_name", family_name)):
        if value and getattr(row, field) is None:
            updates[field] = value
    if updates:
        PersonName.objects.filter(pk=row.pk).update(**updates)
        row.refresh_from_db()
    evidence = {
        "source_kind": source_kind,
        "source_reference": source_reference,
        "source_text": source_text,
        "supports_fields": fields,
        "collection_method": collection_method,
        "review_reason": review_reason,
    }
    PersonNameEvidence.objects.get_or_create(
        name=row,
        evidence_hash=digest(evidence),
        defaults={**evidence, "observed_at": observed_at or timezone.now()},
    )
    return row


@transaction.atomic
def review_name(name, status, reviewer, reason):
    if status not in {"pending", "confirmed", "rejected"} or not reviewer or not reason:
        raise ValueError("Review requires a status, reviewer and reason")
    row = PersonName.objects.select_for_update().get(pk=name.pk)
    if status != "confirmed":
        person = Person.objects.get(pk=row.person_id)
        select_names(
            person,
            primary=None if person.primary_name_id == row.pk else person.primary_name,
            english=None if person.english_name_id == row.pk else person.english_name,
        )
    row.review_history.append(
        {
            "status": status,
            "reviewer": reviewer,
            "reason": reason,
            "at": timezone.now().isoformat(),
        }
    )
    row.review_status = status
    row.save(update_fields=["review_status", "review_history", "updated_at"])
    name.refresh_from_db()
    return row


@transaction.atomic
def select_names(person, *, primary=None, english=None):
    for name in (primary, english):
        if name is not None:
            name.refresh_from_db()
            if name.person_id != person.pk or name.review_status != "confirmed":
                raise ValueError(
                    "Selected names must be confirmed and belong to this person"
                )
    if english and english.language not in {"en", "en-Latn"}:
        raise ValueError("English selection must use an English language tag")
    current = Person.objects.get(pk=person.pk)
    mirrors = {}
    if primary:
        mirrors["display_name"] = primary.full_name
    elif current.primary_name_id:
        mirrors["display_name"] = "Unreviewed person"
    if english or current.english_name_id:
        mirrors["display_name_en"] = english.full_name if english else None
    for language, field in (
        ("zh-Hans", "display_name_zh_cn"),
        ("ja", "display_name_ja"),
    ):
        if primary and primary.language == language:
            mirrors[field] = primary.full_name
        elif current.primary_name_id and current.primary_name.language == language:
            mirrors[field] = None
    Person.objects.filter(pk=person.pk).update(
        primary_name=primary, english_name=english, **mirrors
    )
    person.refresh_from_db()
