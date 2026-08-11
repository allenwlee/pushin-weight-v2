"""Every local static tag in a template must resolve to a shipped asset."""

from __future__ import annotations

import re
from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parents[1]
MONITOR_STATIC_ROOT = (REPO_ROOT / "monitor" / "static").resolve()
STATIC_TAG = re.compile(r"{%\s*static\s+['\"](?P<asset>[^'\"]+)['\"]\s*%}")


class StaticReferencesResolveTests(SimpleTestCase):
    def test_all_local_template_static_references_resolve(self):
        missing: list[str] = []
        for template in sorted((REPO_ROOT / "monitor" / "templates").rglob("*.html")):
            for asset in STATIC_TAG.findall(template.read_text(encoding="utf-8")):
                if not finders.find(asset):
                    missing.append(f"{template.relative_to(REPO_ROOT)} -> {asset}")
        self.assertEqual(missing, [], "Unresolved local {% static %} references:\n" + "\n".join(missing))

    def test_public_home_static_references_resolve_from_monitor_source(self):
        template = REPO_ROOT / "monitor" / "templates" / "monitor" / "home.html"
        wrong_source: list[str] = []
        for asset in STATIC_TAG.findall(template.read_text(encoding="utf-8")):
            resolved = finders.find(asset)
            if not resolved or not Path(resolved).resolve().is_relative_to(MONITOR_STATIC_ROOT):
                wrong_source.append(f"{asset} -> {resolved or '<missing>'}")

        self.assertEqual(
            wrong_source,
            [],
            "Public homepage assets must resolve from monitor/static:\n" + "\n".join(wrong_source),
        )
