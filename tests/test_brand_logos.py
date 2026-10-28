"""Brand logo files and the URL map the pages use to find them."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from django.contrib.staticfiles import finders
from django.test import RequestFactory, SimpleTestCase

from core.brand_presentation import (
    BRAND_ACCENT_COLORS,
    BRAND_LOGO_FILES,
    brand_logo_urls,
)
from core.context_processors import i18n_context

REPO_ROOT = Path(__file__).resolve().parents[1]


class BrandLogoTests(SimpleTestCase):
    def test_every_curated_brand_has_a_resolvable_logo_named_by_nickname(self) -> None:
        self.assertEqual(set(BRAND_LOGO_FILES), set(BRAND_ACCENT_COLORS))
        for nickname, filename in BRAND_LOGO_FILES.items():
            self.assertEqual(Path(filename).stem, nickname)
            self.assertIsNotNone(finders.find(f"brand-logos/{filename}"), filename)

    def test_svg_logos_carry_no_script(self) -> None:
        for filename in BRAND_LOGO_FILES.values():
            if not filename.endswith(".svg"):
                continue
            source = (REPO_ROOT / "monitor/static/brand-logos" / filename).read_text(
                encoding="utf-8"
            ).lower()
            self.assertNotIn("<script", source, filename)
            self.assertNotIn("javascript:", source, filename)
            self.assertNotRegex(source, r"\son[a-z]+=", filename)

    def test_unknown_brand_has_no_logo_url(self) -> None:
        self.assertNotIn("untracked-demo", brand_logo_urls())

    def test_context_exposes_the_same_urls_as_json(self) -> None:
        request = RequestFactory().get("/")
        with patch("core.context_processors._get_brands", return_value=[]):
            context = i18n_context(request)
        # Both values are lazy; they resolve when a template renders them.
        self.assertEqual(json.loads(str(context["brand_logo_urls_json"])), dict(context["brand_logo_urls"]))
        self.assertEqual(context["brand_logo_urls"]["llama"], "/static/brand-logos/llama.svg")

