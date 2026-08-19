from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.ollija.cli import main

SOURCE_ROOT = Path(__file__).resolve().parents[2]


def _git(root: Path, *args: str) -> None:
    subprocess.run(("git", *args), cwd=root, check=True, capture_output=True, text=True)


def write_repository(tmp_path: Path, *, branch: str) -> Path:
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test User")
    (root / "README.md").write_text("test\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "initial")
    _git(root, "checkout", "-b", branch)
    template = (SOURCE_ROOT / ".ollija" / "templates" / "delivery-guide.md").read_text(encoding="utf-8")
    (root / ".ollija" / "templates").mkdir(parents=True)
    (root / ".ollija" / "templates" / "delivery-guide.md").write_text(template, encoding="utf-8")
    contract = "\n".join(
        (
            "schema_version: 1",
            "authority:",
            "  canonical_host: test-host",
            f"  repository_root: {root}",
            "  repository_slug: example/test",
            "  release_worktree_label: Ollija release worktree area",
            "  release_worktree_path: .worktrees",
            "plans:",
            "  directory: docs/plans",
            "git:",
            "  remote: origin",
            "  staging_branch: staging",
            "  production_branch: main",
            "environments:",
            "  staging:",
            "    blueprint: render-staging.yaml",
            "    url: https://staging.example.invalid",
            "    service: staging",
            "  production:",
            "    blueprint: render.yaml",
            "    url: https://production.example.invalid",
            "    service: production",
            "delivery:",
            "  template: .ollija/templates/delivery-guide.md",
            "  test_commands: [pytest tests/ollija]",
            "  code_failure_route: parent workflow",
            "  infra_failure_route: infra skill",
            "",
        )
    )
    (root / ".ollija" / "project.yaml").write_text(contract, encoding="utf-8")
    return root


def invoke(root: Path, *args: str) -> tuple[int, dict[str, str]]:
    stream = io.StringIO()
    code = main(["annotate-plan", *args], cwd=root, stream=stream)
    return code, json.loads(stream.getvalue())


def _plan(root: Path, name: str, branch: str, *, marker: str = "") -> Path:
    path = root / "docs" / "plans" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        (
            "---",
            "title: Existing",
            "artifact_contract: ce-unified-plan/v1",
            "artifact_readiness: requirements-only",
            "execution: code",
            "ollija:",
            "  change_id: existing",
            f"  branch: {branch}",
            "  workflow: plan",
            "  delivery_target: on-request",
            "  delivery_selected_by_user: false",
            "---",
            "",
            "# Goal",
            "",
            marker,
            "",
        )
    )
    path.write_text(content, encoding="utf-8")
    return path


def test_no_match_creates_a_valid_unified_plan_stub_and_reports_locations(tmp_path: Path) -> None:
    root = write_repository(tmp_path, branch="feat/new-plan")
    code, result = invoke(root)

    assert code == 0
    assert result["result"] == "created"
    assert result["status"] == "created"
    path = Path(result["plan_path"])
    content = path.read_text(encoding="utf-8")
    assert path.parent == root / "docs" / "plans"
    assert path.name.endswith("-feat-new-plan-plan.md")
    assert "artifact_contract: ce-unified-plan/v1" in content
    assert "artifact_readiness: requirements-only" in content
    assert "execution: code" in content
    assert "# Goal" in content and "## Product Contract" in content
    assert result["active_worktree"] == str(root)
    assert result["authoritative_root"] == str(root)
    assert result["branch"] == "feat/new-plan"
    assert result["canonical_required_path"] == str(root / ".worktrees" / "feat" / "new-plan")
    assert result["delivery_target"] == "on-request"


def test_one_match_is_reused_but_multiple_matches_fail_without_writing(tmp_path: Path) -> None:
    root = write_repository(tmp_path, branch="feat/reuse")
    first = _plan(root, "one.md", "feat/reuse")
    code, result = invoke(root)
    assert code == 0
    assert result["plan_path"] == str(first)
    second = _plan(root, "two.md", "feat/reuse")
    before = {path: path.read_bytes() for path in (first, second)}
    code, result = invoke(root)
    assert code == 2
    assert result["error"] == "ambiguous_branch_plans_require_explicit_path"
    assert {path: path.read_bytes() for path in (first, second)} == before


def test_concurrent_no_path_invocations_create_one_plan(tmp_path: Path) -> None:
    root = write_repository(tmp_path, branch="feat/concurrent")
    environment = {**os.environ, "PYTHONPATH": str(SOURCE_ROOT)}
    command = [sys.executable, "-m", "scripts.ollija", "annotate-plan"]
    first = subprocess.Popen(command, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
    second = subprocess.Popen(command, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
    first_out, _ = first.communicate()
    second_out, _ = second.communicate()
    assert first.returncode == second.returncode == 0
    results = [json.loads(first_out), json.loads(second_out)]
    assert len({result["plan_path"] for result in results}) == 1
    assert len(list((root / "docs" / "plans").glob("*.md"))) == 1


def test_check_is_write_free_for_current_stale_missing_and_malformed_inputs(tmp_path: Path) -> None:
    root = write_repository(tmp_path, branch="feat/check")
    code, created = invoke(root)
    assert code == 0
    path = Path(created["plan_path"])
    current = path.read_bytes()
    before_check = {item.relative_to(root) for item in root.rglob("*")}
    code, result = invoke(root, "--check")
    assert code == 0 and result["result"] == "unchanged"
    assert path.read_bytes() == current
    assert {item.relative_to(root) for item in root.rglob("*")} == before_check

    path.write_text(_plan(root, "replacement.md", "feat/other").read_text(encoding="utf-8"), encoding="utf-8")
    stale = path.read_bytes()
    code, result = invoke(root, "--check", str(path))
    assert code == 2 and result["error"] == "plan_annotation_stale_run_annotate_plan"
    assert path.read_bytes() == stale

    missing_root = write_repository(tmp_path / "missing", branch="feat/missing")
    code, result = invoke(missing_root, "--check")
    assert code == 2 and result["error"] == "plan_missing_for_branch"

    malformed = _plan(root, "malformed.md", "feat/check", marker="<!-- BEGIN OLLIJA DELIVERY GUIDE -->")
    malformed_before = malformed.read_bytes()
    code, result = invoke(root, "--check", str(malformed))
    assert code == 2 and "marker" in result["error"]
    assert malformed.read_bytes() == malformed_before


def test_explicit_escape_detached_head_and_unselected_autonomous_target_do_not_write(tmp_path: Path) -> None:
    root = write_repository(tmp_path, branch="feat/safe")
    outside = root.parent / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    code, result = invoke(root, str(outside))
    assert code == 2 and result["error"] == "explicit_plan_path_must_be_under_active_plan_directory"
    assert not (root / "docs" / "plans").exists()

    code, result = invoke(root, "--delivery-target", "production")
    assert code == 2 and result["error"] == "delivery_target_requires_explicit_user_selection"
    assert not (root / "docs" / "plans").exists()

    code, result = invoke(
        root,
        "--workflow",
        "lfg",
        "--delivery-target",
        "production",
        "--delivery-selected-by-user",
    )
    assert code == 0 and result["delivery_target"] == "production"
    created = Path(result["plan_path"]).read_text(encoding="utf-8")
    assert "workflow: lfg" in created
    assert "delivery_target: production" in created
    assert "delivery_selected_by_user: true" in created

    _git(root, "checkout", "--detach")
    code, result = invoke(root)
    assert code == 2 and result["error"] == "detached_head_requires_named_branch"
