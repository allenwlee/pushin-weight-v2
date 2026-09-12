"""Measure demand-shaped headline work against saved narrative runs."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from monitor.trend_narrative_replay import build_headline_demand_replay
from x_monitor.config import load_config


class Command(BaseCommand):
    help = "Replay demand-shaped headline policy without provider transport."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--start", required=True)
        parser.add_argument("--end", required=True)
        parser.add_argument("--source-identity", required=True)
        parser.add_argument("--candidate-revision", required=True)
        parser.add_argument(
            "--windows",
            nargs="+",
            type=int,
            default=[1, 7, 30, 365],
        )
        parser.add_argument("--config", default="config.yaml")
        parser.add_argument("--output")

    def handle(self, *args, **options) -> None:
        try:
            report = build_headline_demand_replay(
                start=_parse_datetime(options["start"]),
                end=_parse_datetime(options["end"]),
                windows=options["windows"],
                source_identity=options["source_identity"],
                candidate_revision=options["candidate_revision"],
                config=load_config(Path(options["config"])).headline_narrative,
            )
        except (OSError, TypeError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if options.get("output"):
            output = Path(options["output"])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload, encoding="utf-8")
        self.stdout.write(payload, ending="")


def _parse_datetime(raw: str) -> datetime:
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"invalid ISO datetime: {raw}") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("replay datetimes must include a UTC offset")
    return value
