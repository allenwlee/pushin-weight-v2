from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL = REPO_ROOT / ".agents" / "skills" / "ollija" / "SKILL.md"
CLAUDE_LINK = REPO_ROOT / ".claude" / "skills" / "ollija"


def test_ollija_skill_is_canonical_and_agent_neutral() -> None:
    body = CANONICAL.read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(body.split("---", 2)[1])

    assert frontmatter["name"] == "ollija"
    assert "what is next" in frontmatter["description"].lower()
    assert "TODO" not in body
    assert "./bin/ollija status --json" in body
    assert "Bridgewright as assessment evidence only" in body
    assert "./bin/ollija go" in body
    assert "./bin/ollija stop <task-id> --json" in body
    assert "pushin-weight-v2/.worktrees/<branch>" in body
    assert "`infra-shell` first" in body
    assert "must not stage, commit, push" in body


def test_claude_and_codex_resolve_the_same_skill_bytes() -> None:
    assert CLAUDE_LINK.is_symlink()
    assert CLAUDE_LINK.resolve() == CANONICAL.parent.resolve()
    assert (CLAUDE_LINK / "SKILL.md").read_bytes() == CANONICAL.read_bytes()
    assert "@AGENTS.md" in (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert ".agents/skills/ollija/SKILL.md" in (
        REPO_ROOT / "AGENTS.md"
    ).read_text(encoding="utf-8")


def test_common_owner_prompts_have_one_cli_mapping() -> None:
    body = CANONICAL.read_text(encoding="utf-8")
    mappings = {
        "What’s next?": "./bin/ollija status",
        "Start bounded work": "./bin/ollija go --help",
        "Stop task X": "./bin/ollija stop X",
        "Show local staging": "./bin/ollija preview",
        "Physical iPhone looks good": "./bin/ollija approve iphone",
        "Release the beta": "./bin/ollija release",
        "Verify production": "./bin/ollija verify-production",
    }

    for prompt, command in mappings.items():
        matching_lines = [
            line for line in body.splitlines() if prompt in line and command in line
        ]
        assert len(matching_lines) == 1
