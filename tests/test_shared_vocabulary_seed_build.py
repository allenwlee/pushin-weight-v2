"""Rebuilding registry seeds must preserve independently owned catalogues."""

import json
import shutil

from scripts import build_shared_vocabulary_seeds as builder


def test_registry_rebuild_preserves_other_catalogue_inputs(tmp_path, monkeypatch):
    manifest_name = "shared_vocabulary_manifest.json"
    before = json.loads((builder.DATA / manifest_name).read_text())
    foundational = {
        "shared_time_zones.csv",
        "shared_languages.csv",
        "shared_locales.csv",
        "shared_measurement_units.csv",
    }
    other = {
        name: item for name, item in before["seeds"].items() if name not in foundational
    }
    for filename in [manifest_name, *before["seeds"]]:
        shutil.copyfile(builder.DATA / filename, tmp_path / filename)
    original_bytes = {name: (tmp_path / name).read_bytes() for name in other}
    monkeypatch.setattr(builder, "DATA", tmp_path)
    builder.build()
    after = json.loads((tmp_path / manifest_name).read_text())
    assert {name: after["seeds"].get(name) for name in other} == other
    assert {name: (tmp_path / name).read_bytes() for name in other} == original_bytes
    assert (
        after["seeds"]["shared_measurement_units.csv"]
        == before["seeds"]["shared_measurement_units.csv"]
    )
