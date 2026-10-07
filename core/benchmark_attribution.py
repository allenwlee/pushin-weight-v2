"""Portable dataset credit and explicit public-use decisions for comparison data."""

from functools import cache
from pathlib import Path
from urllib.parse import urlsplit

from core.measurement_taxonomy import digest

DEFAULTS = {
    "opencode": {
        "publisher": "OpenCode",
        "url": "https://opencode.ai/data/llms.txt",
        "license": None,
        "license_url": None,
        "public_display": "unresolved",
        "data_export": "unresolved",
    },
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


USES = frozenset(
    {
        "collection",
        "retention",
        "internal_analysis",
        "forecast_fitting",
        "foundation_training",
        "external_inference",
        "public_forecasts",
        "public_charts",
        "numeric_export",
        "exchange_integration",
    }
)


class UseNotPermitted(PermissionError):
    """A dataset has no reviewed permission for the requested consumer."""


def validate_use_policy(policy):
    """Validate evidence shape, without interpreting a license or granting rights."""
    if not isinstance(policy, dict):
        raise TypeError("use policy must be an object")
    for use, decision in policy.items():
        if use == "datasets":
            if not isinstance(decision, dict):
                raise ValueError("dataset policies must be an object")
            for child in decision.values():
                validate_use_policy(child)
            continue
        if use not in USES or not isinstance(decision, dict):
            raise ValueError("unknown use or invalid policy decision")
        if decision.get("status") not in {
            "allowed",
            "unresolved",
            "conditional",
            "prohibited",
        }:
            raise ValueError("invalid use decision")
        if decision["status"] == "allowed":
            from datetime import date

            date.fromisoformat(decision.get("reviewed_at", ""))
            if not all(
                decision.get(k) for k in ("reviewed_by", "access_route", "evidence_url")
            ):
                raise ValueError("allowed use requires review evidence")
            if urlsplit(decision["evidence_url"]).scheme != "https":
                raise ValueError("policy evidence must use https")
            if not isinstance(decision.get("restrictions"), list):
                raise ValueError("explicit restrictions list required")


def enforce_use(
    contract, comparison, use, *, current_policies=None, isolated_review=False
):
    """Apply frozen grants AND current restrictions to every contributing dataset.

    Review bypass is a different use, never a way to authorize public output.
    Its caller must establish a private, authenticated environment boundary.
    """
    if use == "isolated_review" and isolated_review:
        return
    if use not in USES:
        raise UseNotPermitted("Unknown or unauthorized data use")
    if current_policies is None:
        from core.models import DataSource

        current_policies = {
            source.pk: source.metadata.get("use_policy", {})
            for source in DataSource.objects.filter(
                pk__in={line["source"] for line in comparison["lines"]}
            )
        }
    targets = {(line["source"], None) for line in comparison["lines"]}
    targets.update(
        (a["source"], a.get("dataset_id")) for a in comparison.get("attributions", [])
    )
    for source, dataset in sorted(targets, key=lambda x: (x[0], x[1] or "")):
        frozen = contract.source_configuration.get(source, {}).get(
            "use_policy", {}
        ) or getattr(contract, "methodology", {}).get("source_use_policy", {}).get(
            source, {}
        )
        current = current_policies.get(source, {})
        if dataset:
            frozen = frozen.get("datasets", {}).get(dataset, {})
            current = current.get("datasets", {}).get(dataset, {})
        try:
            validate_use_policy(frozen)
            validate_use_policy(current)
        except (TypeError, ValueError) as exc:
            raise UseNotPermitted("Invalid permission evidence") from exc
        grant = frozen.get(use, {})
        restriction = current.get(use)
        if grant.get("status") != "allowed" or (
            restriction is not None and restriction.get("status") != "allowed"
        ):
            raise UseNotPermitted(f"{source}: {use} is not cleared")


def enforce_source_collection(contract, source, *, dataset=None, isolated_review=False):
    comparison = {
        "lines": [{"source": source}],
        "attributions": [{"source": source, "dataset_id": dataset}],
    }
    for use in ("collection", "retention"):
        enforce_use(
            contract,
            comparison,
            "isolated_review" if isolated_review else use,
            isolated_review=isolated_review,
        )
