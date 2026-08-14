from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ollija.git import CommandOutcome
from scripts.ollija.render import (
    RenderClient,
    RenderObservationError,
    parse_render_deployments,
    parse_render_resources,
)

SHA = "a" * 40


def test_render_inventory_requires_exact_branch_kind_name_and_repo() -> None:
    output = json.dumps(
        [
            {
                "service": {
                    "id": "srv-stage",
                    "name": "pushinweight-staging-web",
                    "type": "web_service",
                    "branch": "staging",
                    "repo": "https://github.com/allenwlee/pushin-weight-v2",
                    "serviceDetails": {"url": "https://staging.example.invalid"},
                }
            }
        ]
    )

    resource = parse_render_resources(output)[0]

    assert resource.kind == "web"
    assert resource.branch == "staging"
    assert resource.resource_id == "srv-stage"


def test_render_deployment_parser_keeps_commit_and_terminal_identity() -> None:
    output = json.dumps(
        [
            {
                "id": "dep-1",
                "status": "live",
                "createdAt": "2026-08-14T05:00:00Z",
                "finishedAt": "2026-08-14T05:02:00Z",
                "commit": {"id": SHA},
            }
        ]
    )

    deployment = parse_render_deployments(output, resource_id="srv-stage")[0]

    assert deployment.deployment_id == "dep-1"
    assert deployment.commit_sha == SHA
    assert deployment.status == "live"


class _Runner:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs

    def run(self, args, *, cwd: Path, timeout: float = 10) -> CommandOutcome:
        return CommandOutcome(0, self.outputs.pop(0), "")


def test_wait_rejects_failed_exact_sha_without_accepting_an_older_live_deploy(
    tmp_path: Path,
) -> None:
    failed = json.dumps(
        [
            {
                "id": "dep-new",
                "status": "build_failed",
                "createdAt": "2026-08-14T05:00:00Z",
                "finishedAt": "2026-08-14T05:02:00Z",
                "commit": {"id": SHA},
            },
            {
                "id": "dep-old",
                "status": "live",
                "createdAt": "2026-08-13T05:00:00Z",
                "finishedAt": "2026-08-13T05:02:00Z",
                "commit": {"id": "b" * 40},
            },
        ]
    )
    client = RenderClient(root=tmp_path, runner=_Runner([failed]), sleep=lambda _: None)

    with pytest.raises(RenderObservationError, match="build_failed"):
        client.wait_for_exact_deployment(
            resource_id="srv-stage",
            candidate_sha=SHA,
            timeout_seconds=1,
            poll_interval_seconds=0.01,
        )
