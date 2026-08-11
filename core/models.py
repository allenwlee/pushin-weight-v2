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

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from django.db import models, transaction
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

    class Meta:
        db_table = "accounts"
        indexes = [
            models.Index(fields=["handle"], name="idx_accounts_handle"),
            models.Index(fields=["last_seen_at"], name="idx_accounts_last_seen_at"),
        ]
        ordering = ["handle"]

    def __str__(self) -> str:
        return f"@{self.handle}"


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
    ):
        """Claim one due interval with PostgreSQL skip-locked semantics."""

        now = now or timezone.now()
        with transaction.atomic():
            self.recover_expired_claims(now=now)
            states = ["pending"]
            if include_quarantined:
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


class AppliedConfigSnapshot(models.Model):
    artifact = models.TextField(primary_key=True)
    content_hash = models.TextField()
    written_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "_applied_config_snapshot"
