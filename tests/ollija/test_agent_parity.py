from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_SKILLS = REPO_ROOT / ".claude" / "skills"
AGENT_LINKS = REPO_ROOT / ".agents" / "skills"
LOCAL_CLAUDE_SKILL = CANONICAL_SKILLS / "ollija"
LOCAL_AGENT_SKILL = AGENT_LINKS / "ollija"


def test_agent_rules_use_the_installed_standalone_command_and_skill() -> None:
    agent_rules = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "ollija annotate-plan" in agent_rules
    assert "installed `ollija` skill" in agent_rules
    assert "./bin/ollija" not in agent_rules
    assert ".claude/skills/ollija" not in agent_rules
    assert "Use the exact `plan_path`" in agent_rules
    assert "delivery_selected_by_user: true" in agent_rules
    assert "Delivery Exceptions" in agent_rules


def test_repository_does_not_shadow_the_installed_ollija_skill() -> None:
    assert not LOCAL_CLAUDE_SKILL.exists()
    assert not LOCAL_CLAUDE_SKILL.is_symlink()
    assert not LOCAL_AGENT_SKILL.exists()
    assert not LOCAL_AGENT_SKILL.is_symlink()
    assert "@AGENTS.md" in (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def test_every_remaining_claude_skill_has_an_agent_alias() -> None:
    canonical_names = {
        path.name for path in CANONICAL_SKILLS.iterdir() if path.is_dir()
    }

    assert canonical_names
    assert {path.name for path in AGENT_LINKS.iterdir()} == canonical_names
    for name in canonical_names:
        alias = AGENT_LINKS / name
        assert alias.is_symlink()
        assert alias.resolve() == (CANONICAL_SKILLS / name).resolve()


def test_lfg_and_goal_delivery_contract_is_shared_with_current_guidance() -> None:
    agent_rules = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    operations = (REPO_ROOT / "docs" / "operations" / "ollija.md").read_text(
        encoding="utf-8"
    )

    for text in (agent_rules, operations):
        assert "LFG and goal" in text
        assert "once" in text
        assert "staging" in text and "production" in text
        assert "delivery_selected_by_user" in text
        assert "on-request" in text
        assert "annotate-plan" in text


def test_production_worktree_cleanup_contract_remains_in_consumer_policy() -> None:
    agent_rules = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    template = (REPO_ROOT / ".ollija" / "templates" / "delivery-guide.md").read_text(
        encoding="utf-8"
    )

    assert "exact-SHA production verification" in agent_rules
    assert "git worktree remove" in agent_rules
    assert "without" in agent_rules and "`--force`" in agent_rules
    assert "does not remove the worktree itself" in agent_rules
    assert "${delivery_actions}" in template
    assert "Never force-remove a worktree" in template
    assert "staging-only" in template
    assert "candidate-mismatched" in template
