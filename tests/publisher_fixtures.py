"""HF test publishers use the same shared account/link storage as production."""

from core.models import DataSource
from core.publisher_accounts import register_publisher


def hf_publisher(
    *,
    namespace,
    company=None,
    company_id=None,
    confirmed=False,
    discovered_via="curated",
    added_at=None,
):
    DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    link, _ = register_publisher(
        source="hf",
        identifier=namespace,
        company=company,
        company_id=company_id,
        confirmed=confirmed,
        discovered_via=discovered_via,
        added_at=added_at,
    )
    return link
