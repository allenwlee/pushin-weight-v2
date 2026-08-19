from __future__ import annotations

from scripts.ollija.config import load_project_config
from scripts.ollija.worktrees import canonical_worktree_path, is_canonical_worktree
from tests.ollija.test_plan_discovery import write_repository


def test_canonical_worktree_requires_the_exact_branch_path(tmp_path) -> None:
    root = write_repository(tmp_path, branch="feat/exact")
    config = load_project_config(root)
    required = canonical_worktree_path(config, "feat/exact")

    assert required == root / ".worktrees" / "feat" / "exact"
    assert is_canonical_worktree(config, required, "feat/exact")
    assert not is_canonical_worktree(config, required / "nested", "feat/exact")
    assert not is_canonical_worktree(config, root / ".worktrees" / "feat-exact", "feat/exact")
    assert not is_canonical_worktree(config, root / "elsewhere", "feat/exact")
