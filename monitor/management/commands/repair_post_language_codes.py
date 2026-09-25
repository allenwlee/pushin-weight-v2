"""Resolve historical `other` language values without touching post content."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from core.models import Post
from x_monitor.config import load_config
from x_monitor.reattribute import build_translator_client_from_env
from x_monitor.translator import normalize_lang_detected

MAX_SAMPLE_CHARS = 4000
MAX_OUTPUT_TOKENS_PER_CALL = 80


def detect_language(client, model: str, post: Post) -> str | None:
    prompt = (
        "Identify the source language of this post. Return only JSON with "
        'one key, `lang_detected`, containing its ISO 639-1 two-letter code '
        "(or zh-Hans/zh-Hant for Chinese). Never use `other`. "
        f"Post: {json.dumps((post.text or '')[:MAX_SAMPLE_CHARS], ensure_ascii=False)}"
    )
    response = client.messages_create(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS_PER_CALL,
        messages=[{"role": "user", "content": prompt}],
    )
    if not isinstance(response, dict):
        return None
    code = normalize_lang_detected(response.get("lang_detected"))
    return code if code and code != "other" else None


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--max-posts", type=int, default=20)
        parser.add_argument("--after-post-id", default="")
        parser.add_argument("--confirm-database")
        parser.add_argument("--confirm-provider-calls", type=int)

    def handle(self, **options):
        limit = options["max_posts"]
        if not 1 <= limit <= 100:
            raise CommandError("--max-posts must be between 1 and 100")
        database = connection.settings_dict["NAME"]
        eligible = Post.objects.filter(lang_detected__iexact="other").exclude(text__isnull=True).exclude(text="")
        if options["after_post_id"]:
            eligible = eligible.filter(pk__gt=options["after_post_id"])
        total = eligible.count()
        preview_ids = list(eligible.order_by("pk").values_list("pk", flat=True)[:limit])
        self.stdout.write(json.dumps({"database": database, "eligible": total, "preview_ids": preview_ids,
                                      "preview_end_cursor": preview_ids[-1] if preview_ids else options["after_post_id"],
                                      "max_provider_calls": len(preview_ids),
                                      "max_input_sample_chars_per_call": MAX_SAMPLE_CHARS,
                                      "max_output_tokens": MAX_OUTPUT_TOKENS_PER_CALL * len(preview_ids),
                                      "apply": options["apply"]}))
        if not options["apply"]:
            return
        if options["confirm_database"] != database:
            raise CommandError("--confirm-database must match the connected database")
        if options["confirm_provider_calls"] != len(preview_ids):
            raise CommandError("--confirm-provider-calls must match the dry-run count")
        if not preview_ids:
            return
        cfg = load_config(Path("config.yaml"))
        client = build_translator_client_from_env(cfg)
        if client is None:
            raise CommandError("configured translator client is unavailable")
        resolved = 0
        unresolved = 0
        attempted = 0
        for post in eligible.order_by("pk")[:limit]:
            code = detect_language(client, cfg.llm.translator_model, post)
            attempted += 1
            updated = 0
            if code is not None:
                updated = Post.objects.filter(pk=post.pk, lang_detected__iexact="other").update(lang_detected=code)
                resolved += updated
            if not updated:
                unresolved += 1
            self.stdout.write(json.dumps({"resume_after": post.pk, "resolved": bool(updated)}))
        self.stdout.write(json.dumps({"resolved": resolved, "unresolved": unresolved,
                                      "provider_calls": attempted}))
