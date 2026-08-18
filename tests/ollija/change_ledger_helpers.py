LEDGER_TEXT = """# Ollija change ledger

This concise ledger records material changes to Ollija's behavior and rules.

## 2026-08-18 — Require a change-ledger entry

Type: Fix

Problem: Ollija fixes were difficult to find without reading plans and commits.

New behavior: Material Ollija changes require a concise ledger entry.

Proof: `pytest tests/ollija`

Release impact: No application, database, or production-data behavior changes.
"""


def write_ledger(root, text: str = LEDGER_TEXT) -> None:
    ledger = root / "docs" / "ollija" / "CHANGES.md"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(text, encoding="utf-8")
