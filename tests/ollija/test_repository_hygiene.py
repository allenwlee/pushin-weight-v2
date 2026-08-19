from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PLACEHOLDER_PASSWORDS = {
    "change-me",
    "changeme",
    "dummy",
    "example",
    "fake",
    "pass",
    "password",
    "placeholder",
    "pushinweight",
    "secret",
    "test",
    "xmonitor",
    "your_password",
}
DATABASE_URL = re.compile(
    r"postgres(?:ql)?://(?P<user>[^\s/:@]+):(?P<password>[^\s@/]+)@",
    re.IGNORECASE,
)
TOKEN_PREFIX = "".join(("s", "k", "-"))  # noqa: FLY002 - avoid scanner self-match
TOKEN = re.compile(rf"(?<![A-Za-z0-9]){TOKEN_PREFIX}[A-Za-z0-9_-]{{20,}}")
PRIVATE_KEY_MARKER = "".join(  # noqa: FLY002 - avoid scanner self-match
    ("-----BEGIN ", "PRIVATE KEY-----")
)


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
    )


def _tracked_files() -> list[str]:
    return [path for path in _git("ls-files", "-z").split("\0") if path]


def _is_placeholder(user: str, password: str) -> bool:
    lowered = password.lower()
    return (
        lowered in PLACEHOLDER_PASSWORDS
        or len(password) <= 3
        or user == password
        or set(password) <= set("*xX-")
        or not password.upper().replace("%2A", "")
        or "<" in password
        or "{" in password
        or password.startswith("$")
    )


def test_runtime_secrets_and_dev_database_are_not_tracked() -> None:
    tracked = set(_tracked_files())

    assert ".env" not in tracked
    assert "data/django_dev.db" not in tracked
    assert ".env.example" in tracked


def test_runtime_secret_and_ollija_state_paths_are_ignored() -> None:
    for relative_path in (
        ".env",
        "data/django_dev.db",
        ".ollija/state/example.json",
    ):
        ignored = subprocess.run(
            ["git", "check-ignore", "--quiet", relative_path],
            cwd=REPO_ROOT,
            check=False,
        )
        assert ignored.returncode == 0, relative_path


def test_claude_policy_imports_canonical_agent_rules() -> None:
    assert (REPO_ROOT / "CLAUDE.md").read_text().strip() == "@AGENTS.md"


def test_current_ollija_boundary_has_no_retired_runtime_or_command_paths() -> None:
    retained_runtime = {
        "__init__.py",
        "__main__.py",
        "annotate_plan.py",
        "cli.py",
        "config.py",
        "worktrees.py",
    }
    runtime = REPO_ROOT / "scripts" / "ollija"
    assert {path.name for path in runtime.glob("*.py")} == retained_runtime
    assert not (runtime / "agents").exists()
    assert not (runtime / "adapters").exists()

    retired_modules = {
        "approvals",
        "bridgewright",
        "checkpoint",
        "changes",
        "database",
        "git",
        "hosted_database",
        "impact",
        "incidents",
        "preview",
        "processes",
        "redaction",
        "release",
        "render",
        "results",
        "state",
        "status",
        "supervisor",
        "task_control",
        "tasks",
        "verification",
        "versioning",
        "workspaces",
    }
    retired_commands = {
        "approve",
        "doctor",
        "go",
        "preview",
        "refresh-local",
        "refresh-staging",
        "release",
        "stage",
        "status",
        "stop",
        "worktree",
    }
    current_paths = [
        REPO_ROOT / "AGENTS.md",
        REPO_ROOT / "bin" / "ollija",
        REPO_ROOT / "build.sh",
        REPO_ROOT / "render-staging.yaml",
        REPO_ROOT / "scripts" / "render_migrate.py",
        REPO_ROOT / "project" / "staging.py",
        REPO_ROOT / ".ollija" / "hooks" / "post-checkout",
        *(runtime.glob("*.py")),
    ]

    for path in current_paths:
        text = path.read_text(encoding="utf-8")
        for module in retired_modules:
            assert f"scripts.ollija.{module}" not in text, path
        for command in retired_commands:
            assert f"./bin/ollija {command}" not in text, path


def test_ollija_documentation_classifies_current_guidance_and_superseded_history() -> None:
    current_paths = (
        ".agents/skills/ollija/SKILL.md",
        ".ollija/templates/delivery-guide.md",
        "AGENTS.md",
        "docs/ollija/README.md",
        "docs/ollija/CHANGES.md",
        "docs/operations/ollija.md",
        "docs/deploy/render.md",
        "CONCEPTS.md",
        "docs/plans/2026-08-14-195746-feat-why-first-trend-headlines-plan.md",
    )
    historical_paths = (
        "docs/ollija/2026-08-15-repeatable-hosted-refresh-fix.md",
        "docs/ollija/readme-test-prompt.md",
        "docs/ollija/test-prompt-2.md",
        "docs/operations/ollija-rollout-baseline.md",
        "docs/solutions/workflow-issues/2026-08-17-190429-ollija-task-recovery.md",
        "docs/plans/2026-08-14-120533-feat-ollija-staging-release-workflow-plan.md",
        "docs/plans/2026-08-17-175832-ollija-autonomous-task-control.md",
    )
    retired_commands = (
        "approve",
        "doctor",
        "go",
        "preview",
        "refresh-local",
        "refresh-staging",
        "release",
        "stage",
        "status",
        "stop",
        "verify-production",
        "worktree",
    )

    for relative_path in current_paths:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "annotate-plan" in text, relative_path
        for command in retired_commands:
            assert f"./bin/ollija {command}" not in text, relative_path

    for relative_path in historical_paths:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        if text.startswith("---\n"):
            _, frontmatter, remainder = text.split("---", 2)
            assert isinstance(yaml.safe_load(frontmatter), dict), relative_path
            opening = remainder.lstrip("\n")
        else:
            opening = text
        assert opening.startswith("> **Superseded Ollija workflow"), relative_path
        opening = "\n".join(opening.splitlines()[:5])
        assert "README.md" in opening, relative_path


def test_change_history_is_advisory_and_concepts_describe_the_guide_model() -> None:
    changes = (REPO_ROOT / "docs/ollija/CHANGES.md").read_text(encoding="utf-8")
    concepts = (REPO_ROOT / "CONCEPTS.md").read_text(encoding="utf-8")
    runtime_sources = (REPO_ROOT / "scripts" / "ollija").glob("*.py")

    assert "Retire the stateful release engine" in changes
    assert "advisory human history" in changes
    assert "validates, or enforces this file" in changes
    assert all("CHANGES.md" not in path.read_text(encoding="utf-8") for path in runtime_sources)
    for required in (
        "Ollija delivery guide",
        "Ollija release worktree area",
        "Delivery target",
    ):
        assert required in concepts
    for retired in (
        "Bounded task generation",
        "Checkpoint commit",
        "Durable stop",
        "Live but unsealed",
    ):
        assert retired not in concepts


def test_tracked_text_contains_no_literal_credentials() -> None:
    findings: list[str] = []

    for relative_path in _tracked_files():
        if relative_path == "tests/ollija/test_repository_hygiene.py":
            continue

        path = REPO_ROOT / relative_path
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:8192]:
            continue

        text = data.decode("utf-8", errors="ignore")
        if PRIVATE_KEY_MARKER in text or TOKEN.search(text):
            findings.append(relative_path)
            continue

        for match in DATABASE_URL.finditer(text):
            if not _is_placeholder(match.group("user"), match.group("password")):
                findings.append(relative_path)
                break

    assert not findings, "credential-shaped values found in: " + ", ".join(sorted(findings))
