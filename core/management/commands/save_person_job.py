"""Render a reviewable proposal from saved evidence, without a database connection."""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.person_names import digest
from core.staff_assets.job_history_preview import render_csv, render_html
from core.staff_assets.manifest import (
    import_manifest,
    load_manifest,
    unique_json_object,
)


class Command(BaseCommand):
    help = "Prepare detailed job-history HTML/CSV/JSON from saved sources and target inventory; no writes to DB."
    requires_system_checks = ()

    def add_arguments(self, parser):
        parser.add_argument("manifest")
        parser.add_argument("--inventory", required=True)
        parser.add_argument("--profiles")
        parser.add_argument(
            "--coverage-baseline", help="Prior prepared JSON for the same person cohort"
        )
        parser.add_argument(
            "--history-plan", help="Write an offline history-search specification"
        )
        parser.add_argument(
            "--history-cutoff",
            help="Frozen timezone-aware cutoff for the offline specification",
        )
        parser.add_argument(
            "--language-review", help="Saved owner language-review decisions"
        )
        parser.add_argument(
            "--scope", help="JSON file containing the selected brand IDs"
        )
        parser.add_argument(
            "--fresh-language",
            action="store_true",
            help="Assess saved evidence with the selected fresh language rules",
        )
        parser.add_argument(
            "--output", required=True, help="Timestamped HTML artifact path"
        )

    def handle(self, *args, **options):
        try:
            inventory = json.loads(Path(options["inventory"]).read_text())
            if inventory.get("read_only") != "on":
                raise ValueError("Expected an explicitly read-only target inventory")
            scope = (
                json.loads(Path(options["scope"]).read_text())
                if options.get("scope")
                else None
            )
            if scope is not None and (
                not isinstance(scope, dict)
                or not isinstance(scope.get("brand_ids"), list)
                or not all(isinstance(x, str) and x for x in scope["brand_ids"])
            ):
                raise ValueError("Scope must contain a brand_ids list")
            review_bytes = (
                Path(options["language_review"]).read_bytes()
                if options.get("language_review")
                else None
            )
            review = (
                json.loads(review_bytes, object_pairs_hook=unique_json_object)
                if review_bytes is not None
                else None
            )
            if review is not None and (
                not isinstance(review, dict)
                or review.get("schema") != "record-job-history-language-review/v1"
                or not isinstance(review.get("owner_exclusions"), dict)
            ):
                raise ValueError("Invalid language-review decision packet")
            manifest = load_manifest(options["manifest"])
            if review is not None:
                for field in (
                    "authorized_by",
                    "created_at_jst",
                    "source_audit",
                    "name_audit",
                ):
                    if (
                        not isinstance(review.get(field), str)
                        or not review[field].strip()
                    ):
                        raise ValueError("Incomplete language-review provenance")
                for field in ("source_audit", "name_audit"):
                    expected = review.get(field + "_sha256")
                    if not isinstance(expected, str) or len(expected) != 64:
                        raise ValueError("Incomplete language-review evidence hash")
                    actual = hashlib.sha256(
                        Path(review[field]).read_bytes()
                    ).hexdigest()
                    if actual != expected:
                        raise ValueError("Stale language-review evidence hash")
                if not options["fresh_language"]:
                    raise ValueError("Language review requires the fresh assessment")
                from core.staff_assets.job_history_names import (
                    adapt_legacy_name_review,
                    validate_name_review,
                )

                adapted = adapt_legacy_name_review(review, manifest["people"])
                if "name_review" in manifest:
                    if validate_name_review(
                        manifest["name_review"], manifest["people"]
                    ) != validate_name_review(adapted, manifest["people"]):
                        raise ValueError("Conflicting name-review decisions")
                else:
                    manifest["name_review"] = adapted
            exclusions = None
            result = import_manifest(
                manifest,
                inventory=inventory,
                fresh_language=options["fresh_language"],
                selected_brands=scope["brand_ids"] if scope else None,
                language_exclusions=exclusions,
                review_provenance={
                    "review_sha256": hashlib.sha256(review_bytes).hexdigest(),
                    "source_audit_sha256": review["source_audit_sha256"],
                    "name_audit_sha256": review["name_audit_sha256"],
                    "authorized_by": review["authorized_by"],
                    "reviewed_at": review["created_at_jst"],
                }
                if review is not None
                else None,
                audited_names=json.loads(Path(review["name_audit"]).read_text())
                if review is not None
                else None,
            )
            history_spec = None
            if bool(options["history_plan"]) != bool(options["history_cutoff"]):
                raise ValueError("History plan and cutoff must be supplied together")
            if options["history_plan"]:
                from core.staff_assets.job_history_collection import build_history_plan

                history_path = Path(options["history_plan"])
                protected = [
                    options["manifest"],
                    options["inventory"],
                    options.get("scope"),
                    options.get("language_review"),
                    options.get("profiles"),
                    options.get("coverage_baseline"),
                ]
                if review is not None:
                    protected.extend([review["source_audit"], review["name_audit"]])
                if history_path.suffix != ".json" or any(
                    value and history_path.resolve() == Path(value).resolve()
                    for value in protected
                ):
                    raise ValueError("History plan must be a separate JSON output")
                from core.staff_assets.job_history import source_post_id

                source_ids = [
                    str(value)
                    for person in manifest["people"]
                    for source in person["sources"]
                    for observation in source.get("observations") or [{}]
                    for value in [source_post_id(source, observation)]
                    if value
                ]
                history_spec = build_history_plan(
                    people=manifest["people"],
                    cutoff=datetime.fromisoformat(options["history_cutoff"]),
                    post_ids=source_ids,
                )
            if result.get("schema") != "record-job-history-preview/v1":
                raise ValueError("Expected a record-job-history/v1 manifest")
            profiles = (
                json.loads(Path(options["profiles"]).read_text())
                if options.get("profiles")
                else {}
            )
            output = Path(options["output"])
            if output.suffix != ".html":
                raise ValueError("Output must be an HTML path")
            coverage_path = output.with_name(output.stem + ".coverage.json")
            comparison = None
            if options.get("coverage_baseline"):
                from core.staff_assets.job_history_coverage import compare

                baseline = json.loads(
                    Path(options["coverage_baseline"]).read_text(),
                    object_pairs_hook=unique_json_object,
                )
                if (
                    not isinstance(baseline, dict)
                    or baseline.get("schema") != "record-job-history-preview/v1"
                    or baseline.get("payload_digest")
                    != digest(
                        {
                            key: value
                            for key, value in baseline.items()
                            if key != "payload_digest"
                        }
                    )
                ):
                    raise ValueError(
                        "Coverage baseline digest or schema does not match"
                    )
                comparison = compare(baseline, result)
            protected_inputs = [
                options["manifest"],
                options["inventory"],
                options.get("scope"),
                options.get("language_review"),
                options.get("profiles"),
                options.get("coverage_baseline"),
            ]
            if review is not None:
                protected_inputs.extend([review["source_audit"], review["name_audit"]])
            output_paths = {
                output.resolve(),
                output.with_suffix(".json").resolve(),
                output.with_suffix(".csv").resolve(),
                *([coverage_path.resolve()] if comparison is not None else []),
            }
            if any(
                value and Path(value).resolve() in output_paths
                for value in protected_inputs
            ):
                raise ValueError("Preview outputs must not overwrite input evidence")
            html = render_html(
                result,
                profiles=profiles,
                csv_name=output.with_suffix(".csv").name,
                json_name=output.with_suffix(".json").name,
                coverage_comparison=comparison,
                coverage_name=coverage_path.name if comparison is not None else None,
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            if history_spec is not None:
                if history_path.resolve() in {
                    output.resolve(),
                    output.with_suffix(".json").resolve(),
                    output.with_suffix(".csv").resolve(),
                    *([coverage_path.resolve()] if comparison is not None else []),
                }:
                    raise ValueError(
                        "History plan must be separate from preview outputs"
                    )
                history_path.parent.mkdir(parents=True, exist_ok=True)
                history_path.write_text(
                    json.dumps(history_spec, ensure_ascii=False, indent=2)
                )
            output.with_suffix(".json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2)
            )
            output.with_suffix(".csv").write_text(render_csv(result))
            if comparison is not None:
                coverage_path.write_text(
                    json.dumps(comparison, ensure_ascii=False, indent=2)
                )
            output.write_text(html)
        except (ValueError, TypeError, KeyError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            json.dumps(
                {
                    "html": str(output),
                    "people": len(result["people"]),
                    "affiliations": result["affiliation_count"],
                    "counts": result["counts"],
                    "payload_digest": result["payload_digest"],
                    "database_writes": 0,
                }
            )
        )
