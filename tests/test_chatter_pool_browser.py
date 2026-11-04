"""Prepared source pools are independent controls and never generate work."""

import pytest
from playwright.sync_api import sync_playwright

from tests.test_chatter_chain import chain_config
from tests.test_chatter_pool_readers import published

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def test_first_failed_run_keeps_activation_age_and_last_good_text(
    live_server, monkeypatch, settings
):
    from datetime import timedelta

    from django.utils import timezone

    settings.SECURE_SSL_REDIRECT = False
    settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    cfg = chain_config()
    cfg = cfg.model_copy(
        update={
            "public_enabled": True,
            "chatter": cfg.chatter.model_copy(
                update={"activated_at": timezone.now() - timedelta(minutes=46)}
            ),
        }
    )
    monkeypatch.setattr("monitor.editorial.views.load_editorial_config", lambda: cfg)
    text = published("rest", "884290")
    run = text.narrative.run
    run.scope_key, run.discovery_state = "chatter:v1", "failed"
    run.created_at = timezone.now() - timedelta(minutes=5)
    run.save(update_fields=["scope_key", "discovery_state", "created_at"])
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(extra_http_headers={"X-Forwarded-Proto": "https"})
        page.goto(live_server.url + "/general/?lang=en", wait_until="networkidle")
        assert page.locator("#chatter .chatter-delay").is_visible()
        assert text.headline in page.locator("#chatter").inner_text()
        browser.close()


def test_general_pool_controls_and_archive_use_saved_pools(
    live_server, monkeypatch, settings
):
    settings.SECURE_SSL_REDIRECT = False
    settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    cfg = chain_config().model_copy(update={"public_enabled": True})
    monkeypatch.setattr("monitor.editorial.views.load_editorial_config", lambda: cfg)
    rest = published("rest", "884201")
    giant = published("giant", "884202")
    giant.headline = "GIANT SOURCE POOL"
    giant.save(update_fields=["headline"])
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(
            viewport={"width": 390, "height": 844},
            extra_http_headers={"X-Forwarded-Proto": "https"},
        )
        page.goto(live_server.url + "/general/")
        controls = page.locator("#chatter .chatter-pools")
        assert controls.count() == 1 and controls.is_visible()
        assert controls.locator('[name="source_lang"]').input_value() == "en"
        assert controls.locator('[name="group"]').input_value() == "rest"
        assert rest.headline in page.locator("#chatter").inner_text()
        controls.locator('[name="group"]').select_option("giant")
        controls.locator('button[type="submit"]').click()
        page.wait_for_load_state("networkidle")
        assert "GIANT SOURCE POOL" in page.locator("#chatter").inner_text()
        page.set_viewport_size({"width": 1440, "height": 900})
        page.locator("#general-settings > summary").click()
        page.locator('.header-settings [data-pref="lang"][data-value="ja"]').click()
        page.wait_for_load_state("networkidle")
        assert controls.locator('[name="source_lang"]').input_value() == "ja"
        assert controls.locator('[name="edition_lang"]').input_value() == "ja"
        controls.locator('[name="source_lang"]').select_option("en")
        controls.locator('[name="edition_lang"]').select_option("zh-cn")
        controls.locator('button[type="submit"]').click()
        page.wait_for_load_state("networkidle")
        page.locator("#general-settings > summary").click()
        page.locator('.header-settings [data-pref="lang"][data-value="en"]').click()
        page.wait_for_load_state("networkidle")
        assert controls.locator('[name="source_lang"]').input_value() == "en"
        assert controls.locator('[name="edition_lang"]').input_value() == "zh-cn"
        page.locator("#chatter .editorial-archive").click()
        page.wait_for_load_state("networkidle")
        assert "GIANT SOURCE POOL" in page.locator(".archive-list").inner_text()
        assert page.locator('[name="group"]').input_value() == "giant"
        browser.close()


def test_declared_pool_controls_are_independent_reversible_and_read_only(
    live_server, monkeypatch, settings
):
    import json
    from pathlib import Path

    from bridgewright.assurance.contracts import AssuranceEvidence
    from bridgewright.assurance.engine import (
        assess_evidence,
        compile_obligations,
        control_model_digest,
    )

    from core.models import OriginalContentCall
    from tests.ui_assurance.chatter import load_declaration, product_identity

    declaration = load_declaration()
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/chatter_pools_contract.json").read_text()
    )
    settings.SECURE_SSL_REDIRECT = False
    settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    cfg = chain_config().model_copy(update={"public_enabled": True})
    monkeypatch.setattr("monitor.editorial.views.load_editorial_config", lambda: cfg)
    for index, group in enumerate(fixture["groups"]):
        text = published(group, str(884210 + index))
        text.headline = fixture["headlines"]["en-" + group]
        text.save(update_fields=["headline"])
    before = OriginalContentCall.objects.count()
    defaults = {control.id: control.initial_value for control in declaration.controls}
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(
            viewport={"width": 390, "height": 844},
            extra_http_headers={"X-Forwarded-Proto": "https"},
        )

        def reset():
            page.goto(live_server.url + "/general/?lang=en")
            return dict(defaults)

        def apply(state, key, value):
            controls = page.locator("#chatter .chatter-pools")
            controls.locator(f'[name="{key}"]').select_option(value)
            controls.locator('button[type="submit"]').click()
            page.wait_for_load_state("networkidle")
            state[key] = value

        def check(state):
            for key, value in state.items():
                locator = page.locator(f'#chatter .chatter-pools [name="{key}"]')
                assert (
                    locator.count() == 1
                    and locator.is_visible()
                    and locator.input_value() == value
                )
            text = page.locator("#chatter").inner_text()
            wanted = fixture["headlines"].get(
                state["source_lang"] + "-" + state["group"]
            )
            for headline in fixture["headlines"].values():
                assert (headline in text) == (headline == wanted)
            assert page.locator("#chatter .editorial-fallback").count() == int(
                wanted is not None and state["edition_lang"] != "en"
            )
            assert not page.evaluate(
                "document.documentElement.scrollWidth > innerWidth"
            )

        for obligation in compile_obligations(declaration):
            parts = obligation.id.split("/")
            state = reset()
            if parts[0] in {"transition", "inverse"}:
                apply(state, parts[1], parts[2])
                check(state)
                if parts[0] == "inverse":
                    apply(state, parts[1], parts[3])
                    check(state)
            elif parts[0] in {"tway", "ordered"}:
                for assignment in parts[2:]:
                    key, value = assignment.split("=" if parts[0] == "tway" else ":", 1)
                    apply(state, key, value)
                    check(state)
            elif parts[0] == "invariant":
                check(state)
            else:
                raise AssertionError(
                    "Unimplemented Chatter obligation: " + obligation.id
                )
            results.append({"obligation_id": obligation.id, "status": "passed"})
        for locale in fixture["languages"]:
            page.goto(live_server.url + "/general/?lang=" + locale)
            assert page.locator('#chatter [name="source_lang"]').input_value() == locale
            assert (
                page.locator('#chatter [name="edition_lang"]').input_value() == locale
            )
        browser.close()
    assert OriginalContentCall.objects.count() == before
    evidence = AssuranceEvidence.model_validate(
        {
            "schema_version": "bridgewright.assurance.evidence/v1",
            "profile": "stateful-ui-assurance/v1",
            "identity": {
                "source_revision": declaration.source_revision,
                "candidate_revision": product_identity(),
                "fixture_digest": declaration.fixture.sha256,
                "control_model_digest": control_model_digest(declaration),
                "generator": declaration.generator.label(),
                "environments": [
                    {"id": "desktop-chromium", "browser_runtime": "playwright-chromium"}
                ],
            },
            "results": results,
        }
    )
    assessment = assess_evidence(declaration, evidence)
    destination = Path(__file__).resolve().parents[1] / ".ollija" / "tmp"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "chatter-ui-evidence.json").write_text(
        evidence.model_dump_json(indent=2)
    )
    (destination / "chatter-ui-assessment.json").write_text(
        assessment.model_dump_json(indent=2)
    )
    assert assessment.status == "clean" and assessment.coverage.passed == len(results)
