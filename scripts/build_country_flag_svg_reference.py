"""Build the deterministic complete-country SVG flag review artifacts."""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from io import BytesIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    REPO_ROOT / "docs/ideation/assets/2026-08-29-162947-country-flag-pixels.json"
)
SPRITE_PATH = (
    REPO_ROOT / "docs/ideation/assets/2026-08-29-162947-country-flag-sprite.svg"
)
HTML_PATH = (
    REPO_ROOT / "docs/reference/2026-08-29-162947-country-flag-svg-reference.html"
)
RUNTIME_TEMPLATE_PATH = (
    REPO_ROOT / "monitor/templates/monitor/_country_flag_sprite.html"
)
RUNTIME_DATA_PATH = REPO_ROOT / "monitor/country_flags.py"
GEOGRAPHY_MANIFEST_PATH = REPO_ROOT / "monitor/data/account_geography.json"
CLDR_ZH_CN_SOURCE = {
    "provider": "Unicode CLDR",
    "release": "48",
    "url": "https://raw.githubusercontent.com/unicode-org/cldr/release-48/common/main/zh.xml",
    "sha256": "b1ef8bcadcf19fa8914d9ba812a7bcec124c72fecbf4acea02e4c8bd2fe51866",
    "license": "Unicode License v3",
    "license_url": "https://www.unicode.org/license.txt",
}
BASE_EXPECTED_CODES = (
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
ADDITIONAL_FLAG_SOURCES = {
    "AI": ("subdivision/anguilla.png", "78dce5792ef25362b84c0d7d169b303161f83899ec1e4c92fcae48d1664b0b77"),
    "AW": ("country/aruba.png", "bb65cb6563c574e7ef5a836197169fc4e899fdbf40510151ee3eff1f4a9e5493"),
    "BM": ("subdivision/bermuda.png", "38aa28239740eb9576a30cc7ca58a3818407ad888d5a4676a12eb0122610e6dd"),
    "BQ": ("subdivision/caribbean_netherlands.png", "30f0c339c664c855f7abf407459ed0fb2fa2c170d1ff06ecfa1ad699df02d3b3"),
    "GF": ("subdivision/french_guiana.png", "e8e8e7a4715fb2897098a9b198173dbe1649595682a3284f14a04b0307773c64"),
    "GG": ("country/guernsey.png", "af8490a424ba21f6d68b59ff7f3c494460b9d3497389913a84320dd360b7a115"),
    "GI": ("subdivision/gibraltar.png", "5c71d70dc5f65abab8c1fcf0be0f96218507db12718ee7e44905aa8470c582df"),
    "HK": ("country/hong_kong.png", "d52fe0820b6a95ff65136d8d26e4cdab2a60c1d4a27cc3ecfe4050dba57aee5c"),
    "IM": ("country/isle_of_man.png", "577a80c90c7c13802fe3ef1fa43b3d88755e0c2cd5f6eda344a43c0bae8f7338"),
    "JE": ("country/jersey.png", "55f5a36c968826b195f502c73174e3212f4dc96c64393ceed1e40f93af9fcab2"),
    "KY": ("subdivision/cayman_islands.png", "96638553997677d392cc338d119752cc6b1b1ebfdf6b60c88ceb5c6b67069bcf"),
    "MO": ("subdivision/macau.png", "18264511ded574c9ed2a880240840549ec1c86703beff1f3ae02cc75aeed6271"),
    "MQ": ("subdivision/martinique.png", "54c264c85dc4d6768f53e1646fb8b44ff961a51c01df140f5a4e4ee181145565"),
    "NC": ("subdivision/new_caledonia.png", "6f63abf57ba2e50c4f4826c5f444267ce85e9f4e65aff8925a481b632442ccd8"),
    "PF": ("country/french_polynesia.png", "ea62224ba763394aa1026290a6d32f3e390850fc3bbb4520a16fc432732e2536"),
    "PR": ("subdivision/puerto_rico.png", "42d20131f7ff94fcd9fc64a2facec2cb25d6763929e953a9dddfe968c043ec94"),
    "RE": ("subdivision/reunion.png", "dbf6af948d5e954d699f858bb9a3d15c155f4e4e78bf904d835655a8b205f87b"),
    "VI": ("subdivision/us_virgin_islands.png", "e30226600cda3da8f5231412e790a746d350600dd510d873e1acfe14737e096b"),
}
EXPECTED_CODES = tuple(sorted((*BASE_EXPECTED_CODES, *ADDITIONAL_FLAG_SOURCES)))
BASE_EXPECTED_IDENTITY_SHA256 = (
    "7985cf36af3bf8eea53150d8de9c9f77bd3f0dd4d72fb8b13d0deca2df440eff"
)
BASE_EXPECTED_PIXELS_SHA256 = (
    "0508e997d36281160df7a3d1e457afc453557553b4eb768373b76b22267d93b8"
)
EXPECTED_IDENTITY_SHA256 = (
    "7618e0313e037adebfee11c1b39a5e766cbc1cdc711480cc2fc9d9a03cb54e42"
)
EXPECTED_PIXELS_SHA256 = (
    "4e1815fd7a82ff21184b09bef4a5e845b1974c77002c5a9d4eeedc12b9234d5a"
)
ADDITIONAL_SOURCE_METADATA = {
    "provider": "R74n Pixel Flags",
    "base_url": "https://r74n.com/pixelflags/png/",
    "retrieved_at": "2026-09-01",
    "files": {
        code: {"path": path, "sha256": digest}
        for code, (path, digest) in sorted(ADDITIONAL_FLAG_SOURCES.items())
    },
}
COLOR_PATTERN = re.compile(r"#[0-9A-F]{6}")
SOURCE_NAME_PATTERN = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*")


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    """Load and validate the committed pixel source."""

    manifest = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    return manifest


def _pixels_sha256(flags: list[dict]) -> str:
    payload = json.dumps(
        [{"code": flag["code"], "pixels": flag["pixels"]} for flag in flags],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _validate_manifest(
    manifest: dict,
    *,
    require_localized_names: bool,
    expected_codes: tuple[str, ...] = EXPECTED_CODES,
    expected_identity_sha256: str = EXPECTED_IDENTITY_SHA256,
    expected_pixels_sha256: str = EXPECTED_PIXELS_SHA256,
    require_additional_sources: bool = True,
) -> None:
    """Reject inventory, identity, dimension, localization, or color drift."""

    expected_fields = {
        "schema_version",
        "dimensions",
        "inventory",
        "source",
        "flags",
    }
    if require_localized_names:
        expected_fields.add("locale_sources")
    if require_additional_sources:
        expected_fields.add("additional_sources")
    if set(manifest) != expected_fields:
        raise ValueError("flag manifest top-level fields are invalid")
    expected_schema = 2 if require_localized_names else 1
    if manifest.get("schema_version") != expected_schema:
        raise ValueError(f"flag manifest schema_version must be {expected_schema}")
    if manifest.get("dimensions") != {"width": 16, "height": 9}:
        raise ValueError("flag manifest dimensions must be 16x9")
    if manifest.get("inventory") != {
        "country_count": len(expected_codes),
        "identity_sha256": expected_identity_sha256,
        "pixels_sha256": expected_pixels_sha256,
    }:
        raise ValueError("flag manifest inventory metadata is invalid")
    source = manifest.get("source")
    if not isinstance(source, dict) or set(source) != {
        "top_gun_commit",
        "r74n_revision",
        "attribution",
        "license_clearance",
    }:
        raise ValueError("flag manifest source metadata is incomplete")
    if require_localized_names and manifest.get("locale_sources") != {
        "zh_cn": CLDR_ZH_CN_SOURCE
    }:
        raise ValueError("flag manifest zh_cn source metadata is invalid")
    if (
        require_additional_sources
        and manifest.get("additional_sources") != ADDITIONAL_SOURCE_METADATA
    ):
        raise ValueError("flag manifest additional source metadata is invalid")

    flags = manifest.get("flags")
    if not isinstance(flags, list):
        raise TypeError("flag manifest flags must be a list")
    if not all(isinstance(flag, dict) for flag in flags):
        raise ValueError("flag manifest entries must be objects")
    codes = tuple(flag.get("code") for flag in flags)
    if codes != expected_codes:
        raise ValueError(
            f"flag manifest must contain the exact {len(expected_codes)}-symbol code set"
        )

    identity_text = "\n".join(
        f"{flag.get('code')}\t{flag.get('source_name')}\t{flag.get('name')}"
        for flag in flags
    )
    identity_sha256 = hashlib.sha256(identity_text.encode()).hexdigest()
    if identity_sha256 != expected_identity_sha256:
        raise ValueError("flag manifest country identity mapping has drifted")

    expected_flag_fields = {"code", "name", "source_name", "pixels"}
    if require_localized_names:
        expected_flag_fields.add("name_zh_cn")
    for flag in flags:
        if set(flag) != expected_flag_fields:
            raise ValueError(f"{flag['code']} has unexpected manifest fields")
        code = flag["code"]
        if not re.fullmatch(r"[A-Z]{2}", code):
            raise ValueError(f"{code!r} is not an uppercase alpha-2 code")
        if not isinstance(flag["name"], str) or not flag["name"].strip():
            raise ValueError(f"{code} must have a review name")
        if require_localized_names and (
            not isinstance(flag["name_zh_cn"], str)
            or not flag["name_zh_cn"].strip()
            or "↑↑↑" in flag["name_zh_cn"]
        ):
            raise ValueError(f"{code} must have a resolved zh_cn display name")
        if not isinstance(
            flag["source_name"], str
        ) or not SOURCE_NAME_PATTERN.fullmatch(flag["source_name"]):
            raise ValueError(f"{code} has an invalid source name")
        pixels = flag["pixels"]
        if not isinstance(pixels, list) or len(pixels) != 9:
            raise ValueError(f"{code} must contain 9 pixel rows")
        for row in pixels:
            if not isinstance(row, list) or len(row) != 16:
                raise ValueError(f"{code} pixel rows must contain 16 cells")
            for cell in row:
                if cell is not None and (
                    not isinstance(cell, str) or not COLOR_PATTERN.fullmatch(cell)
                ):
                    raise ValueError(f"{code} contains invalid pixel color {cell!r}")

    if _pixels_sha256(flags) != expected_pixels_sha256:
        raise ValueError("flag manifest pixel matrices have drifted")


def validate_manifest(manifest: dict) -> None:
    """Validate the committed localized manifest."""

    _validate_manifest(manifest, require_localized_names=True)


def _source_pixels(png_bytes: bytes) -> list[list[str | None]]:
    """Apply the original Top Gun 32x18-to-16x9 Lanczos conversion."""

    try:
        from PIL import Image
    except ModuleNotFoundError as exc:  # pragma: no cover - import-only path
        raise RuntimeError(
            "Pillow is required only for --import-r74n-dir; generated outputs "
            "remain dependency-free"
        ) from exc

    with Image.open(BytesIO(png_bytes)) as source:
        if source.size != (32, 18):
            raise ValueError("additional flag PNG must be 32x18")
        rgba = source.convert("RGBA").resize((16, 9), Image.Resampling.LANCZOS)
    pixels: list[list[str | None]] = []
    for y in range(9):
        row: list[str | None] = []
        for x in range(16):
            red, green, blue, alpha = rgba.getpixel((x, y))
            if alpha < 128:
                row.append(None)
            else:
                row.append(f"#{red:02X}{green:02X}{blue:02X}")
        pixels.append(row)
    return pixels


def import_additional_r74n_flags(manifest: dict, source_directory: Path) -> dict:
    """Expand the approved 197-symbol source with 18 digest-pinned PNGs."""

    _validate_manifest(
        manifest,
        require_localized_names=True,
        expected_codes=BASE_EXPECTED_CODES,
        expected_identity_sha256=BASE_EXPECTED_IDENTITY_SHA256,
        expected_pixels_sha256=BASE_EXPECTED_PIXELS_SHA256,
        require_additional_sources=False,
    )
    geography = json.loads(GEOGRAPHY_MANIFEST_PATH.read_text(encoding="utf-8"))
    country_labels = {
        country["code"]: country["labels"] for country in geography["countries"]
    }
    expanded = copy.deepcopy(manifest)
    for code, (relative_path, expected_sha256) in ADDITIONAL_FLAG_SOURCES.items():
        png_path = source_directory / f"{code}.png"
        png_bytes = png_path.read_bytes()
        if hashlib.sha256(png_bytes).hexdigest() != expected_sha256:
            raise ValueError(f"R74n source digest does not match for {code}")
        labels = country_labels[code]
        expanded["flags"].append(
            {
                "code": code,
                "name": labels["en"],
                "name_zh_cn": labels["zh-cn"],
                "source_name": Path(relative_path).stem,
                "pixels": _source_pixels(png_bytes),
            }
        )
    expanded["flags"].sort(key=lambda flag: flag["code"])
    expanded["additional_sources"] = copy.deepcopy(ADDITIONAL_SOURCE_METADATA)
    identity_text = "\n".join(
        f"{flag['code']}\t{flag['source_name']}\t{flag['name']}"
        for flag in expanded["flags"]
    )
    expanded["inventory"] = {
        "country_count": len(expanded["flags"]),
        "identity_sha256": hashlib.sha256(identity_text.encode()).hexdigest(),
        "pixels_sha256": _pixels_sha256(expanded["flags"]),
    }
    return expanded


def import_cldr_zh_names(
    manifest: dict,
    xml_bytes: bytes,
    *,
    expected_sha256: str = CLDR_ZH_CN_SOURCE["sha256"],
) -> dict:
    """Return a localized manifest imported from one pinned CLDR zh file."""

    is_localized = manifest.get("schema_version") == 2
    _validate_manifest(manifest, require_localized_names=is_localized)
    actual_sha256 = hashlib.sha256(xml_bytes).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError("CLDR zh source digest does not match the pinned release")

    root = ET.fromstring(xml_bytes)
    names: dict[str, str] = {}
    for territory in root.findall("./localeDisplayNames/territories/territory"):
        code = territory.attrib.get("type", "")
        if "alt" in territory.attrib or code not in EXPECTED_CODES:
            continue
        if code in names:
            raise ValueError(f"CLDR contains duplicate standard territory {code}")
        name = (territory.text or "").strip()
        if not name or "↑↑↑" in name:
            raise ValueError(f"CLDR territory {code} is unresolved")
        names[code] = name

    missing = [code for code in EXPECTED_CODES if code not in names]
    if missing:
        raise ValueError(f"CLDR is missing standard territories: {', '.join(missing)}")

    localized = copy.deepcopy(manifest)
    localized["schema_version"] = 2
    localized["locale_sources"] = {"zh_cn": dict(CLDR_ZH_CN_SOURCE)}
    for flag in localized["flags"]:
        flag["name_zh_cn"] = names[flag["code"]]
    validate_manifest(localized)
    return localized


def render_manifest(manifest: dict, *, validate: bool = True) -> str:
    """Render readable metadata while keeping audited pixel rows compact."""

    if validate:
        validate_manifest(manifest)
    rendered_flags = []
    replacements: dict[str, str] = {}
    for flag_index, flag in enumerate(manifest["flags"]):
        pixels = []
        for row_index, row in enumerate(flag["pixels"]):
            marker = f"__PIXEL_ROW_{flag_index}_{row_index}__"
            pixels.append(marker)
            replacements[f'"{marker}"'] = json.dumps(row, separators=(",", ":"))
        rendered_flags.append(
            {
                "code": flag["code"],
                "name": flag["name"],
                "name_zh_cn": flag["name_zh_cn"],
                "source_name": flag["source_name"],
                "pixels": pixels,
            }
        )
    ordered = {
        "schema_version": manifest["schema_version"],
        "dimensions": manifest["dimensions"],
        "inventory": manifest["inventory"],
        "source": manifest["source"],
        "locale_sources": manifest["locale_sources"],
        "additional_sources": manifest["additional_sources"],
        "flags": rendered_flags,
    }
    rendered = json.dumps(ordered, ensure_ascii=False, indent=2)
    for marker, row_json in replacements.items():
        rendered = rendered.replace(marker, row_json)
    return rendered + "\n"


def _paths_by_color(pixels: list[list[str | None]]) -> dict[str, list[str]]:
    paths: dict[str, list[str]] = defaultdict(list)
    for y, row in enumerate(pixels):
        x = 0
        while x < 16:
            color = row[x]
            if color is None:
                x += 1
                continue
            right = x + 1
            while right < 16 and row[right] == color:
                right += 1
            paths[color].append(f"M{x} {y}h{right - x}v1H{x}z")
            x = right
    return dict(paths)


def render_sprite(manifest: dict) -> str:
    """Render one path per source color, composed of horizontal pixel runs."""

    validate_manifest(manifest)
    source = manifest["source"]
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">',
        (
            "  <!-- Pixel flags by R74n; source revisions: "
            f"Top Gun {source['top_gun_commit']}, R74n {source['r74n_revision']}. -->"
        ),
    ]
    for flag in manifest["flags"]:
        lines.append(
            f'  <symbol id="flag-{flag["code"].lower()}" viewBox="0 0 16 9" '
            'shape-rendering="crispEdges">'
        )
        for color, commands in _paths_by_color(flag["pixels"]).items():
            lines.append(f'    <path fill="{color}" d="{" ".join(commands)}"/>')
        lines.append("  </symbol>")
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_runtime_module(manifest: dict) -> str:
    """Render deterministic flag availability with fail-closed symbol lookup."""

    validate_manifest(manifest)
    lines = [
        '"""Generated country flag availability. Do not edit by hand."""',
        "",
        "from __future__ import annotations",
        "",
        "COUNTRY_FLAG_CODES: frozenset[str] = frozenset({",
    ]
    for flag in manifest["flags"]:
        lines.append(f"    {flag['code']!r},")
    lines.extend(
        (
            "})",
            "",
            "",
            "def country_flag_symbol_id(value: object) -> str | None:",
            '    """Return a safe local symbol ID only for an approved exact code."""',
            "",
            "    if not isinstance(value, str) or value not in COUNTRY_FLAG_CODES:",
            "        return None",
            "    return f\"flag-{value.lower()}\"",
        )
    )
    return "\n".join(lines) + "\n"


def render_runtime_template(manifest: dict) -> str:
    """Render the inline Django sprite consumed by homepage flag instances."""

    sprite = render_sprite(manifest)
    sprite = sprite.removeprefix('<?xml version="1.0" encoding="UTF-8"?>\n')
    return sprite.replace(
        "<svg ",
        '<svg class="pw-country-flag-sprite" style="display:none" ',
        1,
    )


def _embedded_sprite(manifest: dict) -> str:
    sprite = render_sprite(manifest)
    sprite = sprite.removeprefix('<?xml version="1.0" encoding="UTF-8"?>\n')
    return sprite.replace("<svg ", '<svg class="sprite" ', 1).rstrip()


def _flag_svg(code: str, class_name: str, width: str, height: str) -> str:
    return (
        f'<svg class="flag-art {class_name}" width="{width}" height="{height}" '
        'viewBox="0 0 16 9" preserveAspectRatio="xMidYMid meet" '
        'aria-hidden="true" focusable="false">'
        f'<use href="#flag-{code.lower()}"></use></svg>'
    )


def _role_badge() -> str:
    return (
        '<span class="account-role role-official" role="img" '
        'aria-label="Official account">'
        '<svg class="role-badge" width="12" height="12" viewBox="0 0 24 24" '
        'aria-hidden="true" focusable="false">'
        '<path d="M11.83 3.18c1.1-.88 2.2-.83 3.08.18.63.73 1.3 1.01 '
        "2.25.91 1.38-.14 2.19.62 2.2 2.04.01.98.34 1.62 1.12 2.22 "
        "1.13.86 1.2 1.99.22 3.02-.67.7-.89 1.41-.7 2.36.28 1.39-.41 "
        "2.28-1.83 2.43-.96.1-1.58.49-2.1 1.31-.77 1.2-1.88 1.36-3 "
        ".46-.76-.61-1.49-.76-2.42-.48-1.36.41-2.32-.19-2.59-1.59-.19 "
        "-.95-.63-1.53-1.5-1.98-1.27-.66-1.52-1.75-.72-2.91.54-.8.63 "
        "-1.53.27-2.44-.52-1.32 0-2.32 1.37-2.7.94-.27 1.49-.75 "
        '1.86-1.65.53-1.32 1.59-1.65 2.83-1.18Z" fill="none" '
        'stroke="currentColor" stroke-width="1.45" stroke-linejoin="round"></path>'
        '<path d="M15.65 10.72c.08 2.16-1.45 3.8-3.65 3.9-2.18.1-3.81-1.39 '
        "-3.9-3.54-.1-2.21 1.42-3.87 3.66-3.97 2.23-.1 3.8 1.39 "
        '3.89 3.61Z" fill="none" stroke="currentColor" stroke-width="1.35"></path>'
        "</svg></span>"
    )


def _treatment_panel(flag: dict, treatment: str, label: str, note: str) -> str:
    code = flag["code"]
    handle = f"@{code.lower()}_signal"
    return f"""      <section class="treatment treatment--{treatment}" data-treatment="{treatment}">
        <header class="treatment-head">
          <span>{html.escape(label)}</span>
          <small>{html.escape(note)}</small>
        </header>
        <div class="inspection-stage">
          {_flag_svg(code, "flag-inspection", "128", "72")}
        </div>
        <div class="feed-sample">
          <span class="avatar" aria-hidden="true">{code[0]}</span>
          <div class="feed-copy">
            <div class="feed-account">
              <strong>{handle}</strong>
              {_role_badge()}
            </div>
            <span class="feed-meta">account signal · now</span>
          </div>
          <div class="feed-flags" aria-label="Flag size comparison">
            <span class="size-candidate">
              {_flag_svg(code, "flag-native", "16", "9")}
              <small>16</small>
            </span>
            <span class="size-candidate">
              {_flag_svg(code, "flag-compact", "14", "7.875")}
              <small>14</small>
            </span>
          </div>
        </div>
      </section>"""


def _flag_card(flag: dict) -> str:
    code_kind = (
        "source-assigned country code" if flag["code"] == "XK" else "ISO 3166-1 alpha-2"
    )
    return f"""  <article class="flag-card" data-country-code="{flag["code"]}">
    <header class="country-head">
      <span class="country-code">{flag["code"]}</span>
      <div>
        <h3>{html.escape(flag["name"])}</h3>
        <p><span class="country-name-zh">{html.escape(flag["name_zh_cn"])}</span> · {code_kind} · source key {html.escape(flag["source_name"])}</p>
      </div>
    </header>
    <div class="treatment-grid">
{_treatment_panel(flag, "original", "Original", "Source color, unchanged")}
{_treatment_panel(flag, "recommended", "Recommended", "72% saturation · 90% brightness · 90% opacity")}
{_treatment_panel(flag, "quiet", "Quieter", "52% saturation · 82% brightness · 82% opacity")}
    </div>
  </article>"""


def render_html(manifest: dict) -> str:
    """Render the standalone PushinWeight feed-context review dossier."""

    validate_manifest(manifest)
    source = manifest["source"]
    cards = "\n".join(_flag_card(flag) for flag in manifest["flags"])
    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PushinWeight — Complete country SVG flag reference</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b1220;
      --card: #111827;
      --card-raised: #172033;
      --line: #1f2937;
      --line-strong: #334155;
      --text: #f3f4f6;
      --muted: #94a3b8;
      --faint: #64748b;
      --cyan: #67e8f9;
      --official: #fbbf24;
      --sans: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
    }

    * { box-sizing: border-box; }
    html { background: var(--bg); }
    body {
      margin: 0;
      min-width: 320px;
      color: var(--text);
      background:
        radial-gradient(circle at 80% -10%, rgba(34, 211, 238, .07), transparent 32rem),
        var(--bg);
      font-family: var(--sans);
      line-height: 1.5;
    }
    .sprite { position: absolute; width: 0; height: 0; overflow: hidden; }
    .shell { width: min(1180px, calc(100% - 40px)); margin: 0 auto; }

    .masthead {
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(280px, .65fr);
      gap: 40px;
      padding: 72px 0 48px;
      border-bottom: 1px solid var(--line);
    }
    .eyebrow, .fact-label, .country-code, .treatment-head, .status {
      font-family: var(--mono);
      text-transform: uppercase;
      letter-spacing: .11em;
    }
    .eyebrow { margin: 0 0 18px; color: var(--cyan); font-size: 11px; }
    h1 { max-width: 760px; margin: 0; font-size: clamp(44px, 7vw, 88px); line-height: .93; letter-spacing: -.055em; }
    .lede { max-width: 680px; margin: 26px 0 0; color: var(--muted); font-size: 18px; }
    .status-card { align-self: end; padding: 22px; border: 1px solid var(--line-strong); background: rgba(17, 24, 39, .72); }
    .status { display: block; margin-bottom: 12px; color: var(--official); font-size: 10px; }
    .status-card strong { display: block; margin-bottom: 8px; font-size: 19px; }
    .status-card p { margin: 0; color: var(--muted); font-size: 13px; }

    .facts { display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid var(--line); border-top: 0; }
    .fact { min-width: 0; padding: 18px 20px; border-right: 1px solid var(--line); }
    .fact:last-child { border-right: 0; }
    .fact-label { display: block; margin-bottom: 5px; color: var(--faint); font-size: 9px; }
    .fact strong { font-size: 14px; }

    .decision-note { display: grid; grid-template-columns: 160px 1fr; gap: 24px; margin: 48px 0; padding: 24px; border-left: 2px solid var(--cyan); background: rgba(17, 24, 39, .66); }
    .decision-note h2 { margin: 0; font-family: var(--mono); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }
    .decision-note p { margin: 0; color: var(--muted); }
    .decision-note strong { color: var(--text); }

    .section-head { display: flex; align-items: end; justify-content: space-between; gap: 24px; margin: 0 0 22px; }
    .section-head h2 { margin: 0; font-size: 30px; letter-spacing: -.025em; }
    .section-head p { max-width: 560px; margin: 0; color: var(--muted); font-size: 14px; }

    .flag-card { margin-bottom: 28px; border: 1px solid var(--line); background: var(--card); }
    .country-head { display: flex; align-items: center; gap: 18px; padding: 20px 22px; border-bottom: 1px solid var(--line); }
    .country-code { display: grid; place-items: center; width: 50px; height: 50px; border: 1px solid var(--line-strong); color: var(--cyan); font-size: 12px; }
    .country-head h3 { margin: 0 0 2px; font-size: 21px; }
    .country-head p { margin: 0; color: var(--faint); font-family: var(--mono); font-size: 10px; }

    .treatment-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .treatment { min-width: 0; padding: 20px; border-right: 1px solid var(--line); }
    .treatment:last-child { border-right: 0; }
    .treatment--recommended { background: linear-gradient(rgba(103, 232, 249, .035), rgba(103, 232, 249, .012)); box-shadow: inset 0 2px var(--cyan); }
    .treatment-head { min-height: 45px; font-size: 10px; }
    .treatment-head span { display: block; margin-bottom: 4px; color: var(--text); }
    .treatment-head small { color: var(--faint); font-family: var(--sans); font-size: 10px; letter-spacing: 0; text-transform: none; }

    .inspection-stage { display: grid; min-height: 112px; margin: 12px 0 20px; place-items: center; border: 1px solid var(--line); background: #0d1524; overflow: hidden; }
    .flag-art { display: block; flex: 0 0 auto; overflow: visible; shape-rendering: crispEdges; }
    .treatment--original .flag-art { filter: none; opacity: 1; }
    .treatment--recommended .flag-art {
      filter: saturate(0.72) brightness(0.90);
      opacity: 0.90;
    }
    .treatment--quiet .flag-art {
      filter: saturate(0.52) brightness(0.82);
      opacity: 0.82;
    }

    .feed-sample { display: grid; grid-template-columns: 30px minmax(0, 1fr) auto; align-items: center; gap: 10px; min-width: 0; padding: 11px; border: 1px solid var(--line); background: #0b1220; }
    .avatar { display: grid; place-items: center; width: 30px; height: 30px; border-radius: 50%; color: var(--bg); background: var(--muted); font-size: 11px; font-weight: 800; }
    .feed-copy { min-width: 0; }
    .feed-account { display: flex; align-items: center; min-width: 0; gap: 3px; }
    .feed-account strong { overflow: hidden; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
    .feed-meta { display: block; overflow: hidden; color: var(--faint); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
    .account-role { display: inline-flex; align-items: center; justify-content: center; width: 14px; height: 12px; margin-top: 2px; color: var(--official); flex: 0 0 auto; }
    .role-badge { display: block; }
    .feed-flags { display: flex; align-items: end; gap: 9px; }
    .size-candidate { display: grid; min-width: 18px; justify-items: center; gap: 3px; }
    .size-candidate small { color: var(--faint); font-family: var(--mono); font-size: 7px; line-height: 1; }

    footer { margin-top: 54px; padding: 28px 0 54px; border-top: 1px solid var(--line); color: var(--faint); font-size: 12px; }
    footer strong { color: var(--muted); }
    footer code { font-family: var(--mono); font-size: 10px; }

    @media (max-width: 820px) {
      .shell { width: min(100% - 24px, 620px); }
      .masthead { grid-template-columns: 1fr; gap: 28px; padding-top: 48px; }
      .facts { grid-template-columns: repeat(2, 1fr); }
      .fact:nth-child(2) { border-right: 0; }
      .fact:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
      .decision-note { grid-template-columns: 1fr; gap: 10px; }
      .section-head { align-items: start; flex-direction: column; }
      .treatment-grid { grid-template-columns: 1fr; }
      .treatment { border-right: 0; border-bottom: 1px solid var(--line); }
      .treatment:last-child { border-bottom: 0; }
    }

    @media print {
      :root { color-scheme: light; }
      body { color: #111827; background: #fff; }
      .flag-card, .status-card, .decision-note, .feed-sample, .inspection-stage { background: #fff; break-inside: avoid; }
      .flag-card, .facts, .fact, .country-head, .treatment, footer { border-color: #cbd5e1; }
    }
  </style>
</head>
<body>
{{SPRITE}}
<header class="shell masthead">
  <div>
    <p class="eyebrow">PushinWeight / design reference / 2026-08-29</p>
    <h1>Country flags at feed weight.</h1>
    <p class="lede">All 215 exact 16×9 country and area flags, converted to reusable SVG symbols. Compare source color against the approved presentation-only reductions before any homepage integration.</p>
  </div>
  <aside class="status-card">
    <span class="status">Review boundary</span>
    <strong>215 flags · Recommended approved</strong>
    <p>Reference artifact for the homepage feed integration. Runtime instances use the Recommended presentation while source fills stay exact.</p>
  </aside>
</header>

<main class="shell">
  <section class="facts" aria-label="Reference facts">
    <div class="fact"><span class="fact-label">Inventory</span><strong>215 symbols</strong></div>
    <div class="fact"><span class="fact-label">Source grid</span><strong>16 × 9 pixels</strong></div>
    <div class="fact"><span class="fact-label">Feed peers</span><strong>12 px role badge</strong></div>
    <div class="fact"><span class="fact-label">Country codes</span><strong>214 ISO · XK source code</strong></div>
  </section>

  <aside class="decision-note">
    <h2>Color approach</h2>
    <p><strong>Keep source fills fixed.</strong> Reduce only the displayed SVG instance with CSS. The recommended starting point uses 72% saturation, 90% brightness, and 90% opacity so flags remain identifiable without competing with role or sentiment accents.</p>
  </aside>

  <div class="section-head">
    <h2>Feed-context comparison</h2>
    <p>Each treatment shows the same source symbol at 8× inspection scale, native 16×9, and 14 px wide at its natural 16:9 height. The official-account badge preserves the current 14×12 slot and 12×12 icon geometry.</p>
  </div>

{{CARDS}}
</main>

<footer class="shell">
  <strong>{{ATTRIBUTION}}</strong> · Top Gun <code>{{TOP_GUN_COMMIT}}</code> · R74n <code>{{R74N_REVISION}}</code>. License clearance confirmed by the owner for this PushinWeight use. Chinese territory names come from Unicode CLDR 48 under Unicode License v3. SVG path fills remain exact to the vendored matrices; muting is presentation-only.
</footer>
</body>
</html>
"""
    return (
        template.replace("{{SPRITE}}", _embedded_sprite(manifest))
        .replace("{{CARDS}}", cards)
        .replace("{{ATTRIBUTION}}", html.escape(source["attribution"]))
        .replace("{{TOP_GUN_COMMIT}}", source["top_gun_commit"])
        .replace("{{R74N_REVISION}}", source["r74n_revision"])
    )


def _check_file(path: Path, expected: str) -> bool:
    try:
        current = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        current = None
    if current != expected:
        display_path = (
            path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
        )
        print(f"out of date: {display_path}", file=sys.stderr)
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--import-cldr-zh",
        type=Path,
        metavar="LOCAL_XML",
        help="import pinned CLDR 48 standard zh territory names into the manifest",
    )
    parser.add_argument(
        "--import-r74n-dir",
        type=Path,
        metavar="PNG_DIRECTORY",
        help="import the 18 digest-pinned R74n PNG sources into the manifest",
    )
    args = parser.parse_args(argv)

    selected_modes = sum(
        bool(value)
        for value in (args.check, args.import_cldr_zh, args.import_r74n_dir)
    )
    if selected_modes > 1:
        parser.error(
            "--check, --import-cldr-zh, and --import-r74n-dir are mutually exclusive"
        )

    if args.import_r74n_dir:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest = import_additional_r74n_flags(manifest, args.import_r74n_dir)
        MANIFEST_PATH.write_text(
            render_manifest(manifest, validate=False),
            encoding="utf-8",
        )
        inventory = manifest["inventory"]
        print(f"wrote {MANIFEST_PATH.relative_to(REPO_ROOT)}")
        print(f"identity_sha256={inventory['identity_sha256']}")
        print(f"pixels_sha256={inventory['pixels_sha256']}")
        return 0
    if args.import_cldr_zh:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest = import_cldr_zh_names(manifest, args.import_cldr_zh.read_bytes())
        MANIFEST_PATH.write_text(
            render_manifest(manifest),
            encoding="utf-8",
        )
        print(f"wrote {MANIFEST_PATH.relative_to(REPO_ROOT)}")
    else:
        manifest = load_manifest()
    sprite = render_sprite(manifest)
    dossier = render_html(manifest)
    runtime_template = render_runtime_template(manifest)
    runtime_data = render_runtime_module(manifest)
    if args.check:
        checks = (
            _check_file(SPRITE_PATH, sprite),
            _check_file(HTML_PATH, dossier),
            _check_file(RUNTIME_TEMPLATE_PATH, runtime_template),
            _check_file(RUNTIME_DATA_PATH, runtime_data),
        )
        return 0 if all(checks) else 1

    SPRITE_PATH.write_text(sprite, encoding="utf-8")
    HTML_PATH.write_text(dossier, encoding="utf-8")
    RUNTIME_TEMPLATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_TEMPLATE_PATH.write_text(runtime_template, encoding="utf-8")
    RUNTIME_DATA_PATH.write_text(runtime_data, encoding="utf-8")
    print(f"wrote {SPRITE_PATH.relative_to(REPO_ROOT)}")
    print(f"wrote {HTML_PATH.relative_to(REPO_ROOT)}")
    print(f"wrote {RUNTIME_TEMPLATE_PATH.relative_to(REPO_ROOT)}")
    print(f"wrote {RUNTIME_DATA_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
