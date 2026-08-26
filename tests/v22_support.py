"""Shared PostgreSQL-only support for the transitional v22 Django view nets.

U1 preserves the existing mocked view dependencies while U2/U3 replace them
with deterministic ORM-seeded fidelity data. Authentication is already real:
each Django test database creates its own ordinary user, so no developer
account lookup can hide an incomplete run.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from core.models import (
    Account,
    Brand,
    DiscourseKey,
    NationalismKey,
    Post,
    PostBrand,
    PostBrandDiscourse,
    PostBrandSignal,
    PostTypeKey,
    PostUnsanctionedFlag,
    SentimentKey,
)
from tests.mockup_spec import build_fixture

V22_TEST_USER_EMAIL = "v22-verifier@example.test"
GOLDEN_V22_FIXTURE = Path(__file__).with_name("golden") / "v22_mockup_fixture.json"
V22_FIXTURE_BRANDS = (
    ("moonshot_kimi", "Kimi", "#ec4899"),
    ("deepseek", "DeepSeek", "#10b981"),
    ("minimax", "MiniMax", "#3b82f6"),
    ("qwen", "Qwen", "#f97316"),
    ("ernie", "ERNIE", "#0ea5e9"),
)
V22_CLOSED_FIXTURE_BRANDS = (
    ("gemini", "Gemini"),
    ("gpt", "GPT"),
    ("claude", "Claude"),
    ("grok", "Grok"),
)


def fixture_from_oracle() -> dict:
    """Build the v22 fixture and guard it against authored-oracle drift."""
    fixture = build_fixture()
    assert json.loads(GOLDEN_V22_FIXTURE.read_text(encoding="utf-8")) == fixture, (
        "U2 golden fixture drifted from its authored mockup source."
    )
    return fixture


def seed_real_home_orm(fixture: dict) -> None:
    """Create only deterministic synthetic rows consumed by ``home()``."""
    for nickname, name, color in V22_FIXTURE_BRANDS:
        Brand.objects.create(
            nickname=nickname,
            display_name=name,
            display_name_en=name,
            display_name_zh_cn=name,
            accent_color=color,
        )
    for nickname, name in V22_CLOSED_FIXTURE_BRANDS:
        Brand.objects.create(
            nickname=nickname,
            display_name=name,
            display_name_en=name,
            display_name_zh_cn=name,
            accent_color="#d97706",
        )
    for key in {key for row in fixture["feed"]["items"] for key in row["post_types"]}:
        PostTypeKey.objects.create(key=key)
    for key in {key for row in fixture["feed"]["items"] for key in row["sentiments"]}:
        SentimentKey.objects.create(key=key)
    DiscourseKey.objects.create(key="genuine_hype")
    for key in ("none", "mild_pro", "pro"):
        NationalismKey.objects.create(key=key)
    now = timezone.now()
    for index, source in enumerate(fixture["feed"]["items"]):
        account = Account.objects.create(
            author_id=f"u3-account-{index}",
            handle=source["handle"].removeprefix("@"),
            followers_count=10_000 - index,
        )
        post = Post.objects.create(
            tweet_id=f"u3-post-{index}",
            author=account,
            author_handle=account.handle,
            text=source["text"]["original"],
            text_en=source["text"]["en"],
            text_zh_cn=source["text"]["zh_cn"],
            commentary_zh_cn=f"综合评论 {index}",
            lang_detected="en",
            created_at=now - timedelta(minutes=source["offset_minutes"]),
            like_count=1200 - index,
            retweet_count=30 + index,
            reply_count=5 + index,
        )
        brand = Brand.objects.get(nickname=V22_FIXTURE_BRANDS[index % len(V22_FIXTURE_BRANDS)][0])
        PostBrand.objects.create(post=post, brand=brand)
        for post_type, sentiment in zip(source["post_types"], source["sentiments"]):
            PostBrandSignal.objects.create(
                post=post,
                brand=brand,
                post_type_id=post_type,
                sentiment_id=sentiment,
            )
        PostBrandDiscourse.objects.create(
            post=post,
            brand=brand,
            discourse_id="genuine_hype",
            act_id=1,
            china_nationalism_id="pro",
            us_nationalism_id="mild_pro",
        )


def seed_v22_metadata_regression_orm() -> dict[str, object]:
    """Seed 51 eligible rows plus one flagged row for anonymous V22 feed tests."""
    brands = {}
    for nickname, name, color in V22_FIXTURE_BRANDS:
        brand, _ = Brand.objects.get_or_create(
            nickname=nickname,
            defaults={
                "display_name": name,
                "display_name_en": name,
                "display_name_zh_cn": name,
                "accent_color": color,
            },
        )
        brands[nickname] = brand
    for nickname, name in V22_CLOSED_FIXTURE_BRANDS:
        Brand.objects.get_or_create(
            nickname=nickname,
            defaults={
                "display_name": name,
                "display_name_en": name,
                "display_name_zh_cn": name,
                "accent_color": "#d97706",
            },
        )
    for key in ("buzz_releases", "hands_on_usage", "feedback_questions"):
        PostTypeKey.objects.get_or_create(key=key)
    for key in ("positive", "negative", "mixed", "neutral"):
        SentimentKey.objects.get_or_create(key=key)
    DiscourseKey.objects.get_or_create(key="genuine_hype")
    for key in ("none", "mild_pro", "pro"):
        NationalismKey.objects.get_or_create(key=key)

    now = timezone.now()
    replacement_id = "v22-metadata-replacement"
    page_two_id = "v22-metadata-page-two"
    brand_scope_id = "v22-metadata-brand-scope"
    for index in range(52):
        tweet_id = (
            replacement_id
            if index == 0
            else page_two_id
            if index == 51
            else brand_scope_id
            if index == 2
            else f"v22-metadata-{index:03d}"
        )
        account = Account.objects.create(
            author_id=f"v22-metadata-account-{index:03d}",
            handle=f"v22metadata{index:03d}",
            followers_count=12_800 - index,
        )
        post = Post.objects.create(
            tweet_id=tweet_id,
            author=account,
            author_handle=account.handle,
            text=f"Original metadata fixture post {index}",
            text_en=f"English metadata fixture post {index}",
            text_zh_cn=f"中文元数据样本 {index}",
            commentary_zh_cn=f"中文综合评论 {index}",
            lang_detected="en",
            created_at=now - timedelta(minutes=index),
            like_count=1200 - index,
            retweet_count=30 + index,
            reply_count=5 + index,
        )
        primary = brands["moonshot_kimi"]
        PostBrand.objects.create(post=post, brand=primary)
        if index == 0:
            PostBrandSignal.objects.create(
                post=post, brand=primary, post_type_id="buzz_releases", sentiment_id="positive"
            )
            secondary = brands["deepseek"]
            PostBrand.objects.create(post=post, brand=secondary)
            PostBrandSignal.objects.create(
                post=post, brand=secondary, post_type_id="hands_on_usage", sentiment_id="mixed"
            )
            discourse_brand = secondary
        elif index == 51:
            PostBrandSignal.objects.create(
                post=post, brand=primary, post_type_id="feedback_questions", sentiment_id="negative"
            )
            secondary = brands["deepseek"]
            PostBrand.objects.create(post=post, brand=secondary)
            PostBrandSignal.objects.create(
                post=post, brand=secondary, post_type_id="hands_on_usage", sentiment_id="mixed"
            )
            discourse_brand = secondary
        elif index == 2:
            PostBrandSignal.objects.create(
                post=post,
                brand=primary,
                post_type_id="feedback_questions",
                sentiment_id="negative",
            )
            secondary = brands["minimax"]
            PostBrand.objects.create(post=post, brand=secondary)
            PostBrandSignal.objects.create(
                post=post,
                brand=secondary,
                post_type_id="hands_on_usage",
                sentiment_id="positive",
            )
            discourse_brand = primary
        else:
            PostBrandSignal.objects.create(
                post=post, brand=primary, post_type_id="feedback_questions", sentiment_id="positive"
            )
            discourse_brand = primary
        PostBrandDiscourse.objects.create(
            post=post,
            brand=discourse_brand,
            discourse_id="genuine_hype",
            act_id=1,
            china_nationalism_id="pro",
            us_nationalism_id="mild_pro",
        )
        if index == 1:
            PostUnsanctionedFlag.objects.create(post=post, flags="marketing_spam")

    # Pulse-only rows are flagged so the ordinary feed remains the same 52-row
    # metadata fixture while the market-wide pulse sees the exact AE11 matrix.
    # Keep every timestamp comfortably inside its bucket: boundary behavior is
    # pinned separately by the clock-frozen server aggregation test.
    pulse_specs = (
        ("pulse_up", "Pulse Up", "脉冲上升", 6, 4),
        ("pulse_down", "Pulse Down", "脉冲下降", 2, 4),
        ("pulse_flat", "Pulse Flat", "脉冲持平", 4, 4),
        ("pulse_new", "Pulse New", "脉冲新", 3, 0),
        ("pulse_absent", "Pulse Absent", "脉冲无", 0, 0),
    )
    pulse_now = timezone.now()
    pulse_serial = 0
    for nickname, display_en, display_zh, current, prior in pulse_specs:
        brand = Brand.objects.create(
            nickname=nickname,
            display_name=display_en,
            display_name_en=display_en,
            display_name_zh_cn=display_zh,
            accent_color="#7c3aed",
        )
        for bucket, count in (("current", current), ("prior", prior)):
            for index in range(count):
                age = (
                    timedelta(hours=1, minutes=index)
                    if bucket == "current"
                    else timedelta(hours=25, minutes=index)
                )
                post = Post.objects.create(
                    tweet_id=f"v22-pulse-{pulse_serial:03d}",
                    created_at=pulse_now - age,
                )
                PostBrand.objects.create(post=post, brand=brand)
                PostUnsanctionedFlag.objects.create(post=post, flags="browser_pulse_fixture")
                pulse_serial += 1
    return {
        "replacement_id": replacement_id,
        "page_two_id": page_two_id,
        "brand_scope_id": brand_scope_id,
        "pulse_expectations": {
            "order": [
                "moonshot_kimi",
                "pulse_up",
                "pulse_flat",
                "pulse_new",
                "deepseek",
                "pulse_down",
                "minimax",
            ],
            "details": {
                "pulse_up": {
                    "text": "50%", "glyph": "▲", "aria": "Pulse Up, up 50 percent",
                },
                "pulse_down": {
                    "text": "50%", "glyph": "▼", "aria": "Pulse Down, down 50 percent",
                },
                "pulse_flat": {
                    "text": "0%", "glyph": "→", "aria": "Pulse Flat, flat 0 percent",
                },
                "pulse_new": {"text": "NEW", "glyph": "", "aria": "Pulse New, NEW"},
            },
        },
    }


class PostgreSQLV22TestCase(TestCase):
    """Django ``TestCase`` with a suite-owned, non-privileged logged-in user."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.v22_test_user = get_user_model().objects.create_user(
            username="v22-verifier",
            email=V22_TEST_USER_EMAIL,
            password="v22-test-only-password",
        )

    def setUp(self):
        super().setUp()
        self.client = Client(HTTP_HOST="127.0.0.1")
        self.client.force_login(self.v22_test_user)


def assert_v22_selector_matches(
    test_case: TestCase,
    matches: int,
    *,
    selector: str,
    locale: str,
    viewport: str,
    oracle_source: str,
) -> None:
    """Fail a zero-match v22 selector with the context needed to reproduce it."""
    if matches == 0:
        test_case.fail(
            "v22 selector matched zero elements: "
            f"selector={selector!r}; locale={locale!r}; viewport={viewport!r}; "
            f"oracle_source={oracle_source!r}"
        )
