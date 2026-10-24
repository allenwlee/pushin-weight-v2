"""Record evidence and deliberate display selections without guessing name parts."""

from __future__ import annotations

import hashlib
import json

from django.db import transaction
from django.utils import timezone

from core.models import (
    Locale,
    Person,
    PersonName,
    PersonNameEvidence,
    PersonNameSelection,
)


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
    try:
        locale = Locale.objects.get(code=language)
    except Locale.DoesNotExist as exc:
        raise ValueError(f"Unregistered PersonName locale: {language}") from exc
    if name_type not in {"professional", "romanized"}:
        raise ValueError(f"Unsupported person name kind: {name_type}")
    row, _ = PersonName.objects.get_or_create(
        person=person,
        fingerprint=digest(representation),
        defaults={
            "full_name": full_name,
            "locale": locale,
            "name_type": name_type,
            "origin": origin,
            "derived_from": derived_from,
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
def record_legacy_display_name(person, full_name):
    """Preserve an unlocalized legacy display value without claiming review."""
    value = (full_name or "").strip()
    if not value:
        return None
    row = record_name(
        person,
        full_name=value,
        language="und",
        source_kind="legacy_unknown",
        source_reference=f"people:{person.pk}:display_name",
        source_text=value,
        collection_method="migration",
        origin="legacy",
        review_reason="Legacy display wording retained; source and identity unverified",
    )
    PersonNameSelection.objects.get_or_create(
        person=person,
        display_locale_id="und",
        defaults={"name": row},
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
    if english and english.locale_id not in {"en", "en-Latn"}:
        raise ValueError("English selection must use an English language tag")
    current = Person.objects.select_related("primary_name").get(pk=person.pk)
    selections = {}
    if primary or current.primary_name_id:
        selections["und"] = primary
    if english or current.english_name_id:
        selections["en"] = english
    for locale in ("zh-Hans", "ja"):
        if primary and primary.locale_id == locale:
            selections[locale] = primary
        elif current.primary_name_id and current.primary_name.locale_id == locale:
            selections[locale] = None
    for locale, name in selections.items():
        if name is None:
            PersonNameSelection.objects.filter(
                person_id=person.pk, display_locale_id=locale
            ).delete()
        else:
            PersonNameSelection.objects.update_or_create(
                person_id=person.pk,
                display_locale_id=locale,
                defaults={"name": name},
            )
    Person.objects.filter(pk=person.pk).update(
        primary_name=primary, english_name=english
    )
    person.refresh_from_db()


def selected_name_for(person, locale: str) -> str | None:
    """Return the explicit locale selection, falling back to the und default."""
    aliases = {"zh-cn": "zh-Hans", "zh_CN": "zh-Hans", "zh_hans": "zh-Hans"}
    requested = aliases.get(locale, locale)
    cached = getattr(person, "_prefetched_objects_cache", {}).get("name_selections")
    if cached is None:
        rows = person.name_selections.select_related("name").all()
    else:
        rows = cached
    by_locale = {row.display_locale_id: row.name.full_name for row in rows}
    return by_locale.get(requested) or (
        None if requested == "und" else by_locale.get("und")
    )
