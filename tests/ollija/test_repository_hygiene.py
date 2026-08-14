from __future__ import annotations

import re
import subprocess
from pathlib import Path

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
