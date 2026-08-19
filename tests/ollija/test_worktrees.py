from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess

from scripts.ollija.config import load_project_config
from scripts.ollija.worktrees import canonical_worktree_path, is_canonical_worktree
from tests.ollija.test_plan_discovery import write_repository

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / ".ollija" / "hooks" / "post-checkout"


def _git(root: Path, *args: str) -> None:
    subprocess.run(("git", *args), cwd=root, check=True, capture_output=True, text=True)


def _linked_worktree(tmp_path: Path) -> tuple[Path, Path]:
    primary = write_repository(tmp_path, branch="primary-hook-test")
    linked = tmp_path / "linked-worktree"
    _git(primary, "worktree", "add", "-b", "feat/hook-test", str(linked))
    return primary, linked


def _write_wrapper(worktree: Path, *, log: Path, label: str, exit_code: int = 0) -> None:
    wrapper = worktree / "bin" / "ollija"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(
        "#!/bin/sh\n"
        "stdin_payload=$(cat)\n"
        f"printf '%s|%s|%s|%s|%s\\n' {shlex.quote(label)} \"$PWD\" \"$*\" \"$stdin_payload\" \"$OLLIJA_WORKTREE_CWD\" >> {shlex.quote(str(log))}\n"
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)


def _run_hook(worktree: Path, *, log: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("/bin/sh", str(HOOK)),
        cwd=worktree,
        input="caller-stdin-must-not-reach-ollija\n",
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "OLLIJA_TEST_LOG": str(log)},
    )


def test_canonical_worktree_requires_the_exact_branch_path(tmp_path) -> None:
    root = write_repository(tmp_path, branch="feat/exact")
    config = load_project_config(root)
    required = canonical_worktree_path(config, "feat/exact")

    assert required == root / ".worktrees" / "feat" / "exact"
    assert is_canonical_worktree(config, required, "feat/exact")
    assert not is_canonical_worktree(config, required / "nested", "feat/exact")
    assert not is_canonical_worktree(config, root / ".worktrees" / "feat-exact", "feat/exact")
    assert not is_canonical_worktree(config, root / "elsewhere", "feat/exact")


def test_post_checkout_skips_primary_and_detached_worktrees(tmp_path) -> None:
    primary, linked = _linked_worktree(tmp_path)
    log = tmp_path / "ollija.log"
    _write_wrapper(primary, log=log, label="primary")
    _write_wrapper(linked, log=log, label="linked")

    primary_result = _run_hook(primary, log=log)
    assert primary_result.returncode == 0
    assert not log.exists()

    _git(linked, "checkout", "--detach")
    detached_result = _run_hook(linked, log=log)
    assert detached_result.returncode == 0
    assert not log.exists()


def test_post_checkout_uses_active_linked_wrapper_with_empty_stdin(tmp_path) -> None:
    primary, linked = _linked_worktree(tmp_path)
    log = tmp_path / "ollija.log"
    _write_wrapper(primary, log=log, label="primary")
    _write_wrapper(linked, log=log, label="linked")

    result = _run_hook(linked, log=log)

    assert result.returncode == 0
    assert result.stderr == ""
    assert log.read_text(encoding="utf-8").splitlines() == [
        f"linked|{linked}|annotate-plan||{linked}"
    ]


def test_post_checkout_failure_is_nonblocking_and_names_active_recovery_path(tmp_path) -> None:
    _, linked = _linked_worktree(tmp_path)
    log = tmp_path / "ollija.log"
    _write_wrapper(linked, log=log, label="linked", exit_code=17)

    result = _run_hook(linked, log=log)

    assert result.returncode == 0
    assert (
        f"Recover with: cd {linked} && {linked}/bin/ollija annotate-plan" in result.stderr
    )
    assert log.read_text(encoding="utf-8").splitlines() == [
        f"linked|{linked}|annotate-plan||{linked}"
    ]


def test_post_checkout_is_executable_and_has_no_interactive_or_retired_surface() -> None:
    hook = HOOK.read_text(encoding="utf-8")

    assert HOOK.stat().st_mode & 0o111
    for forbidden in ("read ", "worktree move", "worktree guard", "status", "go "):
        assert forbidden not in hook
