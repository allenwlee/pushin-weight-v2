"""Build the pinned account-geography manifest and exact runtime resolver."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "monitor" / "data" / "account_geography.json"
OUTPUT_PATH = ROOT / "monitor" / "account_geography.py"
FLAG_MANIFEST_PATH = (
    ROOT / "docs" / "ideation" / "assets" / "2026-08-29-162947-country-flag-pixels.json"
)
M49_URL = "https://unstats.un.org/unsd/methodology/m49/overview/"
CLDR_EN_URL = "https://raw.githubusercontent.com/unicode-org/cldr-json/main/cldr-json/cldr-localenames-full/main/en/territories.json"
CLDR_ZH_URL = "https://raw.githubusercontent.com/unicode-org/cldr-json/main/cldr-json/cldr-localenames-full/main/zh-Hans/territories.json"

GUIDING_COUNTRIES = {
    "HK": ("CN", "special_administrative_region"),
    "MO": ("CN", "special_administrative_region"),
    "TW": ("CN", "owner_display_context"),
    "PR": ("US", "us_insular_area"),
    "VI": ("US", "us_insular_area"),
    "RE": ("FR", "french_overseas"),
    "PF": ("FR", "french_overseas"),
    "MQ": ("FR", "french_overseas"),
    "NC": ("FR", "french_overseas"),
    "GF": ("FR", "french_overseas"),
    "KY": ("GB", "british_overseas_territory"),
    "AI": ("GB", "british_overseas_territory"),
    "BM": ("GB", "british_overseas_territory"),
    "GI": ("GB", "british_overseas_territory"),
    "JE": ("GB", "crown_dependency"),
    "GG": ("GB", "crown_dependency"),
    "IM": ("GB", "crown_dependency"),
    "AW": ("NL", "kingdom_constituent_country"),
    "BQ": ("NL", "netherlands_public_body"),
}

PROVIDER_COUNTRY_ALIASES = {
    "Bahamas": "BS",
    "Bolivia": "BO",
    "Bonaire": "BQ",
    "Bosnia and Herzegovina": "BA",
    "Brunei Darussalam": "BN",
    "Cape Verde": "CV",
    "Czech Republic": "CZ",
    "Côte d'Ivoire": "CI",
    "Hong Kong": "HK",
    "Iran": "IR",
    "Lao People's Democratic Republic": "LA",
    "Macao": "MO",
    "Macedonia": "MK",
    "Moldova": "MD",
    "Myanmar": "MM",
    "Palestine": "PS",
    "Russian Federation": "RU",
    "South Korea": "KR",
    "Syrian Arab Republic": "SY",
    "Taiwan": "TW",
    "Turkey": "TR",
    "United Kingdom": "GB",
    "United States": "US",
    "US Virgin Islands": "VI",
    "Viet Nam": "VN",
}

PROVIDER_REGION_ALIASES = {
    "Africa": "africa",
    "Australasia": "australia-and-new-zealand",
    "Caribbean": "caribbean",
    "Central Asia": "central-asia",
    "East Asia": "eastern-asia",
    "Eastern Europe (Non-EU)": "eastern-europe-non-eu",
    "Europe": "europe",
    "North Africa": "northern-africa",
    "North America": "northern-america",
    "South America": "south-america",
    "South Asia": "southern-asia",
    "Southeast Asia": "south-eastern-asia",
    "West Asia": "western-asia",
}

EXPLICIT_UNRESOLVED = ("Congo", "Korea")
DISPLAY_PARENT_RELATIONSHIP_TYPES = {
    relationship for _parent, relationship in GUIDING_COUNTRIES.values()
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


class _M49Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.table: str | None = None
        self.in_cell = False
        self.cell: list[str] = []
        self.row: list[str] = []
        self.rows: dict[str, list[list[str]]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table" and attributes.get("id") in {
            "downloadTableEN",
            "downloadTableZH",
        }:
            self.table = str(attributes["id"])
        elif self.table and tag == "tr":
            self.row = []
        elif self.table and tag == "td":
            self.in_cell = True
            self.cell = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.table and tag == "td":
            self.row.append(" ".join("".join(self.cell).split()))
            self.in_cell = False
        elif self.table and tag == "tr" and len(self.row) >= 12:
            self.rows.setdefault(self.table, []).append(self.row)
        elif self.table and tag == "table":
            self.table = None


def _parse_m49(path: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    parser = _M49Parser()
    parser.feed(path.read_text(encoding="utf-8"))
    parsed = []
    for table in ("downloadTableEN", "downloadTableZH"):
        rows = {
            row[10]: row
            for row in parser.rows.get(table, [])
            if re.fullmatch(r"[A-Z]{2}", row[10])
        }
        parsed.append(rows)
    english, chinese = parsed
    if len(english) != 248 or set(english) != set(chinese):
        raise ValueError("UN M49 source must contain matching 248-row EN/ZH tables")
    return english, chinese


def _cldr_territories(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    locale = next(iter(payload["main"]))
    territories = payload["main"][locale]["localeDisplayNames"]["territories"]
    return {
        code: label
        for code, label in territories.items()
        if re.fullmatch(r"[A-Z]{2}", code)
    }


def _add_mapping(
    mappings: dict[str, tuple[str | None, str | None, str]],
    value: str,
    *,
    country_code: str | None = None,
    region_key: str | None = None,
    note: str,
) -> None:
    target = (country_code, region_key, note)
    previous = mappings.get(value)
    if previous and previous[:2] != target[:2]:
        raise ValueError(f"ambiguous exact provider mapping: {value!r}")
    mappings[value] = target


def build_manifest(
    *,
    m49_html: Path,
    cldr_en: Path,
    cldr_zh: Path,
    retrieved_at: str,
) -> dict:
    english, chinese = _parse_m49(m49_html)
    cldr_en_names = _cldr_territories(cldr_en)
    cldr_zh_names = _cldr_territories(cldr_zh)
    flag_payload = json.loads(FLAG_MANIFEST_PATH.read_text(encoding="utf-8"))
    flag_names = {
        flag["code"]: flag["name"]
        for flag in flag_payload["flags"]
        if flag["code"] != "XK"
    }

    region_rows: dict[str, dict] = {}
    region_key_by_m49: dict[str, str] = {}
    for code, row in english.items():
        zh_row = chinese[code]
        parent: str | None = None
        for index, level in (
            (0, "global"),
            (2, "region"),
            (4, "subregion"),
            (6, "intermediate"),
        ):
            m49_code = row[index]
            if not m49_code:
                continue
            key = _slug(row[index + 1])
            region_key_by_m49[m49_code] = key
            candidate = {
                "key": key,
                "m49_code": m49_code,
                "source": "un-m49",
                "level": level,
                "parent": parent,
                "labels": {"en": row[index + 1], "zh-cn": zh_row[index + 1]},
            }
            previous = region_rows.get(key)
            if previous and previous != candidate:
                raise ValueError(f"inconsistent region definition: {key}")
            region_rows[key] = candidate
            parent = key

    region_rows["eastern-europe-non-eu"] = {
        "key": "eastern-europe-non-eu",
        "m49_code": None,
        "source": "twitterapi-user-about",
        "level": "provider",
        "parent": "eastern-europe",
        "labels": {"en": "Eastern Europe (Non-EU)", "zh-cn": "东欧（非欧盟）"},
    }

    countries: list[dict] = []
    for code, row in sorted(english.items()):
        zh_row = chinese[code]
        region_m49 = row[6] or row[4] or row[2] or row[0]
        parent_code, relationship = GUIDING_COUNTRIES.get(code, (None, None))
        countries.append(
            {
                "code": code,
                "m49_code": row[9],
                "region_key": region_key_by_m49[region_m49],
                "labels": {"en": row[8], "zh-cn": zh_row[8]},
                "display_parent_country": parent_code,
                "display_parent_relationship_type": relationship,
            }
        )
    countries.append(
        {
            "code": "TW",
            "m49_code": "158",
            "region_key": "eastern-asia",
            "labels": {"en": cldr_en_names["TW"], "zh-cn": cldr_zh_names["TW"]},
            "display_parent_country": "CN",
            "display_parent_relationship_type": "owner_display_context",
        }
    )
    countries.sort(key=lambda item: item["code"])

    country_codes = {country["code"] for country in countries}
    mappings: dict[str, tuple[str | None, str | None, str]] = {}
    for country in countries:
        code = country["code"]
        canonical_name = country["labels"]["en"]
        if canonical_name not in EXPLICIT_UNRESOLVED:
            _add_mapping(
                mappings,
                canonical_name,
                country_code=code,
                note="UN M49 English name" if code != "TW" else "CLDR English name",
            )
        if code in cldr_en_names and cldr_en_names[code] not in EXPLICIT_UNRESOLVED:
            _add_mapping(
                mappings,
                cldr_en_names[code],
                country_code=code,
                note="CLDR English display name",
            )
        if code in flag_names and flag_names[code] not in EXPLICIT_UNRESOLVED:
            _add_mapping(
                mappings,
                flag_names[code],
                country_code=code,
                note="approved flag reference display name",
            )
    for value, code in PROVIDER_COUNTRY_ALIASES.items():
        if code not in country_codes:
            raise ValueError(f"provider alias points to unknown country: {value}")
        _add_mapping(
            mappings,
            value,
            country_code=code,
            note="reviewed TwitterAPI User About country alias",
        )
    for value, key in PROVIDER_REGION_ALIASES.items():
        if key not in region_rows:
            raise ValueError(f"provider alias points to unknown region: {value}")
        _add_mapping(
            mappings,
            value,
            region_key=key,
            note="reviewed TwitterAPI User About region",
        )

    payload = {
        "schema_version": 1,
        "sources": {
            "retrieved_at": retrieved_at,
            "un_m49": {"url": M49_URL, "sha256": _sha256(m49_html)},
            "cldr_en": {"url": CLDR_EN_URL, "sha256": _sha256(cldr_en)},
            "cldr_zh_hans": {"url": CLDR_ZH_URL, "sha256": _sha256(cldr_zh)},
            "flag_manifest": {
                "path": str(FLAG_MANIFEST_PATH.relative_to(ROOT)),
                "sha256": _sha256(FLAG_MANIFEST_PATH),
            },
        },
        "countries": countries,
        "regions": sorted(region_rows.values(), key=lambda item: item["key"]),
        "account_based_in_mappings": [
            {
                "value": value,
                "country_code": target[0],
                "region_key": target[1],
                "review_note": target[2],
            }
            for value, target in sorted(mappings.items())
        ],
        "explicit_unresolved_values": list(EXPLICIT_UNRESOLVED),
    }
    validate_manifest(payload)
    return payload


def validate_manifest(payload: dict) -> None:
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported geography manifest schema")
    countries = payload.get("countries", [])
    regions = payload.get("regions", [])
    mappings = payload.get("account_based_in_mappings", [])
    if len(countries) != 249:
        raise ValueError("geography manifest must contain 249 ISO countries/areas")
    country_by_code = {country["code"]: country for country in countries}
    if len(country_by_code) != len(countries):
        raise ValueError("country codes must be unique")
    if any(not re.fullmatch(r"[A-Z]{2}", code) for code in country_by_code):
        raise ValueError("country codes must be ISO alpha-2 values")
    if any(not re.fullmatch(r"\d{3}", country["m49_code"]) for country in countries):
        raise ValueError("country M49 codes must be three digits")
    if len({country["m49_code"] for country in countries}) != len(countries):
        raise ValueError("country M49 codes must be unique")
    region_by_key = {region["key"]: region for region in regions}
    if len(region_by_key) != len(regions):
        raise ValueError("region keys must be unique")
    for country in countries:
        if set(country["labels"]) != {"en", "zh-cn"}:
            raise ValueError(f"country labels incomplete: {country['code']}")
        if not all(country["labels"].values()):
            raise ValueError(f"country label blank: {country['code']}")
        if country["region_key"] not in region_by_key:
            raise ValueError(f"country region missing: {country['code']}")
        parent = country["display_parent_country"]
        relationship = country["display_parent_relationship_type"]
        if (parent is None) != (relationship is None):
            raise ValueError(f"country display parent is incomplete: {country['code']}")
        if (
            relationship is not None
            and relationship not in DISPLAY_PARENT_RELATIONSHIP_TYPES
        ):
            raise ValueError(
                f"country display relationship is invalid: {country['code']}"
            )
        if parent is not None and (
            parent not in country_by_code or parent == country["code"]
        ):
            raise ValueError(f"country display parent is invalid: {country['code']}")
        if (
            parent is not None
            and country_by_code[parent]["display_parent_country"] is not None
        ):
            raise ValueError(f"guiding country may not have a display parent: {parent}")
    for region in regions:
        if set(region["labels"]) != {"en", "zh-cn"}:
            raise ValueError(f"region labels incomplete: {region['key']}")
        if not all(region["labels"].values()):
            raise ValueError(f"region label blank: {region['key']}")
        if region["m49_code"] is not None and not re.fullmatch(
            r"\d{3}", region["m49_code"]
        ):
            raise ValueError(f"region M49 code invalid: {region['key']}")
        if region["parent"] is not None and region["parent"] not in region_by_key:
            raise ValueError(f"region parent missing: {region['key']}")
        seen: set[str] = set()
        cursor: str | None = region["key"]
        while cursor is not None:
            if cursor in seen:
                raise ValueError(f"region hierarchy cycle: {region['key']}")
            seen.add(cursor)
            cursor = region_by_key[cursor]["parent"]
    values = set()
    for mapping in mappings:
        value = mapping["value"]
        if value in values:
            raise ValueError(f"duplicate exact mapping: {value!r}")
        values.add(value)
        country = mapping["country_code"]
        region = mapping["region_key"]
        if (country is None) == (region is None):
            raise ValueError(f"mapping target must be exclusive: {value!r}")
        if country is not None and country not in country_by_code:
            raise ValueError(f"mapping country missing: {value!r}")
        if region is not None and region not in region_by_key:
            raise ValueError(f"mapping region missing: {value!r}")
    if values & set(payload.get("explicit_unresolved_values", [])):
        raise ValueError("explicit unresolved values may not be mapped")


def render_module(payload: dict) -> str:
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(serialized.encode()).hexdigest()
    return f'''"""Generated exact account-geography resolver. Do not edit by hand.

Source: monitor/data/account_geography.json
Run: python scripts/build_account_geography.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass

MANIFEST_SHA256 = {digest!r}
_PAYLOAD = json.loads({serialized!r})

COUNTRY_NAMES: dict[str, dict[str, str]] = {{
    item["code"]: item["labels"] for item in _PAYLOAD["countries"]
}}
REGION_NAMES: dict[str, dict[str, str]] = {{
    item["key"]: item["labels"] for item in _PAYLOAD["regions"]
}}
COUNTRY_REGIONS: dict[str, str] = {{
    item["code"]: item["region_key"] for item in _PAYLOAD["countries"]
}}
DISPLAY_PARENTS: dict[str, tuple[str, str]] = {{
    item["code"]: (
        item["display_parent_country"],
        item["display_parent_relationship_type"],
    )
    for item in _PAYLOAD["countries"]
    if item["display_parent_country"] is not None
}}
_TARGETS: dict[str, tuple[str | None, str | None]] = {{
    item["value"]: (item["country_code"], item["region_key"])
    for item in _PAYLOAD["account_based_in_mappings"]
}}


@dataclass(frozen=True, slots=True)
class GeographyResolution:
    country_code: str | None
    region_key: str | None


def resolve_account_based_in(value: object) -> GeographyResolution | None:
    """Resolve only an exact, reviewed TwitterAPI User About value."""
    if not isinstance(value, str):
        return None
    target = _TARGETS.get(value)
    if target is None:
        return None
    return GeographyResolution(country_code=target[0], region_key=target[1])
'''


def _write_or_check(path: Path, rendered: str, *, check: bool) -> None:
    if check:
        if not path.exists() or path.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"generated geography artifact is stale: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--m49-html", type=Path)
    parser.add_argument("--cldr-en", type=Path)
    parser.add_argument("--cldr-zh", type=Path)
    parser.add_argument("--retrieved-at", default="2026-09-01")
    args = parser.parse_args()

    if args.refresh:
        if not args.m49_html or not args.cldr_en or not args.cldr_zh:
            parser.error("--refresh requires --m49-html, --cldr-en, and --cldr-zh")
        payload = build_manifest(
            m49_html=args.m49_html.resolve(),
            cldr_en=args.cldr_en.resolve(),
            cldr_zh=args.cldr_zh.resolve(),
            retrieved_at=args.retrieved_at,
        )
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    else:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        validate_manifest(payload)
    _write_or_check(OUTPUT_PATH, render_module(payload), check=args.check)


if __name__ == "__main__":
    main()
