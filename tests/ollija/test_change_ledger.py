from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ollija.changes import (
    ChangeLedgerError,
    require_ollija_change_ledger,
    requires_production_data_refresh,
)
from tests.ollija.change_ledger_helpers import LEDGER_TEXT, write_ledger


def test_product_change_does_not_require_ollija_ledger(tmp_path: Path) -> None:
    require_ollija_change_ledger(
        tmp_path,
        ("monitor/views.py",),
        baseline_text="",
    )


def test_ollija_behavior_change_requires_changed_ledger(tmp_path: Path) -> None:
    write_ledger(tmp_path)

    with pytest.raises(ChangeLedgerError, match="ollija_change_ledger_missing"):
        require_ollija_change_ledger(
            tmp_path,
            ("scripts/ollija/cli.py",),
            baseline_text=LEDGER_TEXT,
        )


def test_ollija_rule_change_requires_changed_ledger(tmp_path: Path) -> None:
    write_ledger(tmp_path)

    with pytest.raises(ChangeLedgerError, match="ollija_change_ledger_missing"):
        require_ollija_change_ledger(
            tmp_path,
            (".agents/skills/ollija/SKILL.md",),
            baseline_text=LEDGER_TEXT,
        )


def test_changed_ledger_must_have_the_required_entry_fields(tmp_path: Path) -> None:
    write_ledger(tmp_path, "# Ollija change ledger\n\n## 2026-08-18 — Incomplete\n")

    with pytest.raises(ChangeLedgerError, match="ollija_change_ledger_invalid"):
        require_ollija_change_ledger(
            tmp_path,
            ("scripts/ollija/cli.py", "docs/ollija/CHANGES.md"),
            baseline_text="",
        )


def test_well_formed_changed_ledger_allows_ollija_change(tmp_path: Path) -> None:
    write_ledger(tmp_path)

    require_ollija_change_ledger(
        tmp_path,
        ("scripts/ollija/cli.py", "docs/ollija/CHANGES.md"),
        baseline_text="",
    )


def test_editing_an_existing_entry_does_not_count_as_a_new_entry(
    tmp_path: Path,
) -> None:
    write_ledger(tmp_path, LEDGER_TEXT.replace("This concise", "This short"))

    with pytest.raises(ChangeLedgerError, match="ollija_change_ledger_invalid"):
        require_ollija_change_ledger(
            tmp_path,
            ("scripts/ollija/cli.py", "docs/ollija/CHANGES.md"),
            baseline_text=LEDGER_TEXT,
        )


def test_new_complete_entry_is_required_beside_existing_history(
    tmp_path: Path,
) -> None:
    new_entry = LEDGER_TEXT + """

## 2026-08-18 — Skip irrelevant refresh

Type: Fix

Problem: Workflow-only candidates copied production-derived data.

New behavior: Workflow-only candidates proceed directly to staging.

Proof: `pytest tests/ollija`

Release impact: No database copy is performed.
"""
    write_ledger(tmp_path, new_entry)

    require_ollija_change_ledger(
        tmp_path,
        ("scripts/ollija/cli.py", "docs/ollija/CHANGES.md"),
        baseline_text=LEDGER_TEXT,
    )


def test_ledger_history_must_remain_an_unchanged_prefix(tmp_path: Path) -> None:
    new_entry = """

## 2026-08-18 — Skip irrelevant refresh

Type: Fix

Problem: Workflow-only candidates copied production-derived data.

New behavior: Workflow-only candidates proceed directly to staging.

Proof: `pytest tests/ollija`

Release impact: No database copy is performed.
"""
    reordered = new_entry.strip() + "\n\n" + LEDGER_TEXT
    write_ledger(tmp_path, reordered)

    with pytest.raises(ChangeLedgerError, match="ollija_change_ledger_invalid"):
        require_ollija_change_ledger(
            tmp_path,
            ("scripts/ollija/cli.py", "docs/ollija/CHANGES.md"),
            baseline_text=LEDGER_TEXT,
        )


def test_ledger_history_cannot_insert_before_existing_entries(tmp_path: Path) -> None:
    inserted = """

## 2026-08-18 — Inserted history

Type: Fix

Problem: Historical ordering was changed.

New behavior: Historical ordering is preserved.

Proof: `pytest tests/ollija`

Release impact: No production effect.
"""
    prefix, suffix = LEDGER_TEXT.split("## 2026-08-18", 1)
    write_ledger(tmp_path, prefix + inserted + "## 2026-08-18" + suffix)

    with pytest.raises(ChangeLedgerError, match="ollija_change_ledger_invalid"):
        require_ollija_change_ledger(
            tmp_path,
            ("scripts/ollija/cli.py", "docs/ollija/CHANGES.md"),
            baseline_text=LEDGER_TEXT,
        )


def test_ollija_only_candidate_does_not_require_production_data() -> None:
    assert requires_production_data_refresh(
        (
            ".agents/skills/ollija/SKILL.md",
            "CONCEPTS.md",
            "bin/ollija",
            "docs/ollija/CHANGES.md",
            "docs/plans/2026-08-17-175832-ollija-autonomous-task-control.md",
            "scripts/ollija/cli.py",
            "tests/ollija/test_cli.py",
        )
    ) is False


def test_unknown_or_product_path_conservatively_requires_production_data() -> None:
    assert requires_production_data_refresh(("monitor/views.py",)) is True
    assert requires_production_data_refresh(
        ("scripts/ollija/cli.py", "core/models.py")
    ) is True
    assert requires_production_data_refresh(()) is True
