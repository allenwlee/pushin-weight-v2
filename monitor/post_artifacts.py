"""Versioned literal-translation and rich-synthesis persistence/readers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from core.models import (
    Post,
    PostSynthesisArtifact,
    PostSynthesisDemand,
    PostSynthesisText,
    PostTranslationArtifact,
    PostTranslationText,
)
from monitor.post_enrichment import commentary_is_distinct, present_text
from x_monitor.translator import normalize_lang_detected

SUPPORTED_CONTENT_LOCALES = ("en", "zh-cn", "ja")


@dataclass(frozen=True, slots=True)
class PostContentProjection:
    literal: Mapping[str, str]
    synthesis: Mapping[str, str]
    literal_source: str
    synthesis_source: str
    synthesis_status: str


def source_content_fingerprint(post: Post) -> str:
    return source_text_fingerprint(post.text)


def source_text_fingerprint(text: object) -> str:
    return _hash({"text": str(text or "")})


def synthesis_context_fingerprint(post: Post, *, parent_text: str = "") -> str:
    return _hash(
        {
            "text": post.text or "",
            "stored_quote": post.quoted_text or "",
            "local_parent": parent_text,
        }
    )


def publish_literal_translation(
    *,
    post: Post,
    row: Mapping[str, Any],
    prompt_version: str,
    model: str,
    expected_source_fingerprint: str,
    provider_role: str = "literal_translation",
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int | None = None,
    now=None,
) -> PostTranslationArtifact | None:
    current = now or timezone.now()
    language = normalize_lang_detected(row.get("lang_detected"))
    if language is None:
        return None
    source = present_text(post.text)
    values = {
        "en": source if language == "en" else present_text(row.get("text_en")),
        "zh-cn": (
            source
            if language == "zh-Hans"
            else present_text(row.get("text_zh_cn") or row.get("literal_zh"))
        ),
        "ja": source if language == "ja" else present_text(row.get("text_ja")),
    }
    if source is None or any(value is None for value in values.values()):
        return None
    with transaction.atomic():
        locked_post = Post.objects.select_for_update().get(pk=post.pk)
        fingerprint = source_content_fingerprint(locked_post)
        if fingerprint != expected_source_fingerprint:
            return None
        artifact, created = PostTranslationArtifact.objects.get_or_create(
            post=locked_post,
            source_content_fingerprint=fingerprint,
            source_language=language,
            prompt_version=prompt_version,
            model=model,
            provider_role=provider_role,
            defaults={
                "state": PostTranslationArtifact.State.GENERATING,
                "started_at": current,
            },
        )
        if artifact.state != PostTranslationArtifact.State.SUCCEEDED:
            if not created:
                artifact.attempts += 1
            artifact.texts.all().delete()
            PostTranslationText.objects.bulk_create(
                [
                    PostTranslationText(
                        artifact=artifact,
                        locale=locale,
                        text=str(value),
                        is_source=(
                            (locale == "en" and language == "en")
                            or (locale == "zh-cn" and language == "zh-Hans")
                            or (locale == "ja" and language == "ja")
                        ),
                    )
                    for locale, value in values.items()
                ]
            )
            artifact.source_language = language
            artifact.state = PostTranslationArtifact.State.SUCCEEDED
            artifact.input_tokens = max(0, input_tokens)
            artifact.output_tokens = max(0, output_tokens)
            artifact.latency_ms = latency_ms
            artifact.error_code = ""
            artifact.completed_at = current
            artifact.save()
        PostTranslationArtifact.objects.filter(
            post=locked_post, is_current=True
        ).exclude(pk=artifact.pk).update(is_current=False)
        if not artifact.is_current:
            artifact.is_current = True
            artifact.save(update_fields=["is_current", "updated_at"])
        Post.objects.filter(pk=locked_post.pk).update(
            lang_detected=language,
            text_en=values["en"],
            text_zh_cn=values["zh-cn"],
        )
        return artifact


def record_literal_translation_failure(
    *,
    post: Post,
    prompt_version: str,
    model: str,
    expected_source_fingerprint: str,
    error_code: str,
    source_language: object = None,
    provider_role: str = "literal_translation",
    now=None,
) -> PostTranslationArtifact | None:
    """Persist one safe failed attempt without replacing last-good output."""

    current = now or timezone.now()
    language = (
        normalize_lang_detected(source_language)
        or normalize_lang_detected(post.lang_detected)
        or normalize_lang_detected(post.lang)
        or "unknown"
    )
    with transaction.atomic():
        locked_post = Post.objects.select_for_update().get(pk=post.pk)
        fingerprint = source_content_fingerprint(locked_post)
        if fingerprint != expected_source_fingerprint:
            return None
        artifact, created = PostTranslationArtifact.objects.get_or_create(
            post=locked_post,
            source_content_fingerprint=fingerprint,
            source_language=language,
            prompt_version=prompt_version,
            model=model,
            provider_role=provider_role,
            defaults={
                "state": PostTranslationArtifact.State.FAILED,
                "error_code": str(error_code or "translation_failed")[:128],
                "started_at": current,
                "completed_at": current,
            },
        )
        if artifact.state == PostTranslationArtifact.State.SUCCEEDED:
            return artifact
        if not created:
            artifact.attempts += 1
        artifact.state = PostTranslationArtifact.State.FAILED
        artifact.error_code = str(error_code or "translation_failed")[:128]
        artifact.completed_at = current
        artifact.is_current = False
        artifact.save()
        return artifact


def publish_post_synthesis(
    *,
    post: Post,
    values: Mapping[str, Any],
    context_fingerprint: str,
    prompt_version: str,
    model: str,
    output_schema_version: int,
    provider_role: str = "rich_synthesis",
    evidence_provenance: Sequence[Mapping[str, Any]] = (),
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int | None = None,
    attempts: int = 1,
    now=None,
) -> PostSynthesisArtifact | None:
    current = now or timezone.now()
    normalized = {
        locale: present_text(values.get(locale)) for locale in SUPPORTED_CONTENT_LOCALES
    }
    if any(value is None for value in normalized.values()):
        return None
    normalized_literal = tuple(
        PostTranslationText.objects.filter(
            artifact__post=post,
            artifact__is_current=True,
            artifact__state=PostTranslationArtifact.State.SUCCEEDED,
        ).values_list("text", flat=True)
    )
    base_comparisons = (
        post.text,
        post.text_en,
        post.text_zh_cn,
        *normalized_literal,
    )
    if not all(
        commentary_is_distinct(
            value,
            *base_comparisons,
            *(other for other_locale, other in normalized.items() if other_locale != locale),
        )
        for locale, value in normalized.items()
    ):
        return None
    with transaction.atomic():
        locked_post = Post.objects.select_for_update().get(pk=post.pk)
        artifact, _created = PostSynthesisArtifact.objects.get_or_create(
            post=locked_post,
            input_context_fingerprint=context_fingerprint,
            prompt_version=prompt_version,
            model=model,
            provider_role=provider_role,
            output_schema_version=output_schema_version,
            defaults={
                "state": PostSynthesisArtifact.State.GENERATING,
                "started_at": current,
            },
        )
        if artifact.state != PostSynthesisArtifact.State.SUCCEEDED:
            artifact.texts.all().delete()
            PostSynthesisText.objects.bulk_create(
                [
                    PostSynthesisText(
                        artifact=artifact,
                        locale=locale,
                        text=str(value),
                    )
                    for locale, value in normalized.items()
                ]
            )
            artifact.state = PostSynthesisArtifact.State.SUCCEEDED
            artifact.attempts = max(1, attempts)
            artifact.input_tokens = max(0, input_tokens)
            artifact.output_tokens = max(0, output_tokens)
            artifact.latency_ms = latency_ms
            artifact.error_code = ""
            artifact.evidence_provenance = list(evidence_provenance)
            artifact.review_state = "validated"
            artifact.completed_at = current
            artifact.save()
        PostSynthesisArtifact.objects.filter(
            post=locked_post, is_current=True
        ).exclude(pk=artifact.pk).update(is_current=False)
        if not artifact.is_current:
            artifact.is_current = True
            artifact.save(update_fields=["is_current", "updated_at"])
        Post.objects.filter(pk=locked_post.pk).update(
            commentary_en=normalized["en"],
            commentary_zh_cn=normalized["zh-cn"],
        )
        return artifact


def record_post_synthesis_failure(
    *,
    post: Post,
    context_fingerprint: str,
    prompt_version: str,
    model: str,
    output_schema_version: int,
    error_code: str,
    attempts: int,
    provider_role: str = "rich_synthesis",
    now=None,
) -> PostSynthesisArtifact:
    """Persist failed synthesis lifecycle state while retaining last-good."""

    current = now or timezone.now()
    artifact, _created = PostSynthesisArtifact.objects.get_or_create(
        post=post,
        input_context_fingerprint=context_fingerprint,
        prompt_version=prompt_version,
        model=model,
        provider_role=provider_role,
        output_schema_version=output_schema_version,
        defaults={
            "state": PostSynthesisArtifact.State.FAILED,
            "attempts": max(1, attempts),
            "error_code": str(error_code or "synthesis_failed")[:128],
            "started_at": current,
            "completed_at": current,
        },
    )
    if artifact.state != PostSynthesisArtifact.State.SUCCEEDED:
        artifact.state = PostSynthesisArtifact.State.FAILED
        artifact.attempts = max(artifact.attempts, attempts, 1)
        artifact.error_code = str(error_code or "synthesis_failed")[:128]
        artifact.completed_at = current
        artifact.is_current = False
        artifact.save()
    return artifact


def read_post_content_many(
    posts: Sequence[Post],
) -> dict[str, PostContentProjection]:
    """Bulk-read normalized current artifacts with explicit legacy fallback."""
    post_ids = [str(post.pk) for post in posts]
    translations = {
        str(artifact.post_id): artifact
        for artifact in PostTranslationArtifact.objects.filter(
            post_id__in=post_ids,
            is_current=True,
            state=PostTranslationArtifact.State.SUCCEEDED,
        ).prefetch_related(
            Prefetch("texts", queryset=PostTranslationText.objects.order_by("locale"))
        )
    }
    syntheses = {
        str(artifact.post_id): artifact
        for artifact in PostSynthesisArtifact.objects.filter(
            post_id__in=post_ids,
            is_current=True,
            state=PostSynthesisArtifact.State.SUCCEEDED,
        ).prefetch_related(
            Prefetch("texts", queryset=PostSynthesisText.objects.order_by("locale"))
        )
    }
    demand_states = dict(
        PostSynthesisDemand.objects.filter(post_id__in=post_ids)
        .order_by("post_id", "-updated_at")
        .distinct("post_id")
        .values_list("post_id", "state")
    )
    projections = {}
    for post in posts:
        post_id = str(post.pk)
        translation = translations.get(post_id)
        synthesis = syntheses.get(post_id)
        literal = (
            {row.locale: row.text for row in translation.texts.all()}
            if translation is not None
            else _legacy_literal(post)
        )
        rich = (
            {row.locale: row.text for row in synthesis.texts.all()}
            if synthesis is not None
            else _legacy_synthesis(post)
        )
        locale_complete = all(rich.get(locale) for locale in SUPPORTED_CONTENT_LOCALES)
        status = (
            "ready"
            if locale_complete
            else str(
                demand_states.get(post_id)
                or ("legacy_partial" if rich else "not_requested")
            )
        )
        projections[post_id] = PostContentProjection(
            literal=literal,
            synthesis=rich,
            literal_source="normalized" if translation is not None else "legacy",
            synthesis_source="normalized" if synthesis is not None else "legacy",
            synthesis_status=status,
        )
    return projections


def _legacy_literal(post: Post) -> dict[str, str]:
    values = {"en": post.text_en, "zh-cn": post.text_zh_cn}
    language = normalize_lang_detected(post.lang_detected)
    if language == "ja" and present_text(post.text):
        values["ja"] = post.text
    return {
        locale: value
        for locale, raw in values.items()
        if (value := present_text(raw)) is not None
    }


def _legacy_synthesis(post: Post) -> dict[str, str]:
    return {
        locale: value
        for locale, raw in {
            "en": post.commentary_en,
            "zh-cn": post.commentary_zh_cn,
        }.items()
        if (value := present_text(raw)) is not None
    }


def _hash(value: Mapping[str, Any]) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
