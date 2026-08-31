"""Generate the compatibility country-code surface from account geography."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "monitor" / "data" / "account_geography.json"
DEFAULT_OUTPUT = ROOT / "monitor" / "country_codes.py"


def render(source: Path) -> str:
    payload = json.loads(source.read_text(encoding="utf-8"))
    countries = payload["countries"]
    mappings = payload["account_based_in_mappings"]
    if len(countries) != 249 or len({item["code"] for item in countries}) != 249:
        raise ValueError("account geography must contain 249 unique country codes")
    exact_country_targets = {
        item["value"]: item["country_code"]
        for item in mappings
        if item["country_code"] is not None
    }
    lines = [
        '"""Generated exact country-code compatibility map. Do not edit by hand.',
        "",
        f"Source: {source.relative_to(ROOT)}",
        "Run: python scripts/build_country_codes.py",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "COUNTRY_NAMES: dict[str, str] = {",
    ]
    lines.extend(
        f"    {item['code']!r}: {item['labels']['en']!r}," for item in countries
    )
    lines.extend(["}", "COUNTRY_CODES_BY_NAME: dict[str, str] = {"])
    lines.extend(
        f"    {value!r}: {code!r},"
        for value, code in sorted(exact_country_targets.items())
    )
    lines.extend(
        [
            "}",
            "",
            "",
            "def normalize_country_code(value: object) -> str | None:",
            '    """Return a code only for an exact reviewed country value."""',
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
