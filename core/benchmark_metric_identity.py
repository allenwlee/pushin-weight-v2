"""Reviewed provider crosswalks; collection never writes catalog identity."""

from __future__ import annotations

import copy
from decimal import Decimal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction

from core.measurement_taxonomy import digest, require
from core.models import (
    DataSource,
    MeasurementSubject,
    MetricCollectionContract,
    MetricType,
    SourceMetric,
    SourceSubjectMapping,
    TaxonomyVersion,
)
from core.publisher_accounts import get_publisher

SOURCE_STATISTICS_POLICY = "source-statistics-v1"

SOURCES = {
    "github": (
        "GitHub",
        "model_adoption",
        "https://github.com",
        "github-catalog-v1",
        "exact-v1",
    ),
    "hf": (
        "Hugging Face",
        "model_adoption",
        "https://huggingface.co",
        "hf-model-v1",
        "casefold-v1",
    ),
    "openrouter": (
        "OpenRouter",
        "model_adoption",
        "https://openrouter.ai",
        "openrouter-daily-v1",
        "exact-v1",
    ),
    "arena": ("Arena", "benchmark", "https://arena.ai", "arena-style-v1", "exact-v1"),
    "opencode": (
        "OpenCode",
        "model_adoption",
        "https://opencode.ai",
        "opencode-daily-v1",
        "exact-v1",
    ),
    "artificial_analysis": (
        "Artificial Analysis",
        "benchmark",
        "https://artificialanalysis.ai",
        None,
        "exact-v1",
    ),
    "vercel_ai_gateway": (
        "Vercel AI Gateway",
        "model_adoption",
        "https://vercel.com",
        None,
        "exact-v1",
    ),
    "x": ("X", "social", "https://x.com", None, "exact-v1"),
}
METRIC_TYPES = [
    "downloads",
    "token_usage",
    "token_share",
    "benchmark_score",
    "vote_count",
    "rank",
    "score_variance",
    "post_volume",
    "likes",
    "followers",
    "active_users",
    "session_count",
    "stars",
    "forks",
    "open_issues",
    "subscribers",
    "storage_size",
    "following",
    "repository_count",
    "observation_count",
]


def definition_rows():
    rows = []
    for source, key, kind, quantity, unit, representation in [
        ("github", "repository_size_kb", "state", "count", "kilobytes", "integer"),
        ("github", "asset_size_bytes", "state", "count", "bytes", "integer"),
        ("github", "followers", "state", "count", "followers", "integer"),
        ("github", "following", "state", "count", "accounts", "integer"),
        ("github", "public_repos", "state", "count", "repositories", "integer"),
        ("github", "stars", "state", "count", "stars", "integer"),
        ("github", "forks", "state", "count", "forks", "integer"),
        ("github", "open_issues", "state", "count", "issues", "integer"),
        ("github", "subscribers", "state", "count", "subscribers", "integer"),
        ("github", "asset_downloads", "flow", "count", "downloads", "integer"),
        ("hf", "downloads", "flow", "count", "downloads", "integer"),
        ("hf", "downloads_all_time", "flow", "count", "downloads", "integer"),
        ("hf", "likes", "state", "count", "likes", "integer"),
        ("hf", "followers", "state", "count", "followers", "integer"),
        ("hf", "trending_score", "state", "score", "hf_trending_points", "float"),
        ("hf", "models_count", "state", "count", "models", "integer"),
        ("hf", "datasets_count", "state", "count", "datasets", "integer"),
        ("hf", "spaces_count", "state", "count", "spaces", "integer"),
        ("openrouter", "total_tokens", "flow", "count", "tokens", "integer"),
        ("opencode", "tokens", "flow", "count", "tokens", "integer"),
        ("opencode", "unique_users", "flow", "count", "users", "integer"),
        ("opencode", "sessions", "flow", "count", "sessions", "integer"),
        ("arena", "rating", "state", "score", "arena_points", "float"),
        ("arena", "rating_lower", "state", "score", "arena_points", "float"),
        ("arena", "rating_upper", "state", "score", "arena_points", "float"),
        ("arena", "vote_count", "state", "count", "battles", "integer"),
        ("arena", "rank", "state", "rank", "position", "integer"),
        ("arena", "variance", "state", "variance", "arena_points_squared", "float"),
    ]:
        metric_type = {
            "repository_size_kb": "storage_size",
            "asset_size_bytes": "storage_size",
            "asset_downloads": "downloads",
            "stars": "stars",
            "forks": "forks",
            "open_issues": "open_issues",
            "subscribers": "subscribers",
            "downloads": "downloads",
            "downloads_all_time": "downloads",
            "total_tokens": "token_usage",
            "tokens": "token_usage",
            "unique_users": "active_users",
            "sessions": "session_count",
            "vote_count": "vote_count",
            "rank": "rank",
            "likes": "likes",
            "followers": "followers",
            "following": "following",
            "public_repos": "repository_count",
            "models_count": "repository_count",
            "datasets_count": "repository_count",
            "spaces_count": "repository_count",
            "variance": "score_variance",
        }.get(key, "benchmark_score")
        row = {
            "source_id": source,
            "metric_type_id": metric_type,
            "metric_key": key,
            "version": 1,
            "name": key.replace("_", " ").title(),
            "unit": unit,
            "value_kind": representation,
            "quantity_form": quantity,
            "value_role": {
                "rating_lower": "lower_bound",
                "rating_upper": "upper_bound",
            }.get(key, "value"),
            "measurement_kind": kind,
            "window_mode": "none",
            "window_amount": None,
            "window_unit": None,
            "window_duration_basis": "none",
            "window_alignment": None,
            "source_timezone": "unknown",
            "required": key
            not in {
                "variance",
                "rank",
                "likes",
                "followers",
                "unique_users",
                "sessions",
                "trending_score",
                "models_count",
                "datasets_count",
                "spaces_count",
            },
            "definition_metadata": {
                "wire_field": "downloadsAllTime"
                if key == "downloads_all_time"
                else key,
                "adapter_version": SOURCES[source][3],
            },
        }
        if source == "github":
            row["required"] = False
            row["definition_metadata"].update(
                wire_field={
                    "followers": "followers",
                    "following": "following",
                    "public_repos": "public_repos",
                    "repository_size_kb": "size",
                    "asset_size_bytes": "size",
                    "stars": "stargazers_count",
                    "forks": "forks_count",
                    "open_issues": "open_issues_count",
                    "subscribers": "subscribers_count",
                    "asset_downloads": "download_count",
                }[key],
                adapter_version="github-statistics-v1",
                resource_grain="release_asset"
                if key in {"asset_downloads", "asset_size_bytes"}
                else "account"
                if key in {"followers", "following", "public_repos"}
                else "repository",
            )
            if key == "asset_downloads":
                row.update(window_mode="since_origin")
        if source == "hf" and key in {
            "trending_score",
            "models_count",
            "datasets_count",
            "spaces_count",
        }:
            row["definition_metadata"].update(
                wire_field={
                    "trending_score": "trendingScore",
                    "models_count": "numModels",
                    "datasets_count": "numDatasets",
                    "spaces_count": "numSpaces",
                }[key],
                adapter_version="hf-statistics-v1",
                resource_grain="repository" if key == "trending_score" else "account",
            )
        if key == "downloads":
            row.update(
                window_mode="rolling",
                window_amount=30,
                window_unit="day",
                window_duration_basis="unknown",
            )
        if key == "downloads_all_time":
            row.update(window_mode="since_origin")
        if source in {"openrouter", "opencode"}:
            row.update(
                window_mode="calendar",
                window_amount=1,
                window_unit="day",
                window_duration_basis="calendar",
                window_alignment="source_local_midnight",
                source_timezone="UTC",
            )
        if source == "opencode":
            row["definition_metadata"].update(
                wire_field="uniqueUsers" if key == "unique_users" else key,
                traffic_scope="opencode_go_and_free",
                approximate_distinct=key in {"unique_users", "sessions"},
                token_components=["input", "output", "cache_read", "cache_write"]
                if key == "tokens"
                else None,
            )
        rows.append(row)
    # Early official Arena publications lack uncertainty/votes. Version this
    # relaxation so already-reviewed v1 definitions remain byte-for-byte intact.
    for row in list(rows):
        if row["source_id"] == "arena" and row["metric_key"] in {
            "rating_lower",
            "rating_upper",
            "vote_count",
        }:
            rows.append({**copy.deepcopy(row), "version": 2, "required": False})
        if row["source_id"] == "hf" and row["metric_key"] in {
            "downloads",
            "downloads_all_time",
        }:
            rows.append({**copy.deepcopy(row), "version": 2, "required": False})
    # Agent Arena publishes IPS scores and signal/session counts, not text votes.
    for key, metric_type, unit, value_kind, role in [
        ("agent_score", "benchmark_score", "arena_ips_score", "float", "value"),
        (
            "agent_score_ci_lower",
            "benchmark_score",
            "arena_ips_score",
            "float",
            "lower_bound",
        ),
        (
            "agent_score_ci_upper",
            "benchmark_score",
            "arena_ips_score",
            "float",
            "upper_bound",
        ),
        (
            "observation_count",
            "observation_count",
            "signal_observations",
            "integer",
            "value",
        ),
        ("session_count", "session_count", "sessions", "integer", "value"),
    ]:
        base = copy.deepcopy(
            next(
                r
                for r in rows
                if r["source_id"] == "arena" and r["metric_key"] == "rating"
            )
        )
        base.update(
            metric_key=key,
            metric_type_id=metric_type,
            name=key.replace("_", " ").title(),
            unit=unit,
            value_kind=value_kind,
            value_role=role,
            required=False,
            quantity_form="count" if value_kind == "integer" else "score",
        )
        base["definition_metadata"] = {
            "wire_field": {
                "agent_score": "score",
                "agent_score_ci_lower": "score_ci_lower",
                "agent_score_ci_upper": "score_ci_upper",
            }.get(key, key),
            "adapter_version": "arena-agent-ips-v1",
            "score_method": "IPS",
        }
        rows.append(base)
    return rows


@transaction.atomic
def register_definitions():
    for key, (name, kind, url, adapter, normalizer) in SOURCES.items():
        source, created = DataSource.objects.get_or_create(
            pk=key,
            defaults={
                "name": name,
                "source_type": kind,
                "website_url": url,
                "adapter_key": adapter,
                "identifier_normalizer": normalizer,
            },
        )
        if created or (not source.metadata and key != "github"):
            from core.benchmark_attribution import DEFAULTS

            source.metadata = {
                "attribution": DEFAULTS.get(
                    key, {"public_display": "unresolved", "data_export": "unresolved"}
                )
            }
            source.save(update_fields=["metadata"])
        if not created and key != "github":
            require(source.source_type == kind, "source category changed")
            # Complete the registry-only U10/U12 records without enabling polling.
            source.website_url = url
            source.adapter_key = adapter
            source.identifier_normalizer = normalizer
            source.save(
                update_fields=["website_url", "adapter_key", "identifier_normalizer"]
            )
    for key in METRIC_TYPES:
        MetricType.objects.get_or_create(
            pk=key, defaults={"name": key.replace("_", " ").title()}
        )
    for row in definition_rows():
        lookup = {k: row[k] for k in ("source_id", "metric_key", "version")}
        obj, created = SourceMetric.objects.get_or_create(
            **lookup, defaults={k: v for k, v in row.items() if k not in lookup}
        )
        if not created:
            require(
                all(getattr(obj, k) == v for k, v in row.items()),
                "definition changed; create a new version",
            )
    return SourceMetric.objects.count()


def definition_snapshot(obj):
    return {
        field.attname: (str(value) if isinstance(value, Decimal) else value)
        for field in obj._meta.concrete_fields
        if field.name not in {"created_at"}
        for value in [getattr(obj, field.attname)]
    }


def validate_evidence_url(value):
    parsed = urlsplit(value)
    require(
        parsed.scheme == "https"
        and parsed.hostname
        and not parsed.username
        and not parsed.password
        and not parsed.query,
        "HTTPS evidence URL without credentials/query required",
    )
    return value


def prepare_collection(spec, *, eligibility_policy="text-benchmark-v1"):
    from core.benchmark_metric_store import safe_payload

    safe_payload(spec)
    require(
        eligibility_policy in {"text-benchmark-v1", SOURCE_STATISTICS_POLICY},
        "unknown eligibility policy",
    )
    statistics = eligibility_policy == SOURCE_STATISTICS_POLICY
    require(bool(spec.get("reviewed_by", "").strip()), "reviewed_by required")
    taxonomy = TaxonomyVersion.objects.get(pk=spec["taxonomy_version"])
    config = copy.deepcopy(spec["source_configuration"])
    require(0 < len(config) <= 10, "invalid source configuration count")
    for source_key, settings in config.items():
        from core.benchmark_metric_operations import validate_operations

        if source_key == "opencode":
            for key, value in {
                "poll_seconds": 3600,
                "freshness_seconds": 7200,
                "publication_freshness_seconds": 7200,
                "max_requests": 100,
                "max_seconds": 120,
                "max_bytes": 16 * 1024 * 1024,
                "completed_day_lag": 0,
                "recheck_days": 56,
            }.items():
                settings.setdefault(key, value)
        validate_operations(settings)
        if not statistics:
            require(
                settings.get("eligibility_policy") in (None, "text-benchmark-v1"),
                "statistics policy requires reviewed statistics contract preparation",
            )
        if statistics:
            require(
                source_key in {"hf", "github", "openrouter", "arena"},
                "unsupported native statistics source",
            )
            settings["eligibility_policy"] = SOURCE_STATISTICS_POLICY
            settings["operation"] = "source_statistics"
            settings.setdefault("native_resources", True)
            if source_key in {"openrouter", "arena"}:
                from core.source_metric_projection import (
                    validate_publication_provenance,
                )

                validate_publication_provenance(source_key, settings)
        if source_key == "arena":
            require(
                settings.get("config", "text_style_control")
                in (
                    {"text", "text_style_control", "agent"}
                    if statistics
                    else {"text", "text_style_control"}
                ),
                "unsupported Arena configuration",
            )
        if source_key == "openrouter":
            require(
                settings["completed_day_lag"] >= 1,
                "OpenRouter completed_day_lag must be at least 1",
            )
        source = DataSource.objects.get(pk=source_key)
        require(source.adapter_key is not None, "source adapter remains disabled")
        selected = settings.get("metrics", [])
        require(
            bool(selected) and len(selected) == len(set(selected)),
            "select unique metric keys",
        )
        definitions = []
        versions = settings.get("metric_versions", {})
        for key in selected:
            obj = SourceMetric.objects.get(
                source=source, metric_key=key, version=versions.get(key, 1)
            )
            if obj.source_timezone != "unknown":
                try:
                    ZoneInfo(obj.source_timezone)
                except ZoneInfoNotFoundError as exc:
                    raise ValueError("invalid source timezone") from exc
            definitions.append(definition_snapshot(obj))
        settings["definitions"] = sorted(definitions, key=lambda row: row["metric_key"])
        settings["adapter_key"] = source.adapter_key
        settings["identifier_normalizer"] = source.identifier_normalizer
        settings.setdefault(
            "attribution", copy.deepcopy(source.metadata.get("attribution", {}))
        )
        from core.benchmark_attribution import validate_use_policy

        settings.setdefault(
            "use_policy", copy.deepcopy(source.metadata.get("use_policy", {}))
        )
        validate_use_policy(settings["use_policy"])
    mappings = []
    seen = set()
    require(
        (0 < len(spec.get("mappings", [])) <= 1000)
        or (
            statistics
            and not spec.get("mappings")
            and set(config) <= {"openrouter", "arena"}
        ),
        "mapping budget exceeded or empty",
    )
    for row in spec["mappings"]:
        source = row["source"]
        literal = row["external_identifier"]
        subject_key = str(row["subject_id"])
        require(source in config, "mapping source not configured")
        require(
            isinstance(literal, str)
            and literal == literal.strip()
            and 0 < len(literal) <= 256,
            "invalid external identifier",
        )
        require(
            subject_key in taxonomy.snapshot["subjects"],
            "subject outside pinned taxonomy",
        )
        subject = MeasurementSubject.objects.select_related(
            "product__publisher_account", "account"
        ).get(pk=subject_key)
        kind = row["source_subject_kind"]
        if source == "opencode":
            from scripts.benchmark_download_collector.sources import opencode_url

            require(kind == "model", "OpenCode mapping must identify a product model")
            opencode_url(row.get("identifier_metadata", {}).get("endpoint_path"))
        scope = row.get("identifier_scope", "")
        require(
            (kind in {"model", "repository"} and subject.subject_kind == "product")
            or (kind == "lab" and subject.subject_kind == "company")
            or (kind == "account" and subject.subject_kind == "account"),
            "source/target kind mismatch",
        )
        normalized = literal.casefold() if source == "hf" else literal
        identity = (source, kind, scope, normalized)
        require(identity not in seen, "duplicate source identifier or usage alias")
        seen.add(identity)
        publisher = row.get("publisher_account_key")
        if subject.subject_kind == "account":
            account = subject.account
            frozen = taxonomy.snapshot["subjects"][subject_key]
            require(
                (source == "hf" or statistics and source == "github")
                and account.data_source_id == source,
                "account source mismatch",
            )
            require(
                normalized == account.normalized_identifier
                and frozen["normalized_identifier"] == normalized
                and frozen["data_source"] == source
                and frozen["account_kind"] == account.account_kind
                and scope == account.account_kind,
                "account identity mismatch",
            )
        if statistics:
            from core.source_metric_projection import validate_statistics_mapping

            validate_statistics_mapping(subject, row, source, taxonomy)
        if subject.subject_kind == "product":
            product = subject.product
            require(
                (
                    product.type in {"llm-model", "other-ai-model", "agent-harness"}
                    or taxonomy.snapshot["products"][str(product.product_key)].get(
                        "model_kind_qualification"
                    )
                )
                if statistics
                else product.type == "llm-model",
                "product type is not reviewed as llm-model",
            )
            require(
                product.private is not True and product.disabled is not True,
                "private or disabled product",
            )
            frozen = taxonomy.snapshot["products"][str(product.product_key)]
            require(
                product.type == frozen["type"] and product.brand_id == frozen["brand"],
                "catalog identity changed since taxonomy review",
            )
            if product.hf_namespace and product.hf_namespace.casefold() == "google":
                require(
                    product.brand_id in {"gemma", "gemini"}, "excluded Google family"
                )
            if source == "hf":
                require(
                    kind == "repository" and scope == "model",
                    "HF download scope must be model",
                )
                require(
                    product.repo_id and normalized == product.repo_id.casefold(),
                    "HF repository identity mismatch",
                )
                require(
                    product.hf_namespace
                    and product.publisher_ownership
                    and product.publisher_ownership.ownership_confirmed,
                    "HF publisher ownership unconfirmed",
                )
                from core.models import BrandCompany

                require(
                    BrandCompany.objects.filter(
                        brand_id=product.brand_id,
                        company_id=product.publisher_ownership.company_id,
                    ).exists(),
                    "HF company does not own selected brand",
                )
                if publisher:
                    require(
                        str(product.publisher_account_id) == str(publisher),
                        "unreviewed repository publisher link",
                    )
        if publisher:
            from core.models import Account

            require(
                Account.objects.filter(pk=publisher).exists()
                if statistics and source in {"openrouter", "arena"}
                else Account.objects.filter(
                    pk=publisher, data_source_id=source
                ).exists(),
                "publisher source mismatch",
            )
        accepted = {
            "source": source,
            "source_subject_kind": kind,
            "identifier_scope": scope,
            "external_identifier": literal,
            "normalized_identifier": normalized,
            "subject_id": subject_key,
            "publisher_account_key": str(publisher) if publisher else None,
            "evidence_url": validate_evidence_url(row["evidence_url"]),
            "identifier_metadata": copy.deepcopy(row.get("identifier_metadata", {})),
            "identity_snapshot": copy.deepcopy(
                taxonomy.snapshot["subjects"][subject_key]
            ),
        }
        accepted["mapping_hash"] = digest(accepted)
        mappings.append(accepted)
    mappings.sort(
        key=lambda r: (
            r["source"],
            r["source_subject_kind"],
            r["identifier_scope"],
            r["normalized_identifier"],
        )
    )
    methodology = copy.deepcopy(spec.get("methodology", {}))
    validate_comparisons(taxonomy, mappings, config, methodology)
    frozen = {
        "schema_version": 1,
        "taxonomy_version": str(taxonomy.pk),
        "catalog_hash": digest(taxonomy.snapshot),
        "mapping_hash": digest(mappings),
        "methodology_hash": digest(methodology),
        "source_configuration": config,
        "methodology": methodology,
    }
    if statistics:
        require(
            set(config) <= {"openrouter", "arena"}
            or any(m["source_subject_kind"] == "account" for m in mappings),
            "reviewed publisher mapping required",
        )
        frozen["eligibility_policy"] = SOURCE_STATISTICS_POLICY
    return taxonomy, mappings, frozen


@transaction.atomic
def configure_collection(spec, *, eligibility_policy="text-benchmark-v1"):
    taxonomy, mappings, frozen = prepare_collection(
        spec, eligibility_policy=eligibility_policy
    )
    key = digest(frozen)
    obj, created = MetricCollectionContract.objects.get_or_create(
        contract_hash=key,
        defaults={
            "taxonomy_version": taxonomy,
            "schema_version": 1,
            "catalog_hash": frozen["catalog_hash"],
            "mapping_hash": frozen["mapping_hash"],
            "methodology_hash": frozen["methodology_hash"],
            "catalog_snapshot": taxonomy.snapshot,
            "source_configuration": frozen["source_configuration"],
            "methodology": frozen["methodology"],
            "reviewed_by": spec["reviewed_by"],
        },
    )
    if not created:
        return obj
    for mapping in mappings:
        row = dict(mapping)
        row["source_id"] = row.pop("source")
        row["publisher_account_id"] = row.pop("publisher_account_key")
        SourceSubjectMapping.objects.create(
            contract=obj, reviewed_by=spec["reviewed_by"], **row
        )
    return obj


@transaction.atomic
def configure_hf_account(namespace, *, reviewed_by, evidence_url):
    require(bool(reviewed_by.strip()), "reviewed_by required")
    validate_evidence_url(evidence_url)
    link = get_publisher(source="hf", identifier=namespace, lock=True)
    require(link.ownership_confirmed is True, "namespace ownership is not confirmed")
    account = link.account
    account.provider_metadata = {
        **account.provider_metadata,
        "ownership_evidence": evidence_url,
        "reviewed_by": reviewed_by,
    }
    account.save(update_fields=["provider_metadata"])
    return account


def validate_comparisons(taxonomy, mappings, config, methodology):
    from core.benchmark_metric_store import aware_instant, native_date
    from core.measurement_taxonomy import resolve_products

    presets = methodology.get("comparisons", {})
    require(len(presets) <= 50, "comparison preset budget exceeded")
    for preset in presets.values():
        anchor = preset["launch_anchor"]
        subject = taxonomy.snapshot["subjects"].get(anchor["product_subject_id"])
        require(
            subject and subject["kind"] == "product", "launch requires reviewed product"
        )
        require(
            anchor.get("reviewed_by") and anchor.get("event_kind"),
            "launch evidence review required",
        )
        validate_evidence_url(anchor["source_url"])
        if anchor.get("precision") == "date":
            native_date(anchor["announced_date"])
            require(not anchor.get("announced_at"), "ambiguous launch representation")
        else:
            require(
                anchor.get("precision") == "instant"
                and not anchor.get("announced_date"),
                "launch precision required",
            )
            aware_instant(anchor["announced_at"])
        from core.benchmark_predecessor import validate_release_history

        validate_release_history(preset, taxonomy, mappings, config)
        lines = preset["lines"]
        chart_kind = preset.get("chart_kind")
        require(chart_kind in (None, "release_response_v1"), "unsupported chart kind")
        if chart_kind == "release_response_v1":
            require(
                len(lines) == 3
                and [line["source"] for line in lines]
                in (["x", "hf", "openrouter"], ["x", "hf", "opencode"]),
                "release response needs posts, HF and one usage provider",
            )
            launch = (
                native_date(anchor["announced_date"])
                if anchor["precision"] == "date"
                else aware_instant(anchor["announced_at"]).date()
            )
            first = native_date(preset["reference_search"]["start_date"])
            last = native_date(preset["reference_search"]["end_date"])
            require(
                launch < first <= last and 6 <= (last - first).days < 366,
                "bounded post-launch reference search required",
            )
            for line in lines:
                require(
                    line["metric_key"]
                    == {
                        "x": "post_volume",
                        "hf": "downloads",
                        "openrouter": "total_tokens",
                        "opencode": "tokens",
                    }[line["source"]],
                    "release response metric mismatch",
                )
                require(
                    line.get("transform", "identity")
                    == (
                        "adjacent_snapshot_difference"
                        if line["source"] == "hf"
                        else "identity"
                    ),
                    "release response transform mismatch",
                )
                if line["source"] != "x":
                    require(
                        line["subject_id"] == anchor["product_subject_id"]
                        and line.get("aggregation", "single") == "single",
                        "release response needs exact launch product",
                    )
            if preset.get("arena_line"):
                panel = preset["arena_line"]
                require(
                    panel["source"] == "arena"
                    and panel["metric_key"] == "rating"
                    and panel["subject_id"] == anchor["product_subject_id"]
                    and panel.get("aggregation", "single") == "single"
                    and config["arena"].get("config") == "text",
                    "Arena panel needs exact no-style-control score",
                )
                lines = [*lines, panel]
        require(
            0 < len(lines) <= 20 and len({line["key"] for line in lines}) == len(lines),
            "unique bounded lines required",
        )
        for line in lines:
            from core.benchmark_measurement_pins import validate_pin

            validate_pin(line, mappings, config)
            key = line["subject_id"]
            require(
                key in taxonomy.snapshot["subjects"], "line subject outside taxonomy"
            )
            require(
                line.get("baseline", "launch") in {"launch", "first_observed"},
                "invalid baseline policy",
            )
            if line["source"] == "x":
                require(
                    line["metric_key"] == "post_volume", "unsupported native X metric"
                )
                require(
                    line.get("post_policy") in {"legacy_brand", "direct_subject"},
                    "explicit post policy required",
                )
                continue
            require(line["source"] in config, "line source outside contract")
            require(
                line["metric_key"] in config[line["source"]]["metrics"],
                "line definition outside contract",
            )
            selected = [
                m
                for m in mappings
                if m["source"] == line["source"]
                and m["external_identifier"] in line["mapping_identifiers"]
            ]
            require(
                selected and len(selected) == len(set(line["mapping_identifiers"])),
                "line mapping missing or ambiguous",
            )
            products = resolve_products(taxonomy, key)
            for mapping in selected:
                mapped = taxonomy.snapshot["subjects"][mapping["subject_id"]]
                require(
                    mapping["subject_id"] == key
                    or (mapped["kind"] == "product" and mapped["key"] in products),
                    "mapping outside line scope",
                )
    for preset in presets.values():
        for source, key in preset.get("usage_provider_options", {}).items():
            target = presets.get(key)
            require(
                source in {"openrouter", "opencode"}
                and target
                and target.get("chart_kind") == "release_response_v1"
                and target["lines"][2]["source"] == source
                and target["launch_anchor"] == preset["launch_anchor"],
                "usage provider option differs from reviewed product",
            )
