"""Contract tests for the three-country SVG flag review trial."""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = REPO_ROOT / "scripts/build_country_flag_svg_reference.py"
MANIFEST_PATH = (
    REPO_ROOT
    / "docs/ideation/assets/2026-08-29-162947-country-flag-pixels.json"
)
SPRITE_PATH = (
    REPO_ROOT
    / "docs/ideation/assets/2026-08-29-162947-country-flag-sprite.svg"
)
EXPECTED_CODES = ("CN", "KR", "US")
EXPECTED_NAMES = {
    "CN": "China",
    "KR": "South Korea",
    "US": "United States",
}
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
RUN_PATTERN = re.compile(r"M(?P<x>\d+) (?P<y>\d+)h(?P<width>\d+)v1H(?P<left>\d+)z")


def _load_generator():
    spec = importlib.util.spec_from_file_location("country_flag_generator", GENERATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_is_the_exact_portable_three_country_source() -> None:
    generator = _load_generator()
    manifest = _load_manifest()

    generator.validate_manifest(manifest)
    assert manifest["schema_version"] == 1
    assert manifest["dimensions"] == {"width": 16, "height": 9}
    assert manifest["source"] == {
        "top_gun_commit": "5ad0dbda9140ffa52ea791a0ec51c975b8c9a97b",
        "r74n_revision": "a1f3a5db7e97961e3e515db192ac7d2c7fa1a8bf",
        "attribution": "Pixel flags by R74n",
        "license_clearance": "Owner confirmed for this PushinWeight use on 2026-08-29",
    }

    flags = manifest["flags"]
    assert tuple(flag["code"] for flag in flags) == EXPECTED_CODES
    assert {flag["code"]: flag["name"] for flag in flags} == EXPECTED_NAMES
    assert {flag["code"]: flag["source_name"] for flag in flags} == {
        "CN": "china",
        "KR": "south_korea",
        "US": "united_states",
    }
    assert sum(len(row) for flag in flags for row in flag["pixels"]) == 432


@pytest.mark.parametrize(
    "mutate",
    (
        lambda data: data["flags"].append(copy.deepcopy(data["flags"][0])),
        lambda data: data["flags"][0].update(code="cn"),
        lambda data: data["flags"][0]["pixels"].pop(),
        lambda data: data["flags"][0]["pixels"][0].pop(),
        lambda data: data["flags"][0]["pixels"][0].__setitem__(0, "red"),
    ),
)
def test_manifest_rejects_inventory_and_pixel_shape_drift(mutate) -> None:
    generator = _load_generator()
    manifest = _load_manifest()
    mutate(manifest)

    with pytest.raises(ValueError):
        generator.validate_manifest(manifest)


def test_generated_sprite_reconstructs_all_manifest_pixels() -> None:
    generator = _load_generator()
    manifest = _load_manifest()
    committed = SPRITE_PATH.read_text(encoding="utf-8")

    assert generator.render_sprite(manifest) == committed

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


def test_sprite_inventory_excludes_deferred_flags_and_sentinels() -> None:
    source = SPRITE_PATH.read_text(encoding="utf-8")

    assert source.count("<symbol ") == 3
    for excluded in ("flag-ww", "flag-hf", "flag-jp", "flag-gb", "flag-xk"):
        assert excluded not in source
