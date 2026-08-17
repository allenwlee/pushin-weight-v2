from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ollija.config import (
    AuthorityConfig,
    GitConfig,
    ProjectConfig,
    StateConfig,
)
from scripts.ollija.workspaces import WorkspaceError, prepare_runtime_links


def _config(canonical: Path, workspace: Path) -> ProjectConfig:
    return ProjectConfig(
        root=workspace,
        path=workspace / ".ollija" / "project.yaml",
        schema_version=1,
        adapter="pushinweight",
        authority=AuthorityConfig(
            canonical_host="fuchitalee",
            forbidden_hosts=("allenwlee",),
            repository_root=canonical,
            repository_slug="allenwlee/pushin-weight-v2",
        ),
        git=GitConfig(staging_branch="staging", production_branch="main"),
        state=StateConfig(directory=Path(".ollija/state"), retention_days=30),
        versioning={},
        environments={},
        database_safety={},
        verification={},
        ui_impact={},
        bridgewright={},
        tooling={},
    )


def test_prepare_runtime_links_uses_canonical_virtualenv(tmp_path: Path) -> None:
    canonical = tmp_path / "repo"
    workspace = canonical / ".worktrees" / "feat" / "example"
    python = canonical / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    python.chmod(0o700)
    workspace.mkdir(parents=True)

    linked = prepare_runtime_links(_config(canonical, workspace))

    assert linked == workspace / ".venv"
    assert linked.is_symlink()
    assert linked.resolve() == canonical / ".venv"


def test_prepare_runtime_links_refuses_missing_or_wrong_existing_target(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "repo"
    workspace = canonical / ".worktrees" / "feat" / "example"
    workspace.mkdir(parents=True)
    config = _config(canonical, workspace)

    with pytest.raises(WorkspaceError, match="canonical_virtualenv_missing"):
        prepare_runtime_links(config)

    python = canonical / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    python.chmod(0o700)
    foreign = tmp_path / "foreign-venv"
    foreign.mkdir()
    (workspace / ".venv").symlink_to(foreign, target_is_directory=True)

    with pytest.raises(WorkspaceError, match="workspace_virtualenv_mismatch"):
        prepare_runtime_links(config)
