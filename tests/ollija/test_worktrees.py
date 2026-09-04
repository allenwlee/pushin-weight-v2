from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / ".ollija" / "hooks" / "post-checkout"


def _git(
    root: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> None:
    subprocess.run(
        ("git", *args),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def _write_repository(tmp_path: Path, *, branch: str) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "-b", branch)
    _git(root, "config", "user.email", "tests@example.com")
    _git(root, "config", "user.name", "Tests")
    (root / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "fixture")
    return root


def _linked_worktree(
    tmp_path: Path,
    *,
    linked_name: str = "linked-worktree",
) -> tuple[Path, Path]:
    primary = _write_repository(tmp_path, branch="primary-hook-test")
    linked = tmp_path / linked_name
    _git(primary, "worktree", "add", "-b", "feat/hook-test", str(linked))
    return primary, linked


def _write_fake_cli(
    directory: Path,
    *,
    log: Path,
    label: str = "standalone",
    exit_code: int = 0,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    command = directory / "ollija"
    command.write_text(
        "#!/bin/sh\n"
        "stdin_payload=$(cat)\n"
        f'printf \'%s|%s|%s|%s|%s|%s|%s\\n\' {shlex.quote(label)} "$PWD" "$*" "$stdin_payload" "$OLLIJA_WORKTREE_CWD" "$OLLIJA_PROJECT_ROOT" "$OLLIJA_HOOK_NONBLOCKING_LOCK" >> {shlex.quote(str(log))}\n'
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    command.chmod(0o755)
    return directory


def _path_with(directory: Path) -> str:
    return os.pathsep.join((str(directory), "/usr/bin", "/bin"))


def _run_hook(
    worktree: Path,
    *,
    path: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("/bin/sh", str(HOOK)),
        cwd=worktree,
        input="caller-stdin-must-not-reach-ollija\n",
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PATH": path},
    )


def _configure_tracked_hook(primary: Path) -> None:
    hook_path = primary / ".ollija" / "hooks"
    hook_path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HOOK, hook_path / "post-checkout")
    _git(primary, "config", "core.hooksPath", str(hook_path))


def test_post_checkout_skips_primary_and_detached_worktrees(tmp_path: Path) -> None:
    primary, linked = _linked_worktree(tmp_path)
    log = tmp_path / "ollija.log"
    cli_dir = _write_fake_cli(tmp_path / "fake-bin", log=log)

    primary_result = _run_hook(primary, path=_path_with(cli_dir))
    assert primary_result.returncode == 0
    assert not log.exists()

    _git(linked, "checkout", "--detach")
    detached_result = _run_hook(linked, path=_path_with(cli_dir))
    assert detached_result.returncode == 0
    assert not log.exists()


def test_post_checkout_uses_path_cli_with_linked_worktree_facts(tmp_path: Path) -> None:
    primary, linked = _linked_worktree(tmp_path)
    log = tmp_path / "ollija.log"
    cli_dir = _write_fake_cli(tmp_path / "fake-bin", log=log)

    result = _run_hook(linked, path=_path_with(cli_dir))

    assert result.returncode == 0
    assert result.stderr == ""
    assert log.read_text(encoding="utf-8").splitlines() == [
        f"standalone|{linked}|annotate-plan||{linked}|{primary}|1"
    ]


def test_post_checkout_failure_is_nonblocking_and_names_standalone_recovery(
    tmp_path: Path,
) -> None:
    primary, linked = _linked_worktree(tmp_path)
    log = tmp_path / "ollija.log"
    cli_dir = _write_fake_cli(tmp_path / "fake-bin", log=log, exit_code=17)

    result = _run_hook(linked, path=_path_with(cli_dir))

    assert result.returncode == 0
    assert f'Recover with: cd -- "{linked}" && ollija annotate-plan' in result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        f"standalone|{linked}|annotate-plan||{linked}|{primary}|1"
    ]


def test_post_checkout_missing_cli_is_nonblocking_and_actionable(
    tmp_path: Path,
) -> None:
    _, linked = _linked_worktree(tmp_path)

    result = _run_hook(linked, path="/usr/bin:/bin")

    assert result.returncode == 0
    assert "annotation skipped: the ollija command is not installed" in result.stderr


def test_post_checkout_passes_metacharacter_paths_as_data(tmp_path: Path) -> None:
    sentinel = tmp_path / "should-not-exist"
    primary, linked = _linked_worktree(
        tmp_path,
        linked_name="linked worktree $(touch should-not-exist)",
    )
    log = tmp_path / "ollija.log"
    cli_dir = _write_fake_cli(tmp_path / "fake-bin", log=log)

    result = _run_hook(linked, path=_path_with(cli_dir))

    assert result.returncode == 0
    logged = log.read_text(encoding="utf-8")
    assert str(linked) in logged
    assert str(primary) in logged
    assert not sentinel.exists()


def test_configured_hook_runs_during_actual_git_worktree_add(tmp_path: Path) -> None:
    primary = _write_repository(tmp_path, branch="primary-hook-install")
    log = tmp_path / "ollija.log"
    cli_dir = _write_fake_cli(tmp_path / "fake-bin", log=log)
    _configure_tracked_hook(primary)
    linked = tmp_path / "actual-linked-worktree"

    _git(
        primary,
        "worktree",
        "add",
        "-b",
        "feat/actual-hook",
        str(linked),
        env={**os.environ, "PATH": _path_with(cli_dir)},
    )

    assert log.read_text(encoding="utf-8").splitlines() == [
        f"standalone|{linked}|annotate-plan||{linked}|{primary}|1"
    ]


def test_post_checkout_is_executable_and_uses_only_the_supported_surface() -> None:
    hook = HOOK.read_text(encoding="utf-8")

    assert HOOK.stat().st_mode & 0o111
    assert "command -v ollija" in hook
    assert "ollija annotate-plan" in hook
    assert "bin/ollija" not in hook
    for forbidden in ("read ", "worktree move", "worktree guard", "status", "go "):
        assert forbidden not in hook
