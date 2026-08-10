"""Every local static tag in a template must resolve to a shipped asset."""

from __future__ import annotations

import re
from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC_TAG = re.compile(r"{%\s*static\s+['\"](?P<asset>[^'\"]+)['\"]\s*%}")


class StaticReferencesResolveTests(SimpleTestCase):
    def test_all_local_template_static_references_resolve(self):
        missing: list[str] = []
        for template in sorted((REPO_ROOT / "monitor" / "templates").rglob("*.html")):
            for asset in STATIC_TAG.findall(template.read_text(encoding="utf-8")):
                if not finders.find(asset):
                    missing.append(f"{template.relative_to(REPO_ROOT)} -> {asset}")
        self.assertEqual(missing, [], "Unresolved local {% static %} references:\n" + "\n".join(missing))
