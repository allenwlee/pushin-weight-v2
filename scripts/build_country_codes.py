"""Generate the runtime country-code map from the approved flag inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = (
    ROOT / "docs" / "ideation" / "assets" / "2026-08-29-162947-country-flag-pixels.json"
)
DEFAULT_OUTPUT = ROOT / "monitor" / "country_codes.py"


def render(source: Path) -> str:
    payload = json.loads(source.read_text(encoding="utf-8"))
    flags = payload["flags"]
    countries = sorted((flag["code"], flag["name"]) for flag in flags)
    if len(countries) != 197 or len(dict(countries)) != 197:
        raise ValueError("approved country inventory must contain 197 unique codes")
    if any(len(code) != 2 or code != code.upper() for code, _name in countries):
        raise ValueError("country codes must be uppercase alpha-2 values")
    if len({name for _code, name in countries}) != 197:
        raise ValueError("canonical country names must be unique")

    lines = [
        '"""Generated exact country-code map. Do not edit by hand.',
        "",
        f"Source: {source.relative_to(ROOT)}",
        "Run: python scripts/build_country_codes.py",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "COUNTRY_NAMES: dict[str, str] = {",
    ]
    lines.extend(f"    {code!r}: {name!r}," for code, name in countries)
    lines.extend(
        [
            "}",
            "COUNTRY_CODES_BY_NAME: dict[str, str] = {",
            "    name: code for code, name in COUNTRY_NAMES.items()",
            "}",
            "",
            "",
            "def normalize_country_code(value: object) -> str | None:",
            '    """Return a code only for an exact approved code or English name."""',
            "    if not isinstance(value, str):",
            "        return None",
            "    if value in COUNTRY_NAMES:",
            "        return value",
            "    return COUNTRY_CODES_BY_NAME.get(value)",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = render(args.source.resolve())
    if args.check:
        if (
            not args.output.exists()
            or args.output.read_text(encoding="utf-8") != rendered
        ):
            raise SystemExit(f"generated country map is stale: {args.output}")
        return
    args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
