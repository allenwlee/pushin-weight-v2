from __future__ import annotations

import json
import re
from pathlib import Path

from django.core.management import call_command
from django.test import Client
from django.test.utils import override_settings

PRODUCTION_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


def test_feed_sprites_collectstatic_are_hashed_and_immutable(tmp_path: Path) -> None:
    declaration = json.loads(
        (
            Path(__file__).parent / "fixtures/performance_assurance/declaration.json"
        ).read_text(encoding="utf-8")
    )
    static_root = tmp_path / "staticfiles"
    static_root.mkdir()
    with override_settings(
        DEBUG=False,
        STATIC_ROOT=static_root,
        ALLOWED_HOSTS=["testserver"],
        SECURE_SSL_REDIRECT=False,
        STORAGES=PRODUCTION_STORAGES,
    ):
        call_command("collectstatic", interactive=False, verbosity=0, clear=True)
        for sprite in ("country-flags", "pw-processing-glyphs"):
            hashed = next(static_root.glob(f"{sprite}.*.svg"))
            response = Client().get(f"/static/{hashed.name}")
            assert response.status_code == 200
            cache_control = response.headers["Cache-Control"]
            assert "immutable" in cache_control
            match = re.search(r"(?:^|,\s*)max-age=(\d+)", cache_control)
            assert match is not None
            assert int(match.group(1)) >= 31_536_000

    country_sprite = next(static_root.glob("country-flags.*.svg"))
    expected_path = f"/static/{country_sprite.name}"
    for scenario in declaration["scenarios"]:
        network_paths = [
            expectation["path"]
            for expectation in scenario["network_expectations"]
            if "country-flags." in expectation["path"]
            and expectation["path"].endswith(".svg")
        ]
        assert network_paths == [expected_path]
        assert [
            expectation["max_requests"]
            for expectation in scenario["network_expectations"]
            if expectation["path"] == expected_path
        ] == [2]
        assert all(
            expectation["path"] == expected_path
            for expectation in scenario["cache_expectations"]
        )
