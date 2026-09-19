"""Emit deterministic JSON analysis for stored Stage 1 classifications."""

from __future__ import annotations

import json
from types import MethodType

from django.core.management.base import BaseCommand
from django.db import DatabaseError
from django.utils.dateparse import parse_datetime

from core.classification_analysis import (
    ANALYSIS_SCHEMA_VERSION,
    AnalysisInputError,
    AnalysisRequest,
    analyze_classifications,
    safe_error_document,
)


class Command(BaseCommand):
    help = "Analyze current-compatible Stage 1 and optional approximate legacy rows."

    def create_parser(self, prog_name, subcommand, **kwargs):
        parser = super().create_parser(prog_name, subcommand, **kwargs)

        def structured_error(parser_self, _message):
            error = AnalysisInputError(
                "invalid_arguments", "invalid classification analysis arguments"
            )
            parser_self.exit(
                2, json.dumps(safe_error_document(error), sort_keys=True) + "\n"
            )

        parser.error = MethodType(structured_error, parser)
        return parser

    def add_arguments(self, parser) -> None:
        parser.add_argument("--history-policy", required=True)
        parser.add_argument("--start", required=True, help="Inclusive UTC timestamp.")
        parser.add_argument("--end", required=True, help="Exclusive UTC timestamp.")
        parser.add_argument(
            "--brand",
            action="append",
            default=[],
            dest="brands",
            help="Optional non-sentinel brand nickname; repeat for multiple brands.",
        )
        parser.add_argument(
            "--schema-version",
            default=ANALYSIS_SCHEMA_VERSION,
            help="Requested output schema version.",
        )

    def _timestamp(self, value: str, field: str):
        try:
            parsed = parse_datetime(value)
        except (TypeError, ValueError, OverflowError):
            parsed = None
        if parsed is None:
            raise AnalysisInputError(
                "invalid_utc_timestamp",
                f"{field} must be an ISO-8601 UTC timestamp",
                field=field,
            )
        return parsed

    def handle(self, *args, **options) -> None:
        try:
            request = AnalysisRequest(
                history_policy=options["history_policy"],
                start=self._timestamp(options["start"], "start"),
                end=self._timestamp(options["end"], "end"),
                brands=tuple(options["brands"]),
                schema_version=options["schema_version"],
            )
            result = analyze_classifications(request)
        except AnalysisInputError as exc:
            self.stderr.write(json.dumps(safe_error_document(exc), sort_keys=True))
            raise SystemExit(2) from exc
        except DatabaseError as exc:
            error = AnalysisInputError(
                "analysis_query_failed", "classification analysis query failed"
            )
            self.stderr.write(json.dumps(safe_error_document(error), sort_keys=True))
            raise SystemExit(3) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
