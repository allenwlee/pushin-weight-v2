"""Preflight or execute the frozen direct-TypeSafe Jev assessment."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
import django

django.setup()

from x_monitor.config import load_config
from x_monitor.jev_assessment_runner import (
    atomic_new_json,
    build_assessment,
    deterministic_live_manifest,
    preflight,
    run,
)

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests/fixtures/rare_type_extra_search/gate_cases.json"
HITS = REPO / ".context/rare-volume-20260924/probe/hits.jsonl"
PRIVATE_ROOT = Path("/Users/fuchitalee/.local/share/pushinweight/jev-assessments")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--write-live-manifest", action="store_true")
    parser.add_argument("--live-evidence", type=Path)
    args = parser.parse_args()
    corpus = json.loads(FIXTURE.read_text())
    config = load_config(REPO / "config.yaml").discovery.rare_types.jev
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
