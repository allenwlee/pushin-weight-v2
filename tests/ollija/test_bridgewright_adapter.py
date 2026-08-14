from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ollija.bridgewright import (
    BridgewrightError,
    collect_bridgewright_evidence,
)
from scripts.ollija.config import load_project_config
from scripts.ollija.git import CommandOutcome

REPO_ROOT = Path(__file__).resolve().parents[2]


class FakeRunner:
    def __init__(self, *, validation_status: str = "clean") -> None:
        self.validation_status = validation_status

    def run(self, args, *, cwd, timeout=10):
        if args[1] == "capabilities":
            return CommandOutcome(
                0,
                json.dumps(
                    {
                        "status": "clean",
                        "capability_contract": {
                            "build_identity": {
                                "clean": True,
                                "source_revision": "a" * 40,
                                "version": "0.1.0",
                                "capability_schema": "bridgewright.capabilities/v1",
                                "skill_digest": "b" * 64,
                            }
                        },
                    }
                ),
                "",
            )
        return CommandOutcome(
            0 if self.validation_status == "clean" else 1,
            json.dumps(
                {
                    "status": self.validation_status,
                    "findings": [],
                    "manifest_path": str(REPO_ROOT / "bridgewright.yaml"),
                }
            ),
            "",
        )


def test_bridgewright_evidence_is_clean_pinned_and_assessment_only() -> None:
    evidence = collect_bridgewright_evidence(
        load_project_config(REPO_ROOT),
        runner=FakeRunner(),
    )

    assert evidence.status == "clean"
    assert evidence.source_revision == "a" * 40
    assert len(evidence.evidence_id) == 64


def test_invalid_bridgewright_project_cannot_become_evidence() -> None:
    with pytest.raises(BridgewrightError, match="project_invalid"):
        collect_bridgewright_evidence(
            load_project_config(REPO_ROOT),
            runner=FakeRunner(validation_status="invalid"),
        )
