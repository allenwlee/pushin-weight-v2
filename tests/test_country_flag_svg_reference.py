"""Contract tests for the complete country SVG flag review reference."""

from __future__ import annotations

import copy
import hashlib
import html
import importlib.util
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = REPO_ROOT / "scripts/build_country_flag_svg_reference.py"
MANIFEST_PATH = (
    REPO_ROOT / "docs/ideation/assets/2026-08-29-162947-country-flag-pixels.json"
)
SPRITE_PATH = (
    REPO_ROOT / "docs/ideation/assets/2026-08-29-162947-country-flag-sprite.svg"
)
HTML_PATH = (
    REPO_ROOT / "docs/reference/2026-08-29-162947-country-flag-svg-reference.html"
)
OLD_HTML_PATH = (
    REPO_ROOT / "docs/ideation/2026-08-29-162947-country-flag-svg-reference.html"
)
RUNTIME_SPRITE_PATH = REPO_ROOT / "monitor/static/pw-country-flags.svg"
RUNTIME_DATA_PATH = REPO_ROOT / "monitor/country_flags.py"
EXPECTED_CODES = (
    "AD",
    "AE",
    "AF",
    "AG",
    "AL",
    "AM",
    "AO",
    "AR",
    "AT",
    "AU",
    "AZ",
    "BA",
    "BB",
    "BD",
    "BE",
    "BF",
    "BG",
    "BH",
    "BI",
    "BJ",
    "BN",
    "BO",
    "BR",
    "BS",
    "BT",
    "BW",
    "BY",
    "BZ",
    "CA",
    "CD",
    "CF",
    "CG",
    "CH",
    "CI",
    "CL",
    "CM",
    "CN",
    "CO",
    "CR",
    "CU",
    "CV",
    "CY",
    "CZ",
    "DE",
    "DJ",
    "DK",
    "DM",
    "DO",
    "DZ",
    "EC",
    "EE",
    "EG",
    "ER",
    "ES",
    "ET",
    "FI",
    "FJ",
    "FM",
    "FR",
    "GA",
    "GB",
    "GD",
    "GE",
    "GH",
    "GM",
    "GN",
    "GQ",
    "GR",
    "GT",
    "GW",
    "GY",
    "HN",
    "HR",
    "HT",
    "HU",
    "ID",
    "IE",
    "IL",
    "IN",
    "IQ",
    "IR",
    "IS",
    "IT",
    "JM",
    "JO",
    "JP",
    "KE",
    "KG",
    "KH",
    "KI",
    "KM",
    "KN",
    "KP",
    "KR",
    "KW",
    "KZ",
    "LA",
    "LB",
    "LC",
    "LI",
    "LK",
    "LR",
    "LS",
    "LT",
    "LU",
    "LV",
    "LY",
    "MA",
    "MC",
    "MD",
    "ME",
    "MG",
    "MH",
    "MK",
    "ML",
    "MM",
    "MN",
    "MR",
    "MT",
    "MU",
    "MV",
    "MW",
    "MX",
    "MY",
    "MZ",
    "NA",
    "NE",
    "NG",
    "NI",
    "NL",
    "NO",
    "NP",
    "NR",
    "NZ",
    "OM",
    "PA",
    "PE",
    "PG",
    "PH",
    "PK",
    "PL",
    "PS",
    "PT",
    "PW",
    "PY",
    "QA",
    "RO",
    "RS",
    "RU",
    "RW",
    "SA",
    "SB",
    "SC",
    "SD",
    "SE",
    "SG",
    "SI",
    "SK",
    "SL",
    "SM",
    "SN",
    "SO",
    "SR",
    "SS",
    "ST",
    "SV",
    "SY",
    "SZ",
    "TD",
    "TG",
    "TH",
    "TJ",
    "TL",
    "TM",
    "TN",
    "TO",
    "TR",
    "TT",
    "TV",
    "TW",
    "TZ",
    "UA",
    "UG",
    "US",
    "UY",
    "UZ",
    "VA",
    "VC",
    "VE",
    "VN",
    "VU",
    "WS",
    "XK",
    "YE",
    "ZA",
    "ZM",
    "ZW",
)
EXPECTED_IDENTITY_SHA256 = (
    "7985cf36af3bf8eea53150d8de9c9f77bd3f0dd4d72fb8b13d0deca2df440eff"
)
EXPECTED_PIXELS_SHA256 = (
    "0508e997d36281160df7a3d1e457afc453557553b4eb768373b76b22267d93b8"
)
EXPECTED_NAME_SAMPLES = {
    "CD": "Congo - Kinshasa",
    "CI": "Côte d’Ivoire",
    "CN": "China",
    "KR": "South Korea",
    "SZ": "Eswatini",
    "TR": "Türkiye",
    "US": "United States",
    "XK": "Kosovo",
}
EXPECTED_ZH_CN_NAME_SAMPLES = {
    "CD": "刚果（金）",
    "CI": "科特迪瓦",
    "CN": "中国",
    "KR": "韩国",
    "SZ": "斯威士兰",
    "TR": "土耳其",
    "US": "美国",
    "XK": "科索沃",
}
EXPECTED_CLDR_SOURCE = {
    "provider": "Unicode CLDR",
    "release": "48",
    "url": "https://raw.githubusercontent.com/unicode-org/cldr/release-48/common/main/zh.xml",
    "sha256": "b1ef8bcadcf19fa8914d9ba812a7bcec124c72fecbf4acea02e4c8bd2fe51866",
    "license": "Unicode License v3",
    "license_url": "https://www.unicode.org/license.txt",
}
APPROVED_SYMBOL_SHA256 = {
    "flag-cn": "b2b8b8866a47d1b6519507112bdb2dbe194ebf3cbe0b76424b85b914caf4072c",
    "flag-kr": "6cfee124679d2da52ecb80b35ccdf9cd9165c229092cfac89890890ccb1f3e67",
    "flag-us": "221c2158dc06e6d23181d311ee48acb37943a6b16fafa06ccd6016b24f27de7b",
}
COUNTRY_COUNT = 197
TREATMENT_COUNT = COUNTRY_COUNT * 3
SPECIMEN_COUNT = TREATMENT_COUNT * 3
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
RUN_PATTERN = re.compile(r"M(?P<x>\d+) (?P<y>\d+)h(?P<width>\d+)v1H(?P<left>\d+)z")


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "country_flag_generator", GENERATOR_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _pixels_sha256(flags: list[dict]) -> str:
    payload = json.dumps(
        [{"code": flag["code"], "pixels": flag["pixels"]} for flag in flags],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _cldr_fixture(manifest: dict, **overrides: str) -> bytes:
    names = {
        flag["code"]: overrides.get(flag["code"], flag["name_zh_cn"])
        for flag in manifest["flags"]
    }
    territories = "".join(
        f'<territory type="{code}">{html.escape(name)}</territory>'
        for code, name in names.items()
    )
    return (
        f"<ldml><localeDisplayNames><territories>{territories}"
        "</territories></localeDisplayNames></ldml>"
    ).encode()


def test_manifest_is_the_exact_portable_country_source() -> None:
    generator = _load_generator()
    manifest = _load_manifest()

    generator.validate_manifest(manifest)
    assert manifest["schema_version"] == 2
    assert manifest["dimensions"] == {"width": 16, "height": 9}
    assert manifest["inventory"] == {
        "country_count": COUNTRY_COUNT,
        "identity_sha256": EXPECTED_IDENTITY_SHA256,
        "pixels_sha256": EXPECTED_PIXELS_SHA256,
    }
    assert manifest["source"] == {
        "top_gun_commit": "5ad0dbda9140ffa52ea791a0ec51c975b8c9a97b",
        "r74n_revision": "a1f3a5db7e97961e3e515db192ac7d2c7fa1a8bf",
        "attribution": "Pixel flags by R74n",
        "license_clearance": "Owner confirmed for this PushinWeight use on 2026-08-29",
    }
    assert manifest["locale_sources"]["zh_cn"] == EXPECTED_CLDR_SOURCE

    flags = manifest["flags"]
    assert tuple(flag["code"] for flag in flags) == EXPECTED_CODES
    names = {flag["code"]: flag["name"] for flag in flags}
    assert {code: names[code] for code in EXPECTED_NAME_SAMPLES} == (
        EXPECTED_NAME_SAMPLES
    )
    names_zh_cn = {flag["code"]: flag["name_zh_cn"] for flag in flags}
    assert {code: names_zh_cn[code] for code in EXPECTED_ZH_CN_NAME_SAMPLES} == (
        EXPECTED_ZH_CN_NAME_SAMPLES
    )
    assert all(name.strip() and "↑↑↑" not in name for name in names_zh_cn.values())
    assert sum(len(row) for flag in flags for row in flag["pixels"]) == 28_368
    assert _pixels_sha256(flags) == EXPECTED_PIXELS_SHA256


@pytest.mark.parametrize(
    "mutate",
    (
        lambda data: data["flags"].append(copy.deepcopy(data["flags"][0])),
        lambda data: data["flags"][0].update(code="cn"),
        lambda data: data["flags"][0].update(source_name="wrong_country"),
        lambda data: data["flags"][0].update(name="Wrong country"),
        lambda data: data["flags"][0]["pixels"].pop(),
        lambda data: data["flags"][0]["pixels"][0].pop(),
        lambda data: data["flags"][0]["pixels"][0].__setitem__(0, "red"),
        lambda data: data["flags"][0]["pixels"][0].__setitem__(0, "#010203"),
    ),
)
def test_manifest_rejects_inventory_and_pixel_shape_drift(mutate) -> None:
    generator = _load_generator()
    manifest = _load_manifest()
    mutate(manifest)

    with pytest.raises((TypeError, ValueError)):
        generator.validate_manifest(manifest)


def test_cldr_import_accepts_only_complete_pinned_standard_names() -> None:
    generator = _load_generator()
    manifest = _load_manifest()
    fixture = _cldr_fixture(manifest)
    root = ET.fromstring(fixture)
    territories = root.find("./localeDisplayNames/territories")
    assert territories is not None
    ET.SubElement(territories, "territory", {"type": "CN", "alt": "short"}).text = (
        "not-the-standard-name"
    )
    fixture = ET.tostring(root, encoding="utf-8")

    imported = generator.import_cldr_zh_names(
        manifest,
        fixture,
        expected_sha256=hashlib.sha256(fixture).hexdigest(),
    )

    assert imported["locale_sources"]["zh_cn"] == EXPECTED_CLDR_SOURCE
    assert imported["flags"] == manifest["flags"]


def test_cldr_import_rejects_digest_mismatch() -> None:
    generator = _load_generator()
    manifest = _load_manifest()

    with pytest.raises(ValueError, match="digest"):
        generator.import_cldr_zh_names(manifest, _cldr_fixture(manifest))


@pytest.mark.parametrize("failure", ("missing", "duplicate", "inheritance"))
def test_cldr_import_rejects_incomplete_or_ambiguous_standard_names(
    failure: str,
) -> None:
    generator = _load_generator()
    manifest = _load_manifest()
    fixture = _cldr_fixture(manifest, CN="↑↑↑" if failure == "inheritance" else "中国")
    root = ET.fromstring(fixture)
    territories = root.find("./localeDisplayNames/territories")
    assert territories is not None
    cn = territories.find('./territory[@type="CN"]')
    assert cn is not None
    if failure == "missing":
        territories.remove(cn)
    elif failure == "duplicate":
        territories.append(copy.deepcopy(cn))
    fixture = ET.tostring(root, encoding="utf-8")

    with pytest.raises(ValueError):
        generator.import_cldr_zh_names(
            manifest,
            fixture,
            expected_sha256=hashlib.sha256(fixture).hexdigest(),
        )


def test_generated_sprite_reconstructs_all_manifest_pixels() -> None:
    generator = _load_generator()
    manifest = _load_manifest()
    committed = SPRITE_PATH.read_text(encoding="utf-8")

    assert generator.render_sprite(manifest) == committed
    assert RUNTIME_SPRITE_PATH.read_text(encoding="utf-8") == committed

    root = ET.fromstring(committed)
    assert root.tag == f"{{{SVG_NAMESPACE}}}svg"
    assert root.attrib["aria-hidden"] == "true"
    assert root.attrib["focusable"] == "false"

    symbols = root.findall(f"{{{SVG_NAMESPACE}}}symbol")
    assert tuple(symbol.attrib["id"] for symbol in symbols) == tuple(
        f"flag-{code.lower()}" for code in EXPECTED_CODES
    )
    assert all(symbol.attrib["viewBox"] == "0 0 16 9" for symbol in symbols)
    assert all(symbol.attrib["shape-rendering"] == "crispEdges" for symbol in symbols)

    flags_by_code = {flag["code"]: flag for flag in manifest["flags"]}
    for symbol in symbols:
        code = symbol.attrib["id"].removeprefix("flag-").upper()
        reconstructed: list[list[str | None]] = [
            [None for _ in range(16)] for _ in range(9)
        ]
        for path in symbol.findall(f"{{{SVG_NAMESPACE}}}path"):
            fill = path.attrib["fill"]
            runs = tuple(RUN_PATTERN.finditer(path.attrib["d"]))
            assert runs
            assert " ".join(run.group(0) for run in runs) == path.attrib["d"]
            for run in runs:
                left = int(run.group("left"))
                x = int(run.group("x"))
                y = int(run.group("y"))
                width = int(run.group("width"))
                assert left == x
                for column in range(x, x + width):
                    assert reconstructed[y][column] is None
                    reconstructed[y][column] = fill

        assert reconstructed == flags_by_code[code]["pixels"]

    symbol_bodies = _symbol_bodies(committed)
    for symbol_id, expected_digest in APPROVED_SYMBOL_SHA256.items():
        assert hashlib.sha256(symbol_bodies[symbol_id].encode()).hexdigest() == (
            expected_digest
        )


def test_sprite_inventory_is_complete_and_excludes_sentinels() -> None:
    source = SPRITE_PATH.read_text(encoding="utf-8")

    assert source.count("<symbol ") == COUNTRY_COUNT
    assert "flag-ww" not in source
    assert "flag-hf" not in source


def _symbol_bodies(source: str) -> dict[str, str]:
    return {
        symbol_id: re.sub(r"\s+", "", body)
        for symbol_id, body in re.findall(
            r'<symbol id="(flag-[^"]+)"[^>]*>(.*?)</symbol>',
            source,
            flags=re.DOTALL,
        )
    }


def test_review_page_is_generated_from_the_same_country_symbols() -> None:
    generator = _load_generator()
    manifest = _load_manifest()
    source = HTML_PATH.read_text(encoding="utf-8")

    assert not OLD_HTML_PATH.exists()
    assert generator.render_html(manifest) == source
    assert _symbol_bodies(source) == _symbol_bodies(
        SPRITE_PATH.read_text(encoding="utf-8")
    )
    assert (
        tuple(
            re.findall(
                r'<article class="flag-card" data-country-code="([A-Z]{2})">',
                source,
            )
        )
        == EXPECTED_CODES
    )
    for flag in manifest["flags"]:
        code = flag["code"]
        assert source.count(f'<span class="country-code">{code}</span>') == 1
        assert source.count(f"<h3>{html.escape(flag['name'])}</h3>") == 1
        assert source.count(
            f'<span class="country-name-zh">{html.escape(flag["name_zh_cn"])}</span>'
        ) == 1


def test_runtime_country_module_is_generated_from_manifest() -> None:
    generator = _load_generator()
    manifest = _load_manifest()

    assert generator.render_runtime_module(manifest) == RUNTIME_DATA_PATH.read_text(
        encoding="utf-8"
    )


def test_review_page_exposes_all_treatments_in_realistic_feed_headers() -> None:
    source = HTML_PATH.read_text(encoding="utf-8")

    assert source.count('data-treatment="original"') == COUNTRY_COUNT
    assert source.count('data-treatment="recommended"') == COUNTRY_COUNT
    assert source.count('data-treatment="quiet"') == COUNTRY_COUNT
    assert source.count('class="feed-sample"') == TREATMENT_COUNT
    assert (
        source.count('class="flag-art flag-native" width="16" height="9"')
        == TREATMENT_COUNT
    )
    assert (
        source.count('class="flag-art flag-compact" width="14" height="7.875"')
        == TREATMENT_COUNT
    )
    assert source.count('class="role-badge" width="12" height="12"') == TREATMENT_COUNT
    assert "filter: saturate(0.72) brightness(0.90);" in source
    assert "opacity: 0.90;" in source
    assert "filter: saturate(0.52) brightness(0.82);" in source
    assert "opacity: 0.82;" in source


def test_review_page_is_standalone_and_decorative_svgs_are_accessible() -> None:
    source = HTML_PATH.read_text(encoding="utf-8")

    specimens = re.findall(r'<svg class="flag-art[^>]+>', source)
    assert len(specimens) == SPECIMEN_COUNT
    assert all('aria-hidden="true"' in specimen for specimen in specimens)
    assert all('focusable="false"' in specimen for specimen in specimens)
    assert re.search(r'<use href="#flag-[a-z]{2}"></use>', source)
    assert not re.search(r'(?:src|href)="(?!#)[^"]+"', source)
    assert "Pixel flags by R74n" in source
    assert "Reference artifact for the homepage feed integration" in source
    assert "Chinese territory names come from Unicode CLDR 48" in source


def test_check_mode_fails_loudly_after_controlled_output_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    generator = _load_generator()
    manifest = _load_manifest()
    sprite_path = tmp_path / SPRITE_PATH.name
    html_path = tmp_path / HTML_PATH.name
    runtime_sprite_path = tmp_path / RUNTIME_SPRITE_PATH.name
    runtime_data_path = tmp_path / RUNTIME_DATA_PATH.name
    sprite_path.write_text(generator.render_sprite(manifest), encoding="utf-8")
    html_path.write_text(generator.render_html(manifest), encoding="utf-8")
    runtime_sprite_path.write_text(generator.render_sprite(manifest), encoding="utf-8")
    runtime_data_path.write_text(generator.render_runtime_module(manifest), encoding="utf-8")
    monkeypatch.setattr(generator, "SPRITE_PATH", sprite_path)
    monkeypatch.setattr(generator, "HTML_PATH", html_path)
    monkeypatch.setattr(generator, "RUNTIME_SPRITE_PATH", runtime_sprite_path)
    monkeypatch.setattr(generator, "RUNTIME_DATA_PATH", runtime_data_path)

    assert generator.main(["--check"]) == 0
    sprite_path.write_text("<!-- controlled drift -->\n", encoding="utf-8")
    assert generator.main(["--check"]) == 1
    assert sprite_path.name in capsys.readouterr().err


@pytest.mark.parametrize(
    "viewport",
    (
        {"width": 1440, "height": 960},
        {"width": 390, "height": 844},
    ),
)
def test_standalone_review_page_renders_in_chromium_without_errors(
    viewport: dict[str, int],
) -> None:
    page_errors: list[str] = []
    failed_requests: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context(viewport=viewport)
            page = context.new_page()
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on(
                "requestfailed", lambda request: failed_requests.append(request.url)
            )
            page.goto(HTML_PATH.as_uri(), wait_until="load")

            cards = page.locator(".flag-card")
            assert cards.count() == COUNTRY_COUNT
            assert page.locator(".feed-sample").count() == TREATMENT_COUNT
            assert page.locator(".flag-art").count() == SPECIMEN_COUNT
            for index in (0, COUNTRY_COUNT // 2, COUNTRY_COUNT - 1):
                card = cards.nth(index)
                card.scroll_into_view_if_needed()
                assert card.is_visible()
                bounds = card.locator(".flag-art").first.bounding_box()
                assert bounds and bounds["width"] > 0 and bounds["height"] > 0
            assert (
                page.locator(".treatment--original .flag-art").first.evaluate(
                    "node => getComputedStyle(node).filter"
                )
                == "none"
            )
            assert (
                page.locator(".treatment--recommended .flag-art").first.evaluate(
                    "node => getComputedStyle(node).filter"
                )
                == "saturate(0.72) brightness(0.9)"
            )
            assert (
                page.locator(".treatment--recommended .flag-art").first.evaluate(
                    "node => getComputedStyle(node).opacity"
                )
                == "0.9"
            )
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert page_errors == []
            assert failed_requests == []
        finally:
            browser.close()
