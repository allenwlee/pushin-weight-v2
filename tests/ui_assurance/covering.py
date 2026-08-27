"""Deterministic target-side t-way row generation and obligation probes."""

from __future__ import annotations

from itertools import combinations, permutations, product
from typing import Any


def _control_map(declaration: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {control["id"]: control for control in declaration["controls"]}


def _forbidden(declaration: dict[str, Any], row: dict[str, str]) -> bool:
    return any(
        all(row.get(control) == value for control, value in item["values"].items())
        for item in declaration.get("constraints", [])
    )


def covering_rows(declaration: dict[str, Any]) -> list[dict[str, str]]:
    """Build stable partial rows that cover every declared legal t-way tuple."""

    controls = _control_map(declaration)
    required: list[dict[str, str]] = []
    for group in declaration["coverage_groups"]:
        for selected in combinations(group["controls"], group["strength"]):
            for values in product(*(controls[item]["values"] for item in selected)):
                row = dict(zip(selected, values, strict=True))
                if not _forbidden(declaration, row):
                    required.append(row)

    rows: list[dict[str, str]] = []
    for requirement in sorted(required, key=lambda row: tuple(sorted(row.items()))):
        if any(all(row.get(key) == value for key, value in requirement.items()) for row in rows):
            continue
        compatible = next(
            (
                row
                for row in rows
                if all(key not in row or row[key] == value for key, value in requirement.items())
                and not _forbidden(declaration, {**row, **requirement})
            ),
            None,
        )
        if compatible is None:
            rows.append(dict(requirement))
        else:
            compatible.update(requirement)
    return sorted(rows, key=lambda row: tuple(sorted(row.items())))


def covered_tuples(
    declaration: dict[str, Any], rows: list[dict[str, str]]
) -> set[tuple[str, tuple[tuple[str, str], ...]]]:
    controls = _control_map(declaration)
    covered = set()
    for group in declaration["coverage_groups"]:
        for selected in combinations(group["controls"], group["strength"]):
            for row in rows:
                if all(control in row for control in selected):
                    assignment = tuple(sorted((control, row[control]) for control in selected))
                    if all(row[control] in controls[control]["values"] for control in selected):
                        covered.add((group["id"], assignment))
    return covered


def required_tuples(
    declaration: dict[str, Any],
) -> set[tuple[str, tuple[tuple[str, str], ...]]]:
    controls = _control_map(declaration)
    required = set()
    for group in declaration["coverage_groups"]:
        for selected in combinations(group["controls"], group["strength"]):
            for values in product(*(controls[item]["values"] for item in selected)):
                row = dict(zip(selected, values, strict=True))
                if not _forbidden(declaration, row):
                    required.add((group["id"], tuple(sorted(row.items()))))
    return required


def ordered_sequences(declaration: dict[str, Any]) -> list[tuple[str, ...]]:
    return sorted(
        sequence
        for group in declaration.get("ordered_groups", [])
        for sequence in permutations(group["actions"], group["strength"])
    )
