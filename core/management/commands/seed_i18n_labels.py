"""Management command: seed the i18n label tables with known taxonomy values.

Usage:
  python manage.py seed_i18n_labels          # insert missing rows
  python manage.py seed_i18n_labels --dry-run  # preview only
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from core.models import (
    PostTypeKey,
    PostTypeLabel,
    SentimentKey,
    SentimentLabel,
    DiscourseKey,
    DiscourseLabel,
    NationalismKey,
    NationalismLabel,
    Role,
    RoleLabel,
)

# ---------------------------------------------------------------------------
# Canonical taxonomy values (mirrors x_monitor/attribution.py constants)
# ---------------------------------------------------------------------------

_POST_TYPES: list[str] = [
    "buzz_releases",
    "hands_on_usage",
    "performance_comparisons",
    "feedback_questions",
    "advertising_marketing",
    "event_announcement",
]

_SENTIMENTS: list[str] = [
    "positive",
    "negative",
    "neutral",
    "mixed",
]

_DISCOURSE: list[str] = [
    "genuine_hype",
    "sarcasm",
    "dunk_yingyang",
    "self_deprecation",
    "cope",
    "fud",
    "distillation_accusation",
    "ai_slop_critique",
    "absurdist_meme",
    "advertising-marketing",
]

_NATIONALISM: list[str] = [
    "none",
    "mild_pro",
    "pro",
    "constructive_critical",
    "anti",
    "mixed",
]

_ROLES: list[str] = [
    "official",
    "staff",
    "community",
]

_LOCALES = ["en", "zh-cn"]

# ---------------------------------------------------------------------------
# Label maps — en and zh-cn for every taxonomy key
# ---------------------------------------------------------------------------

POST_TYPE_LABELS: dict[str, dict[str, str]] = {
    "buzz_releases":            {"en": "Buzz & Releases",          "zh-cn": "热点发布"},
    "hands_on_usage":           {"en": "Hands-On Usage",           "zh-cn": "实际使用"},
    "performance_comparisons":  {"en": "Performance Comparisons",  "zh-cn": "性能对比"},
    "feedback_questions":       {"en": "Feedback & Questions",     "zh-cn": "反馈提问"},
    "advertising_marketing":    {"en": "Advertising & Marketing",  "zh-cn": "广告营销"},
    "event_announcement":       {"en": "Event Announcement",       "zh-cn": "活动公告"},
}

SENTIMENT_LABELS: dict[str, dict[str, str]] = {
    "positive": {"en": "Positive", "zh-cn": "正面"},
    "negative": {"en": "Negative", "zh-cn": "负面"},
    "neutral":  {"en": "Neutral",  "zh-cn": "中性"},
    "mixed":    {"en": "Mixed",    "zh-cn": "混合"},
}

DISCOURSE_LABELS: dict[str, dict[str, str]] = {
    "genuine_hype":             {"en": "Genuine Hype",              "zh-cn": "真实热度"},
    "sarcasm":                  {"en": "Sarcasm",                   "zh-cn": "讽刺"},
    "dunk_yingyang":            {"en": "Dunk / Yingyang",           "zh-cn": "阴阳怪气"},
    "self_deprecation":         {"en": "Self-Deprecation",          "zh-cn": "自嘲"},
    "cope":                     {"en": "Cope",                      "zh-cn": "自我安慰"},
    "fud":                      {"en": "FUD",                       "zh-cn": "恐惧不确定怀疑"},
    "distillation_accusation":  {"en": "Distillation Accusation",   "zh-cn": "蒸馏指控"},
    "ai_slop_critique":         {"en": "AI Slop Critique",          "zh-cn": "AI垃圾批评"},
    "absurdist_meme":           {"en": "Absurdist Meme",            "zh-cn": "荒诞梗"},
    "advertising-marketing":    {"en": "Advertising / Marketing",   "zh-cn": "广告营销"},
}

NATIONALISM_LABELS: dict[str, dict[str, str]] = {
    "none":                   {"en": "None",                    "zh-cn": "无"},
    "mild_pro":               {"en": "Mild Pro",                "zh-cn": "温和支持"},
    "pro":                    {"en": "Pro",                     "zh-cn": "支持"},
    "constructive_critical":  {"en": "Constructive Critical",   "zh-cn": "建设性批评"},
    "anti":                   {"en": "Anti",                    "zh-cn": "反对"},
    "mixed":                  {"en": "Mixed",                   "zh-cn": "混合"},
}

ROLE_LABELS: dict[str, dict[str, str]] = {
    "official":   {"en": "Official",   "zh-cn": "官方"},
    "staff":      {"en": "Staff",      "zh-cn": "员工"},
    "community":  {"en": "Community",  "zh-cn": "社区"},
}

# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = "Seed i18n label tables with the canonical taxonomy values."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Report what would be inserted without writing to the database.",
        )

    def handle(self, **options):
        dry_run: bool = options["dry_run"]

        seeds = self._collect_seeds()

        if dry_run:
            self._report_dry_run(seeds)
        else:
            self._apply(seeds)

    # -- seed collection ------------------------------------------------------

    def _collect_seeds(self) -> list[dict]:
        """Return a flat list of dicts describing rows to ensure."""
        seeds: list[dict] = []

        # Post types
        for key in _POST_TYPES:
            for lang in _LOCALES:
                label = POST_TYPE_LABELS.get(key, {}).get(lang, key)
                seeds.append({
                    "family": "post_type",
                    "key_model": PostTypeKey,
                    "label_model": PostTypeLabel,
                    "key": key,
                    "lang": lang,
                    "label": label,
                })

        # Sentiments
        for key in _SENTIMENTS:
            for lang in _LOCALES:
                label = SENTIMENT_LABELS.get(key, {}).get(lang, key)
                seeds.append({
                    "family": "sentiment",
                    "key_model": SentimentKey,
                    "label_model": SentimentLabel,
                    "key": key,
                    "lang": lang,
                    "label": label,
                })

        # Discourse
        for key in _DISCOURSE:
            for lang in _LOCALES:
                label = DISCOURSE_LABELS.get(key, {}).get(lang, key)
                seeds.append({
                    "family": "discourse",
                    "key_model": DiscourseKey,
                    "label_model": DiscourseLabel,
                    "key": key,
                    "lang": lang,
                    "label": label,
                })

        # Nationalism
        for key in _NATIONALISM:
            for lang in _LOCALES:
                label = NATIONALISM_LABELS.get(key, {}).get(lang, key)
                seeds.append({
                    "family": "nationalism",
                    "key_model": NationalismKey,
                    "label_model": NationalismLabel,
                    "key": key,
                    "lang": lang,
                    "label": label,
                })

        # Roles
        for key in _ROLES:
            for lang in _LOCALES:
                label = ROLE_LABELS.get(key, {}).get(lang, key)
                seeds.append({
                    "family": "role",
                    "key_model": Role,
                    "label_model": RoleLabel,
                    "key": key,
                    "lang": lang,
                    "label": label,
                })

        return seeds

    # -- apply ----------------------------------------------------------------

    def _apply(self, seeds: list[dict]) -> None:
        """Insert key rows and label rows that don't already exist."""
        key_inserted = 0
        label_inserted = 0

        for seed in seeds:
            key_model = seed["key_model"]
            label_model = seed["label_model"]
            family = seed["family"]
            key_val = seed["key"]
            lang = seed["lang"]
            label_text = seed["label"]

            # Ensure the key row exists.
            _obj, created = key_model.objects.get_or_create(key=key_val)
            if created:
                key_inserted += 1
                self.stdout.write(f"  + {family}_key: {key_val}")

            # Ensure the label row exists.
            # The label FK field names differ per family — map them:
            fk_kwargs = {family: _obj, "lang": lang}
            _label_obj, created = label_model.objects.get_or_create(
                defaults={"label": label_text}, **fk_kwargs
            )
            if created:
                label_inserted += 1
                self.stdout.write(
                    f"  + {family}_label: {key_val}/{lang} -> {label_text!r}"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {key_inserted} keys, {label_inserted} labels "
                f"({len(seeds)} total rows checked)."
            )
        )

    # -- dry-run --------------------------------------------------------------

    def _report_dry_run(self, seeds: list[dict]) -> None:
        self.stdout.write(
            self.style.WARNING("DRY RUN — no database writes will be performed.\n")
        )

        lines: list[str] = []
        for seed in seeds:
            lines.append(
                f"  {seed['family']:>14s}  {seed['key']:<30s}  "
                f"{seed['lang']:<6s}  {seed['label']!r}"
            )

        self.stdout.write("\n".join(lines))
        self.stdout.write(
            f"\n{len(seeds)} rows would be checked (keys + labels)."
        )
