"""Read and write the current localized labels owned by a Company."""

from core.models import CompanyLabel

_LOCALE_ALIASES = {"zh-cn": "zh-Hans", "zh_CN": "zh-Hans", "zh_hans": "zh-Hans"}


def set_company_label(company, locale: str, label: str | None) -> None:
    locale = _LOCALE_ALIASES.get(locale, locale)
    if locale not in {"und", "en", "zh-Hans", "ja"}:
        raise ValueError(f"unsupported company label locale: {locale}")
    if label is None or label == "":
        CompanyLabel.objects.filter(company=company, locale_id=locale).delete()
        return
    if not isinstance(label, str):
        raise TypeError("company labels must be strings")
    CompanyLabel.objects.update_or_create(
        company=company,
        locale_id=locale,
        defaults={"label": label},
    )


def company_label_for(company, locale: str = "und", *, fallback: bool = True) -> str:
    locale = _LOCALE_ALIASES.get(locale, locale)
    rows = getattr(company, "_prefetched_objects_cache", {}).get("labels")
    if rows is None:
        rows = company.labels.all()
    labels = {row.locale_id: row.label for row in rows}
    label = labels.get(locale)
    if label is None and fallback and locale != "und":
        label = labels.get("und")
    return label or company.nickname
