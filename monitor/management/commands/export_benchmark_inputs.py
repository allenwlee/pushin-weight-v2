"""Export frozen identities and post counts without writing application data."""

from datetime import UTC, datetime, time, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Count
from django.db.models.functions import TruncDate

from core.models import Brand, BrandCompany, Company, PostBrand, Product
from scripts.benchmark_download_collector.identity import (
    day,
    days,
    validate_inputs,
    write_new,
)


def export_inputs(brand_ids, start_date, end_date):
    days(start_date, end_date)
    if connection.vendor != "postgresql" or connection.in_atomic_block:
        raise ValueError("export requires PostgreSQL and its own read-only transaction")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
        brands = list(
            Brand.objects.filter(pk__in=brand_ids, is_sentinel=False).order_by("pk")
        )
        if {b.pk for b in brands} != set(brand_ids):
            raise ValueError("unknown or sentinel brand selected")
        links = list(
            BrandCompany.objects.filter(brand_id__in=brand_ids).values_list(
                "brand_id", "company_id"
            )
        )
        company_ids = {company for _, company in links}
        companies = list(Company.objects.filter(pk__in=company_ids).order_by("pk"))
        products = (
            Product.objects.filter(
                brand_id__in=brand_ids, type="llm-model", hf_type="model"
            )
            .select_related("hf_org")
            .order_by("product_key")
        )
        rows = (
            PostBrand.objects.filter(
                brand_id__in=brand_ids,
                post__created_at__gte=datetime.combine(day(start_date), time.min, UTC),
                post__created_at__lt=datetime.combine(
                    day(end_date) + timedelta(days=1), time.min, UTC
                ),
            )
            .annotate(date=TruncDate("post__created_at", tzinfo=UTC))
            .values("brand_id", "date")
            .annotate(count=Count("post_id", distinct=True))
            .order_by("date", "brand_id")
        )
        result = {
            "schema_version": 1,
            "exported_at": datetime.now(UTC).isoformat(),
            "brands": [
                {
                    "id": b.pk,
                    "label": b.display_name_en or b.display_name or b.pk,
                    "label_zh": b.display_name_zh_cn or b.display_name or b.pk,
                    "company_ids": sorted(c for brand, c in links if brand == b.pk),
                }
                for b in brands
            ],
            "companies": [
                {"id": c.pk, "label": c.display_name or c.pk} for c in companies
            ],
            "products": [
                {
                    "product_key": str(p.product_key),
                    "brand_id": p.brand_id,
                    "label": p.display_name or p.repo_id or str(p.product_key),
                    "repo_id": p.repo_id,
                    "hf_namespace": p.hf_org_id,
                    "hf_confirmed": bool(p.hf_org and p.hf_org.confirmed),
                    "hf_company_id": p.hf_org.company_id if p.hf_org else None,
                }
                for p in products
                if p.private is not True and p.disabled is not True
            ],
            "posts": {
                "start_date": start_date,
                "end_date": end_date,
                "scope": "collected_postbrand",
                "counts": [
                    {
                        "date": row["date"].isoformat(),
                        "brand_id": row["brand_id"],
                        "count": row["count"],
                    }
                    for row in rows
                ],
            },
        }
    validate_inputs(
        result, {"schema_version": 1, "hf_product_keys": [], "mappings": []}
    )
    return result


class Command(BaseCommand):
    help = (
        "Read-only export for the isolated benchmark/download collector (no network)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--brands", nargs="+", required=True)
        parser.add_argument("--start-date", required=True)
        parser.add_argument("--end-date", required=True)
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        try:
            value = export_inputs(
                options["brands"], options["start_date"], options["end_date"]
            )
            write_new(options["output"], value)
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"Exported {len(value['brands'])} brands and {len(value['products'])} LLM products to {options['output']}"
        )
