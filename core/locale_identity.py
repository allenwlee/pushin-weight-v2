"""SQL expression matching the existing app-edition locale lookup contract."""

from django.db.models import Case, F, Value, When
from django.db.models.functions import Lower, Replace
from django.db.models.lookups import Exact


def app_edition_locale_key(field="lang"):
    normalized = Lower(Replace(F(field), Value("_"), Value("-")))
    return Case(
        When(Exact(normalized, Value("zh-cn")), then=Value("zh-hans")),
        default=normalized,
    )
