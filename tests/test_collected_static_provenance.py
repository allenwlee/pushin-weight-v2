"""Collected static output must be a disposable projection of monitor/static."""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.management import call_command
from django.test import Client, SimpleTestCase, override_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "monitor" / "static"
HOME_TEMPLATE = REPO_ROOT / "monitor" / "templates" / "monitor" / "home.html"
STATIC_TAG = re.compile(r"{%\s*static\s+['\"](?P<asset>[^'\"]+)['\"]\s*%}")
REGRESSION_TARGETS = ("pw-feed.js", "pw-chart.js", "pw-filter-store.js")
PRODUCTION_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


def _home_static_assets() -> tuple[str, ...]:
    return tuple(dict.fromkeys(STATIC_TAG.findall(HOME_TEMPLATE.read_text(encoding="utf-8"))))


def _response_bytes(response) -> bytes:
    if response.streaming:
        return b"".join(response.streaming_content)
    return response.content


class CollectedStaticProvenanceTests(SimpleTestCase):
    def test_staticfiles_is_untracked_ignored_build_output(self):
        tracked = subprocess.run(
            ["git", "ls-files", "--", "staticfiles"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        tracked_present = [path for path in tracked if (REPO_ROOT / path).exists()]
        self.assertEqual(
            tracked_present,
            [],
            "staticfiles/ must not contain tracked collection output",
        )

        ignored = subprocess.run(
            ["git", "check-ignore", "-q", "staticfiles/.provenance-probe"],
            cwd=REPO_ROOT,
            check=False,
        )
        self.assertEqual(ignored.returncode, 0, "staticfiles/ must be ignored")

    def test_render_build_clears_static_root_before_collection(self):
        collect_line = next(
            line.strip()
            for line in (REPO_ROOT / "build.sh").read_text(encoding="utf-8").splitlines()
            if "manage.py collectstatic" in line
        )
        self.assertIn(
            "--clear",
            shlex.split(collect_line),
            "Render collection must clear stale destination files",
        )

    def test_clean_manifest_collection_and_whitenoise_serve_current_source(self):
        assets = _home_static_assets()
        self.assertTrue(assets, "home.html must emit at least one local static asset")
        for target in REGRESSION_TARGETS:
            self.assertIn(target, assets)

        for asset in assets:
            resolved = Path(finders.find(asset) or "").resolve()
            self.assertTrue(
                resolved.is_relative_to(SOURCE_ROOT.resolve()),
                f"{asset} must resolve from monitor/static, got {resolved}",
            )

        with TemporaryDirectory(prefix="pushinweight-static-") as destination:
            static_root = Path(destination)
            stale_target = static_root / "pw-feed.js"
            stale_target.write_bytes(b"deliberately stale collected bytes")
            orphan = static_root / "retired-static-output.js"
            orphan.write_bytes(b"must not survive a clean collection")

            with override_settings(
                DEBUG=False,
                STATIC_ROOT=static_root,
                STORAGES=PRODUCTION_STORAGES,
            ):
                call_command("collectstatic", interactive=False, verbosity=0, clear=True)

                self.assertFalse(orphan.exists(), "clean collection left stale destination output")
                for asset in assets:
                    source_bytes = (SOURCE_ROOT / asset).read_bytes()
                    self.assertEqual((static_root / asset).read_bytes(), source_bytes)

                    hashed_name = staticfiles_storage.stored_name(asset)
                    self.assertNotEqual(hashed_name, asset, f"{asset} was not manifest-hashed")
                    self.assertEqual((static_root / hashed_name).read_bytes(), source_bytes)

                client = Client()
                for target in REGRESSION_TARGETS:
                    emitted_url = staticfiles_storage.url(target)
                    response = client.get("/" + emitted_url.lstrip("/"), secure=True)
                    self.assertEqual(response.status_code, 200, emitted_url)
                    self.assertEqual(_response_bytes(response), (SOURCE_ROOT / target).read_bytes())
