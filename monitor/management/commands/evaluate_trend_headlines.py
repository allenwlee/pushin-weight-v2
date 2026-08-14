"""Explicit, finite synthetic headline evaluation and calibration command."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone as django_timezone

from monitor.trend_narrative_evaluation import (
    EvaluationConfigurationError,
    EvaluationManifest,
    calibrate_historical_materiality,
    calibration_anchors,
    evaluation_preflight,
    load_evaluation_scenarios,
    run_synthetic_evaluation,
    write_evaluation_artifacts,
)
from x_monitor.config import load_config

DEFAULT_SCENARIOS = Path("tests/fixtures/trend_narrative_evaluation_scenarios.json")


class Command(BaseCommand):
    help = (
        "Preflight or explicitly run bounded synthetic headline evaluation, "
        "or produce a read-only historical materiality proposal."
    )

    def add_arguments(self, parser) -> None:
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--execute", action="store_true")
        mode.add_argument("--calibrate", action="store_true")
        parser.add_argument("--manifest", type=Path)
        parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
        parser.add_argument("--output-dir", type=Path, default=Path("docs/analysis"))
        parser.add_argument("--cancel-file", type=Path)
        parser.add_argument("--as-of")
        parser.add_argument("--anchor-count", type=int, default=12)
        parser.add_argument("--anchor-step-days", type=int, default=7)
        parser.add_argument("--minimum-samples", type=int, default=20)
        parser.add_argument("--epsilon", default="0.1")
        parser.add_argument(
            "--windows",
            default="1,7,30,365",
            help="Comma-separated fixed windows for read-only calibration.",
        )

    def handle(self, *args, **options) -> None:
        try:
            if options["calibrate"]:
                artifact = self._calibrate(options)
                stem = self._stem("why-first-headline-materiality-calibration")
                paths = write_evaluation_artifacts(
                    artifact,
                    output_dir=options["output_dir"],
                    stem=stem,
                )
                self.stdout.write(
                    json.dumps(
                        {"json": str(paths[0]), "markdown": str(paths[1])},
                        sort_keys=True,
                    )
                )
                return

            manifest_path = options.get("manifest")
            if manifest_path is None:
                raise EvaluationConfigurationError("evaluation_manifest_required")
            manifest = EvaluationManifest.from_path(manifest_path)
            scenarios = load_evaluation_scenarios(options["scenarios"])
            config = load_config(Path("config.yaml")).headline_narrative
            if options["dry_run"]:
                self.stdout.write(
                    json.dumps(
                        evaluation_preflight(manifest, scenarios, config),
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                )
                return

            artifact = run_synthetic_evaluation(
                manifest,
                scenarios,
                config,
                cancellation_path=options.get("cancel_file"),
            )
            stem = self._stem("why-first-headline-evaluation")
            paths = write_evaluation_artifacts(
                artifact,
                output_dir=options["output_dir"],
                stem=stem,
            )
            self.stdout.write(
                json.dumps(
                    {
                        "json": str(paths[0]),
                        "markdown": str(paths[1]),
                        "execution": artifact["execution"],
                    },
                    sort_keys=True,
                )
            )
        except EvaluationConfigurationError as exc:
            raise CommandError(str(exc)) from exc

    def _calibrate(self, options) -> dict:
        try:
            epsilon = Decimal(str(options["epsilon"]))
            windows = tuple(
                int(value.strip())
                for value in str(options["windows"]).split(",")
                if value.strip()
            )
        except (InvalidOperation, ValueError) as exc:
            raise EvaluationConfigurationError("calibration_arguments_invalid") from exc
        as_of = _parse_as_of(options.get("as_of"))
        anchors = calibration_anchors(
            as_of=as_of,
            count=options["anchor_count"],
            step_days=options["anchor_step_days"],
        )
        calibration = calibrate_historical_materiality(
            anchors=anchors,
            windows=windows,
            minimum_samples=options["minimum_samples"],
            epsilon=epsilon,
        )
        return {
            "artifact_schema_version": 1,
            "manifest": {
                "run_id": self._stem("materiality-calibration"),
                "model": "none-read-only",
            },
            "execution": {
                "calls_used": 0,
                "accounted_input_tokens": 0,
                "accounted_cost_dollars": "0.000000",
                "stop_reason": "completed",
            },
            "calibration": calibration,
        }

    @staticmethod
    def _stem(description: str) -> str:
        return django_timezone.now().strftime(f"%Y-%m-%d-%H%M%S-{description}")


def _parse_as_of(value: str | None) -> datetime:
    if not value:
        return django_timezone.now().astimezone(UTC)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise EvaluationConfigurationError("calibration_as_of_invalid") from exc
    if parsed.tzinfo is None:
        raise EvaluationConfigurationError("calibration_as_of_timezone_required")
    return parsed.astimezone(UTC)
