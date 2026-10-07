"""Portable dataset credit and explicit public-use decisions for comparison data."""

from functools import cache
from pathlib import Path
from urllib.parse import urlsplit

from core.measurement_taxonomy import digest

DEFAULTS = {
    "arena": {
        "publisher": "LMArena",
        "url": "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset",
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "public_display": "allowed_with_attribution",
        "data_export": "allowed_with_attribution",
    },
    "openrouter": {
        "publisher": "OpenRouter",
        "url": "https://openrouter.ai/rankings",
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "public_display": "allowed_with_attribution",
        "data_export": "allowed_with_attribution",
    },
    "hf": {
        "publisher": "Hugging Face",
        "url": "https://huggingface.co",
        "license": None,
        "license_url": None,
        "public_display": "unresolved",
        "data_export": "unresolved",
    },
    "x": {
        "publisher": "X via TwitterAPI.io",
        "url": "https://x.com",
        "license": None,
        "license_url": None,
        "public_display": "unresolved",
        "data_export": "unresolved",
    },
}
ARCHIVES = {
    "cfahlgren1/hub-stats": {
        "publisher": "cfahlgren1",
        "url": "https://huggingface.co/datasets/cfahlgren1/hub-stats",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0",
        "public_display": "allowed_with_attribution",
        "data_export": "allowed_with_attribution",
    },
    "hfmlsoc/hub_weekly_snapshots": {
        "publisher": "hfmlsoc",
        "url": "https://huggingface.co/datasets/hfmlsoc/hub_weekly_snapshots",
        "license": "ODbL-1.0",
        "license_url": "https://opendatacommons.org/licenses/odbl/1-0/",
        "public_display": "unresolved",
        "data_export": "unresolved",
    },
}


@cache
def apache_license():
    return (
        Path(__file__).with_name("benchmark_licenses") / "Apache-2.0.txt"
    ).read_text()


def comparison_attributions(contract, lines):
    """Credit all used evidence, including an offscreen normalization baseline."""
    collected = {}
    for line in lines:
        source = line["source"]
        evidence = list(line["baseline"].get("evidence", []))
        evidence.extend(e for p in line["points"] for e in p.get("evidence", []))
        if not evidence:
            continue
        policy = contract.source_configuration.get(source, {}).get("attribution", {})
        for e in evidence:
            archive = e.get("archive") or {}
            dataset = archive.get("dataset_id")
            credit = dict(ARCHIVES.get(dataset, DEFAULTS[source]))
            if not dataset:
                credit.update(policy)
            for key in ("url", "license_url"):
                url = credit.get(key)
                if url and urlsplit(url).scheme != "https":
                    credit[key] = None
            if credit.get("license") == "Apache-2.0":
                credit["license_text"] = apache_license()
                credit["modifications"] = (
                    "Selected repository counters; normalized percentage changes are calculated by PushinWeight."
                )
            credit.update(
                source=source,
                dataset_id=dataset,
                source_as_of=e.get("source_as_of"),
                revision=archive.get("immutable_revision"),
                history_basis=archive.get(
                    "history_basis",
                    "archived_snapshot" if dataset else "observed_snapshot",
                ),
            )
            credit["notice"] = (
                f"Source: OpenRouter (openrouter.ai/rankings), as of {credit['source_as_of']}."
                if source == "openrouter"
                else f"Source: {credit['publisher']}."
            )
            collected[digest(credit)] = credit
    return list(collected.values())
