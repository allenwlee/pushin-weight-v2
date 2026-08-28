"""Explicit finite evaluation for per-brand trend narratives."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from monitor.trend_narrative_evaluation import (
    EvaluationConfigurationError,
    EvaluationManifest,
    build_real_evaluation_snapshots,
    build_synthetic_per_brand_snapshot,
    calibrate_historical_materiality,
    calibration_anchors,
    evaluation_preflight,
    run_per_brand_evaluation,
    write_evaluation_artifacts,
)
from x_monitor.config import load_config


class Command(BaseCommand):
    help = (
        "Preflight or execute bounded no-publication per-brand headline "
        "evaluation, or produce a read-only materiality proposal."
    )

    def add_arguments(self, parser) -> None:
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--execute", action="store_true")
        mode.add_argument("--calibrate", action="store_true")
        dataset = parser.add_mutually_exclusive_group()
        dataset.add_argument("--synthetic", action="store_true")
        dataset.add_argument("--real", action="store_true")
        parser.add_argument("--manifest", type=Path)
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
            help="Comma-separated fixed real-data or calibration windows.",
        )

    def handle(self, *args, **options) -> None:
        try:
            if options["calibrate"]:
                artifact = self._calibrate(options)
                paths = write_evaluation_artifacts(
                    artifact,
                    output_dir=options["output_dir"],
                    stem=self._stem("trend-headline-materiality-calibration"),
                )
                self.stdout.write(_paths_json(paths))
                return
            # Preserve the original operator contract: an omitted selector is
            # the bounded synthetic suite. Real data always remains explicit.
            if not options["synthetic"] and not options["real"]:
                options["synthetic"] = True
            if options.get("manifest") is None:
                raise EvaluationConfigurationError("evaluation_manifest_required")
            manifest = EvaluationManifest.from_path(options["manifest"])
            config = load_config(Path("config.yaml")).headline_narrative
            if options["synthetic"]:
                snapshots = [
                    build_synthetic_per_brand_snapshot(count) for count in (1, 3, 5)
                ]
                include_controls = True
                dataset_name = "synthetic"
            else:
                snapshots = build_real_evaluation_snapshots(
                    _parse_windows(options["windows"]),
                    as_of=_parse_as_of(options.get("as_of")),
                    manifest=manifest,
                )
                include_controls = False
                dataset_name = "real-data"
            if options["dry_run"]:
                self.stdout.write(
                    json.dumps(
                        evaluation_preflight(
                            manifest,
                            snapshots,
                            config,
                            include_calibration_controls=include_controls,
                        ),
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                )
                return
            artifact = run_per_brand_evaluation(
                manifest,
                snapshots,
                config,
                include_calibration_controls=include_controls,
                cancellation_path=options.get("cancel_file"),
            )
            paths = write_evaluation_artifacts(
                artifact,
                output_dir=options["output_dir"],
                stem=self._stem(f"per-brand-trend-headline-{dataset_name}-evaluation"),
            )
            self.stdout.write(
                json.dumps(
                    {
                        "json": str(paths[0]),
                        "markdown": str(paths[1]),
                        "execution": artifact["execution"],
                        "activation_assessment": artifact["activation_assessment"],
                    },
                    sort_keys=True,
                )
            )
        except EvaluationConfigurationError as exc:
            raise CommandError(str(exc)) from exc

    def _calibrate(self, options) -> dict:
        try:
            epsilon = Decimal(str(options["epsilon"]))
            windows = _parse_windows(options["windows"])
        except (InvalidOperation, ValueError) as exc:
            raise EvaluationConfigurationError("calibration_arguments_invalid") from exc
        anchors = calibration_anchors(
            as_of=_parse_as_of(options.get("as_of")),
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
            "artifact_schema_version": 2,
            "architecture": "read_only_materiality_calibration",
            "manifest": {
                "run_id": self._stem("materiality-calibration"),
                "reviewer": "operator",
                "model": "none-read-only",
            },
            "publication_enabled": False,
            "execution": {
                "calls_used": 0,
                "accounted_input_tokens": 0,
                "accounted_output_tokens": 0,
                "accounted_cost_dollars": "0.000000",
                "stop_reason": "completed",
            },
            "brand_outcomes": [],
            "critic_calibration": {},
            "calibration": calibration,
        }

    @staticmethod
    def _stem(description: str) -> str:
        return timezone.now().strftime(f"%Y-%m-%d-%H%M%S-{description}")


def _parse_as_of(value: str | None) -> datetime:
    if not value:
        return timezone.now().astimezone(UTC)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise EvaluationConfigurationError("evaluation_as_of_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvaluationConfigurationError("evaluation_as_of_timezone_required")
    return parsed.astimezone(UTC)


def _parse_windows(value: str) -> tuple[int, ...]:
    try:
        windows = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise EvaluationConfigurationError("evaluation_window_invalid") from exc
    if not windows:
        raise EvaluationConfigurationError("evaluation_window_invalid")
    return windows


def _paths_json(paths: tuple[Path, Path]) -> str:
    return json.dumps(
        {"json": str(paths[0]), "markdown": str(paths[1])}, sort_keys=True
    )
