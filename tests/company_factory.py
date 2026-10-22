"""Fixture helper for a Company with its registered default-locale label."""

from core.company_labels import set_company_label
from core.models import Company


def company_with_label(nickname: str, label: str | None = None, **fields) -> Company:
    company = Company.objects.create(nickname=nickname, **fields)
    if label:
        set_company_label(company, "und", label)
    return company
