"""The General-style port ships no prototype scaffolding.

The approved design came from a relay-served prototype whose class names
(``gx-``), comparison switches, relay paths and "Prototype" badge must not reach
production sources or rendered pages.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from monitor.views import _clear_home_pulse_cache
from tests.v22_support import fixture_from_oracle, seed_real_home_orm

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "monitor/templates/monitor/home.html",
    "monitor/templates/monitor/dashboard_each.html",
    "monitor/templates/monitor/_pro_masthead.html",
    "monitor/templates/monitor/_pro_rail.html",
    "monitor/templates/monitor/_home_chart.html",
    "monitor/templates/monitor/_feed_initial_v22.html",
    "monitor/templates/monitor/_site_footer.html",
    "monitor/templates/monitor/_cyber_quan_sprite.html",
    "monitor/templates/monitor/general.html",
    "monitor/templates/monitor/general/_navigation.html",
    "monitor/templates/monitor/general/_cards.html",
    "monitor/static/pro-general.css",
    "monitor/static/monitor/general.css",
    "monitor/static/fonts/pw-fonts.css",
    "monitor/static/favicon.svg",
    "monitor/static/pw-shell.js",
    "monitor/static/pw-chart.js",
    "monitor/static/pw-feed.js",
    "monitor/static/pw-tz.js",
    "monitor/static/pw-each-chart.js",
    "monitor/static/pw-locale-toggle.js",
)
FORBIDDEN = re.compile(
    r"\bgx-[a-z]|\bgx\.gx\b|data-gx|gxmark|/__proto/|ce-prototype|\bPrototype\b|owner item \d"
)


def hygiene_findings(text: str) -> list[str]:
    return [match.group(0) for match in FORBIDDEN.finditer(text)]


def test_detector_flags_injected_prototype_markup() -> None:
    assert hygiene_findings('<div class="gx-proto">Prototype</div>') == ["gx-p", "Prototype"]
    assert hygiene_findings("fetch('/__proto/feed')") == ["/__proto/"]
    assert hygiene_findings("Array.prototype.slice") == []


@pytest.mark.parametrize("relative", SOURCES)
def test_shipped_sources_carry_no_prototype_scaffolding(relative: str) -> None:
    assert hygiene_findings((ROOT / relative).read_text(encoding="utf-8")) == []


@pytest.mark.django_db
@pytest.mark.requires_postgres
@pytest.mark.parametrize("path", ["/?locale=en", "/dashboard/each?brand=deepseek&locale=ja", "/general/?lang=zh-cn"])
def test_rendered_pages_carry_no_prototype_scaffolding(client, settings, path: str) -> None:
    settings.SECURE_SSL_REDIRECT = False
    seed_real_home_orm(fixture_from_oracle())
    _clear_home_pulse_cache()
    response = client.get(path)
    assert response.status_code == 200
    assert hygiene_findings(response.content.decode()) == []
