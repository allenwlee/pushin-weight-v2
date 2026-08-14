from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from scripts.ollija.adapters.base import AuthorityObservation
from scripts.ollija.git import GitObservation, mutation_preflight

SHA = "a" * 40


def _authority(allowed: bool = True) -> AuthorityObservation:
    return AuthorityObservation(
        hostname="fuchitalee" if allowed else "allenwlee",
        repository_root=Path("/repo"),
        repository_slug="allenwlee/pushin-weight-v2",
        mutation_allowed=allowed,
        reason_codes=() if allowed else ("forbidden_host", "host_mismatch"),
    )


def _git() -> GitObservation:
    return GitObservation(
        repository_root=Path("/repo"),
        head_sha=SHA,
        branch="staging",
        detached=False,
        registered_worktree=True,
        dirty_paths=(),
        production_sha="1" * 40,
        staging_sha=SHA,
        branch_relationship="staging_ahead",
        remote_reachable=True,
    )


def test_common_mutation_guard_rejects_wrong_host_detached_dirty_and_unregistered() -> None:
    cases = (
        (_authority(False), _git(), "forbidden_host"),
        (_authority(), replace(_git(), detached=True, branch=None), "detached_head"),
        (_authority(), replace(_git(), dirty_paths=("core/models.py",)), "dirty_tree"),
        (
            _authority(),
            replace(_git(), registered_worktree=False),
            "unregistered_worktree",
        ),
    )

    for authority, git, expected in cases:
        decision = mutation_preflight(authority, git, operation="stage")
        assert decision.allowed is False
        assert expected in decision.reason_codes


def test_release_guard_rejects_diverged_main_and_staging() -> None:
    decision = mutation_preflight(
        _authority(),
        replace(_git(), branch_relationship="diverged"),
        operation="release",
    )

    assert decision.allowed is False
    assert "production_staging_diverged" in decision.reason_codes


def test_clean_registered_candidate_passes_common_guard() -> None:
    decision = mutation_preflight(_authority(), _git(), operation="stage")

    assert decision.allowed is True
    assert decision.reason_codes == ()
