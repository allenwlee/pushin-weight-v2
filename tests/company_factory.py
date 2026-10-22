"""Create a fixture Company using the label owner in its selected schema."""

from core.company_labels import set_company_label
from core.models import Company


def company_with_label(nickname: str, label: str | None = None, **fields) -> Company:
    legacy_label = any(field.name == "display_name" for field in Company._meta.fields)
    if label and legacy_label:
        fields.setdefault("display_name", label)
    company = Company.objects.create(nickname=nickname, **fields)
    if label and not legacy_label:
        set_company_label(company, "und", label)
    return company
