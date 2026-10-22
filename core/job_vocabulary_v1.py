"""Frozen, conservative aliases for the first shared job vocabulary.

Migration and runtime use this version verbatim. New meanings require a new
version; unknown source wording is evidence, never an invented category.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass


ALIASES = {
    "job_function": {
        "engineering": ("engineering",),
        "research": ("research",),
        "product": ("product", "产品类/product"),
        "design": ("design", "设计类/design"),
        "operations": ("operations", "operation", "运营类/operation"),
        "corporate_functions": ("corporate functions", "职能类/corporate functions"),
        "legal": ("legal",),
        "administrative_support": ("administrative support",),
        "developer_relations": ("developer relations", "devrel"),
    },
    "seniority": {
        "intern": ("intern", "internship", "实习"),
        "junior": ("junior",),
        "mid": ("mid", "mid-level"),
        "senior": ("senior", "senior level", "senior-level"),
        "lead": ("lead",),
        "staff": ("staff",),
        "principal": ("principal",),
    },
    "employment_type": {
        "full_time": ("full_time", "full-time", "full time", "全职"),
        "part_time": ("part_time", "part-time", "part time", "兼职"),
        "internship": ("internship", "intern", "实习"),
        "contract": ("contract", "contractor"),
        "fixed_term": ("fixed-term", "fixed-term contractor"),
        "freelance": ("freelance",),
        "permanent": ("permanent",),
    },
    "workplace_type": {
        "remote": ("remote",),
        "on_site": ("on_site", "on-site", "onsite", "on site"),
        "hybrid": ("hybrid", "in-office hybrid"),
    },
    "organization_ai_relationship": {
        "ai_company": ("ai company", "ai_company"),
    },
    # Existing values are explanations, not an established set of categories.
    "role_ai_relationship": {},
    "salary_period": {
        "hour": ("hour", "hourly", "per hour"),
        "day": ("day", "daily", "per day"),
        "week": ("week", "weekly", "per week"),
        "month": ("month", "monthly", "per month"),
        "year": ("year", "yearly", "annual", "annually", "annum", "per year"),
    },
}

EXPLICIT_PLURALS = {
    "employment_type": {
        "full-time/contract": ("Full-time", "Contract"),
        "全职或实习": ("全职", "实习"),
    },
    "seniority": {
        "mid/senior": ("Mid", "Senior"),
        "principal / staff": ("Principal", "Staff"),
        "principal/staff": ("Principal", "Staff"),
    },
}


@dataclass(frozen=True)
class AssignmentValue:
    reported_value: str
    category_code: str | None

    @property
    def source_value_sha256(self) -> str:
        return hashlib.sha256(self.reported_value.encode("utf-8")).hexdigest()


def canonical_code(dimension: str, value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip().casefold()
    # Some legacy adapters stored str({"id": ..., "name": ...}). Preserve
    # the reported string, but recognize its explicit name when possible.
    if value.startswith("{") and len(value) <= 4096:
        try:
            source = ast.literal_eval(value)
        except (ValueError, SyntaxError, TypeError, RecursionError):
            source = None
        if isinstance(source, dict) and isinstance(source.get("name"), str):
            candidate = source["name"].strip().casefold()
    for code, aliases in ALIASES[dimension].items():
        if candidate == code or candidate in aliases:
            return code
    return None


def assignment_values(dimension: str, value: object) -> tuple[AssignmentValue, ...]:
    """One row per explicit source value; never infer categories from prose."""
    values = value if isinstance(value, (list, tuple)) else (value,)
    result = {}
    for item in values:
        if isinstance(item, dict):
            item = item.get("name")
        if not isinstance(item, str) or not item.strip():
            continue
        parts = EXPLICIT_PLURALS.get(dimension, {}).get(item.strip().casefold(), (item,))
        for reported in parts:
            result[reported] = AssignmentValue(reported, canonical_code(dimension, reported))
    return tuple(result.values())
