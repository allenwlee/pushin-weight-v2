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
