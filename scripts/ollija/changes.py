from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from .git import CommandRunner

CHANGE_LEDGER_PATH = "docs/ollija/CHANGES.md"

_BEHAVIOR_PATHS = frozenset(
    {
        ".ollija/project.yaml",
        "bin/ollija",
        "docs/ollija/README.md",
        "docs/operations/ollija-rollout-baseline.md",
        "docs/operations/ollija.md",
    }
)
_BEHAVIOR_PREFIXES = (
    ".agents/skills/ollija/",
    "scripts/ollija/",
)
_NO_PRODUCTION_DATA_PATHS = frozenset(
    {
        ".ollija/project.yaml",
        "AGENTS.md",
        "CONCEPTS.md",
        "bin/ollija",
    }
)
_NO_PRODUCTION_DATA_PREFIXES = (
    ".agents/skills/ollija/",
    "docs/",
    "scripts/ollija/",
    "tests/ollija/",
)
_ENTRY_HEADING = re.compile(r"^## \d{4}-\d{2}-\d{2} — \S.*$", re.MULTILINE)
_REQUIRED_FIELDS = (
    "Type",
    "Problem",
    "New behavior",
    "Proof",
    "Release impact",
)


class ChangeLedgerError(ValueError):
    """A material Ollija change is missing its concise durable record."""


def _is_behavior_or_rule_path(path: str) -> bool:
    if path == CHANGE_LEDGER_PATH:
        return False
    return path in _BEHAVIOR_PATHS or path.startswith(_BEHAVIOR_PREFIXES)


def _entries(text: str) -> dict[str, str]:
    if not text:
        return {}
    if not text.startswith("# Ollija change ledger\n"):
        raise ChangeLedgerError("ollija_change_ledger_invalid")
    headings = tuple(_ENTRY_HEADING.finditer(text))
    if not headings:
        raise ChangeLedgerError("ollija_change_ledger_invalid")
    entries: dict[str, str] = {}
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        entry = text[heading.end() : end]
        for field in _REQUIRED_FIELDS:
            if not re.search(rf"^{re.escape(field)}:\s+\S", entry, re.MULTILINE):
                raise ChangeLedgerError("ollija_change_ledger_invalid")
        title = heading.group(0)
        if title in entries:
            raise ChangeLedgerError("ollija_change_ledger_invalid")
        entries[title] = entry.rstrip()
    return entries


def load_change_ledger_baseline(
    root: Path,
    ref: str,
    *,
    runner: CommandRunner,
) -> str:
    listed = runner.run(
        ("git", "ls-tree", "-r", "--name-only", ref, "--", CHANGE_LEDGER_PATH),
        cwd=root,
        timeout=15,
    )
    if listed.returncode != 0:
        raise ChangeLedgerError("ollija_change_ledger_baseline_unavailable")
    if CHANGE_LEDGER_PATH not in listed.stdout.splitlines():
        return ""
    shown = runner.run(
        ("git", "show", f"{ref}:{CHANGE_LEDGER_PATH}"),
        cwd=root,
        timeout=15,
    )
    if shown.returncode != 0:
        raise ChangeLedgerError("ollija_change_ledger_baseline_unavailable")
    return shown.stdout


def require_ollija_change_ledger(
    root: Path,
    changed_paths: Iterable[str],
    *,
    baseline_text: str,
) -> None:
    """Require a readable ledger entry beside material Ollija changes."""

    paths = frozenset(changed_paths)
    if not any(_is_behavior_or_rule_path(path) for path in paths):
        return
    if CHANGE_LEDGER_PATH not in paths:
        raise ChangeLedgerError("ollija_change_ledger_missing")
    ledger = root / CHANGE_LEDGER_PATH
    try:
        text = ledger.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ChangeLedgerError("ollija_change_ledger_invalid") from exc
    current_entries = _entries(text)
    baseline_entries = _entries(baseline_text)
    if baseline_text and not text.startswith(baseline_text):
        raise ChangeLedgerError("ollija_change_ledger_invalid")
    for title, entry in baseline_entries.items():
        if current_entries.get(title) != entry:
            raise ChangeLedgerError("ollija_change_ledger_invalid")
    if not current_entries.keys() - baseline_entries.keys():
        raise ChangeLedgerError("ollija_change_ledger_missing")


def requires_production_data_refresh(changed_paths: Iterable[str]) -> bool:
    """Default to refresh unless every changed path is Ollija or documentation."""

    paths = tuple(changed_paths)
    if not paths:
        return True
    return any(
        path not in _NO_PRODUCTION_DATA_PATHS
        and not path.startswith(_NO_PRODUCTION_DATA_PREFIXES)
        for path in paths
    )
