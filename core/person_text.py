"""Versioned original prose; translations are explicit, cached display artifacts."""

from django.db import connection
from django.utils import timezone

from core.models import PersonText, PersonTextTranslation
from core.person_names import digest


def literal_translator(*, client, config):
    """Adapt the existing explicitly configured literal translator for one original."""
    from x_monitor.translator import translate_batch_literal

    def translate(*, text, source_language, language):
        rows = translate_batch_literal(
            [{"tweet_id": "person-prose", "text": text, "lang": source_language}],
            client,
            cfg=config,
            max_workers=1,
        )
        if len(rows) != 1 or rows[0].get("translation_failed"):
            raise ValueError("Prose translation failed; retain the original")
        return rows[0].get("text_" + language)

    return translate


def record_text(
    person,
    *,
    kind,
    language,
    text,
    source_reference,
    observed_at=None,
    affiliation=None,
    origin="source",
    derived_from=None,
    review_status="pending",
    review_note="",
):
    if kind not in {"biography", "role", "job_description", "location", "title"}:
        raise ValueError("Names belong in PersonName, not the prose translation path")
    if not text or not source_reference:
        raise ValueError("Original text and source are required")
    if affiliation and affiliation.person_id != person.pk:
        raise ValueError("Text and affiliation must belong to the same person")
    if kind == "title" and affiliation is None:
        raise ValueError("A title requires an affiliation")
    if derived_from and (
        derived_from.person_id != person.pk
        or derived_from.affiliation_id != (affiliation.pk if affiliation else None)
    ):
        raise ValueError("Derived text requires the same person and affiliation")
    version = [language, text]
    if origin != "source" or derived_from:
        version += [origin, derived_from.pk if derived_from else None]
    return PersonText.objects.get_or_create(
        person=person,
        affiliation=affiliation,
        kind=kind,
        source_reference=source_reference,
        version_hash=digest(version),
        defaults={
            "language": language,
            "text": text,
            "observed_at": observed_at or timezone.now(),
            "origin": origin,
            "derived_from": derived_from,
            "review_status": review_status,
            "review_note": review_note,
        },
    )[0]


def translate_text(original, *, language, provider, model, prompt_version, translator):
    if language not in {"en", "ja"} or not all((provider, model, prompt_version)):
        raise ValueError("Explicit EN/JA target and translation configuration required")
    key = {
        "original": original,
        "language": language,
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
    }
    cached = PersonTextTranslation.objects.filter(**key).first()
    if cached:
        return cached
    if connection.in_atomic_block:
        raise RuntimeError("Translation must run outside source transactions")
    text = translator(
        text=original.text, source_language=original.language, language=language
    )
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Translation returned no text; original retained")
    return PersonTextTranslation.objects.get_or_create(**key, defaults={"text": text})[
        0
    ]
