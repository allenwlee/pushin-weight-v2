"""Real-ORM, root-route fidelity characterization against the v22 mockup."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
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
from tests.mockup_spec import build_fixture, load_spec
from tests.shell_diff import (
    assert_data_shape,
    first_authored_difference,
    validate_allowlist,
)
from tests.v22_support import PostgreSQLV22TestCase

pytestmark = pytest.mark.requires_postgres

GOLDEN_FIXTURE = Path(__file__).with_name("golden") / "v22_mockup_fixture.json"
ALLOWLIST = Path(__file__).with_name("golden") / "v22_shell_allowlist.json"
VIEWPORT = "desktop"
_BRANDS = (("moonshot_kimi", "Kimi", "#ec4899"), ("deepseek", "DeepSeek", "#10b981"), ("minimax", "MiniMax", "#3b82f6"), ("qwen", "Qwen", "#f97316"), ("ernie", "ERNIE", "#0ea5e9"))


def _fixture_from_oracle() -> dict:
    fixture = build_fixture()
    assert json.loads(GOLDEN_FIXTURE.read_text(encoding="utf-8")) == fixture, "U2 golden fixture drifted from its authored mockup source."
    return fixture


def _seed_real_home_orm(fixture: dict) -> None:
    """Create only deterministic synthetic rows consumed by ``home()``."""
    for nickname, name, color in _BRANDS:
        Brand.objects.create(nickname=nickname, display_name=name, display_name_en=name, display_name_zh_cn=name, accent_color=color)
    for key in {key for row in fixture["feed"]["items"] for key in row["post_types"]}:
        PostTypeKey.objects.create(key=key)
    for key in {key for row in fixture["feed"]["items"] for key in row["sentiments"]}:
        SentimentKey.objects.create(key=key)
    DiscourseKey.objects.create(key="genuine_hype")
    for key in ("none", "mild_pro", "pro"):
        NationalismKey.objects.create(key=key)
    now = timezone.now()
    for index, source in enumerate(fixture["feed"]["items"]):
        account = Account.objects.create(author_id=f"u3-account-{index}", handle=source["handle"].removeprefix("@"), followers_count=10_000 - index)
        post = Post.objects.create(
            tweet_id=f"u3-post-{index}", author=account, author_handle=account.handle,
            text=source["text"]["original"], text_en=source["text"]["en"], text_zh_cn=source["text"]["zh_cn"],
            lang_detected="en", created_at=now - timedelta(minutes=source["offset_minutes"]),
            like_count=1200 - index, retweet_count=30 + index, reply_count=5 + index,
        )
        brand = Brand.objects.get(nickname=_BRANDS[index % len(_BRANDS)][0])
        PostBrand.objects.create(post=post, brand=brand)
        for post_type, sentiment in zip(source["post_types"], source["sentiments"]):
            PostBrandSignal.objects.create(post=post, brand=brand, post_type_id=post_type, sentiment_id=sentiment)
        PostBrandDiscourse.objects.create(post=post, brand=brand, discourse_id="genuine_hype", act_id=1, china_nationalism_id="pro", us_nationalism_id="mild_pro")


class HomeV22MockupDiffTests(PostgreSQLV22TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.fixture = _fixture_from_oracle()
        _seed_real_home_orm(cls.fixture)

    def _render(self, locale: str) -> str:
        # Exercise the production locale route/cookie contract.  A query
        # parameter only characterizes a request override and can leave the
        # browser's persisted locale behavior untested.
        response = self.client.post(f"/locale/{locale}/", HTTP_REFERER="/")
        self.assertEqual(response.status_code, 302)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200, response.content[:500].decode("utf-8", errors="replace"))
        return response.content.decode("utf-8")

    def test_allowlist_requires_narrow_reviewed_entries(self):
        assert validate_allowlist(json.loads(ALLOWLIST.read_text(encoding="utf-8"))) == []
        with self.assertRaisesRegex(AssertionError, "selector, region, and rationale"):
            validate_allowlist({"entries": [{"selector": ".x"}]})
        with self.assertRaisesRegex(AssertionError, "broad wildcard"):
            validate_allowlist({"entries": [{"selector": "*", "region": "topbar", "rationale": "no"}]})

    def test_root_route_matches_authored_shell_or_reports_first_difference(self):
        spec = load_spec()
        allowlist = validate_allowlist(json.loads(ALLOWLIST.read_text(encoding="utf-8")))
        for locale in ("zh_cn", "en", "original"):
            with self.subTest(locale=locale):
                rendered = self._render(locale)
                assert_data_shape(spec, self.fixture, rendered, locale=locale, viewport=VIEWPORT)
                difference = first_authored_difference(spec, rendered, locale=locale, viewport=VIEWPORT, allowlist=allowlist)
                self.assertIsNone(difference, difference.report(locale=locale, viewport=VIEWPORT, oracle_source=str(spec.source)) if difference else "")
