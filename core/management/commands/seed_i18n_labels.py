"""Management command: seed the i18n label tables with known taxonomy values.

Usage:
  python manage.py seed_i18n_labels          # insert missing rows
  python manage.py seed_i18n_labels --dry-run  # preview only
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from core.classification_contract import (
    CANONICAL_POST_TYPE_KEYS,
    CANONICAL_PRODUCT_LABEL_KEYS,
    LEGACY_POST_TYPE_KEYS,
    LEGACY_PRODUCT_LABEL_KEYS,
    NATIONALISM_KEYS,
    SENTIMENT_KEYS,
)
from core.classification_labels import (
    AUDIENCE_TOPIC_LABELS,
    DISCOURSE_LABELS,
    GEOPOLITICAL_MODE_LABELS,
    NATIONALISM_LABELS,
    POST_TYPE_LABELS,
    PRODUCT_LABEL_LABELS,
    ROLE_LABELS,
    SENTIMENT_LABELS,
    UNTRACKED_BRAND_PROMOTION_LABELS,
)
from core.models import (
    AudienceTopicConcept,
    AudienceTopicLabel,
    AudienceTopicScheme,
    DiscourseKey,
    DiscourseLabel,
    GeopoliticalModeKey,
    GeopoliticalModeLabel,
    NationalismKey,
    NationalismLabel,
    NationalStanceKey,
    NationalStanceLabel,
    PostTypeKey,
    PostTypeLabel,
    ProductLabelKey,
    ProductLabelLabel,
    Role,
    RoleLabel,
    SentimentKey,
    SentimentLabel,
    UntrackedBrandPromotionKey,
    UntrackedBrandPromotionLabel,
)

# ---------------------------------------------------------------------------
# Canonical taxonomy values (mirrors x_monitor/attribution.py constants)
# ---------------------------------------------------------------------------

_V4_POST_TYPES = ("results_analysis", "news_reporting")
_V4_PRODUCT_LABELS = ("investigate_claim",)
_POST_TYPES = list(
    dict.fromkeys((*LEGACY_POST_TYPE_KEYS, *CANONICAL_POST_TYPE_KEYS, *_V4_POST_TYPES))
)
_PRODUCT_LABELS = list(
    dict.fromkeys(
        (*LEGACY_PRODUCT_LABEL_KEYS, *CANONICAL_PRODUCT_LABEL_KEYS, *_V4_PRODUCT_LABELS)
    )
)
_CANONICAL_POST_TYPES = frozenset((*CANONICAL_POST_TYPE_KEYS, *_V4_POST_TYPES))
_CANONICAL_PRODUCT_LABELS = frozenset(
    (*CANONICAL_PRODUCT_LABEL_KEYS, *_V4_PRODUCT_LABELS)
)
_SENTIMENTS = list(SENTIMENT_KEYS)

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

_NATIONALISM = list(NATIONALISM_KEYS)

_AUDIENCE_TOPIC_SCHEME_KEY = "ai_audience_topics/v1"
_AUDIENCE_TOPIC_MANIFEST_HASH = (
    "a31f753183b4287b050e7ed8740cba0153ac79ab7ea6ff634a22c28713007a7d"
)
_AUDIENCE_TOPICS = list(AUDIENCE_TOPIC_LABELS)
_GEOPOLITICAL_MODES = list(GEOPOLITICAL_MODE_LABELS)
_UNTRACKED_BRAND_PROMOTIONS = list(UNTRACKED_BRAND_PROMOTION_LABELS)

_ROLES: list[str] = [
    "official",
    "staff",
    "community",
]

_ACTIVE_LOCALES = ["en", "zh-cn", "ja"]
_LEGACY_LOCALES = ["en", "zh-cn"]

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
            locales = (
                _ACTIVE_LOCALES if key in _CANONICAL_POST_TYPES else _LEGACY_LOCALES
            )
            for lang in locales:
                label = POST_TYPE_LABELS.get(key, {}).get(lang, key)
                seeds.append(
                    {
                        "family": "post_type",
                        "key_model": PostTypeKey,
                        "label_model": PostTypeLabel,
                        "key": key,
                        "lang": lang,
                        "label": label,
                    }
                )

        # Sentiments
        for key in _SENTIMENTS:
            for lang in _ACTIVE_LOCALES:
                label = SENTIMENT_LABELS.get(key, {}).get(lang, key)
                seeds.append(
                    {
                        "family": "sentiment",
                        "key_model": SentimentKey,
                        "label_model": SentimentLabel,
                        "key": key,
                        "lang": lang,
                        "label": label,
                    }
                )

        # Product labels
        for key in _PRODUCT_LABELS:
            locales = (
                _ACTIVE_LOCALES
                if key in _CANONICAL_PRODUCT_LABELS
                else _LEGACY_LOCALES
            )
            for lang in locales:
                seeds.append(
                    {
                        "family": "product_label",
                        "key_model": ProductLabelKey,
                        "label_model": ProductLabelLabel,
                        "key": key,
                        "lang": lang,
                        "label": PRODUCT_LABEL_LABELS.get(key, {}).get(lang, key),
                    }
                )

        # Discourse
        for key in _DISCOURSE:
            for lang in _LEGACY_LOCALES:
                label = DISCOURSE_LABELS.get(key, {}).get(lang, key)
                seeds.append(
                    {
                        "family": "discourse",
                        "key_model": DiscourseKey,
                        "label_model": DiscourseLabel,
                        "key": key,
                        "lang": lang,
                        "label": label,
                    }
                )

        # Nationalism
        for key in _NATIONALISM:
            for lang in _ACTIVE_LOCALES:
                label = NATIONALISM_LABELS.get(key, {}).get(lang, key)
                seeds.append(
                    {
                        "family": "nationalism",
                        "key_model": NationalismKey,
                        "label_model": NationalismLabel,
                        "key": key,
                        "lang": lang,
                        "label": label,
                    }
                )

        # Roles
        for key in _ROLES:
            for lang in _LEGACY_LOCALES:
                label = ROLE_LABELS.get(key, {}).get(lang, key)
                seeds.append(
                    {
                        "family": "role",
                        "key_model": Role,
                        "label_model": RoleLabel,
                        "key": key,
                        "lang": lang,
                        "label": label,
                    }
                )

        # Audience Topics are a normalized scheme/concept catalog rather than
        # another enum family.  A label-only copy update creates a new label
        # revision while retaining the same concept identity.
        for key in _AUDIENCE_TOPICS:
            for lang in _ACTIVE_LOCALES:
                seeds.append(
                    {
                        "family": "audience_topic",
                        "key": key,
                        "lang": lang,
                        "label": AUDIENCE_TOPIC_LABELS[key][lang],
                    }
                )

        for family, key_model, label_model, labels in (
            (
                "geopolitical_mode",
                GeopoliticalModeKey,
                GeopoliticalModeLabel,
                GEOPOLITICAL_MODE_LABELS,
            ),
            (
                "national_stance",
                NationalStanceKey,
                NationalStanceLabel,
                NATIONALISM_LABELS,
            ),
            (
                "untracked_brand_promotion",
                UntrackedBrandPromotionKey,
                UntrackedBrandPromotionLabel,
                UNTRACKED_BRAND_PROMOTION_LABELS,
            ),
        ):
            for key, localized in labels.items():
                for lang in _ACTIVE_LOCALES:
                    seeds.append(
                        {
                            "family": family,
                            "key_model": key_model,
                            "label_model": label_model,
                            "key": key,
                            "lang": lang,
                            "label": localized[lang],
                        }
                    )

        return seeds

    # -- apply ----------------------------------------------------------------

    def _apply(self, seeds: list[dict]) -> None:
        """Insert key rows and label rows that don't already exist."""
        key_inserted = 0
        label_inserted = 0

        for seed in seeds:
            if seed["family"] == "audience_topic":
                scheme, scheme_created = AudienceTopicScheme.objects.get_or_create(
                    key=_AUDIENCE_TOPIC_SCHEME_KEY,
                    defaults={
                        "revision": 1,
                        "manifest_hash": _AUDIENCE_TOPIC_MANIFEST_HASH,
                    },
                )
                if scheme_created:
                    key_inserted += 1
                    self.stdout.write(
                        f"  + audience_topic_scheme: {_AUDIENCE_TOPIC_SCHEME_KEY}"
                    )
                concept, created = AudienceTopicConcept.objects.get_or_create(
                    scheme=scheme,
                    key=seed["key"],
                )
                if created:
                    key_inserted += 1
                    self.stdout.write(f"  + audience_topic_concept: {seed['key']}")
                _label, created = AudienceTopicLabel.objects.get_or_create(
                    concept=concept,
                    revision=scheme.revision,
                    lang=seed["lang"],
                    defaults={"label": seed["label"]},
                )
                if created:
                    label_inserted += 1
                    self.stdout.write(
                        "  + audience_topic_label: "
                        f"{seed['key']}/{seed['lang']} -> {seed['label']!r}"
                    )
                continue

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
        self.stdout.write(f"\n{len(seeds)} rows would be checked (keys + labels).")
