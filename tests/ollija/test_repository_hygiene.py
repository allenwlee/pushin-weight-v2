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


def test_current_ollija_boundary_uses_only_the_standalone_runtime() -> None:
    embedded_paths = (
        REPO_ROOT / "bin" / "ollija",
        REPO_ROOT / "scripts" / "ollija",
        REPO_ROOT / ".claude" / "skills" / "ollija",
        REPO_ROOT / ".agents" / "skills" / "ollija",
    )
    retained_consumer_paths = {
        ".ollija/hooks/post-checkout",
        ".ollija/project.yaml",
        ".ollija/templates/delivery-guide.md",
    }

    assert all(not path.exists() and not path.is_symlink() for path in embedded_paths)
    assert {
        path for path in _tracked_files() if path.startswith(".ollija/")
    } == retained_consumer_paths

    current_paths = (
        REPO_ROOT / "AGENTS.md",
        REPO_ROOT / "CONCEPTS.md",
        REPO_ROOT / ".ollija" / "hooks" / "post-checkout",
        REPO_ROOT / ".ollija" / "templates" / "delivery-guide.md",
        REPO_ROOT / "docs" / "ollija" / "README.md",
        REPO_ROOT / "docs" / "operations" / "ollija.md",
        REPO_ROOT / "docs" / "deploy" / "render.md",
        REPO_ROOT
        / "docs"
        / "operations"
        / "2026-08-27-171845-staging-harvester-acceptance.md",
    )
    for path in current_paths:
        text = path.read_text(encoding="utf-8")
        assert "scripts.ollija" not in text, path
        assert "./bin/ollija" not in text, path


def test_staging_refresh_is_independent_from_ollija_runtime() -> None:
    refresh_runtime = REPO_ROOT / "scripts" / "staging_refresh"

    assert refresh_runtime.is_dir()
    for path in [
        REPO_ROOT / "bin" / "refresh-staging-data",
        *refresh_runtime.glob("*.py"),
    ]:
        assert "scripts.ollija" not in path.read_text(encoding="utf-8"), path


def test_ollija_documentation_classifies_current_guidance_and_superseded_history() -> (
    None
):
    current_paths = (
        ".ollija/templates/delivery-guide.md",
        "AGENTS.md",
        "docs/ollija/README.md",
        "docs/ollija/CHANGES.md",
        "docs/operations/ollija.md",
        "docs/deploy/render.md",
        "docs/operations/2026-08-27-171845-staging-harvester-acceptance.md",
        "CONCEPTS.md",
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
        assert "./bin/ollija" not in text, relative_path
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

    assert "Adopt standalone Ollija" in changes
    assert "Retire the stateful release engine" in changes
    assert "advisory human history" in changes
    assert "validates, or enforces this file" in changes
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

    assert not findings, "credential-shaped values found in: " + ", ".join(
        sorted(findings)
    )
