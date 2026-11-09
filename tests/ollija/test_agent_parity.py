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
    canonical_paths = {
        path.name: path for path in CANONICAL_SKILLS.iterdir() if path.is_dir()
    }
    # Query comparison belongs to the harvester; its public name is only a
    # discovery alias. Pin its exact nested owner instead of permitting copies.
    canonical_paths["harvest-query-diff"] = (
        CANONICAL_SKILLS / "change-harvester" / "subskills" / "harvest-query-diff"
    )

    assert canonical_paths
    assert {path.name for path in AGENT_LINKS.iterdir()} == set(canonical_paths)
    for name, canonical in canonical_paths.items():
        alias = AGENT_LINKS / name
        assert (canonical / "SKILL.md").is_file()
        assert alias.is_symlink()
        assert alias.resolve() == canonical.resolve()


AGENT_RULES = REPO_ROOT / "AGENTS.md"
DELIVERY_TEMPLATE = REPO_ROOT / ".ollija" / "templates" / "delivery-guide.md"
OLLIJA_OPERATIONS = REPO_ROOT / "docs" / "operations" / "ollija.md"
OLLIJA_README = REPO_ROOT / "docs" / "ollija" / "README.md"
POLICY_POINTER = "AGENTS.md"
POLICY_SECTION = "Plans and delivery"


def _read(path: Path) -> str:
    """Return the document with whitespace collapsed so re-wrapping cannot hide a rule."""

    return " ".join(path.read_text(encoding="utf-8").split())


def test_lfg_and_goal_delivery_contract_lives_in_agent_rules() -> None:
    agent_rules = _read(AGENT_RULES)

    assert "LFG and goal" in agent_rules
    assert "existing" in agent_rules
    assert "enabled: false" in agent_rules
    assert "direct" in agent_rules
    assert "staging" in agent_rules and "production" in agent_rules
    assert "delivery_selected_by_user" in agent_rules
    assert "on-request" in agent_rules
    assert "annotate-plan" in agent_rules


def test_other_current_ollija_guidance_points_to_agent_rules() -> None:
    operations = _read(OLLIJA_OPERATIONS)
    readme = _read(OLLIJA_README)

    for text in (operations, readme):
        assert POLICY_POINTER in text
        assert POLICY_SECTION in text
    # The operations guide keeps its procedures and commands.
    assert "annotate-plan" in operations
    assert "enabled: false" in operations
    assert "--delivery-route direct" in operations
    # Policy is stated once in AGENTS.md, not restated in the operations guide.
    assert "A production guide defaults to staged delivery" not in operations
    assert "Commit-and-push alone does not select staging or production" not in (
        operations
    )
    assert "Commit-and-push alone authorizes neither" not in readme


def test_production_worktree_cleanup_contract_remains_in_consumer_policy() -> None:
    agent_rules = _read(AGENT_RULES)
    template = _read(DELIVERY_TEMPLATE)

    assert "exact-SHA production verification" in agent_rules
    assert "git worktree remove" in agent_rules
    assert "without" in agent_rules and "`--force`" in agent_rules
    assert "does not remove the worktree itself" in agent_rules
    assert "Never force-remove a worktree" in agent_rules
    assert "staging-only" in agent_rules
    assert "candidate-mismatched" in agent_rules
    assert "${delivery_actions}" in template
    assert POLICY_POINTER in template


def test_agent_rules_state_the_occupied_staging_default() -> None:
    agent_rules = _read(AGENT_RULES)

    assert "Occupied staging" in agent_rules
    assert "unrelated release" in agent_rules
    assert "go direct to production" in agent_rules
    assert "--delivery-route direct --delivery-route-selected-by-user" in agent_rules
    assert "staging-only target is outside this default" in agent_rules


def test_agent_rules_absorb_the_former_guide_failure_rules() -> None:
    agent_rules = _read(AGENT_RULES)

    for rule in (
        "Complete the applicable, unwaived checks for the selected route",
        "owner-selected direct production does not require staging",
        "repeat only the checks it invalidated",
        "Retry only after a relevant fact changes",
        "persistent Ollija process",
        "infra/multi-machine skill",
        "change ledger",
    ):
        assert rule in agent_rules, rule


def test_delivery_guide_template_carries_only_per_plan_facts() -> None:
    template = _read(DELIVERY_TEMPLATE)

    for placeholder in (
        "${plan_path}",
        "${branch}",
        "${change_id}",
        "${active_worktree}",
        "${workflow}",
        "${delivery_target}",
        "${delivery_route}",
        "${delivery_selected_by_user}",
        "${placement}",
        "${delivery_actions}",
    ):
        assert placeholder in template, placeholder
    for project_constant in (
        "${canonical_host}",
        "${repository_root}",
        "${release_worktree_area}",
        "${staging_blueprint}",
        "${production_blueprint}",
        "${staging_url}",
        "${production_url}",
    ):
        assert project_constant not in template, project_constant
    assert "Failure handling" not in template
    assert "annotate-plan" in template
    assert ".ollija/project.yaml" in template
    assert POLICY_SECTION in template
    actions = template.index("${delivery_actions}")
    assert template.index("Occupied staging", actions) > actions
