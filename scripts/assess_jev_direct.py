"""Preflight or execute the frozen direct-TypeSafe Jev assessment."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
import django

django.setup()

from x_monitor.config import load_config
from x_monitor.jev_assessment_runner import (
    assemble_archived_sample_assessment,
    atomic_new_json,
    atomic_new_text,
    build_assessment,
    deterministic_live_manifest,
    preflight,
    render_archived_assessment_report,
    run,
)
from x_monitor.rare_type_quality_gate import validate_assessment

FIXTURE = REPO / "tests/fixtures/rare_type_extra_search/gate_cases.json"
HITS = REPO / ".context/rare-volume-20260924/probe/hits.jsonl"
PRIVATE_ROOT = Path("/Users/fuchitalee/.local/share/pushinweight/jev-assessments")
ARCHIVED_FROZEN_RUN = PRIVATE_ROOT / "20260924-direct-v3"
ARCHIVED_LIVE_RUN = PRIVATE_ROOT / "20260924-direct-v3-live56"
ARCHIVED_LIVE_MANIFEST = PRIVATE_ROOT / "v3-live-cohort-unlabeled.json"
ARCHIVED_LABELS = (
    REPO
    / "docs/analysis/harvester/2026-09-24-160000-rare-type-live56-independent-labels.json"
)
ARCHIVED_LIVE_CORPUS_SHA256 = (
    "6092c89524ba59fe70a8773dec87267f1ac24b6df132b152286a9bbcec0fbef3"
)
ARCHIVED_ACCEPTED_HTTP_ERRORS = {
    "2101529884388716918": 529,
    "2102305091680137600": 529,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--write-live-manifest", action="store_true")
    parser.add_argument("--live-evidence", type=Path)
    parser.add_argument("--assemble-archived-live56", action="store_true")
    parser.add_argument("--archive-assessment-output", type=Path)
    parser.add_argument("--archive-report-output", type=Path)
    args = parser.parse_args()
    corpus = json.loads(FIXTURE.read_text())
    config = load_config(REPO / "config.yaml").discovery.rare_types.jev
    if args.assemble_archived_live56:
        if args.execute or args.write_live_manifest or args.live_evidence is not None:
            parser.error("archived assembly is distinct from fresh-query execution")
        if args.archive_assessment_output is None or args.archive_report_output is None:
            parser.error(
                "archived assembly requires --archive-assessment-output and "
                "--archive-report-output"
            )
        assessment = assemble_archived_sample_assessment(
            fixture_path=FIXTURE,
            frozen_run_dir=ARCHIVED_FROZEN_RUN,
            live_manifest_path=ARCHIVED_LIVE_MANIFEST,
            live_run_dir=ARCHIVED_LIVE_RUN,
            independent_labels_path=ARCHIVED_LABELS,
            config=config,
            expected_live_corpus_sha256=ARCHIVED_LIVE_CORPUS_SHA256,
            accepted_live_http_errors=ARCHIVED_ACCEPTED_HTTP_ERRORS,
            source_window_count=192,
            source_estimated_credits=22935,
        )
        validate_assessment(assessment, expected_identity=assessment["identity"])
        atomic_new_json(args.archive_assessment_output, assessment)
        atomic_new_text(
            args.archive_report_output,
            render_archived_assessment_report(assessment),
        )
        print(
            json.dumps(
                {
                    "assessment_mode": assessment["assessment_mode"],
                    "assessment_digest": assessment["assessment_digest"],
                    "assessment_path": str(args.archive_assessment_output),
                    "report_path": str(args.archive_report_output),
                    "network_calls": 0,
                },
                sort_keys=True,
            )
        )
        return 0
    if args.archive_assessment_output is not None or args.archive_report_output is not None:
        parser.error("archive output paths require --assemble-archived-live56")
    check = preflight(corpus, config)
    print(json.dumps(check, sort_keys=True))
    if args.write_live_manifest:
        target = PRIVATE_ROOT / "v3-live-cohort-unlabeled.json"
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if target.exists():
            raise SystemExit(f"refusing to overwrite {target}")
        atomic_new_json(target, deterministic_live_manifest(HITS))
    if args.execute:
        if not args.run_id or "/" in args.run_id or args.run_id in {".", ".."}:
            parser.error("--execute requires a safe --run-id")
        summary = run(
            corpus=corpus, config=config, output_dir=PRIVATE_ROOT / args.run_id
        )
        print(
            json.dumps(
                {key: value for key, value in summary.items() if key != "predictions"},
                sort_keys=True,
            )
        )
        if summary["complete"]:
            if args.live_evidence is None:
                print(
                    json.dumps(
                        {
                            "provider_capture_complete": True,
                            "assessment_status": "pending_independent_live_evidence",
                        },
                        sort_keys=True,
                    )
                )
                return 0
            assessment = build_assessment(
                fixture_path=FIXTURE,
                predictions=summary["predictions"],
                config=config,
                live_evidence=json.loads(args.live_evidence.read_text()),
            )
            target = (
                PRIVATE_ROOT
                / args.run_id
                / f"assessment-{assessment['assessment_digest']}.json"
            )
            if target.exists():
                raise SystemExit(f"refusing to overwrite {target}")
            atomic_new_json(target, assessment)
        return 0 if summary["complete"] else 2
    return 0 if check["ready"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
