"""Django models for x-monitor v2.

This is the single source of truth for the DB schema. Migrations are
auto-generated from these via `python manage.py makemigrations core`.

Mirrors the live SQLite schema at x-monitoring/data/x_monitoring.db
(v39, 31 tables), migrated to Django ORM with pushin_weight conventions.

Conventions:
- Entity and lookup tables use their natural key as the PK
  (TEXT for slugs, handles, tweet_ids, keys). No synthetic id.
- Junction and i18n-label tables use CompositePrimaryKey (import from
  `django.db.models`). No surrogate id column.
- Only control-plane tables (products, search_queries) keep
  BigAutoField synthetic id.
- All timestamps are DateTimeField (TIMESTAMPTZ with USE_TZ=True).
- Natural keys (slugs, handles, namespaces) use VARCHAR(64) with
  db_collation="case_insensitive" for case-insensitive equality.
- Enum families (post_type, sentiment, discourse, nationalism, role)
  are lookup tables, not PG ENUMs — separate *_keys and *_labels
  tables.
- For FK columns that reference a natural-key PK, use to_field and
  db_column to match the existing SQLite column names.
- Use class Meta: db_table = "..." to match existing table names
  exactly.
- No soft-delete columns.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlparse

from django.db import IntegrityError, models, transaction
from django.utils import timezone

# ============================================================================
# Enum-family lookup tables (i18n-friendly)
# ============================================================================


class PostTypeKey(models.Model):
    """Lookup table for post_type vocabulary (release, update, review, etc.)."""

    key = models.CharField(
        max_length=64,
        primary_key=True,
        db_collation="case_insensitive",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "post_type_keys"
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key


class PostTypeLabel(models.Model):
    pk = models.CompositePrimaryKey("post_type", "lang")
    post_type = models.ForeignKey(
        PostTypeKey,
        on_delete=models.CASCADE,
        related_name="labels",
        db_column="key",
        to_field="key",
    )
    lang = models.TextField()
    label = models.TextField()

    class Meta:
        db_table = "post_type_labels"


class ProductLabelKey(models.Model):
    """Lookup vocabulary for independent product-feedback labels."""

    key = models.CharField(
        max_length=64,
        primary_key=True,
        db_collation="case_insensitive",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "product_label_keys"
        ordering = ["key"]


class ProductLabelLabel(models.Model):
    pk = models.CompositePrimaryKey("product_label", "lang")
    product_label = models.ForeignKey(
        ProductLabelKey,
        on_delete=models.CASCADE,
        related_name="labels",
        db_column="key",
        to_field="key",
    )
    lang = models.TextField()
    label = models.TextField()

    class Meta:
        db_table = "product_label_labels"


class SentimentKey(models.Model):
    """Lookup table for sentiment vocabulary (positive, negative, mixed, neutral)."""

    key = models.CharField(
        max_length=64,
        primary_key=True,
        db_collation="case_insensitive",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sentiment_keys"
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key


class SentimentLabel(models.Model):
    pk = models.CompositePrimaryKey("sentiment", "lang")
    sentiment = models.ForeignKey(
        SentimentKey,
        on_delete=models.CASCADE,
        related_name="labels",
        db_column="key",
        to_field="key",
    )
    lang = models.TextField()
    label = models.TextField()

    class Meta:
        db_table = "sentiment_labels"


class DiscourseKey(models.Model):
    """9-way pragmatic-register vocabulary (genuine_hype, sarcasm, dunk, etc.)."""

    key = models.CharField(
        max_length=64,
        primary_key=True,
        db_collation="case_insensitive",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "discourse_keys"
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key


class DiscourseLabel(models.Model):
    pk = models.CompositePrimaryKey("discourse", "lang")
    discourse = models.ForeignKey(
        DiscourseKey,
        on_delete=models.CASCADE,
        related_name="labels",
        db_column="key",
        to_field="key",
    )
    lang = models.TextField()
    label = models.TextField()

    class Meta:
        db_table = "discourse_labels"


class NationalismKey(models.Model):
    """6-step nationalism scale shared across both axes (china / us).

    Keys: none, mild_pro, pro, constructive_critical, anti, mixed.
    """

    key = models.CharField(
        max_length=64,
        primary_key=True,
        db_collation="case_insensitive",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nationalism_keys"
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key


class NationalismLabel(models.Model):
    pk = models.CompositePrimaryKey("nationalism", "lang")
    nationalism = models.ForeignKey(
        NationalismKey,
        on_delete=models.CASCADE,
        related_name="labels",
        db_column="key",
        to_field="key",
    )
    lang = models.TextField()
    label = models.TextField()

    class Meta:
        db_table = "nationalism_labels"


class Role(models.Model):
    """Roles vocabulary (official, researcher, executive, investor, etc.)."""

    key = models.CharField(
        max_length=64,
        primary_key=True,
        db_collation="case_insensitive",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "roles"
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key


class RoleLabel(models.Model):
    pk = models.CompositePrimaryKey("role", "lang")
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="labels",
        db_column="key",
        to_field="key",
    )
    lang = models.TextField()
    label = models.TextField()

    class Meta:
        db_table = "role_labels"


class UnsanctionedFlagKey(models.Model):
    """Lookup table for unsanctioned flag vocabulary. No label table."""

    key = models.CharField(
        max_length=64,
        primary_key=True,
        db_collation="case_insensitive",
    )

    class Meta:
        db_table = "unsanctioned_flag_keys"
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key


# ============================================================================
# Brands
# ============================================================================


class Brand(models.Model):
    nickname = models.CharField(
        max_length=64,
        primary_key=True,
        db_collation="case_insensitive",
    )
    display_name = models.TextField(blank=True, null=True)
    accent_color = models.TextField(blank=True, null=True)
    is_sentinel = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    display_name_en = models.TextField(blank=True, null=True)
    display_name_zh_cn = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "brands"
        ordering = ["nickname"]

    def __str__(self) -> str:
        return self.nickname


# ============================================================================
# Companies
# ============================================================================


class Company(models.Model):
    nickname = models.CharField(
        max_length=64,
        primary_key=True,
        db_collation="case_insensitive",
    )
    display_name = models.TextField(blank=True, null=True)
    hq_country = models.TextField(blank=True, null=True)
    accent_color = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    display_name_en = models.TextField(blank=True, null=True)
    display_name_zh_cn = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "companies"
        ordering = ["nickname"]

    def __str__(self) -> str:
        return self.nickname


# ============================================================================
# HF orgs
# ============================================================================


class HFOrg(models.Model):
    namespace = models.CharField(
        max_length=64,
        primary_key=True,
        db_collation="case_insensitive",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="hf_orgs",
        db_column="company_id",
        to_field="nickname",
    )
    confirmed = models.BooleanField(default=False)
    discovered_via = models.TextField(default="curated")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "hf_orgs"
        ordering = ["namespace"]
        indexes = [
            models.Index(fields=["company"], name="idx_hf_orgs_company"),
        ]

    def __str__(self) -> str:
        return self.namespace


# ============================================================================
# Accounts
# ============================================================================


@dataclass(frozen=True)
class AccountObservationOutcome:
    account: Account | None
    created: bool
    applied_fields: tuple[str, ...]
    unchanged_fields: tuple[str, ...]
    rejected_fields: dict[str, str]
    identity_rejected: bool = False


_ACCOUNT_COUNT_FIELDS = {
    "followers_count",
    "following_count",
    "favourites_count",
    "statuses_count",
    "media_count",
    "fast_followers_count",
    "username_changes_count",
}
_ACCOUNT_BIGINT_FIELDS = {
    "username_changes_last_changed_at_msec",
    "verification_info_reason_verified_since_msec",
}
_ACCOUNT_YEAR_FIELDS = {
    "verification_info_reason_override_verified_year",
}
_ACCOUNT_BOOLEAN_FIELDS = {
    "verified",
    "is_blue_verified",
    "protected",
    "location_accurate",
    "created_country_accurate",
    "verification_info_is_identity_verified",
    "unavailable",
}
_ACCOUNT_URL_FIELDS = {
    "affiliate_label_badge_url",
    "affiliate_label_url",
    "learn_more_url",
    "identity_profile_label_badge_url",
    "identity_profile_label_url",
}
_ACCOUNT_SHORT_TEXT_FIELDS = {
    "handle": 64,
    "affiliate_label_url_type": 128,
    "affiliate_label_user_label_display_type": 128,
    "affiliate_label_user_label_type": 128,
    "affiliate_username": 64,
    "source": 128,
    "identity_profile_label_url_type": 128,
    "identity_profile_label_user_label_display_type": 128,
    "identity_profile_label_user_label_type": 128,
    "verification_info_id": 128,
    "country_code": 2,
    "based_in_region_key": 64,
}
_ACCOUNT_TEXT_FIELDS = {
    "display_name",
    "affiliate_label_description",
    "account_based_in",
    "identity_profile_label_description",
    "identity_profile_label_long_description",
    "verified_type",
    "profile_picture",
    "location",
    "description",
    "profile_bio_text",
    "unavailable_reason",
}
_AFFILIATE_LABEL_FIELDS = {
    "affiliate_label_badge_url",
    "affiliate_label_description",
    "affiliate_label_url",
    "affiliate_label_url_type",
    "affiliate_label_user_label_display_type",
    "affiliate_label_user_label_type",
}
_IDENTITY_LABEL_FIELDS = {
    "identity_profile_label_badge_url",
    "identity_profile_label_description",
    "identity_profile_label_long_description",
    "identity_profile_label_url",
    "identity_profile_label_url_type",
    "identity_profile_label_user_label_display_type",
    "identity_profile_label_user_label_type",
}
_GEOGRAPHY_FIELDS = {"country_code", "based_in_region_key"}
_ACCOUNT_STORAGE_ATTRIBUTES = {
    "country_code": "country_id",
    "based_in_region_key": "based_in_region_id",
}
_ACCOUNT_MODEL_FIELDS = {
    "country_code": "country",
    "based_in_region_key": "based_in_region",
}
_ABOUT_ONLY_FIELDS = {
    "account_based_in",
    "location_accurate",
    "created_country_accurate",
    "learn_more_url",
    "affiliate_username",
    "source",
    "username_changes_count",
    "username_changes_last_changed_at_msec",
    "verification_info_id",
    "verification_info_is_identity_verified",
    "verification_info_reason_override_verified_year",
    "verification_info_reason_verified_since_msec",
    "unavailable",
    "unavailable_reason",
    "country_code",
    "based_in_region_key",
    "account_based_in_fetched_at",
    *_IDENTITY_LABEL_FIELDS,
}
_POST_FIELDS = {
    "handle",
    "display_name",
    "created_at",
    "verified",
    "followers_count",
    "following_count",
    "favourites_count",
    "statuses_count",
    "media_count",
    "fast_followers_count",
    "is_blue_verified",
    "protected",
    "verified_type",
    "profile_picture",
    "location",
    "description",
    "profile_bio_text",
    *_AFFILIATE_LABEL_FIELDS,
}
_WRITER_FIELDS = {
    "post": _POST_FIELDS,
    "list": {"handle", "display_name"},
    "seed": {"handle", "display_name"},
    "user_about": {
        "handle",
        "display_name",
        "created_at",
        "verified",
        "is_blue_verified",
        "protected",
        "profile_picture",
        *_AFFILIATE_LABEL_FIELDS,
        *_ABOUT_ONLY_FIELDS,
    },
}


def _contains_control(value: str, *, allow_layout: bool = False) -> bool:
    allowed = {"\t", "\n", "\r"} if allow_layout else set()
    return any(
        (ord(character) < 32 and character not in allowed)
        or ord(character) == 127
        for character in value
    )


def _validate_account_field(
    field_name: str,
    value: Any,
    *,
    observed_at: datetime,
) -> tuple[Any, str | None]:
    if value is None:
        return None, None
    if field_name in _ACCOUNT_COUNT_FIELDS:
        if type(value) is not int or value < 0 or value > 2_147_483_647:
            return None, "invalid_nonnegative_integer"
        return value, None
    if field_name in _ACCOUNT_BIGINT_FIELDS:
        if type(value) is not int or value < 0 or value > 9_223_372_036_854_775_807:
            return None, "invalid_nonnegative_bigint"
        return value, None
    if field_name in _ACCOUNT_YEAR_FIELDS:
        if (
            type(value) is not int
            or value < 2006
            or value > observed_at.year + 1
        ):
            return None, "invalid_year"
        return value, None
    if field_name in _ACCOUNT_BOOLEAN_FIELDS:
        if type(value) is not bool:
            return None, "invalid_boolean"
        return value, None
    if field_name in _ACCOUNT_URL_FIELDS:
        if not isinstance(value, str) or len(value) > 2_048 or _contains_control(value):
            return None, "invalid_url"
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None, "invalid_url"
        return value, None
    if field_name == "created_at":
        if not isinstance(value, datetime) or timezone.is_naive(value):
            return None, "invalid_datetime"
        if value < datetime(2006, 3, 21, tzinfo=value.tzinfo):
            return None, "invalid_datetime"
        if value > observed_at + timedelta(days=1):
            return None, "invalid_datetime"
        return value, None
    if field_name == "account_based_in_fetched_at":
        if not isinstance(value, datetime) or timezone.is_naive(value):
            return None, "invalid_datetime"
        if value > observed_at + timedelta(minutes=5):
            return None, "invalid_datetime"
        return value, None
    if field_name in _ACCOUNT_SHORT_TEXT_FIELDS:
        if not isinstance(value, str):
            return None, "invalid_string"
        if not value or value != value.strip() or _contains_control(value):
            return None, "invalid_string"
        if len(value) > _ACCOUNT_SHORT_TEXT_FIELDS[field_name]:
            return None, "too_long"
        if field_name == "handle" and (
            value.startswith("@")
            or any(character.isspace() for character in value)
        ):
            return None, "invalid_handle"
        if field_name == "country_code":
            from monitor.account_geography import COUNTRY_NAMES

            if value not in COUNTRY_NAMES:
                return None, "unsupported_country_code"
        if field_name == "based_in_region_key":
            from monitor.account_geography import REGION_NAMES

            if value not in REGION_NAMES:
                return None, "unsupported_region_key"
        return value, None
    if field_name in _ACCOUNT_TEXT_FIELDS:
        if not isinstance(value, str) or _contains_control(value, allow_layout=True):
            return None, "invalid_string"
        if value != value.strip():
            return None, "invalid_string"
        return value, None
    return None, "unsupported_field"


_COUNTRY_DISPLAY_PARENT_RELATIONSHIPS = (
    ("special_administrative_region", "Special administrative region"),
    ("owner_display_context", "Owner-selected display context"),
    ("us_insular_area", "US insular area"),
    ("french_overseas", "French overseas arrangement"),
    ("british_overseas_territory", "British Overseas Territory"),
    ("crown_dependency", "Crown Dependency"),
    ("kingdom_constituent_country", "Kingdom constituent country"),
    ("netherlands_public_body", "Netherlands public body"),
)


class Region(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    m49_code = models.CharField(max_length=3, unique=True, blank=True, null=True)
    source = models.CharField(max_length=64)
    level = models.CharField(max_length=32)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="children",
        blank=True,
        null=True,
    )

    class Meta:
        db_table = "regions"
        ordering = ["key"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(parent__isnull=True)
                    | ~models.Q(parent=models.F("key"))
                ),
                name="ck_regions_not_self_parent",
            )
        ]

    def __str__(self) -> str:
        return self.key


class RegionLabel(models.Model):
    pk = models.CompositePrimaryKey("region", "lang")
    region = models.ForeignKey(
        Region,
        on_delete=models.CASCADE,
        related_name="labels",
        db_column="region_key",
        to_field="key",
    )
    lang = models.CharField(max_length=16)
    label = models.TextField()

    class Meta:
        db_table = "region_labels"


class Country(models.Model):
    DISPLAY_PARENT_RELATIONSHIPS = _COUNTRY_DISPLAY_PARENT_RELATIONSHIPS

    code = models.CharField(max_length=2, primary_key=True)
    m49_code = models.CharField(max_length=3, unique=True)
    display_parent_country = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="display_children",
        blank=True,
        null=True,
    )
    display_parent_relationship_type = models.CharField(
        max_length=64,
        choices=DISPLAY_PARENT_RELATIONSHIPS,
        blank=True,
        null=True,
    )

    class Meta:
        db_table = "countries"
        ordering = ["code"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(display_parent_country__isnull=True)
                        & models.Q(display_parent_relationship_type__isnull=True)
                    )
                    | (
                        models.Q(display_parent_country__isnull=False)
                        & models.Q(display_parent_relationship_type__isnull=False)
                    )
                ),
                name="ck_countries_display_parent_complete",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(display_parent_country__isnull=True)
                    | ~models.Q(display_parent_country=models.F("code"))
                ),
                name="ck_countries_not_self_parent",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(display_parent_relationship_type__isnull=True)
                    | models.Q(
                        display_parent_relationship_type__in=tuple(
                            key for key, _label in _COUNTRY_DISPLAY_PARENT_RELATIONSHIPS
                        )
                    )
                ),
                name="ck_countries_parent_relationship_type",
            ),
        ]

    def __str__(self) -> str:
        return self.code


class CountryLabel(models.Model):
    pk = models.CompositePrimaryKey("country", "lang")
    country = models.ForeignKey(
        Country,
        on_delete=models.CASCADE,
        related_name="labels",
        db_column="country_code",
        to_field="code",
    )
    lang = models.CharField(max_length=16)
    label = models.TextField()

    class Meta:
        db_table = "country_labels"


class CountryRegion(models.Model):
    country = models.OneToOneField(
        Country,
        on_delete=models.CASCADE,
        related_name="region_mapping",
        db_column="country_code",
        to_field="code",
        primary_key=True,
    )
    region = models.ForeignKey(
        Region,
        on_delete=models.PROTECT,
        related_name="country_mappings",
        db_column="region_key",
        to_field="key",
    )
    source = models.CharField(max_length=64)

    class Meta:
        db_table = "country_codes_region"


class AccountBasedInMapping(models.Model):
    value = models.TextField(primary_key=True)
    country = models.ForeignKey(
        Country,
        on_delete=models.CASCADE,
        related_name="provider_mappings",
        db_column="country_code",
        to_field="code",
        blank=True,
        null=True,
    )
    region = models.ForeignKey(
        Region,
        on_delete=models.CASCADE,
        related_name="provider_mappings",
        db_column="region_key",
        to_field="key",
        blank=True,
        null=True,
    )
    review_note = models.TextField()

    class Meta:
        db_table = "account_based_in_mappings"
        constraints = [
            models.CheckConstraint(
                condition=(
                    (models.Q(country__isnull=False) & models.Q(region__isnull=True))
                    | (models.Q(country__isnull=True) & models.Q(region__isnull=False))
                ),
                name="ck_account_based_in_mapping_one_target",
            )
        ]


class Account(models.Model):
    author_id = models.TextField(primary_key=True)
    handle = models.CharField(
        max_length=64,
        db_collation="case_insensitive",
        blank=True,
        null=True,
    )
    display_name = models.TextField(blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    bio_fetched_at = models.DateTimeField(blank=True, null=True)
    verified = models.BooleanField(default=False)
    bio_contains_brand = models.BooleanField(blank=True, null=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    source_query_ids = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    bio_en = models.TextField(blank=True, null=True)
    bio_zh_cn = models.TextField(blank=True, null=True)
    # Migration 039 — inline author metadata from tweet payloads
    followers_count = models.IntegerField(blank=True, null=True)
    following_count = models.IntegerField(blank=True, null=True)
    favourites_count = models.IntegerField(blank=True, null=True)
    statuses_count = models.IntegerField(blank=True, null=True)
    media_count = models.IntegerField(blank=True, null=True)
    fast_followers_count = models.IntegerField(blank=True, null=True)
    is_blue_verified = models.BooleanField(blank=True, null=True)
    verified_type = models.TextField(blank=True, null=True)
    profile_picture = models.TextField(blank=True, null=True)
    location = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    profile_bio_text = models.TextField(blank=True, null=True)
    followers_fetched_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    protected = models.BooleanField(blank=True, null=True)
    affiliate_label_badge_url = models.URLField(max_length=2048, blank=True, null=True)
    affiliate_label_description = models.TextField(blank=True, null=True)
    affiliate_label_url = models.URLField(max_length=2048, blank=True, null=True)
    affiliate_label_url_type = models.CharField(max_length=128, blank=True, null=True)
    affiliate_label_user_label_display_type = models.CharField(
        max_length=128, blank=True, null=True
    )
    affiliate_label_user_label_type = models.CharField(
        max_length=128, blank=True, null=True
    )
    account_based_in = models.TextField(blank=True, null=True)
    location_accurate = models.BooleanField(blank=True, null=True)
    learn_more_url = models.URLField(max_length=2048, blank=True, null=True)
    affiliate_username = models.CharField(max_length=64, blank=True, null=True)
    source = models.CharField(max_length=128, blank=True, null=True)
    username_changes_count = models.PositiveIntegerField(blank=True, null=True)
    username_changes_last_changed_at_msec = models.PositiveBigIntegerField(
        blank=True, null=True
    )
    created_country_accurate = models.BooleanField(blank=True, null=True)
    verification_info_id = models.CharField(
        max_length=128, blank=True, null=True
    )
    verification_info_is_identity_verified = models.BooleanField(
        blank=True, null=True
    )
    verification_info_reason_verified_since_msec = models.PositiveBigIntegerField(
        blank=True, null=True
    )
    verification_info_reason_override_verified_year = models.PositiveSmallIntegerField(
        blank=True, null=True
    )
    unavailable = models.BooleanField(blank=True, null=True)
    unavailable_reason = models.TextField(blank=True, null=True)
    identity_profile_label_badge_url = models.URLField(
        max_length=2048, blank=True, null=True
    )
    identity_profile_label_description = models.TextField(blank=True, null=True)
    identity_profile_label_long_description = models.TextField(blank=True, null=True)
    identity_profile_label_url = models.URLField(
        max_length=2048, blank=True, null=True
    )
    identity_profile_label_url_type = models.CharField(
        max_length=128, blank=True, null=True
    )
    identity_profile_label_user_label_display_type = models.CharField(
        max_length=128, blank=True, null=True
    )
    identity_profile_label_user_label_type = models.CharField(
        max_length=128, blank=True, null=True
    )
    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name="accounts",
        db_column="country_code",
        to_field="code",
        blank=True,
        null=True,
    )
    based_in_region = models.ForeignKey(
        Region,
        on_delete=models.PROTECT,
        related_name="accounts",
        db_column="based_in_region_key",
        to_field="key",
        blank=True,
        null=True,
    )
    account_based_in_fetched_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "accounts"
        indexes = [
            models.Index(fields=["handle"], name="idx_accounts_handle"),
            models.Index(fields=["last_seen_at"], name="idx_accounts_last_seen_at"),
        ]
        ordering = ["handle"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(country__isnull=True)
                    | models.Q(based_in_region__isnull=True)
                ),
                name="ck_accounts_one_geography_target",
            )
        ]

    def __str__(self) -> str:
        return f"@{self.handle}"

    @property
    def country_code(self) -> str | None:
        """Expose the raw alpha-2 value at observation and wire boundaries."""
        return self.country_id

    @country_code.setter
    def country_code(self, value: str | None) -> None:
        self.country_id = value

    @property
    def based_in_region_key(self) -> str | None:
        return self.based_in_region_id

    @based_in_region_key.setter
    def based_in_region_key(self, value: str | None) -> None:
        self.based_in_region_id = value

    @classmethod
    def apply_observation(
        cls,
        *,
        author_id: str,
        observed_author_id: str,
        source: Literal["post", "list", "seed", "user_about"],
        observed_at: datetime,
        candidates: dict[str, Any],
        present_fields: set[str],
        expected_handle: str | None = None,
    ) -> AccountObservationOutcome:
        """Apply the valid subset of one explicitly-present Account snapshot."""
        target_id = str(author_id).strip()
        observed_id = str(observed_author_id).strip()
        if not target_id or target_id != observed_id:
            return AccountObservationOutcome(
                account=None,
                created=False,
                applied_fields=(),
                unchanged_fields=(),
                rejected_fields={"author_id": "identity_mismatch"},
                identity_rejected=True,
            )
        if source not in _WRITER_FIELDS:
            raise ValueError(f"unsupported Account observation source: {source}")
        if not isinstance(observed_at, datetime) or timezone.is_naive(observed_at):
            raise ValueError("observed_at must be a timezone-aware datetime")

        rejected: dict[str, str] = {}
        applied: list[str] = []
        unchanged: list[str] = []
        allowed = _WRITER_FIELDS[source]
        supplied = set(present_fields)
        for field_name in supplied:
            if field_name not in candidates:
                rejected[field_name] = "missing_candidate"
            elif field_name not in allowed:
                rejected[field_name] = "writer_not_allowed"

        if expected_handle is not None and source != "user_about":
            raise ValueError("expected_handle is supported only for User About")
        if expected_handle is not None and (
            not isinstance(expected_handle, str)
            or not expected_handle
            or expected_handle != expected_handle.strip()
        ):
            raise ValueError("expected_handle must be a nonblank trimmed string")

        with transaction.atomic():
            if expected_handle is None:
                account, created = cls.objects.select_for_update().get_or_create(
                    author_id=target_id
                )
            else:
                account = (
                    cls.objects.select_for_update()
                    .filter(author_id=target_id)
                    .first()
                )
                if (
                    account is None
                    or not account.handle
                    or account.handle.casefold() != expected_handle.casefold()
                ):
                    return AccountObservationOutcome(
                        account=None,
                        created=False,
                        applied_fields=(),
                        unchanged_fields=(),
                        rejected_fields={"handle": "identity_mismatch"},
                        identity_rejected=True,
                    )
                created = False

            accepted: dict[str, Any] = {}
            for group in (_AFFILIATE_LABEL_FIELDS, _IDENTITY_LABEL_FIELDS):
                group_present = supplied & group
                if not group_present:
                    continue
                if not group <= allowed:
                    for field_name in group_present:
                        rejected[field_name] = "writer_not_allowed"
                    continue
                if group_present != group:
                    for field_name in group_present:
                        rejected[field_name] = "incomplete_label_group"
                    continue
                if any(field_name in rejected for field_name in group):
                    for field_name in group:
                        rejected.setdefault(field_name, "missing_candidate")
                    continue
                group_values: dict[str, Any] = {}
                group_errors: dict[str, str] = {}
                for field_name in group:
                    validated, error = _validate_account_field(
                        field_name,
                        candidates[field_name],
                        observed_at=observed_at,
                    )
                    if error:
                        group_errors[field_name] = error
                    else:
                        group_values[field_name] = validated
                if group_errors:
                    reason = next(iter(group_errors.values()))
                    for field_name in group:
                        rejected[field_name] = reason
                else:
                    accepted.update(group_values)

            geography_present = supplied & _GEOGRAPHY_FIELDS
            if geography_present:
                if geography_present != _GEOGRAPHY_FIELDS:
                    for field_name in geography_present:
                        rejected[field_name] = "incomplete_geography_target"
                elif any(field_name in rejected for field_name in _GEOGRAPHY_FIELDS):
                    for field_name in _GEOGRAPHY_FIELDS:
                        rejected.setdefault(field_name, "missing_candidate")
                else:
                    geography_values: dict[str, Any] = {}
                    geography_errors: dict[str, str] = {}
                    for field_name in _GEOGRAPHY_FIELDS:
                        validated, error = _validate_account_field(
                            field_name,
                            candidates[field_name],
                            observed_at=observed_at,
                        )
                        if error:
                            geography_errors[field_name] = error
                        else:
                            geography_values[field_name] = validated
                    if all(geography_values.values()):
                        geography_errors = {
                            field_name: "multiple_geography_targets"
                            for field_name in _GEOGRAPHY_FIELDS
                        }
                    if geography_errors:
                        reason = next(iter(geography_errors.values()))
                        for field_name in _GEOGRAPHY_FIELDS:
                            rejected[field_name] = reason
                    else:
                        accepted.update(geography_values)

            grouped = (
                _AFFILIATE_LABEL_FIELDS
                | _IDENTITY_LABEL_FIELDS
                | _GEOGRAPHY_FIELDS
            )
            for field_name in supplied - grouped:
                if field_name in rejected:
                    continue
                validated, error = _validate_account_field(
                    field_name,
                    candidates[field_name],
                    observed_at=observed_at,
                )
                if error:
                    rejected[field_name] = error
                    continue
                if validated is None:
                    unchanged.append(field_name)
                    continue
                if field_name == "created_at" and account.created_at is not None:
                    if account.created_at == validated:
                        unchanged.append(field_name)
                    else:
                        rejected[field_name] = "conflict"
                    continue
                if (
                    field_name == "handle"
                    and account.handle != validated
                    and cls.objects.filter(handle__iexact=validated)
                    .exclude(author_id=target_id)
                    .exists()
                ):
                    rejected[field_name] = "conflict"
                    continue
                accepted[field_name] = validated

            update_fields: set[str] = set()
            for field_name, value in accepted.items():
                storage_attribute = _ACCOUNT_STORAGE_ATTRIBUTES.get(
                    field_name, field_name
                )
                model_field = _ACCOUNT_MODEL_FIELDS.get(field_name, field_name)
                if getattr(account, storage_attribute) == value:
                    unchanged.append(field_name)
                else:
                    setattr(account, storage_attribute, value)
                    applied.append(field_name)
                    update_fields.add(model_field)

            if (
                source == "post"
                and "followers_count" in supplied
                and "followers_count" not in rejected
                and candidates.get("followers_count") is not None
                and account.followers_fetched_at != observed_at
            ):
                account.followers_fetched_at = observed_at
                applied.append("followers_fetched_at")
                update_fields.add("followers_fetched_at")

            if update_fields:
                try:
                    with transaction.atomic():
                        account.save(
                            update_fields=[*sorted(update_fields), "last_seen_at"]
                        )
                except IntegrityError:
                    if "handle" not in update_fields:
                        raise
                    rejected["handle"] = "conflict"
                    applied = [field for field in applied if field != "handle"]
                    update_fields.remove("handle")
                    account.refresh_from_db()
                    for field_name, value in accepted.items():
                        model_field = _ACCOUNT_MODEL_FIELDS.get(
                            field_name, field_name
                        )
                        if model_field not in update_fields:
                            continue
                        setattr(
                            account,
                            _ACCOUNT_STORAGE_ATTRIBUTES.get(field_name, field_name),
                            value,
                        )
                    if "followers_fetched_at" in update_fields:
                        account.followers_fetched_at = observed_at
                    if update_fields:
                        account.save(
                            update_fields=[*sorted(update_fields), "last_seen_at"]
                        )

        return AccountObservationOutcome(
            account=account,
            created=created,
            applied_fields=tuple(sorted(set(applied))),
            unchanged_fields=tuple(sorted(set(unchanged))),
            rejected_fields=rejected,
        )


class TwitterListMembership(models.Model):
    """Durable membership snapshot keyed by Twitter list and account."""

    list_id = models.BigIntegerField()
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="twitter_list_memberships",
        db_column="author_id",
        to_field="author_id",
    )
    active = models.BooleanField(default=True)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    last_complete_reconciliation_at = models.DateTimeField(blank=True, null=True)
    source = models.CharField(max_length=32)
    source_run_id = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        db_table = "twitter_list_memberships"
        constraints = [
            models.UniqueConstraint(
                fields=["list_id", "account"],
                name="uq_twitter_list_membership",
            ),
            models.CheckConstraint(
                condition=models.Q(last_seen_at__gte=models.F("first_seen_at")),
                name="ck_tlm_seen_order",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(last_complete_reconciliation_at__isnull=True)
                    | models.Q(
                        last_complete_reconciliation_at__gte=models.F(
                            "first_seen_at"
                        )
                    )
                ),
                name="ck_tlm_reconciled_order",
            ),
        ]
        indexes = [
            models.Index(
                fields=["list_id", "active"], name="idx_tlm_list_active"
            ),
        ]


class TwitterListSyncState(models.Model):
    """Completion marker kept separately so even empty lists are rate-limited."""

    list_id = models.BigIntegerField(primary_key=True)
    snapshot_id = models.CharField(max_length=128)
    last_complete_at = models.DateTimeField()

    class Meta:
        db_table = "twitter_list_sync_state"


# ============================================================================
# Posts
# ============================================================================


class Post(models.Model):
    tweet_id = models.TextField(primary_key=True)
    author_handle = models.CharField(
        max_length=64,
        db_collation="case_insensitive",
        blank=True,
        null=True,
    )
    author = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="posts",
        db_column="author_id",
        to_field="author_id",
    )
    text = models.TextField(blank=True, null=True)
    lang = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    fetched_at = models.DateTimeField(auto_now_add=True)
    like_count = models.IntegerField(blank=True, null=True)
    retweet_count = models.IntegerField(blank=True, null=True)
    reply_count = models.IntegerField(blank=True, null=True)
    quote_count = models.IntegerField(blank=True, null=True)
    in_reply_to_user_id = models.TextField(blank=True, null=True)
    # Self-referential FK to the inner quoted/retweeted tweet (Policy A:
    # NULL if the parent tweet was never harvested).
    quoted_status_id = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="quoted_by",
        db_column="quoted_status_id",
        db_constraint=True,
    )
    conversation_id = models.TextField(blank=True, null=True)
    entities = models.JSONField(blank=True, null=True)
    source_query_id = models.TextField(blank=True, null=True)
    headline = models.TextField(blank=True, null=True)
    headline_source = models.TextField(blank=True, null=True)
    text_en = models.TextField(blank=True, null=True)
    text_zh_cn = models.TextField(blank=True, null=True)
    commentary_en = models.TextField(blank=True, null=True)
    commentary_zh_cn = models.TextField(blank=True, null=True)
    lang_detected = models.TextField(blank=True, null=True)
    quoted_text = models.TextField(blank=True, null=True)
    last_quote_count_seen = models.IntegerField(blank=True, null=True)
    last_quote_fetched_at = models.DateTimeField(blank=True, null=True)
    # One-shot metrics re-fetch stamp (plan 2026-08-10-002).
    metrics_refreshed_at = models.DateTimeField(blank=True, null=True)
    created_at_epoch = models.BigIntegerField(blank=True, null=True)

    # --- § 1.2 TwitterAPI top-level tweet fields ---
    created_at_raw = models.TextField(blank=True, null=True)
    bookmark_count = models.IntegerField(blank=True, null=True)
    is_reply = models.BooleanField(blank=True, null=True)
    is_retweet = models.BooleanField(blank=True, null=True)
    is_quote = models.BooleanField(blank=True, null=True)
    in_reply_to_id = models.TextField(blank=True, null=True)
    in_reply_to_username = models.TextField(blank=True, null=True)
    tweet_type = models.TextField(blank=True, null=True)
    tweet_url = models.TextField(blank=True, null=True)
    tweet_twitter_url = models.TextField(blank=True, null=True)
    card = models.JSONField(blank=True, null=True)
    place = models.JSONField(blank=True, null=True)
    client_source = models.TextField(blank=True, null=True)
    view_count = models.IntegerField(blank=True, null=True)
    article = models.JSONField(blank=True, null=True)
    is_limited_reply = models.BooleanField(blank=True, null=True)
    community_info = models.JSONField(blank=True, null=True)
    display_text_range = models.JSONField(blank=True, null=True)
    extended_entities = models.JSONField(blank=True, null=True)
    quoted_author_handle = models.TextField(blank=True, null=True)

    # --- § 1.3 TwitterAPI author fields (snapshot at fetch time) ---
    author_name = models.TextField(blank=True, null=True)
    author_followers_count = models.IntegerField(blank=True, null=True)
    author_following_count = models.IntegerField(blank=True, null=True)
    author_verified = models.BooleanField(blank=True, null=True)
    author_is_blue_verified = models.BooleanField(blank=True, null=True)
    author_verified_type = models.TextField(blank=True, null=True)
    author_is_translator = models.BooleanField(blank=True, null=True)
    author_is_automated = models.BooleanField(blank=True, null=True)
    author_automated_by = models.TextField(blank=True, null=True)
    author_description = models.TextField(blank=True, null=True)
    author_location = models.TextField(blank=True, null=True)
    author_media_count = models.IntegerField(blank=True, null=True)
    author_statuses_count = models.IntegerField(blank=True, null=True)
    author_favourites_count = models.IntegerField(blank=True, null=True)
    author_fast_followers_count = models.IntegerField(blank=True, null=True)
    author_can_dm = models.BooleanField(blank=True, null=True)
    author_can_media_tag = models.BooleanField(blank=True, null=True)
    author_profile_picture = models.TextField(blank=True, null=True)
    author_profile_bio = models.JSONField(blank=True, null=True)
    author_cover_picture = models.TextField(blank=True, null=True)
    author_pinned_tweet_ids = models.JSONField(blank=True, null=True)
    author_affiliates_highlighted_label = models.JSONField(blank=True, null=True)
    author_withheld_in_countries = models.JSONField(blank=True, null=True)
    author_possibly_sensitive = models.BooleanField(blank=True, null=True)
    author_has_custom_timelines = models.BooleanField(blank=True, null=True)
    author_entities = models.JSONField(blank=True, null=True)
    author_twitter_url = models.TextField(blank=True, null=True)
    author_type = models.TextField(blank=True, null=True)
    author_url = models.TextField(blank=True, null=True)
    author_created_at_raw = models.TextField(blank=True, null=True)
    author_status = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "posts"
        indexes = [
            models.Index(fields=["author"], name="idx_posts_author_id"),
            models.Index(fields=["created_at"], name="idx_posts_created_at"),
            models.Index(
                fields=["created_at"],
                name="idx_posts_created_cover",
                include=["tweet_id", "author"],
            ),
            models.Index(fields=["lang"], name="idx_posts_lang"),
            models.Index(fields=["lang_detected"], name="idx_posts_lang_detected"),
            models.Index(fields=["source_query_id"], name="idx_posts_source_query_id"),
            models.Index(
                fields=["created_at_epoch"], name="idx_posts_created_at_epoch"
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.tweet_id


class PostEnrichmentState(models.Model):
    """Payload-free, replayable translation and classification state."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    post = models.OneToOneField(
        Post,
        on_delete=models.CASCADE,
        related_name="enrichment_state",
        db_column="post_id",
        to_field="tweet_id",
        primary_key=True,
    )
    translation_status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    translation_attempts = models.PositiveSmallIntegerField(default=0)
    translation_first_attempt_at = models.DateTimeField(blank=True, null=True)
    translation_last_attempt_at = models.DateTimeField(blank=True, null=True)
    translation_next_attempt_at = models.DateTimeField(blank=True, null=True)
    translation_error_code = models.CharField(max_length=128, blank=True, default="")
    classification_status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    classification_attempts = models.PositiveSmallIntegerField(default=0)
    classification_first_attempt_at = models.DateTimeField(blank=True, null=True)
    classification_last_attempt_at = models.DateTimeField(blank=True, null=True)
    classification_next_attempt_at = models.DateTimeField(blank=True, null=True)
    classification_error_code = models.CharField(
        max_length=128, blank=True, default=""
    )
    claim_owner = models.CharField(max_length=128, blank=True, default="")
    claim_run_id = models.CharField(max_length=128, blank=True, default="")
    claimed_at = models.DateTimeField(blank=True, null=True)
    claim_expires_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "post_enrichment_states"
        indexes = [
            models.Index(
                fields=["translation_status", "translation_next_attempt_at"],
                name="idx_pes_translation_due",
            ),
            models.Index(
                fields=["classification_status", "classification_next_attempt_at"],
                name="idx_pes_classify_due",
            ),
            models.Index(fields=["claim_expires_at"], name="idx_pes_claim_expiry"),
        ]


class PostTranslationArtifact(models.Model):
    """One versioned literal-translation lifecycle for a post body."""

    class State(models.TextChoices):
        GENERATING = "generating", "Generating"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="translation_artifacts",
        db_column="post_id",
        to_field="tweet_id",
    )
    source_content_fingerprint = models.CharField(max_length=64)
    source_language = models.CharField(max_length=16)
    prompt_version = models.CharField(max_length=64)
    model = models.CharField(max_length=128)
    provider_role = models.CharField(max_length=64)
    state = models.CharField(max_length=16, choices=State.choices)
    attempts = models.PositiveSmallIntegerField(default=1)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(blank=True, null=True)
    error_code = models.CharField(max_length=128, blank=True, default="")
    is_current = models.BooleanField(default=False)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "post_translation_artifacts"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "post",
                    "source_content_fingerprint",
                    "source_language",
                    "prompt_version",
                    "model",
                    "provider_role",
                ],
                name="uq_post_translation_identity",
            ),
            models.UniqueConstraint(
                fields=["post"],
                condition=models.Q(is_current=True),
                name="uq_post_translation_current",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state="generating",
                        completed_at__isnull=True,
                        is_current=False,
                    )
                    | models.Q(
                        state="succeeded",
                        completed_at__isnull=False,
                        error_code="",
                    )
                    | models.Q(
                        state="failed",
                        completed_at__isnull=False,
                        is_current=False,
                        error_code__gt="",
                    )
                ),
                name="ck_post_translation_state",
            ),
        ]
        indexes = [
            models.Index(
                fields=["post", "-created_at"], name="idx_post_translation_post"
            ),
            models.Index(fields=["state", "updated_at"], name="idx_post_translation_state"),
        ]


class PostTranslationText(models.Model):
    artifact = models.ForeignKey(
        PostTranslationArtifact,
        on_delete=models.CASCADE,
        related_name="texts",
    )
    locale = models.CharField(max_length=8)
    text = models.TextField()
    is_source = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "post_translation_texts"
        constraints = [
            models.UniqueConstraint(
                fields=["artifact", "locale"], name="uq_post_translation_locale"
            ),
            models.CheckConstraint(
                condition=models.Q(locale__in=["en", "zh-cn", "ja"]),
                name="ck_post_translation_locale",
            ),
            models.CheckConstraint(
                condition=~models.Q(text=""), name="ck_post_translation_text"
            ),
        ]


class PostSynthesisArtifact(models.Model):
    """One versioned locale-complete analyst synthesis for a post context."""

    class State(models.TextChoices):
        GENERATING = "generating", "Generating"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="synthesis_artifacts",
        db_column="post_id",
        to_field="tweet_id",
    )
    input_context_fingerprint = models.CharField(max_length=64)
    prompt_version = models.CharField(max_length=64)
    model = models.CharField(max_length=128)
    provider_role = models.CharField(max_length=64)
    output_schema_version = models.PositiveSmallIntegerField(default=1)
    state = models.CharField(max_length=16, choices=State.choices)
    attempts = models.PositiveSmallIntegerField(default=1)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(blank=True, null=True)
    error_code = models.CharField(max_length=128, blank=True, default="")
    evidence_provenance = models.JSONField(default=list, db_default=[])
    review_state = models.CharField(max_length=32, blank=True, default="")
    is_current = models.BooleanField(default=False)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "post_synthesis_artifacts"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "post",
                    "input_context_fingerprint",
                    "prompt_version",
                    "model",
                    "provider_role",
                    "output_schema_version",
                ],
                name="uq_post_synthesis_identity",
            ),
            models.UniqueConstraint(
                fields=["post"],
                condition=models.Q(is_current=True),
                name="uq_post_synthesis_current",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state="generating",
                        completed_at__isnull=True,
                        is_current=False,
                    )
                    | models.Q(
                        state="succeeded",
                        completed_at__isnull=False,
                        error_code="",
                    )
                    | models.Q(
                        state="failed",
                        completed_at__isnull=False,
                        is_current=False,
                        error_code__gt="",
                    )
                ),
                name="ck_post_synthesis_state",
            ),
        ]
        indexes = [
            models.Index(
                fields=["post", "-created_at"], name="idx_post_synthesis_post"
            ),
            models.Index(fields=["state", "updated_at"], name="idx_post_synthesis_state"),
        ]


class PostSynthesisText(models.Model):
    artifact = models.ForeignKey(
        PostSynthesisArtifact,
        on_delete=models.CASCADE,
        related_name="texts",
    )
    locale = models.CharField(max_length=8)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "post_synthesis_texts"
        constraints = [
            models.UniqueConstraint(
                fields=["artifact", "locale"], name="uq_post_synthesis_locale"
            ),
            models.CheckConstraint(
                condition=models.Q(locale__in=["en", "zh-cn", "ja"]),
                name="ck_post_synthesis_locale",
            ),
            models.CheckConstraint(
                condition=~models.Q(text=""), name="ck_post_synthesis_text"
            ),
        ]


class PostSynthesisDemand(models.Model):
    """PostgreSQL-backed, coalesced synthesis work request."""

    class Reason(models.TextChoices):
        PREWARM = "prewarm", "Prewarm"
        LOOKAHEAD = "lookahead", "Lookahead"
        VISIBLE = "visible", "Visible"
        EXPANDED = "expanded", "Expanded"
        OPERATOR = "operator", "Operator"

    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="synthesis_demands",
        db_column="post_id",
        to_field="tweet_id",
    )
    input_context_fingerprint = models.CharField(max_length=64)
    prompt_version = models.CharField(max_length=64)
    model = models.CharField(max_length=128)
    output_schema_version = models.PositiveSmallIntegerField(default=1)
    reason = models.CharField(max_length=16, choices=Reason.choices)
    priority = models.PositiveSmallIntegerField()
    request_count = models.PositiveIntegerField(default=1)
    first_requested_at = models.DateTimeField()
    last_requested_at = models.DateTimeField()
    not_before = models.DateTimeField()
    expires_at = models.DateTimeField(blank=True, null=True)
    state = models.CharField(
        max_length=16, choices=State.choices, default=State.PENDING
    )
    lease_owner = models.CharField(max_length=128, blank=True, default="")
    lease_expires_at = models.DateTimeField(blank=True, null=True)
    lease_fence = models.PositiveIntegerField(default=0)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=128, blank=True, default="")
    artifact = models.ForeignKey(
        PostSynthesisArtifact,
        on_delete=models.SET_NULL,
        related_name="demands",
        blank=True,
        null=True,
    )
    budget = models.ForeignKey(
        "PostSynthesisDailyBudget",
        on_delete=models.PROTECT,
        related_name="demands",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "post_synthesis_demands"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "post",
                    "input_context_fingerprint",
                    "prompt_version",
                    "model",
                    "output_schema_version",
                ],
                name="uq_post_synthesis_demand_identity",
            ),
            models.CheckConstraint(
                condition=models.Q(priority__gte=1, priority__lte=100),
                name="ck_post_synth_demand_priority",
            ),
            models.CheckConstraint(
                condition=models.Q(last_requested_at__gte=models.F("first_requested_at")),
                name="ck_post_synth_request_order",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state="processing",
                        lease_owner__gt="",
                        lease_fence__gt=0,
                        lease_expires_at__isnull=False,
                    )
                    | (
                        ~models.Q(state="processing")
                        & models.Q(
                            lease_owner="",
                            lease_expires_at__isnull=True,
                        )
                    )
                ),
                name="ck_post_synth_demand_lease",
            ),
        ]
        indexes = [
            models.Index(
                fields=["state", "not_before", "-priority"],
                name="idx_post_synth_demand_due",
            ),
            models.Index(
                fields=["lease_expires_at"], name="idx_post_synth_lease_expiry"
            ),
        ]


class PostSynthesisDailyBudget(models.Model):
    """Conservative per-day reservations for synthesis provider transport."""

    usage_date = models.DateField()
    control_revision = models.CharField(max_length=64)
    provider = models.CharField(max_length=32)
    model = models.CharField(max_length=128)
    reserved_requests = models.PositiveIntegerField(default=0)
    reserved_input_tokens = models.PositiveBigIntegerField(default=0)
    reserved_output_tokens = models.PositiveBigIntegerField(default=0)
    observed_input_tokens = models.PositiveBigIntegerField(default=0)
    observed_output_tokens = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "post_synthesis_daily_budgets"
        constraints = [
            models.UniqueConstraint(
                fields=["usage_date", "control_revision", "provider", "model"],
                name="uq_post_synth_daily_budget",
            )
        ]


class PostSynthesisRateLimitBucket(models.Model):
    """Cross-process request throttle without storing a user ID or IP address."""

    bucket_start = models.DateTimeField()
    scope_hash = models.CharField(max_length=64)
    count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "post_synthesis_rate_limit_buckets"
        constraints = [
            models.UniqueConstraint(
                fields=["bucket_start", "scope_hash"],
                name="uq_post_synth_rate_bucket",
            )
        ]
        indexes = [
            models.Index(
                fields=["bucket_start"], name="idx_psynth_rate_time"
            )
        ]


# ============================================================================
# Edges / junctions
# ============================================================================


class BrandCompany(models.Model):
    pk = models.CompositePrimaryKey("brand", "company")
    brand = models.ForeignKey(
        Brand,
        on_delete=models.CASCADE,
        related_name="companies",
        db_column="brand_id",
        to_field="nickname",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="brands",
        db_column="company_id",
        to_field="nickname",
    )
    ownership_pct = models.FloatField(default=1.0)

    class Meta:
        db_table = "brands_companies"


class BrandAccount(models.Model):
    pk = models.CompositePrimaryKey("brand", "account")
    brand = models.ForeignKey(
        Brand,
        on_delete=models.CASCADE,
        related_name="accounts",
        db_column="brand_id",
        to_field="nickname",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="brands",
        db_column="accounts_id",
        to_field="author_id",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="+",
        db_column="role_id",
        to_field="key",
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "brands_accounts"
        indexes = [
            models.Index(fields=["role"], name="idx_brands_accounts_role_id"),
        ]


class CompanyAccount(models.Model):
    pk = models.CompositePrimaryKey("company", "account")
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="accounts",
        db_column="company_id",
        to_field="nickname",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="companies",
        db_column="author_id",
        to_field="author_id",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="+",
        db_column="role_id",
        to_field="key",
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "companies_accounts"
        indexes = [
            models.Index(fields=["role"], name="idx_companies_accounts_role_id"),
        ]


class PostBrand(models.Model):
    pk = models.CompositePrimaryKey("post", "brand")
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="brands",
        db_column="post_id",
        to_field="tweet_id",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.CASCADE,
        related_name="posts",
        db_column="brand_id",
        to_field="nickname",
    )
    weight = models.FloatField(default=1.0)

    class Meta:
        db_table = "posts_brands"
        indexes = [
            models.Index(fields=["brand"], name="idx_posts_brands_brand_id"),
        ]


class PostBrandMention(models.Model):
    pk = models.CompositePrimaryKey("post", "brand", "source")
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="mentions",
        db_column="post_id",
        to_field="tweet_id",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="+",
        db_column="brand_id",
        to_field="nickname",
    )
    source = models.TextField()
    raw_token = models.TextField(blank=True, null=True)
    mentioned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "posts_brands_mentions"
        indexes = [
            models.Index(
                fields=["brand"], name="idx_post_brand_mention_brand"
            ),
        ]


class PostBrandSignal(models.Model):
    pk = models.CompositePrimaryKey("post", "brand", "post_type")
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="signals",
        db_column="post_id",
        to_field="tweet_id",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="+",
        db_column="brand_id",
        to_field="nickname",
    )
    post_type = models.ForeignKey(
        PostTypeKey,
        on_delete=models.PROTECT,
        related_name="+",
        db_column="post_type_key",
        to_field="key",
    )
    sentiment = models.ForeignKey(
        SentimentKey,
        on_delete=models.PROTECT,
        related_name="+",
        db_column="sentiment",
        to_field="key",
    )

    class Meta:
        db_table = "posts_brands_signals"
        indexes = [
            models.Index(
                fields=["brand", "post_type"],
                name="idx_pb_sig_b_p_type",
            ),
            models.Index(
                fields=["brand", "sentiment"],
                name="idx_pb_sig_b_sent",
            ),
        ]


class PostBrandClassificationState(models.Model):
    """Current Stage 1 classification identity and scalar judgments."""

    class Outcome(models.TextChoices):
        CLASSIFIED = "classified", "Classified"
        CONTEXT_MISSING = "context_missing", "Context missing"

    pk = models.CompositePrimaryKey("post", "brand")
    post = models.ForeignKey(
        Post, on_delete=models.CASCADE, related_name="classification_states",
        db_column="post_id", to_field="tweet_id",
    )
    brand = models.ForeignKey(
        Brand, on_delete=models.PROTECT, related_name="+",
        db_column="brand_id", to_field="nickname",
    )
    contract_version = models.CharField(max_length=64)
    taxonomy_version = models.CharField(max_length=64)
    prompt_version = models.CharField(max_length=64)
    model = models.CharField(max_length=256)
    source_language = models.CharField(max_length=64, blank=True, default="")
    input_context_fingerprint = models.CharField(max_length=64)
    outcome = models.CharField(max_length=32, choices=Outcome.choices)
    sentiment = models.ForeignKey(
        SentimentKey, on_delete=models.PROTECT, related_name="+",
        db_column="sentiment", to_field="key", blank=True, null=True,
    )
    china_nationalism = models.ForeignKey(
        NationalismKey, on_delete=models.PROTECT, related_name="+",
        db_column="china_nationalism", to_field="key", blank=True, null=True,
    )
    us_nationalism = models.ForeignKey(
        NationalismKey, on_delete=models.PROTECT, related_name="+",
        db_column="us_nationalism", to_field="key", blank=True, null=True,
    )
    classified_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "posts_brands_classification_states"
        indexes = [
            models.Index(
                fields=["brand", "outcome"],
                name="idx_pb_cls_state_brand_outcome",
            ),
            models.Index(fields=["contract_version"], name="idx_pb_cls_state_contract"),
        ]


class PostBrandProductLabel(models.Model):
    """Independent product labels for a post-brand classification."""

    pk = models.CompositePrimaryKey("post", "brand", "product_label")
    post = models.ForeignKey(
        Post, on_delete=models.CASCADE, related_name="product_label_edges",
        db_column="post_id", to_field="tweet_id",
    )
    brand = models.ForeignKey(
        Brand, on_delete=models.PROTECT, related_name="+",
        db_column="brand_id", to_field="nickname",
    )
    product_label = models.ForeignKey(
        ProductLabelKey, on_delete=models.PROTECT, related_name="+",
        db_column="product_label_key", to_field="key",
    )

    class Meta:
        db_table = "posts_brands_product_labels"
        indexes = [
            models.Index(
                fields=["brand", "product_label"],
                name="idx_pb_product_brand_label",
            ),
        ]


class PostBrandDiscourse(models.Model):
    """(post x brand) signal table for per-act pragmatics.

    Composite PK (post, brand, discourse, act_id): a single tweet can have
    N speech-acts toward the same brand.  The two nationalism FKs are
    nullable during the backfill window.
    """

    pk = models.CompositePrimaryKey("post", "brand", "discourse", "act_id")
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="discourse_signals",
        db_column="post_id",
        to_field="tweet_id",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="+",
        db_column="brand_id",
        to_field="nickname",
    )
    discourse = models.ForeignKey(
        DiscourseKey,
        on_delete=models.PROTECT,
        related_name="+",
        db_column="discourse_key",
        to_field="key",
    )
    act_id = models.PositiveSmallIntegerField()
    china_nationalism = models.ForeignKey(
        NationalismKey,
        on_delete=models.PROTECT,
        related_name="+",
        db_column="china_nationalism",
        to_field="key",
        blank=True,
        null=True,
    )
    us_nationalism = models.ForeignKey(
        NationalismKey,
        on_delete=models.PROTECT,
        related_name="+",
        db_column="us_nationalism",
        to_field="key",
        blank=True,
        null=True,
    )

    class Meta:
        db_table = "posts_brands_discourse"
        indexes = [
            models.Index(
                fields=["brand", "discourse"],
                name="idx_post_brand_dis_b_dr",
            ),
            models.Index(
                fields=["brand", "china_nationalism"],
                name="idx_post_brand_dis_b_cn_nat",
            ),
            models.Index(
                fields=["brand", "us_nationalism"],
                name="idx_post_brand_dis_b_us_nat",
            ),
        ]


class PostUnsanctionedFlag(models.Model):
    """Per-post unsanctioned-flag assignment.

    Single PK on post (one flag-set row per post).  flags contains the
    JSON array of flag keys; flag_set is a generated column extracted
    from flags.
    """

    post = models.OneToOneField(
        Post,
        on_delete=models.CASCADE,
        related_name="unsanctioned_flags",
        db_column="post_id",
        to_field="tweet_id",
        primary_key=True,
    )
    flags = models.TextField()
    flag_set = models.JSONField(blank=True, null=True)
    evidence = models.TextField(blank=True, null=True)
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "posts_unsanctioned_flags"
        indexes = [
            models.Index(
                fields=["flag_set"], name="idx_unsanctioned_flag_set"
            ),
        ]


class AccountPostAppearance(models.Model):
    pk = models.CompositePrimaryKey("account", "post")
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="appearances",
        db_column="author_id",
        to_field="author_id",
    )
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="appearances",
        db_column="tweet_id",
        to_field="tweet_id",
    )
    role_at_time = models.TextField(blank=True, null=True)
    source_query_ids = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "account_post_appearances"
        indexes = [
            models.Index(fields=["post"], name="idx_acct_post_app_post_id"),
        ]


# ============================================================================
# Products
# ============================================================================


class Product(models.Model):
    id = models.BigAutoField(primary_key=True)
    repo_id = models.CharField(
        max_length=256,
        unique=True,
        db_collation="case_insensitive",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="products",
        db_column="brand_id",
        to_field="nickname",
    )
    hf_org = models.ForeignKey(
        HFOrg,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="products",
        db_column="hf_org_id",
        to_field="namespace",
    )
    hf_type = models.TextField(default="model")
    display_name = models.TextField(blank=True, null=True)
    author = models.TextField(blank=True, null=True)
    sha = models.TextField(blank=True, null=True)
    private = models.BooleanField(blank=True, null=True)
    gated = models.TextField(blank=True, null=True)
    disabled = models.BooleanField(blank=True, null=True)
    pipeline_tag = models.TextField(blank=True, null=True)
    library_name = models.TextField(blank=True, null=True)
    downloads = models.IntegerField(blank=True, null=True)
    downloads_all_time = models.IntegerField(blank=True, null=True)
    download_velocity = models.FloatField(blank=True, null=True)
    likes = models.IntegerField(blank=True, null=True)
    trending_score = models.FloatField(blank=True, null=True)
    paperswithcode_id = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    last_modified = models.DateTimeField(blank=True, null=True)
    tags = models.JSONField(blank=True, null=True, db_column="tags_json")
    siblings = models.JSONField(blank=True, null=True, db_column="siblings_json")
    card_data = models.JSONField(blank=True, null=True, db_column="card_data_json")
    config = models.JSONField(blank=True, null=True, db_column="config_json")
    spaces = models.JSONField(blank=True, null=True, db_column="spaces_json")
    raw = models.JSONField(blank=True, null=True, db_column="raw_json")
    collected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "products"
        indexes = [
            models.Index(fields=["brand"], name="idx_products_brand"),
            models.Index(fields=["hf_org"], name="idx_products_hf_org_id"),
            models.Index(
                fields=["collected_at"], name="idx_products_collected_at"
            ),
        ]
        ordering = ["repo_id"]

    def __str__(self) -> str:
        return self.repo_id


# ============================================================================
# Attribution map
# ============================================================================


class BrandSearchTerm(models.Model):
    pk = models.CompositePrimaryKey("brand", "term")
    brand = models.ForeignKey(
        Brand,
        on_delete=models.CASCADE,
        related_name="search_terms",
        db_column="brand_id",
        to_field="nickname",
    )
    term = models.TextField()
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "brand_search_terms"


class BrandKeyword(models.Model):
    pk = models.CompositePrimaryKey("brand", "pattern")
    brand = models.ForeignKey(
        Brand,
        on_delete=models.CASCADE,
        related_name="keywords",
        db_column="brand_id",
        to_field="nickname",
    )
    pattern = models.TextField()
    is_regex = models.BooleanField(default=False)
    added_at = models.DateTimeField(auto_now_add=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        db_table = "brand_keywords"
        indexes = [
            models.Index(
                fields=["brand"], name="idx_brand_keywords_brand_id"
            ),
        ]


class BrandHashtag(models.Model):
    pk = models.CompositePrimaryKey("brand", "hashtag")
    brand = models.ForeignKey(
        Brand,
        on_delete=models.CASCADE,
        related_name="hashtags",
        db_column="brand_id",
        to_field="nickname",
    )
    hashtag = models.TextField(db_column="tag")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "brand_hashtags"
        indexes = [
            models.Index(
                fields=["brand"], name="idx_brand_hashtags_brand_id"
            ),
        ]


# ============================================================================
# Cycle / introspection
# ============================================================================


class SearchQuery(models.Model):
    id = models.BigAutoField(primary_key=True)
    query_id = models.TextField(unique=True)
    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
        db_column="brand_id",
        to_field="nickname",
    )
    keywords = models.JSONField(blank=True, null=True, db_column="keywords_json")
    plan_calls_run_id = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "search_queries"
        indexes = [
            models.Index(
                fields=["brand"], name="idx_search_queries_brand_id"
            ),
        ]


class CallState(models.Model):
    """Cursor tracker for per-call brand harvest cycles.

    Composite PK on (brand_id, call_id, call_kind, bucket, query_id).
    brand_id uses nickname slugs (e.g. "deepseek" or "*" for fan-in).
    """

    pk = models.CompositePrimaryKey(
        "brand_id", "call_id", "call_kind", "bucket", "query_id"
    )
    brand_id = models.TextField()
    call_id = models.TextField()
    call_kind = models.TextField()
    bucket = models.TextField(blank=True, default="")
    query_id = models.TextField()
    last_completed_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "call_state"
        indexes = [
            models.Index(
                fields=["last_completed_at"],
                name="idx_call_state_completed_at",
            ),
        ]


@dataclass(frozen=True)
class BacklogNormalizationResult:
    """Durable ownership result consumed by the later cursor-transfer unit."""

    outcome: Literal[
        "created", "duplicate", "coalesced", "capacity_refused"
    ]
    ownership_recorded: bool
    window_id: int | None
    merged_count: int = 0


class HarvestBacklogWindowManager(models.Manager):
    _IDENTITY_FIELDS = frozenset(
        {"brand_id", "call_id", "call_kind", "bucket", "query_id"}
    )

    def normalize_residual(
        self,
        *,
        call_identity: dict[str, str],
        original_since,
        original_until,
        remaining_since,
        remaining_until,
        reason_code: str,
        pending_limit: int,
        quarantined_limit: int,
        state: str = "pending",
    ) -> BacklogNormalizationResult:
        """Record a bounded residual without transferring cursor ownership.

        The CallState lock serializes capacity checks and interval normalization
        for one complete call identity. The caller remains responsible for
        updating CallState in the surrounding transaction.
        """

        if set(call_identity) != self._IDENTITY_FIELDS:
            raise ValueError("call_identity must contain the full call identity")

        with transaction.atomic():
            call_state = (
                CallState.objects.select_for_update()
                .filter(**call_identity)
                .first()
            )
            if call_state is None:
                raise ValueError("CallState must exist before recording a residual")

            if original_since >= original_until:
                raise ValueError("original interval must be increasing")
            if remaining_since >= remaining_until:
                raise ValueError("remaining interval must be increasing")
            if (
                remaining_since < original_since
                or remaining_until > original_until
            ):
                raise ValueError("remaining interval must be within original bounds")
            if state not in {"pending", "quarantined"}:
                raise ValueError("new residual state must be pending or quarantined")
            if pending_limit <= 0 or quarantined_limit <= 0:
                raise ValueError("backlog row ceilings must be positive")

            identity_rows = self.select_for_update().filter(**call_identity)
            exact = identity_rows.filter(
                remaining_since=remaining_since,
                remaining_until=remaining_until,
            ).first()
            if exact is not None:
                if exact.state == state:
                    return BacklogNormalizationResult(
                        outcome="duplicate",
                        ownership_recorded=True,
                        window_id=exact.pk,
                    )
                return BacklogNormalizationResult(
                    outcome="capacity_refused",
                    ownership_recorded=False,
                    window_id=None,
                )

            if state in {"pending", "quarantined"}:
                merged_since = remaining_since
                merged_until = remaining_until
                candidates = {}
                while True:
                    adjacent = identity_rows.filter(
                        state=state,
                        remaining_since__lte=merged_until + timedelta(seconds=1),
                        remaining_until__gte=merged_since - timedelta(seconds=1),
                    ).exclude(pk__in=candidates)
                    additions = list(adjacent.order_by("first_seen_at", "pk"))
                    if not additions:
                        break
                    for candidate in additions:
                        candidates[candidate.pk] = candidate
                        merged_since = min(merged_since, candidate.remaining_since)
                        merged_until = max(merged_until, candidate.remaining_until)

                if candidates:
                    windows = list(candidates.values())
                    keeper = windows[0]
                    secondary_ids = [window.pk for window in windows[1:]]
                    if secondary_ids:
                        self.filter(pk__in=secondary_ids).delete()
                    keeper.original_since = min(
                        original_since,
                        *(window.original_since for window in windows),
                    )
                    keeper.original_until = max(
                        original_until,
                        *(window.original_until for window in windows),
                    )
                    keeper.remaining_since = merged_since
                    keeper.remaining_until = merged_until
                    keeper.save(
                        update_fields=[
                            "original_since",
                            "original_until",
                            "remaining_since",
                            "remaining_until",
                            "last_seen_at",
                        ]
                    )
                    return BacklogNormalizationResult(
                        outcome="coalesced",
                        ownership_recorded=True,
                        window_id=keeper.pk,
                        merged_count=len(windows) + 1,
                    )

            if state == "pending":
                limit = pending_limit
                capacity_states = ["pending", "claimed"]
            else:
                limit = quarantined_limit
                capacity_states = ["quarantined"]
            if identity_rows.filter(state__in=capacity_states).count() >= limit:
                return BacklogNormalizationResult(
                    outcome="capacity_refused",
                    ownership_recorded=False,
                    window_id=None,
                )

            window = self.create(
                **call_identity,
                original_since=original_since,
                original_until=original_until,
                remaining_since=remaining_since,
                remaining_until=remaining_until,
                state=state,
                reason_code=reason_code,
            )
            return BacklogNormalizationResult(
                outcome="created",
                ownership_recorded=True,
                window_id=window.pk,
            )

    def recover_expired_claims(self, *, now=None) -> int:
        now = now or timezone.now()
        return self.filter(
            state="claimed", claim_expires_at__lte=now
        ).update(
            state="pending",
            claim_owner="",
            claim_run_id="",
            claimed_at=None,
            claim_expires_at=None,
        )

    def claim_next(
        self,
        *,
        owner: str,
        run_id: str,
        claim_expires_at,
        now=None,
        call_identity: dict[str, str] | None = None,
        include_quarantined: bool = False,
        only_quarantined: bool = False,
    ):
        """Claim one due interval with PostgreSQL skip-locked semantics."""

        now = now or timezone.now()
        with transaction.atomic():
            self.recover_expired_claims(now=now)
            states = ["quarantined"] if only_quarantined else ["pending"]
            if include_quarantined and not only_quarantined:
                states.append("quarantined")
            candidates = self.select_for_update(skip_locked=True).filter(
                state__in=states
            ).filter(
                models.Q(next_attempt_at__isnull=True)
                | models.Q(next_attempt_at__lte=now)
            )
            if call_identity:
                candidates = candidates.filter(**call_identity)
            window = candidates.order_by("first_seen_at", "remaining_since", "pk").first()
            if window is None:
                return None
            window.state = "claimed"
            window.attempts += 1
            window.claim_owner = owner[:128]
            window.claim_run_id = run_id[:128]
            window.claimed_at = now
            window.claim_expires_at = claim_expires_at
            window.save(
                update_fields=[
                    "state",
                    "attempts",
                    "claim_owner",
                    "claim_run_id",
                    "claimed_at",
                    "claim_expires_at",
                    "last_seen_at",
                ]
            )
            return window


class HarvestBacklogWindow(models.Model):
    """Bounded recall-debt metadata; tweet/provider payloads never live here."""

    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        CLAIMED = "claimed", "Claimed"
        QUARANTINED = "quarantined", "Quarantined"
        WAIVED = "waived", "Waived"

    brand_id = models.TextField()
    call_id = models.TextField()
    call_kind = models.TextField()
    bucket = models.TextField(blank=True, default="")
    query_id = models.TextField()
    original_since = models.DateTimeField()
    original_until = models.DateTimeField()
    remaining_since = models.DateTimeField()
    remaining_until = models.DateTimeField()
    state = models.CharField(
        max_length=16, choices=State.choices, default=State.PENDING
    )
    reason_code = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    next_attempt_at = models.DateTimeField(blank=True, null=True)
    claim_owner = models.CharField(max_length=128, blank=True, default="")
    claim_run_id = models.CharField(max_length=128, blank=True, default="")
    claimed_at = models.DateTimeField(blank=True, null=True)
    claim_expires_at = models.DateTimeField(blank=True, null=True)
    quarantine_reason = models.CharField(max_length=128, blank=True, default="")
    quarantined_at = models.DateTimeField(blank=True, null=True)
    waiver_reason = models.CharField(max_length=128, blank=True, default="")
    waived_at = models.DateTimeField(blank=True, null=True)

    objects = HarvestBacklogWindowManager()

    class Meta:
        db_table = "harvest_backlog_windows"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(original_since__lt=models.F("original_until")),
                name="ck_hbw_original_interval",
            ),
            models.CheckConstraint(
                condition=models.Q(remaining_since__lt=models.F("remaining_until")),
                name="ck_hbw_remaining_interval",
            ),
            models.CheckConstraint(
                condition=models.Q(remaining_since__gte=models.F("original_since")),
                name="ck_hbw_remaining_start",
            ),
            models.CheckConstraint(
                condition=models.Q(remaining_until__lte=models.F("original_until")),
                name="ck_hbw_remaining_end",
            ),
            models.UniqueConstraint(
                fields=[
                    "brand_id",
                    "call_id",
                    "call_kind",
                    "bucket",
                    "query_id",
                    "remaining_since",
                    "remaining_until",
                ],
                name="uq_hbw_call_remaining",
            ),
        ]
        indexes = [
            models.Index(
                fields=[
                    "brand_id",
                    "call_id",
                    "call_kind",
                    "bucket",
                    "query_id",
                    "state",
                    "remaining_since",
                ],
                name="idx_hbw_call_state_since",
            ),
            models.Index(
                fields=["state", "next_attempt_at"], name="idx_hbw_state_due"
            ),
            models.Index(fields=["claim_expires_at"], name="idx_hbw_claim_expiry"),
        ]


# ============================================================================
# Trend narrative publication + outbound-call ledger
# ============================================================================


class TrendNarrative(models.Model):
    """One durable attempt/version for a shared fixed-window headline.

    The table is intentionally both the publication cache and the outbound
    call ledger.  A source cycle can consume at most one irreversible provider
    slot per window, while a valid current row remains servable across later
    failures.
    """

    class Status(models.TextChoices):
        CHECKED = "checked", "Checked"
        SUPPRESSED = "suppressed", "Suppressed"
        GENERATING = "generating", "Generating"
        ABANDONED = "abandoned", "Abandoned"
        FAILED = "failed", "Failed"
        PUBLISHED = "published", "Published"
        SUPERSEDED = "superseded", "Superseded"

    source_cycle_id = models.CharField(max_length=128)
    window_days = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices)
    semantic_fingerprint = models.CharField(max_length=64, blank=True, default="")
    publication_epoch = models.PositiveIntegerField(default=1)
    is_current = models.BooleanField(default=False)

    facts_as_of = models.DateTimeField()
    generation_facts = models.JSONField(blank=True, null=True)
    output_schema_version = models.PositiveSmallIntegerField(
        default=1,
        db_default=1,
    )
    observations_en = models.JSONField(blank=True, default=list, db_default=[])
    observations_zh_cn = models.JSONField(
        blank=True,
        default=list,
        db_default=[],
    )
    selected_candidate_ids = models.JSONField(
        blank=True,
        default=list,
        db_default=[],
    )
    claims = models.JSONField(blank=True, default=list, db_default=[])
    latest_checked_source_cycle_id = models.CharField(
        max_length=128, blank=True, default=""
    )
    latest_checked_as_of = models.DateTimeField(blank=True, null=True)
    latest_checked_at = models.DateTimeField(blank=True, null=True)
    latest_checked_facts = models.JSONField(blank=True, null=True)
    narrative_type = models.CharField(max_length=32, blank=True, default="")
    coverage_state = models.CharField(max_length=32, blank=True, default="")

    primary_brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
        db_column="primary_brand_id",
        to_field="nickname",
    )
    secondary_brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
        db_column="secondary_brand_id",
        to_field="nickname",
    )
    primary_brand_key = models.CharField(max_length=64, blank=True, default="")
    primary_brand_name_en = models.TextField(blank=True, default="")
    primary_brand_name_zh_hans = models.TextField(blank=True, default="")
    secondary_brand_key = models.CharField(max_length=64, blank=True, default="")
    secondary_brand_name_en = models.TextField(blank=True, default="")
    secondary_brand_name_zh_hans = models.TextField(blank=True, default="")

    body_en = models.TextField(blank=True, default="")
    body_zh_hans = models.TextField(blank=True, default="")
    body_zh_cn = models.TextField(blank=True, null=True)
    output_hash = models.CharField(max_length=64, blank=True, default="")
    prompt_version = models.CharField(max_length=64, blank=True, default="")
    provider = models.CharField(max_length=32, blank=True, default="")
    provider_host = models.CharField(max_length=255, blank=True, default="")
    model_name = models.CharField(max_length=128, blank=True, default="")
    llm_model_name = models.CharField(max_length=128, blank=True, null=True)

    call_slot_consumed = models.BooleanField(default=False)
    claim_owner = models.CharField(max_length=128, blank=True, default="")
    claim_fence = models.PositiveIntegerField(default=0)
    claimed_at = models.DateTimeField(blank=True, null=True)
    claim_expires_at = models.DateTimeField(blank=True, null=True)
    transport_started_at = models.DateTimeField(blank=True, null=True)
    transport_completed_at = models.DateTimeField(blank=True, null=True)
    generated_at = models.DateTimeField(blank=True, null=True)
    published_at = models.DateTimeField(blank=True, null=True)
    next_attempt_at = models.DateTimeField(blank=True, null=True)
    consecutive_failures = models.PositiveIntegerField(default=0, db_default=0)
    error_code = models.CharField(max_length=64, blank=True, default="")
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "trend_narratives"
        constraints = [
            models.UniqueConstraint(
                fields=["source_cycle_id", "window_days"],
                name="uq_tnv_source_window",
            ),
            models.UniqueConstraint(
                fields=["window_days"],
                condition=models.Q(is_current=True),
                name="uq_tnv_current_window",
            ),
            models.CheckConstraint(
                condition=models.Q(window_days__in=[1, 7, 30, 365]),
                name="ck_tnv_window",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        "checked",
                        "suppressed",
                        "generating",
                        "abandoned",
                        "failed",
                        "published",
                        "superseded",
                    ]
                ),
                name="ck_tnv_status",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_current=False)
                    | models.Q(status="published")
                ),
                name="ck_tnv_current_published",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        call_slot_consumed=False,
                        status__in=["checked", "suppressed"],
                    )
                    | models.Q(
                        call_slot_consumed=True,
                        status__in=[
                            "generating",
                            "abandoned",
                            "failed",
                            "published",
                            "superseded",
                        ],
                    )
                ),
                name="ck_tnv_slot_status",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        call_slot_consumed=False,
                        claim_owner="",
                        claim_fence=0,
                        claimed_at__isnull=True,
                        claim_expires_at__isnull=True,
                    )
                    | models.Q(
                        call_slot_consumed=True,
                        claim_owner__gt="",
                        claim_fence__gt=0,
                        claimed_at__isnull=False,
                        claim_expires_at__isnull=False,
                    )
                ),
                name="ck_tnv_claim_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(claimed_at__isnull=True)
                    | models.Q(claim_expires_at__gt=models.F("claimed_at"))
                ),
                name="ck_tnv_claim_order",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(status__in=["failed", "abandoned"])
                    | models.Q(error_code__gt="")
                ),
                name="ck_tnv_terminal_error",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status__in=["published", "superseded"],
                        body_en__gt="",
                        body_zh_hans__gt="",
                        output_hash__gt="",
                        primary_brand_key__gt="",
                        primary_brand_name_en__gt="",
                        primary_brand_name_zh_hans__gt="",
                        generated_at__isnull=False,
                        published_at__isnull=False,
                    )
                    | models.Q(
                        status__in=[
                            "checked",
                            "suppressed",
                            "generating",
                            "abandoned",
                            "failed",
                        ],
                        body_en="",
                        body_zh_hans="",
                        output_hash="",
                        generated_at__isnull=True,
                        published_at__isnull=True,
                    )
                ),
                name="ck_tnv_output_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(transport_started_at__isnull=True)
                    | models.Q(
                        call_slot_consumed=True,
                        transport_started_at__gte=models.F("claimed_at"),
                    )
                ),
                name="ck_tnv_transport_start",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(transport_completed_at__isnull=True)
                    | models.Q(
                        transport_started_at__isnull=False,
                        transport_completed_at__gte=models.F(
                            "transport_started_at"
                        ),
                    )
                ),
                name="ck_tnv_transport_finish",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(generated_at__isnull=True)
                    | models.Q(
                        transport_completed_at__isnull=False,
                        generated_at__gte=models.F("transport_completed_at"),
                    )
                ),
                name="ck_tnv_generated_order",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(published_at__isnull=True)
                    | models.Q(published_at__gte=models.F("generated_at"))
                ),
                name="ck_tnv_published_order",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        latest_checked_source_cycle_id="",
                        latest_checked_as_of__isnull=True,
                        latest_checked_at__isnull=True,
                        latest_checked_facts__isnull=True,
                    )
                    | models.Q(
                        latest_checked_source_cycle_id__gt="",
                        latest_checked_as_of__isnull=False,
                        latest_checked_at__isnull=False,
                        latest_checked_facts__isnull=False,
                    )
                ),
                name="ck_tnv_check_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=["window_days", "semantic_fingerprint"],
                name="idx_tnv_window_fingerprint",
            ),
            models.Index(
                fields=["window_days", "facts_as_of"],
                name="idx_tnv_window_facts",
            ),
            models.Index(
                fields=["status", "next_attempt_at"],
                name="idx_tnv_status_retry",
            ),
            models.Index(
                fields=["window_days", "-created_at"],
                name="idx_tnv_window_created",
            ),
        ]

    @property
    def resolved_body_zh_cn(self) -> str:
        """Read canonical Chinese copy with rolling-deploy fallback."""
        return self.body_zh_cn if self.body_zh_cn is not None else self.body_zh_hans

    @property
    def resolved_llm_model_name(self) -> str:
        """Read canonical model provenance with rolling-deploy fallback."""
        return (
            self.llm_model_name
            if self.llm_model_name is not None
            else self.model_name
        )


class TrendNarrativeRun(models.Model):
    """Immutable all-brand facts cutoff for one source-cycle/window pair."""

    class Status(models.TextChoices):
        PREPARING = "preparing", "Preparing"
        SUSPENDED = "suspended", "Suspended"
        TERMINAL = "terminal", "Terminal"
        ACTIVE = "active", "Active"
        SUPERSEDED = "superseded", "Superseded"

    source_cycle_id = models.CharField(max_length=128)
    window_days = models.PositiveSmallIntegerField()
    facts_as_of = models.DateTimeField()
    packet_schema_version = models.PositiveSmallIntegerField()
    snapshot = models.JSONField()
    brand_manifest = models.JSONField(default=list, db_default=[])
    batch_manifest = models.JSONField(default=list, db_default=[])
    internal_order = models.JSONField(default=list, db_default=[])
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PREPARING
    )
    suspension_reason = models.CharField(max_length=64, blank=True, default="")
    activated_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "trend_narrative_runs"
        constraints = [
            models.UniqueConstraint(
                fields=["source_cycle_id", "window_days"],
                name="uq_tnr_source_window",
            ),
            models.CheckConstraint(
                condition=models.Q(window_days__in=[1, 7, 30, 365]),
                name="ck_tnr_window",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        "preparing",
                        "suspended",
                        "terminal",
                        "active",
                        "superseded",
                    ]
                ),
                name="ck_tnr_status",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status__in=["active", "superseded"], activated_at__isnull=False)
                    | models.Q(
                        status__in=["preparing", "suspended", "terminal"],
                        activated_at__isnull=True,
                    )
                ),
                name="ck_tnr_activation_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="suspended", suspension_reason__gt="")
                    | ~models.Q(status="suspended")
                ),
                name="ck_tnr_suspension_reason",
            ),
        ]
        indexes = [
            models.Index(
                fields=["window_days", "facts_as_of"],
                name="idx_tnr_window_facts",
            ),
            models.Index(fields=["status", "created_at"], name="idx_tnr_status_created"),
        ]


class TrendNarrativeWorkSlot(models.Model):
    """One active envelope and at most one newer queued cutoff per window."""

    window_days = models.PositiveSmallIntegerField(primary_key=True)
    active_source_cycle_id = models.CharField(max_length=128, blank=True, default="")
    active_facts_as_of = models.DateTimeField(blank=True, null=True)
    active_run = models.ForeignKey(
        TrendNarrativeRun,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="work_slots",
    )
    snapshot_claim_owner = models.CharField(max_length=128, blank=True, default="")
    snapshot_claim_fence = models.PositiveIntegerField(default=0)
    snapshot_claimed_at = models.DateTimeField(blank=True, null=True)
    snapshot_claim_expires_at = models.DateTimeField(blank=True, null=True)
    queued_source_cycle_id = models.CharField(max_length=128, blank=True, default="")
    queued_facts_as_of = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "trend_narrative_work_slots"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(window_days__in=[1, 7, 30, 365]),
                name="ck_tnws_window",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        active_source_cycle_id="",
                        active_facts_as_of__isnull=True,
                        active_run__isnull=True,
                        snapshot_claim_owner="",
                        snapshot_claim_fence=0,
                        snapshot_claimed_at__isnull=True,
                        snapshot_claim_expires_at__isnull=True,
                    )
                    | models.Q(
                        active_source_cycle_id__gt="",
                        active_facts_as_of__isnull=False,
                    )
                ),
                name="ck_tnws_active_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        snapshot_claim_owner="",
                        snapshot_claim_fence=0,
                        snapshot_claimed_at__isnull=True,
                        snapshot_claim_expires_at__isnull=True,
                    )
                    | models.Q(
                        snapshot_claim_owner__gt="",
                        snapshot_claim_fence__gt=0,
                        snapshot_claimed_at__isnull=False,
                        snapshot_claim_expires_at__gt=models.F(
                            "snapshot_claimed_at"
                        ),
                    )
                ),
                name="ck_tnws_snapshot_claim",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        queued_source_cycle_id="", queued_facts_as_of__isnull=True
                    )
                    | models.Q(
                        queued_source_cycle_id__gt="",
                        queued_facts_as_of__isnull=False,
                    )
                ),
                name="ck_tnws_queued_shape",
            ),
        ]


class TrendNarrativeVisibleRun(models.Model):
    """The one monotonic visible cutoff for a supported time window."""

    window_days = models.PositiveSmallIntegerField(primary_key=True)
    run = models.ForeignKey(
        TrendNarrativeRun,
        on_delete=models.PROTECT,
        related_name="visible_pointers",
    )
    facts_as_of = models.DateTimeField()
    activated_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "trend_narrative_visible_runs"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(window_days__in=[1, 7, 30, 365]),
                name="ck_tnvr_window",
            ),
        ]


class TrendNarrativeDemand(models.Model):
    """Coalesced demand for one brand/window headline projection."""

    class Reason(models.TextChoices):
        VISIBLE = "visible", "Visible"
        PREWARM = "prewarm", "Prewarm"
        OPERATOR = "operator", "Operator"

    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        SCHEDULED = "scheduled", "Scheduled"
        SATISFIED = "satisfied", "Satisfied"
        SUPPRESSED = "suppressed", "Suppressed"
        FAILED = "failed", "Failed"

    brand = models.ForeignKey(
        Brand,
        on_delete=models.CASCADE,
        related_name="trend_narrative_demands",
        db_column="brand_id",
        to_field="nickname",
    )
    window_days = models.PositiveSmallIntegerField()
    target_contract_version = models.CharField(max_length=64)
    target_prompt_version = models.CharField(max_length=255)
    target_model = models.CharField(max_length=128)
    demand_reason = models.CharField(max_length=16, choices=Reason.choices)
    priority = models.PositiveSmallIntegerField(default=10)
    request_count = models.PositiveIntegerField(default=1)
    last_enqueued_request_count = models.PositiveIntegerField(default=0)
    operator_request_count = models.PositiveIntegerField(default=0)
    last_enqueued_operator_request_count = models.PositiveIntegerField(default=0)
    first_requested_at = models.DateTimeField()
    last_requested_at = models.DateTimeField()
    hot_until = models.DateTimeField()
    is_pinned = models.BooleanField(default=False)
    last_material_input_fingerprint = models.CharField(
        max_length=64, blank=True, default=""
    )
    last_enqueued_at = models.DateTimeField(blank=True, null=True)
    last_satisfied_at = models.DateTimeField(blank=True, null=True)
    last_decision_reason = models.CharField(max_length=64, blank=True, default="")
    suppression_count = models.PositiveIntegerField(default=0)
    state = models.CharField(
        max_length=16, choices=State.choices, default=State.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "trend_narrative_demands"
        constraints = [
            models.UniqueConstraint(
                fields=["brand", "window_days"], name="uq_tnd_brand_window"
            ),
            models.CheckConstraint(
                condition=models.Q(window_days__in=[1, 7, 30, 365]),
                name="ck_tnd_window",
            ),
            models.CheckConstraint(
                condition=models.Q(priority__gte=1, priority__lte=100),
                name="ck_tnd_priority",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    last_requested_at__gte=models.F("first_requested_at")
                ),
                name="ck_tnd_request_order",
            ),
            models.CheckConstraint(
                condition=models.Q(hot_until__gte=models.F("last_requested_at")),
                name="ck_tnd_hot_order",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    last_enqueued_request_count__lte=models.F("request_count")
                ),
                name="ck_tnd_enqueued_count",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    last_enqueued_operator_request_count__lte=models.F(
                        "operator_request_count"
                    )
                ),
                name="ck_tnd_operator_count",
            ),
        ]
        indexes = [
            models.Index(
                fields=["window_days", "state", "hot_until"],
                name="idx_tnd_window_due",
            ),
            models.Index(
                fields=["state", "-priority"], name="idx_tnd_state_priority"
            ),
        ]


class TrendNarrativeProviderCall(models.Model):
    """Append-only bounded transport ledger for rank/editor/critic work."""

    class Stage(models.TextChoices):
        RANK = "rank", "Rank"
        EDITOR = "editor", "Editor"
        CRITIC = "critic", "Critic"

    class State(models.TextChoices):
        RESERVED = "reserved", "Reserved"
        SENT = "sent", "Sent"
        COMPLETED = "completed", "Completed"
        AMBIGUOUS = "ambiguous", "Ambiguous"
        FAILED = "failed", "Failed"

    run = models.ForeignKey(
        TrendNarrativeRun,
        on_delete=models.CASCADE,
        related_name="provider_calls",
    )
    stage = models.CharField(max_length=16, choices=Stage.choices)
    batch_key = models.CharField(max_length=128, blank=True, default="")
    request_identity = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    response_hash = models.CharField(max_length=64, blank=True, default="")
    request_packet = models.JSONField(blank=True, null=True)
    response_payload = models.JSONField(blank=True, null=True)
    state = models.CharField(max_length=16, choices=State.choices, default=State.RESERVED)
    claim_owner = models.CharField(max_length=128, blank=True, default="")
    claim_fence = models.PositiveIntegerField(default=0)
    claimed_at = models.DateTimeField(blank=True, null=True)
    claim_expires_at = models.DateTimeField(blank=True, null=True)
    reserved_at = models.DateTimeField()
    sent_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    error_code = models.CharField(max_length=64, blank=True, default="")
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "trend_narrative_provider_calls"
        constraints = [
            models.UniqueConstraint(
                fields=["run", "stage", "batch_key"],
                name="uq_tnpc_run_stage_batch",
            ),
            models.UniqueConstraint(
                fields=["request_identity"], name="uq_tnpc_request_identity"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    stage__in=["rank", "editor", "critic"]
                ),
                name="ck_tnpc_stage",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    state__in=["reserved", "sent", "completed", "ambiguous", "failed"]
                ),
                name="ck_tnpc_state",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(claimed_at__isnull=True, claim_expires_at__isnull=True, claim_owner="", claim_fence=0)
                    | models.Q(claimed_at__isnull=False, claim_expires_at__gt=models.F("claimed_at"), claim_owner__gt="", claim_fence__gt=0)
                ),
                name="ck_tnpc_claim_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(sent_at__isnull=True, state="reserved")
                    | models.Q(sent_at__isnull=False, state__in=["sent", "completed", "ambiguous", "failed"])
                ),
                name="ck_tnpc_sent_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(completed_at__isnull=True, state__in=["reserved", "sent", "ambiguous", "failed"])
                    | models.Q(completed_at__isnull=False, state="completed", response_hash__gt="")
                ),
                name="ck_tnpc_completed_shape",
            ),
        ]
        indexes = [
            models.Index(fields=["state", "claim_expires_at"], name="idx_tnpc_claim_due"),
            models.Index(fields=["run", "stage"], name="idx_tnpc_run_stage"),
        ]


class BrandTrendNarrative(models.Model):
    """One immutable prepared outcome for a brand within a run."""

    class Status(models.TextChoices):
        PREPARED = "prepared", "Prepared"
        APPROVED = "approved", "Approved"
        HELD = "held", "Held"
        UNAVAILABLE = "unavailable", "Unavailable"
        NO_CONTENT = "no_content", "No content"
        DATA_QUALITY_UNAVAILABLE = "data_quality_unavailable", "Data quality unavailable"

    class CriticDecision(models.TextChoices):
        APPROVE = "approve", "Approve"
        REPAIR = "repair", "Repair"
        HOLD = "hold", "Hold"

    class NarrativeKind(models.TextChoices):
        EVENT_LED = "event_led", "Event led"
        CONTENT_SHIFT = "content_shift", "Content shift"
        MIX_SHIFT = "mix_shift", "Mix shift"
        QUIET_CONTEXT = "quiet_context", "Quiet context"

    class Confidence(models.TextChoices):
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"

    run = models.ForeignKey(
        TrendNarrativeRun,
        on_delete=models.CASCADE,
        related_name="brand_narratives",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
        db_column="brand_id",
        to_field="nickname",
    )
    brand_key_snapshot = models.CharField(max_length=64)
    brand_name_en_snapshot = models.TextField()
    brand_name_zh_cn_snapshot = models.TextField()
    status = models.CharField(max_length=32, choices=Status.choices)
    headline_en = models.TextField(blank=True, default="")
    headline_zh_cn = models.TextField(blank=True, default="")
    secondary_en = models.TextField(blank=True, default="")
    secondary_zh_cn = models.TextField(blank=True, default="")
    critic_decision = models.CharField(
        max_length=16, choices=CriticDecision.choices, blank=True, default=""
    )
    critic_review_state = models.CharField(max_length=16, blank=True, default="")
    critic_reason_codes = models.JSONField(default=list, db_default=[])
    critic_audit_eligible = models.BooleanField(default=False)
    narrative_kind = models.CharField(
        max_length=32, choices=NarrativeKind.choices, blank=True, default=""
    )
    confidence = models.CharField(
        max_length=16, choices=Confidence.choices, blank=True, default=""
    )
    propositions = models.JSONField(default=list, db_default=[])
    events = models.JSONField(default=list, db_default=[])
    cited_fact_ids = models.JSONField(default=list, db_default=[])
    cited_evidence_ids = models.JSONField(default=list, db_default=[])
    selected_evidence_packet = models.JSONField(blank=True, null=True)
    final_critic_payload = models.JSONField(blank=True, null=True)
    verified_at = models.DateTimeField(blank=True, null=True)
    attempted_at = models.DateTimeField()
    error_code = models.CharField(max_length=64, blank=True, default="")
    last_good = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="held_successors",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "brand_trend_narratives"
        constraints = [
            models.UniqueConstraint(
                fields=["run", "brand_key_snapshot"],
                name="uq_btn_run_brand",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["prepared", "approved", "held", "unavailable", "no_content", "data_quality_unavailable"]
                ),
                name="ck_btn_status",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="prepared", verified_at__isnull=True)
                    | models.Q(status="approved", verified_at__isnull=False, headline_en__gt="", headline_zh_cn__gt="", secondary_en__gt="", secondary_zh_cn__gt="")
                    | models.Q(status__in=["held", "unavailable", "no_content", "data_quality_unavailable"])
                ),
                name="ck_btn_output_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="held", last_good__isnull=False)
                    | ~models.Q(status="held")
                ),
                name="ck_btn_held_last_good",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    critic_decision__in=["", "approve", "repair", "hold"]
                ),
                name="ck_btn_critic_decision",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    critic_review_state__in=["", "bypassed", "reviewed"]
                ),
                name="ck_btn_critic_review_state",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    narrative_kind__in=[
                        "",
                        "event_led",
                        "content_shift",
                        "mix_shift",
                        "quiet_context",
                    ]
                ),
                name="ck_btn_narrative_kind",
            ),
            models.CheckConstraint(
                condition=models.Q(confidence__in=["", "high", "medium", "low"]),
                name="ck_btn_confidence",
            ),
        ]
        indexes = [
            models.Index(fields=["brand_key_snapshot", "-attempted_at"], name="idx_btn_brand_attempt"),
            models.Index(fields=["run", "status"], name="idx_btn_run_status"),
        ]


class BrandTrendNarrativeText(models.Model):
    """Locale-complete text bundle for a versioned brand narrative."""

    narrative = models.ForeignKey(
        BrandTrendNarrative,
        on_delete=models.CASCADE,
        related_name="localized_texts",
    )
    locale = models.CharField(max_length=8)
    headline = models.TextField()
    secondary = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "brand_trend_narrative_texts"
        constraints = [
            models.UniqueConstraint(
                fields=["narrative", "locale"],
                name="uq_brand_trend_narrative_locale",
            ),
            models.CheckConstraint(
                condition=models.Q(locale__in=["en", "zh-cn", "ja"]),
                name="ck_brand_trend_narrative_locale",
            ),
            models.CheckConstraint(
                condition=~models.Q(headline="") & ~models.Q(secondary=""),
                name="ck_brand_trend_narrative_text",
            ),
        ]


class TrendNarrativeSubject(models.Model):
    """One immutable reported identity on a narrative publication."""

    class Position(models.IntegerChoices):
        PRIMARY = 0, "Primary"
        SECONDARY = 1, "Secondary"

    class SupportType(models.TextChoices):
        MEASURED_CANDIDATE = "measured_candidate", "Measured candidate"
        EVIDENCE_ONLY = "evidence_only", "Evidence only"

    class IdentityType(models.TextChoices):
        BRAND = "brand", "Brand"
        PRODUCT = "product", "Product"
        UNRESOLVED = "unresolved", "Unresolved"

    class EntityType(models.TextChoices):
        COMPANY = "company", "Company"
        BRAND = "brand", "Brand"
        PRODUCT = "product", "Product"
        MODEL = "model", "Model"
        ORGANIZATION = "organization", "Organization"

    trend_narrative = models.ForeignKey(
        TrendNarrative,
        on_delete=models.CASCADE,
        related_name="subjects",
        db_column="trend_narrative_id",
    )
    position = models.PositiveSmallIntegerField(choices=Position.choices)
    support_type = models.CharField(
        max_length=32,
        choices=SupportType.choices,
    )
    entity_type = models.CharField(max_length=16, choices=EntityType.choices)
    identity_type = models.CharField(max_length=16, choices=IdentityType.choices)
    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
        db_column="brand_id",
        to_field="nickname",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
        db_column="product_id",
    )
    observed_name = models.TextField(blank=True, default="")
    canonical_key_snapshot = models.TextField(blank=True, default="")
    name_en_snapshot = models.TextField(blank=True, default="")
    name_zh_cn_snapshot = models.TextField(blank=True, default="")
    candidate_id = models.CharField(max_length=192, blank=True, default="")
    evidence_ids = models.JSONField(blank=True, default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "trend_narrative_subjects"
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["trend_narrative", "position"],
                name="uq_tns_narrative_position",
            ),
            models.CheckConstraint(
                condition=models.Q(position__in=[0, 1]),
                name="ck_tns_position",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    entity_type__in=[
                        "company",
                        "brand",
                        "product",
                        "model",
                        "organization",
                    ]
                ),
                name="ck_tns_entity_type",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        identity_type="brand",
                        product__isnull=True,
                        observed_name="",
                        canonical_key_snapshot__gt="",
                        name_en_snapshot__gt="",
                        name_zh_cn_snapshot__gt="",
                    )
                    | models.Q(
                        identity_type="product",
                        brand__isnull=True,
                        observed_name="",
                        canonical_key_snapshot__gt="",
                        name_en_snapshot__gt="",
                        name_zh_cn_snapshot__gt="",
                    )
                    | models.Q(
                        identity_type="unresolved",
                        brand__isnull=True,
                        product__isnull=True,
                        observed_name__gt="",
                        canonical_key_snapshot="",
                        name_en_snapshot__gt="",
                        name_zh_cn_snapshot__gt="",
                    )
                ),
                name="ck_tns_identity_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        support_type="measured_candidate",
                        candidate_id__gt="",
                        evidence_ids=[],
                    )
                    | (
                        models.Q(
                            support_type="evidence_only",
                            candidate_id="",
                        )
                        & ~models.Q(evidence_ids=[])
                    )
                ),
                name="ck_tns_support_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(support_type="measured_candidate")
                    | models.Q(position=1)
                ),
                name="ck_tns_evidence_pos",
            ),
        ]


class AppliedConfigSnapshot(models.Model):
    artifact = models.TextField(primary_key=True)
    content_hash = models.TextField()
    written_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "_applied_config_snapshot"
DATE_PRECISION_CHOICES = (
    ("day", "Day"),
    ("month", "Month"),
    ("year", "Year"),
    ("unknown", "Unknown"),
)
TEMPORAL_PRECISION_CHOICES = (
    ("datetime", "Date and time"),
    *DATE_PRECISION_CHOICES,
)
REVIEW_STATUS_CHOICES = (
    ("pending", "Pending"),
    ("confirmed", "Confirmed"),
    ("rejected", "Rejected"),
    ("needs_review", "Needs review"),
)
RELATIONSHIP_STATUS_CHOICES = (
    ("current", "Current"),
    ("former", "Former"),
    ("future", "Future"),
    ("unknown", "Unknown"),
)


def _precision_value_condition(
    value_field: str,
    precision_field: str,
    *,
    allow_datetime: bool = False,
) -> models.Q:
    condition = (
        models.Q(
            **{
                f"{value_field}__isnull": True,
                precision_field: "unknown",
            }
        )
        | models.Q(
            **{
                precision_field: "day",
                f"{value_field}__regex": r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
            }
        )
        | models.Q(
            **{
                precision_field: "month",
                f"{value_field}__regex": r"^[0-9]{4}-[0-9]{2}$",
            }
        )
        | models.Q(
            **{
                precision_field: "year",
                f"{value_field}__regex": r"^[0-9]{4}$",
            }
        )
    )
    if allow_datetime:
        condition |= models.Q(
            **{
                precision_field: "datetime",
                f"{value_field}__regex": (
                    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
                    r"[0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]+)?)?"
                    r"(Z|[+-][0-9]{2}:[0-9]{2})$"
                ),
            }
        )
    return condition


class Person(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_name = models.TextField()
    display_name_en = models.TextField(blank=True, null=True)
    display_name_zh_cn = models.TextField(blank=True, null=True)
    display_name_ja = models.TextField(blank=True, null=True)
    date_of_birth = models.CharField(max_length=10, blank=True, null=True)
    date_of_birth_precision = models.CharField(
        max_length=16,
        choices=DATE_PRECISION_CHOICES,
        default="unknown",
    )
    # The owner selected this column name explicitly.
    sexs = models.TextField(blank=True, null=True)
    nationality = models.TextField(blank=True, null=True)
    ethnicity = models.TextField(blank=True, null=True)
    primary_language = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "people"
        ordering = ["display_name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=_precision_value_condition(
                    "date_of_birth", "date_of_birth_precision"
                ),
                name="ck_people_dob_precision",
            ),
        ]


class PersonAccount(models.Model):
    pk = models.CompositePrimaryKey("person", "account")
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="account_links",
        db_column="person_id",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="person_links",
        db_column="author_id",
        to_field="author_id",
    )
    is_primary = models.BooleanField(default=False)
    first_observed_at = models.DateTimeField()
    last_observed_at = models.DateTimeField()
    confidence = models.FloatField(blank=True, null=True)
    resolution_status = models.CharField(
        max_length=16,
        choices=REVIEW_STATUS_CHOICES,
        default="pending",
    )
    review_note = models.TextField(blank=True, default="")
    reviewed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "people_accounts"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    resolution_status__in=[
                        value for value, _label in REVIEW_STATUS_CHOICES
                    ]
                ),
                name="ck_people_accounts_resolution",
            ),
            models.CheckConstraint(
                condition=models.Q(last_observed_at__gte=models.F("first_observed_at")),
                name="ck_people_accounts_window",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(confidence__isnull=True)
                    | (models.Q(confidence__gte=0.0) & models.Q(confidence__lte=1.0))
                ),
                name="ck_people_accounts_conf",
            ),
            models.UniqueConstraint(
                fields=["account"],
                condition=models.Q(resolution_status="confirmed"),
                name="uq_people_accounts_confirmed",
            ),
            models.UniqueConstraint(
                fields=["person"],
                condition=models.Q(
                    resolution_status="confirmed",
                    is_primary=True,
                ),
                name="uq_people_accounts_primary",
            ),
        ]


class AccountProfileSnapshot(models.Model):
    id = models.BigAutoField(primary_key=True)
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="profile_snapshots",
        db_column="author_id",
        to_field="author_id",
    )
    profile_hash = models.CharField(max_length=64)
    first_observed_at = models.DateTimeField()
    last_observed_at = models.DateTimeField()
    observation_count = models.PositiveIntegerField(default=1)
    first_source_kind = models.CharField(max_length=32)
    first_source_post = models.ForeignKey(
        Post,
        on_delete=models.SET_NULL,
        related_name="profile_snapshots",
        blank=True,
        null=True,
    )
    first_source_run = models.TextField(blank=True, null=True)
    handle = models.CharField(max_length=64, blank=True, null=True)
    display_name = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    profile_bio_text = models.TextField(blank=True, null=True)
    location = models.TextField(blank=True, null=True)
    profile_image_url = models.URLField(max_length=2048, blank=True, null=True)
    verified = models.BooleanField(blank=True, null=True)
    is_blue_verified = models.BooleanField(blank=True, null=True)
    verified_type = models.TextField(blank=True, null=True)
    affiliate_target_username = models.CharField(max_length=64, blank=True, null=True)
    affiliate_target_url = models.URLField(max_length=2048, blank=True, null=True)
    affiliate_label_description = models.TextField(blank=True, null=True)
    affiliate_badge_image_url = models.URLField(max_length=2048, blank=True, null=True)
    affiliate_label_type = models.CharField(max_length=128, blank=True, null=True)
    affiliate_display_type = models.CharField(max_length=128, blank=True, null=True)
    present_fields = models.JSONField(default=list)
    profile_data = models.JSONField(default=dict)
    raw_profile_payload = models.JSONField(blank=True, null=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "account_profile_snapshots"
        ordering = ["account_id", "first_observed_at", "id"]
        indexes = [
            models.Index(
                fields=["account", "-last_observed_at"],
                name="idx_profile_snap_account_last",
            ),
            models.Index(fields=["profile_hash"], name="idx_profile_snap_hash"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(last_observed_at__gte=models.F("first_observed_at")),
                name="ck_profile_snap_window",
            ),
            models.CheckConstraint(
                condition=models.Q(observation_count__gte=1),
                name="ck_profile_snap_count",
            ),
            models.UniqueConstraint(
                fields=["account", "profile_hash", "first_observed_at"],
                name="uq_profile_snap_identity",
            ),
        ]


class PersonBrandAffiliation(models.Model):
    AFFILIATION_TYPES = (
        ("employment", "Employment"),
        ("founder", "Founder"),
        ("advisor", "Advisor"),
        ("board_member", "Board member"),
        ("contractor", "Contractor"),
        ("ambassador", "Ambassador"),
        ("creator_partner", "Creator partner"),
        ("affiliate", "Affiliate"),
        ("investor", "Investor"),
        ("community", "Community"),
        ("other", "Other"),
    )

    id = models.BigAutoField(primary_key=True)
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="brand_affiliations",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="person_affiliations",
        to_field="nickname",
        blank=True,
        null=True,
    )
    brand_discovery_candidate = models.ForeignKey(
        "BrandDiscoveryCandidate",
        on_delete=models.PROTECT,
        related_name="person_affiliations",
        blank=True,
        null=True,
    )
    affiliation_type = models.CharField(max_length=32, choices=AFFILIATION_TYPES)
    observed_organization_name = models.TextField()
    observed_organization_handle = models.CharField(
        max_length=64, blank=True, null=True
    )
    title_raw = models.TextField(blank=True, null=True)
    title_normalized = models.TextField(blank=True, null=True)
    department = models.TextField(blank=True, null=True)
    team = models.TextField(blank=True, null=True)
    job_function = models.TextField(blank=True, null=True)
    seniority = models.TextField(blank=True, null=True)
    employment_type = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=16,
        choices=RELATIONSHIP_STATUS_CHOICES,
        default="unknown",
    )
    start_date = models.CharField(max_length=10, blank=True, null=True)
    start_date_precision = models.CharField(
        max_length=16,
        choices=DATE_PRECISION_CHOICES,
        default="unknown",
    )
    end_date = models.CharField(max_length=10, blank=True, null=True)
    end_date_precision = models.CharField(
        max_length=16,
        choices=DATE_PRECISION_CHOICES,
        default="unknown",
    )
    location = models.TextField(blank=True, null=True)
    workplace_type = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    confidence = models.FloatField(blank=True, null=True)
    review_status = models.CharField(
        max_length=16,
        choices=REVIEW_STATUS_CHOICES,
        default="pending",
    )
    review_note = models.TextField(blank=True, default="")
    reviewed_at = models.DateTimeField(blank=True, null=True)
    source_system = models.CharField(max_length=64, blank=True, null=True)
    external_id = models.TextField(blank=True, null=True)
    claim_identity = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "people_brand_affiliations"
        ordering = ["person_id", "brand_id", "id"]
        indexes = [
            models.Index(
                fields=["brand", "affiliation_type", "status"],
                name="idx_pba_brand_type_status",
            ),
            models.Index(
                fields=["person", "affiliation_type"],
                name="idx_pba_person_type",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        brand__isnull=False,
                        brand_discovery_candidate__isnull=True,
                    )
                    | models.Q(
                        brand__isnull=True,
                        brand_discovery_candidate__isnull=False,
                    )
                ),
                name="ck_pba_one_organization",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    affiliation_type__in=[
                        "employment",
                        "founder",
                        "advisor",
                        "board_member",
                        "contractor",
                        "ambassador",
                        "creator_partner",
                        "affiliate",
                        "investor",
                        "community",
                        "other",
                    ]
                ),
                name="ck_pba_affiliation_type",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[value for value, _label in RELATIONSHIP_STATUS_CHOICES]
                ),
                name="ck_pba_status",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    review_status__in=[value for value, _label in REVIEW_STATUS_CHOICES]
                ),
                name="ck_pba_review_status",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(confidence__isnull=True)
                    | (models.Q(confidence__gte=0.0) & models.Q(confidence__lte=1.0))
                ),
                name="ck_pba_confidence",
            ),
            models.CheckConstraint(
                condition=_precision_value_condition(
                    "start_date", "start_date_precision"
                ),
                name="ck_pba_start_precision",
            ),
            models.CheckConstraint(
                condition=_precision_value_condition("end_date", "end_date_precision"),
                name="ck_pba_end_precision",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(start_date__isnull=True)
                    | models.Q(end_date__isnull=True)
                    | ~models.Q(start_date_precision=models.F("end_date_precision"))
                    | models.Q(start_date__lte=models.F("end_date"))
                ),
                name="ck_pba_comparable_dates",
            ),
        ]


class PersonBrandAffiliationEvidence(models.Model):
    id = models.BigAutoField(primary_key=True)
    affiliation = models.ForeignKey(
        PersonBrandAffiliation,
        on_delete=models.CASCADE,
        related_name="evidence",
    )
    source_post = models.ForeignKey(
        Post,
        on_delete=models.SET_NULL,
        related_name="affiliation_evidence",
        blank=True,
        null=True,
    )
    source_profile_snapshot = models.ForeignKey(
        AccountProfileSnapshot,
        on_delete=models.SET_NULL,
        related_name="affiliation_evidence",
        blank=True,
        null=True,
    )
    source_url = models.URLField(max_length=2048, blank=True, null=True)
    evidence_text = models.TextField(blank=True, default="")
    observed_at = models.DateTimeField()
    extracted_claim_data = models.JSONField(default=dict)
    extraction_method = models.CharField(max_length=64)
    extraction_model = models.TextField(blank=True, null=True)
    extraction_prompt_version = models.TextField(blank=True, null=True)
    confidence = models.FloatField(blank=True, null=True)
    review_status = models.CharField(
        max_length=16,
        choices=REVIEW_STATUS_CHOICES,
        default="pending",
    )
    reviewer = models.TextField(blank=True, null=True)
    review_note = models.TextField(blank=True, default="")
    reviewed_at = models.DateTimeField(blank=True, null=True)
    evidence_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "people_brand_affiliation_evidence"
        ordering = ["affiliation_id", "observed_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    review_status__in=[value for value, _label in REVIEW_STATUS_CHOICES]
                ),
                name="ck_pbae_review_status",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(source_post__isnull=False)
                    | models.Q(source_profile_snapshot__isnull=False)
                    | (models.Q(source_url__isnull=False) & ~models.Q(source_url=""))
                ),
                name="ck_pbae_has_source",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(confidence__isnull=True)
                    | (models.Q(confidence__gte=0.0) & models.Q(confidence__lte=1.0))
                ),
                name="ck_pbae_confidence",
            ),
            models.UniqueConstraint(
                fields=["affiliation", "evidence_hash"],
                name="uq_pbae_affiliation_hash",
            ),
        ]


class BrandDiscoveryCandidate(models.Model):
    id = models.BigAutoField(primary_key=True)
    observed_name = models.TextField()
    aliases = models.JSONField(default=list)
    candidate_handles = models.JSONField(default=list)
    organization_ai_relationship = models.TextField(blank=True, null=True)
    source_post = models.ForeignKey(
        Post,
        on_delete=models.SET_NULL,
        related_name="brand_discovery_candidates",
        blank=True,
        null=True,
    )
    source_query = models.ForeignKey(
        SearchQuery,
        on_delete=models.SET_NULL,
        related_name="brand_discovery_candidates",
        blank=True,
        null=True,
    )
    source_identities = models.JSONField(default=list)
    confidence = models.FloatField(blank=True, null=True)
    verification_status = models.CharField(
        max_length=16,
        choices=REVIEW_STATUS_CHOICES,
        default="pending",
    )
    reviewer = models.TextField(blank=True, null=True)
    review_note = models.TextField(blank=True, default="")
    reviewed_at = models.DateTimeField(blank=True, null=True)
    reviewed_brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="discovery_candidates",
        blank=True,
        null=True,
        to_field="nickname",
    )
    candidate_identity = models.CharField(max_length=64, unique=True)
    first_observed_at = models.DateTimeField()
    last_observed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "brand_discovery_candidates"
        ordering = ["observed_name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    verification_status__in=[
                        value for value, _label in REVIEW_STATUS_CHOICES
                    ]
                ),
                name="ck_brand_candidate_review",
            ),
            models.CheckConstraint(
                condition=models.Q(last_observed_at__gte=models.F("first_observed_at")),
                name="ck_brand_candidate_window",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(confidence__isnull=True)
                    | (models.Q(confidence__gte=0.0) & models.Q(confidence__lte=1.0))
                ),
                name="ck_brand_candidate_conf",
            ),
        ]


class JobListing(models.Model):
    APPLICATION_ROUTE_KINDS = (
        ("direct_url", "Direct URL"),
        ("careers_page", "Careers page"),
        ("email", "Email"),
        ("qr", "QR"),
        ("direct_message", "Direct message"),
        ("other", "Other"),
        ("unresolved", "Unresolved"),
    )
    LISTING_STATUSES = (
        ("open", "Open"),
        ("closed", "Closed"),
        ("future", "Future"),
        ("unknown", "Unknown"),
    )

    id = models.BigAutoField(primary_key=True)
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="job_listings",
        blank=True,
        null=True,
        to_field="nickname",
    )
    brand_discovery_candidate = models.ForeignKey(
        BrandDiscoveryCandidate,
        on_delete=models.PROTECT,
        related_name="job_listings",
        blank=True,
        null=True,
    )
    hiring_organization = models.TextField()
    # Null means the listing was extracted from an X post. A non-null key
    # makes the official-site reconciler the authority for this row.
    source_key = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    source_name = models.TextField(blank=True, null=True)
    source_listing_id = models.TextField(blank=True, null=True)
    canonical_url = models.URLField(max_length=2048, blank=True, null=True)
    application_url = models.URLField(max_length=2048, blank=True, null=True)
    application_route_kind = models.CharField(
        max_length=32,
        choices=APPLICATION_ROUTE_KINDS,
        default="unresolved",
    )
    application_contact = models.TextField(blank=True, null=True)
    application_resolution_status = models.CharField(
        max_length=32, blank=True, null=True
    )
    title = models.TextField()
    description_html = models.TextField(blank=True, null=True)
    description_text = models.TextField(blank=True, null=True)
    department = models.TextField(blank=True, null=True)
    team = models.TextField(blank=True, null=True)
    job_function = models.TextField(blank=True, null=True)
    seniority = models.TextField(blank=True, null=True)
    employment_type = models.TextField(blank=True, null=True)
    workplace_type = models.TextField(blank=True, null=True)
    locations_raw = models.TextField(blank=True, null=True)
    locations = models.JSONField(default=list)
    remote_applicant_restrictions = models.TextField(blank=True, null=True)
    salary_text = models.TextField(blank=True, null=True)
    salary_min = models.DecimalField(
        max_digits=18, decimal_places=2, blank=True, null=True
    )
    salary_max = models.DecimalField(
        max_digits=18, decimal_places=2, blank=True, null=True
    )
    salary_currency = models.CharField(max_length=3, blank=True, null=True)
    salary_period = models.CharField(max_length=32, blank=True, null=True)
    posted_at = models.DateTimeField(blank=True, null=True)
    updated_source_at = models.DateTimeField(blank=True, null=True)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    expires_at = models.DateTimeField(blank=True, null=True)
    closed_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(
        max_length=16,
        choices=LISTING_STATUSES,
        default="unknown",
    )
    consecutive_missing_snapshots = models.PositiveSmallIntegerField(default=0)
    last_complete_source_sync_at = models.DateTimeField(blank=True, null=True)
    campaign_openings = models.PositiveIntegerField(blank=True, null=True)
    role_openings = models.PositiveIntegerField(blank=True, null=True)
    skills = models.JSONField(default=list)
    responsibilities = models.JSONField(default=list)
    qualifications = models.JSONField(default=list)
    education_requirements = models.TextField(blank=True, null=True)
    experience_requirements = models.TextField(blank=True, null=True)
    benefits = models.JSONField(default=list)
    eligibility = models.TextField(blank=True, null=True)
    source_language = models.CharField(max_length=32, blank=True, null=True)
    organization_ai_relationship = models.TextField(blank=True, null=True)
    role_ai_relationship = models.TextField(blank=True, null=True)
    listing_identity = models.CharField(max_length=64, unique=True)
    content_hash = models.CharField(max_length=64, blank=True, null=True)
    extraction_version = models.TextField(blank=True, null=True)
    extraction_confidence = models.FloatField(blank=True, null=True)
    raw_payload = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "job_listings"
        ordering = ["-first_seen_at", "id"]
        indexes = [
            models.Index(fields=["brand", "status"], name="idx_jobs_brand_status"),
            models.Index(
                fields=["source_key", "status"], name="idx_jobs_source_status"
            ),
            models.Index(
                fields=["status", "expires_at"], name="idx_jobs_status_expiry"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        brand__isnull=False,
                        brand_discovery_candidate__isnull=True,
                    )
                    | models.Q(
                        brand__isnull=True,
                        brand_discovery_candidate__isnull=False,
                    )
                ),
                name="ck_jobs_one_organization",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    application_route_kind__in=[
                        "direct_url",
                        "careers_page",
                        "email",
                        "qr",
                        "direct_message",
                        "other",
                        "unresolved",
                    ]
                ),
                name="ck_jobs_application_route",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["open", "closed", "future", "unknown"]),
                name="ck_jobs_status",
            ),
            models.CheckConstraint(
                condition=models.Q(last_seen_at__gte=models.F("first_seen_at")),
                name="ck_jobs_seen_window",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(salary_min__isnull=True)
                    | models.Q(salary_max__isnull=True)
                    | models.Q(salary_max__gte=models.F("salary_min"))
                ),
                name="ck_jobs_salary_range",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(salary_min__isnull=True)
                    | models.Q(salary_min__gte=0)
                )
                & (
                    models.Q(salary_max__isnull=True)
                    | models.Q(salary_max__gte=0)
                ),
                name="ck_jobs_salary_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(campaign_openings__isnull=True)
                    | models.Q(campaign_openings__gte=1)
                ),
                name="ck_jobs_campaign_openings",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(role_openings__isnull=True)
                    | models.Q(role_openings__gte=1)
                ),
                name="ck_jobs_role_openings",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(extraction_confidence__isnull=True)
                    | (
                        models.Q(extraction_confidence__gte=0.0)
                        & models.Q(extraction_confidence__lte=1.0)
                    )
                ),
                name="ck_jobs_extraction_conf",
            ),
        ]


class JobSourceSyncRun(models.Model):
    RUN_STATUSES = (
        ("running", "Running"),
        ("succeeded", "Succeeded"),
        ("partial", "Partial"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
    )

    id = models.BigAutoField(primary_key=True)
    source_key = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=RUN_STATUSES, default="running")
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(blank=True, null=True)
    snapshot_complete = models.BooleanField(default=False)
    declared_total = models.PositiveIntegerField(blank=True, null=True)
    observed_total = models.PositiveIntegerField(blank=True, null=True)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    unchanged_count = models.PositiveIntegerField(default=0)
    reopened_count = models.PositiveIntegerField(default=0)
    closed_count = models.PositiveIntegerField(default=0)
    error_summary = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "job_source_sync_runs"
        ordering = ["-started_at", "id"]
        indexes = [
            models.Index(
                fields=["source_key", "started_at"],
                name="idx_job_sync_source_started",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["running", "succeeded", "partial", "failed", "skipped"]
                ),
                name="ck_job_sync_run_status",
            ),
        ]


class JobSourceState(models.Model):
    source_key = models.CharField(max_length=64, primary_key=True)
    lease_token = models.CharField(max_length=64, blank=True, null=True)
    lease_expires_at = models.DateTimeField(blank=True, null=True)
    active_run = models.ForeignKey(
        JobSourceSyncRun,
        on_delete=models.SET_NULL,
        related_name="active_source_states",
        blank=True,
        null=True,
    )
    last_successful_at = models.DateTimeField(blank=True, null=True)
    last_snapshot_count = models.PositiveIntegerField(blank=True, null=True)
    last_error = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "job_source_states"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(lease_token__isnull=True, lease_expires_at__isnull=True)
                    | models.Q(
                        lease_token__isnull=False, lease_expires_at__isnull=False
                    )
                ),
                name="ck_job_source_lease_complete",
            )
        ]

    def lease_is_active(self, *, now=None) -> bool:
        current = now or timezone.now()
        return bool(
            self.lease_token
            and self.lease_expires_at
            and self.lease_expires_at > current
        )


class JobListingEvidence(models.Model):
    SOURCE_RELATIONSHIPS = (
        ("official", "Official"),
        ("staff", "Staff"),
        ("third_party", "Third party"),
    )
    EXTRACTION_METHODS = (
        ("structured_text", "Structured text"),
        ("ocr", "OCR"),
        ("vision", "Vision"),
        ("manual", "Manual"),
    )

    id = models.BigAutoField(primary_key=True)
    listing = models.ForeignKey(
        JobListing,
        on_delete=models.CASCADE,
        related_name="evidence",
    )
    source_post = models.ForeignKey(
        Post,
        on_delete=models.SET_NULL,
        related_name="job_listing_evidence",
        blank=True,
        null=True,
    )
    source_url = models.URLField(max_length=2048, blank=True, null=True)
    observed_author_handle = models.CharField(max_length=64, blank=True, null=True)
    observed_author_display_name = models.TextField(blank=True, null=True)
    source_relationship = models.CharField(max_length=16, choices=SOURCE_RELATIONSHIPS)
    evidence_text = models.TextField(blank=True, default="")
    linked_urls = models.JSONField(default=list)
    observed_at = models.DateTimeField()
    media_url = models.URLField(max_length=2048, blank=True, null=True)
    media_hash = models.CharField(max_length=64, blank=True, null=True)
    extraction_method = models.CharField(max_length=32, choices=EXTRACTION_METHODS)
    image_derived_fields = models.JSONField(default=list)
    confidence = models.FloatField(blank=True, null=True)
    raw_evidence = models.JSONField(blank=True, null=True)
    extraction_identity = models.CharField(max_length=64)
    evidence_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "job_listing_evidence"
        ordering = ["listing_id", "observed_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    source_relationship__in=[
                        "official",
                        "staff",
                        "third_party",
                    ]
                ),
                name="ck_job_evidence_relationship",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    extraction_method__in=[
                        "structured_text",
                        "ocr",
                        "vision",
                        "manual",
                    ]
                ),
                name="ck_job_evidence_method",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(source_post__isnull=False)
                    | (models.Q(source_url__isnull=False) & ~models.Q(source_url=""))
                    | (models.Q(media_url__isnull=False) & ~models.Q(media_url=""))
                ),
                name="ck_job_evidence_has_source",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(confidence__isnull=True)
                    | (models.Q(confidence__gte=0.0) & models.Q(confidence__lte=1.0))
                ),
                name="ck_job_evidence_conf",
            ),
            models.UniqueConstraint(
                fields=["listing", "evidence_hash"],
                name="uq_job_evidence_hash",
            ),
        ]


class DiscoveryRunBase(models.Model):
    RUN_STATUSES = (
        ("planned", "Planned"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("truncated", "Truncated"),
        ("blocked", "Blocked"),
    )

    run_identity = models.CharField(max_length=64, unique=True)
    run_id = models.TextField()
    cycle_id = models.TextField(blank=True, null=True)
    query = models.ForeignKey(SearchQuery, on_delete=models.PROTECT, related_name="+")
    query_text = models.TextField()
    query_hash = models.CharField(max_length=64)
    query_pack_version = models.TextField()
    provider_boundary = models.TextField()
    tool_boundary = models.TextField(blank=True, null=True)
    language = models.CharField(max_length=16)
    query_family = models.CharField(max_length=32)
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    input_cursor = models.TextField(blank=True, null=True)
    output_cursor = models.TextField(blank=True, null=True)
    reviewed_post_count = models.PositiveIntegerField(default=0)
    accepted_post_count = models.PositiveIntegerField(default=0)
    excluded_count = models.PositiveIntegerField(default=0)
    exclusion_reasons = models.JSONField(default=dict)
    discovered_organization_count = models.PositiveIntegerField(default=0)
    provider_capabilities = models.JSONField(default=dict)
    provider_call_count = models.PositiveIntegerField(default=0)
    provider_credit_count = models.PositiveIntegerField(default=0)
    telemetry = models.JSONField(default=dict)
    limitations = models.JSONField(default=list)
    status = models.CharField(
        max_length=16,
        choices=RUN_STATUSES,
        default="planned",
    )
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    completion_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class JobDiscoveryRun(DiscoveryRunBase):
    extracted_listing_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "job_discovery_runs"
        ordering = ["-window_start", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        value for value, _label in DiscoveryRunBase.RUN_STATUSES
                    ]
                ),
                name="ck_job_runs_status",
            ),
            models.CheckConstraint(
                condition=models.Q(window_end__gt=models.F("window_start")),
                name="ck_job_runs_window",
            ),
        ]


class PersonnelDiscoveryRun(DiscoveryRunBase):
    extracted_affiliation_count = models.PositiveIntegerField(default=0)
    extracted_evidence_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "personnel_discovery_runs"
        ordering = ["-window_start", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        value for value, _label in DiscoveryRunBase.RUN_STATUSES
                    ]
                ),
                name="ck_personnel_runs_status",
            ),
            models.CheckConstraint(
                condition=models.Q(window_end__gt=models.F("window_start")),
                name="ck_personnel_runs_window",
            ),
        ]


class Event(models.Model):
    ATTENDANCE_MODES = (
        ("in_person", "In person"),
        ("online_live", "Online live"),
        ("hybrid", "Hybrid"),
        ("unknown", "Unknown"),
    )
    SOURCE_STATUSES = (
        ("scheduled", "Scheduled"),
        ("live", "Live"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("postponed", "Postponed"),
        ("unknown", "Unknown"),
    )

    id = models.BigAutoField(primary_key=True)
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="events",
        to_field="nickname",
    )
    source_post = models.ForeignKey(
        Post,
        on_delete=models.SET_NULL,
        related_name="extracted_events",
        blank=True,
        null=True,
    )
    source_url = models.URLField(max_length=2048, blank=True, null=True)
    title = models.TextField()
    organizer_name = models.TextField()
    organizer_handle = models.CharField(max_length=64, blank=True, null=True)
    attendance_mode = models.CharField(
        max_length=16,
        choices=ATTENDANCE_MODES,
        default="unknown",
    )
    physical_location = models.TextField(blank=True, null=True)
    virtual_location = models.TextField(blank=True, null=True)
    attendance_url = models.URLField(max_length=2048, blank=True, null=True)
    start_value = models.CharField(max_length=64, blank=True, null=True)
    start_precision = models.CharField(
        max_length=16,
        choices=TEMPORAL_PRECISION_CHOICES,
        default="unknown",
    )
    end_value = models.CharField(max_length=64, blank=True, null=True)
    end_precision = models.CharField(
        max_length=16,
        choices=TEMPORAL_PRECISION_CHOICES,
        default="unknown",
    )
    source_timezone = models.CharField(max_length=64, blank=True, null=True)
    source_schedule_text = models.TextField(blank=True, null=True)
    source_status = models.CharField(
        max_length=16,
        choices=SOURCE_STATUSES,
        default="unknown",
    )
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    event_identity = models.CharField(max_length=64, unique=True)
    content_hash = models.CharField(max_length=64, blank=True, null=True)
    extraction_version = models.TextField(blank=True, null=True)
    extraction_confidence = models.FloatField(blank=True, null=True)
    review_status = models.CharField(
        max_length=16,
        choices=REVIEW_STATUS_CHOICES,
        default="pending",
    )
    raw_payload = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "events"
        ordering = ["-first_seen_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    attendance_mode__in=[
                        "in_person",
                        "online_live",
                        "hybrid",
                        "unknown",
                    ]
                ),
                name="ck_events_attendance_mode",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    source_status__in=[
                        "scheduled",
                        "live",
                        "completed",
                        "cancelled",
                        "postponed",
                        "unknown",
                    ]
                ),
                name="ck_events_source_status",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    review_status__in=[value for value, _label in REVIEW_STATUS_CHOICES]
                ),
                name="ck_events_review_status",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(source_post__isnull=False)
                    | (models.Q(source_url__isnull=False) & ~models.Q(source_url=""))
                ),
                name="ck_events_has_source",
            ),
            models.CheckConstraint(
                condition=models.Q(last_seen_at__gte=models.F("first_seen_at")),
                name="ck_events_seen_window",
            ),
            models.CheckConstraint(
                condition=_precision_value_condition(
                    "start_value", "start_precision", allow_datetime=True
                ),
                name="ck_events_start_precision",
            ),
            models.CheckConstraint(
                condition=_precision_value_condition(
                    "end_value", "end_precision", allow_datetime=True
                ),
                name="ck_events_end_precision",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(extraction_confidence__isnull=True)
                    | (
                        models.Q(extraction_confidence__gte=0.0)
                        & models.Q(extraction_confidence__lte=1.0)
                    )
                ),
                name="ck_events_extraction_conf",
            ),
        ]


class Opportunity(models.Model):
    OPPORTUNITY_TYPES = (
        ("giveaway", "Giveaway"),
        ("discount", "Discount"),
        ("free_credits", "Free credits"),
        ("beta_access", "Beta access"),
        ("grant", "Grant"),
        ("bounty", "Bounty"),
        ("contest", "Contest"),
        ("referral", "Referral"),
        ("collaboration", "Collaboration"),
        ("other", "Other"),
    )
    SOURCE_STATUSES = (
        ("upcoming", "Upcoming"),
        ("open", "Open"),
        ("closed", "Closed"),
        ("cancelled", "Cancelled"),
        ("unknown", "Unknown"),
    )

    id = models.BigAutoField(primary_key=True)
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="opportunities",
        to_field="nickname",
    )
    related_event = models.ForeignKey(
        Event,
        on_delete=models.SET_NULL,
        related_name="opportunities",
        blank=True,
        null=True,
    )
    source_post = models.ForeignKey(
        Post,
        on_delete=models.SET_NULL,
        related_name="extracted_opportunities",
        blank=True,
        null=True,
    )
    source_url = models.URLField(max_length=2048, blank=True, null=True)
    sponsor_name = models.TextField()
    sponsor_handle = models.CharField(max_length=64, blank=True, null=True)
    opportunity_type = models.CharField(
        max_length=32,
        choices=OPPORTUNITY_TYPES,
    )
    action_type = models.TextField()
    action_url = models.URLField(max_length=2048, blank=True, null=True)
    benefit_type = models.TextField()
    benefit_value = models.DecimalField(
        max_digits=18, decimal_places=2, blank=True, null=True
    )
    benefit_currency = models.CharField(max_length=8, blank=True, null=True)
    benefit_text = models.TextField(blank=True, null=True)
    eligibility = models.TextField(blank=True, null=True)
    geographic_restrictions = models.TextField(blank=True, null=True)
    open_value = models.CharField(max_length=64, blank=True, null=True)
    open_precision = models.CharField(
        max_length=16,
        choices=TEMPORAL_PRECISION_CHOICES,
        default="unknown",
    )
    close_value = models.CharField(max_length=64, blank=True, null=True)
    close_precision = models.CharField(
        max_length=16,
        choices=TEMPORAL_PRECISION_CHOICES,
        default="unknown",
    )
    source_timezone = models.CharField(max_length=64, blank=True, null=True)
    source_availability_text = models.TextField(blank=True, null=True)
    source_status = models.CharField(
        max_length=16,
        choices=SOURCE_STATUSES,
        default="unknown",
    )
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    opportunity_identity = models.CharField(max_length=64, unique=True)
    content_hash = models.CharField(max_length=64, blank=True, null=True)
    extraction_version = models.TextField(blank=True, null=True)
    extraction_confidence = models.FloatField(blank=True, null=True)
    review_status = models.CharField(
        max_length=16,
        choices=REVIEW_STATUS_CHOICES,
        default="pending",
    )
    raw_payload = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "opportunities"
        ordering = ["-first_seen_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    opportunity_type__in=[
                        "giveaway",
                        "discount",
                        "free_credits",
                        "beta_access",
                        "grant",
                        "bounty",
                        "contest",
                        "referral",
                        "collaboration",
                        "other",
                    ]
                ),
                name="ck_opportunities_type",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    source_status__in=[
                        "upcoming",
                        "open",
                        "closed",
                        "cancelled",
                        "unknown",
                    ]
                ),
                name="ck_opportunities_source_status",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    review_status__in=[value for value, _label in REVIEW_STATUS_CHOICES]
                ),
                name="ck_opportunities_review_status",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(source_post__isnull=False)
                    | (models.Q(source_url__isnull=False) & ~models.Q(source_url=""))
                ),
                name="ck_opportunities_has_source",
            ),
            models.CheckConstraint(
                condition=models.Q(last_seen_at__gte=models.F("first_seen_at")),
                name="ck_opportunities_seen_window",
            ),
            models.CheckConstraint(
                condition=_precision_value_condition(
                    "open_value", "open_precision", allow_datetime=True
                ),
                name="ck_opportunities_open_precision",
            ),
            models.CheckConstraint(
                condition=_precision_value_condition(
                    "close_value", "close_precision", allow_datetime=True
                ),
                name="ck_opportunities_close_precision",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(extraction_confidence__isnull=True)
                    | (
                        models.Q(extraction_confidence__gte=0.0)
                        & models.Q(extraction_confidence__lte=1.0)
                    )
                ),
                name="ck_opportunities_extraction_conf",
            ),
        ]


class TargetedExtractionState(models.Model):
    STATUSES = (
        ("pending", "Pending"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
    )

    id = models.BigAutoField(primary_key=True)
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="targeted_extraction_states",
        db_column="post_id",
        to_field="tweet_id",
    )
    role = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=STATUSES, default="pending")
    content_identity = models.CharField(max_length=64)
    model = models.TextField()
    prompt_version = models.CharField(max_length=64)
    attempts = models.PositiveIntegerField(default=0)
    result_hash = models.CharField(max_length=64, blank=True, null=True)
    last_error_code = models.CharField(max_length=128, blank=True, default="")
    last_attempted_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "targeted_extraction_states"
        indexes = [
            models.Index(fields=["status", "role"], name="idx_target_extract_due")
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["pending", "succeeded", "failed"]),
                name="ck_target_extract_status",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    role__in=[
                        "event_extraction",
                        "opportunity_extraction",
                        "job_listing_extraction",
                        "personnel_change_extraction",
                        "profile_affiliation_extraction",
                    ]
                ),
                name="ck_target_extract_role",
            ),
            models.UniqueConstraint(
                fields=["post", "role"], name="uq_target_extract_post_role"
            ),
        ]


class TargetedExtractionAttempt(models.Model):
    OUTCOMES = (
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
    )

    id = models.BigAutoField(primary_key=True)
    state = models.ForeignKey(
        TargetedExtractionState,
        on_delete=models.CASCADE,
        related_name="attempt_events",
    )
    attempt_identity = models.CharField(max_length=64, unique=True)
    attempted_at = models.DateTimeField()
    outcome = models.CharField(max_length=16, choices=OUTCOMES)
    model = models.TextField()
    prompt_version = models.CharField(max_length=64)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        db_table = "targeted_extraction_attempts"
        ordering = ["attempted_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(outcome__in=["succeeded", "failed"]),
                name="ck_target_attempt_outcome",
            )
        ]
