from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_SKILLS = REPO_ROOT / ".claude" / "skills"
AGENT_LINKS = REPO_ROOT / ".agents" / "skills"
CANONICAL = CANONICAL_SKILLS / "ollija" / "SKILL.md"
AGENT_LINK = AGENT_LINKS / "ollija"


def test_ollija_skill_is_canonical_and_agent_neutral() -> None:
    body = CANONICAL.read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(body.split("---", 2)[1])

    assert frontmatter["name"] == "ollija"
    assert "agent-agnostic" in frontmatter["description"]
    assert "TODO" not in body
    assert "./bin/ollija annotate-plan [optional-plan-path]" in body
    assert "Codex, Claude, CE, Superpowers, goal" in body
    assert "Use the exact `plan_path` returned" in body
    assert "parallel plan" in body
    assert "delivery_selected_by_user: true" in body
    assert "delivery_target: on-request" in body
    assert "Delivery Exceptions" in body
    assert "does not start agents" in body
    assert "infra/multi-machine skill first" in body

    for retired in (
        "./bin/ollija status",
        "./bin/ollija go",
        "./bin/ollija stop",
        "./bin/ollija approve",
        "./bin/ollija release",
    ):
        assert retired not in body


def test_claude_and_other_agents_resolve_the_same_skill_bytes() -> None:
    assert AGENT_LINK.is_symlink()
    assert AGENT_LINK.resolve() == CANONICAL.parent.resolve()
    assert (AGENT_LINK / "SKILL.md").read_bytes() == CANONICAL.read_bytes()
    assert "@AGENTS.md" in (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert ".claude/skills/ollija/SKILL.md" in (REPO_ROOT / "AGENTS.md").read_text(
        encoding="utf-8"
    )


def test_every_claude_skill_has_an_agent_alias() -> None:
    canonical_names = {
        path.name for path in CANONICAL_SKILLS.iterdir() if path.is_dir()
    }

    assert canonical_names
    assert {path.name for path in AGENT_LINKS.iterdir()} == canonical_names
    for name in canonical_names:
        alias = AGENT_LINKS / name
        assert alias.is_symlink()
        assert alias.resolve() == (CANONICAL_SKILLS / name).resolve()


def test_lfg_and_goal_delivery_contract_is_shared_with_agent_rules() -> None:
    body = CANONICAL.read_text(encoding="utf-8")
    agent_rules = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    for text in (body, agent_rules):
        assert "LFG and goal" in text
        assert "once" in text
        assert "staging" in text and "production" in text
        assert "delivery_selected_by_user" in text
        assert "on-request" in text
        assert "annotate-plan" in text


def test_production_worktree_cleanup_contract_is_shared_with_agent_rules() -> None:
    body = CANONICAL.read_text(encoding="utf-8")
    agent_rules = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    for text in (body, agent_rules):
        assert "exact-SHA production verification" in text
        assert "git worktree remove" in text
        assert "without" in text and "`--force`" in text
        assert "staging-only" in text
        assert "parent workflow" in text

    assert "does not remove the worktree itself" in body
