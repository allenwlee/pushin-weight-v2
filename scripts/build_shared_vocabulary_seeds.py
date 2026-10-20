"""Rebuild the reviewed, offline F0 catalogue seeds from pinned registry bytes."""

from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REGISTRY = DATA / "shared_vocabulary_registry"
SOURCES = {
    "tzdata2026e.tar.gz": (
        "b26882805f26aac59d5b222978e6580484b834ccdc98be89df2f05a6dc53a652",
        "https://data.iana.org/time-zones/releases/tzdata2026e.tar.gz",
    ),
    "language-subtag-registry.txt": (
        "755fad43283be7b41ebe3c89ad054b6eaf928f404f9c0edb74799e0eab74beb1",
        "https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry",
    ),
}
QUALIFIED_LOCALES = (
    "en-GB",
    "en-US",
    "ja-JP",
    "ko-KR",
    "zh-CN",
    "zh-HK",
    "zh-TW",
    "zh-Hans",
    "zh-Hant",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def registry_records(text: str) -> list[dict[str, str]]:
    records = []
    for block in text.split("%%"):
        record = {}
        for line in block.splitlines():
            if line.startswith(" ") or ": " not in line:
                continue
            key, value = line.split(": ", 1)
            record[key] = value
        records.append(record)
    return records


def build() -> None:
    sources = {}
    for name, (expected_hash, url) in SOURCES.items():
        raw = (REGISTRY / name).read_bytes()
        if sha256(raw) != expected_hash:
            raise ValueError(f"Pinned source hash mismatch: {name}")
        sources[name] = {"sha256": expected_hash, "url": url, "bytes": len(raw)}

    zones = set()
    with tarfile.open(REGISTRY / "tzdata2026e.tar.gz", "r:gz") as archive:
        for name in (
            "africa",
            "antarctica",
            "asia",
            "australasia",
            "europe",
            "northamerica",
            "southamerica",
            "etcetera",
            "backward",
        ):
            with archive.extractfile(name) as member:
                for line in member.read().decode().splitlines():
                    tokens = line.split("#", 1)[0].split()
                    if tokens and tokens[0] == "Zone":
                        zones.add(tokens[1])
                    elif tokens and tokens[0] == "Link":
                        zones.add(tokens[2])
    # Factory explicitly denotes unknown local time, not a resolved timezone.
    zones.discard("Factory")

    records = registry_records((REGISTRY / "language-subtag-registry.txt").read_text())
    languages = {
        r["Subtag"]
        for r in records
        if r.get("Type") == "language"
        and "Preferred-Value" not in r
        and re.fullmatch(r"[a-z]{2,8}", r.get("Subtag", ""))
    }
    scripts = {r["Subtag"] for r in records if r.get("Type") == "script"}
    regions = {r["Subtag"] for r in records if r.get("Type") == "region"}
    locales = {(code, code) for code in languages}
    for tag in QUALIFIED_LOCALES:
        language, qualifier = tag.split("-", 1)
        if language not in languages or qualifier not in scripts | regions:
            raise ValueError(f"Unregistered curated locale: {tag}")
        locales.add((tag, language))

    tree = ast.parse((ROOT / "core/benchmark_metric_identity.py").read_text())
    definitions = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "definition_rows"
    )
    definitions_loop = next(n for n in definitions.body if isinstance(n, ast.For))
    units = {row[4] for row in ast.literal_eval(definitions_loop.iter)} | {
        "day",
        "second",
    }
    datasets = {
        "shared_time_zones.csv": (["code"], [(zone,) for zone in sorted(zones)]),
        "shared_languages.csv": (
            ["code"],
            [(language,) for language in sorted(languages)],
        ),
        "shared_locales.csv": (["code", "language_code"], sorted(locales)),
        "shared_measurement_units.csv": (["code"], [(unit,) for unit in sorted(units)]),
    }
    manifest = {
        "schema_version": 1,
        "tzdata_release": "2026e",
        "language_registry_date": "2026-09-17",
        "sources": sources,
        "seeds": {},
    }
    for name, (header, rows) in datasets.items():
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
        raw = stream.getvalue().encode()
        (DATA / name).write_bytes(raw)
        manifest["seeds"][name] = {"sha256": sha256(raw), "rows": len(rows)}
    (DATA / "shared_vocabulary_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(
        json.dumps(
            {name: value["rows"] for name, value in manifest["seeds"].items()},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    build()
