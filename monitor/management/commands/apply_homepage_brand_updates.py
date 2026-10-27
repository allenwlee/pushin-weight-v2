"""Preview or apply curated Meta identity and homepage brand colors."""

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.brand_presentation import BRAND_ACCENT_COLORS, META_BRAND_NAMES
from core.models import Brand, BrandCompany, BrandSearchTerm
from core.publisher_accounts import publisher_links, register_publisher


class Command(BaseCommand):
    help = "Preview Meta names, aliases, HF publisher and brand colors; --commit applies without network calls"

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true")

    def handle(self, **options):
        commit = options["commit"]
        try:
            with transaction.atomic():
                brands = Brand.objects.filter(nickname__in=BRAND_ACCENT_COLORS)
                if commit:
                    brands = brands.select_for_update()
                brands = {brand.pk: brand for brand in brands}
                if "llama" not in brands or not BrandCompany.objects.filter(
                    brand_id="llama", company_id="meta",
                ).exists():
                    raise CommandError("Existing llama brand and meta company ownership are required")
                if publisher_links(source="hf", identifier="meta-models").exclude(
                    company_id="meta",
                ).exists():
                    raise CommandError("Conflicting meta-models publisher ownership")

                meta = brands["llama"]
                aliases = {"Llama", "Meta Llama", "Code Llama", "Meta", "Muse"}
                aliases.update(
                    name for field in META_BRAND_NAMES
                    if (name := getattr(meta, field))
                )
                aliases -= set(BrandSearchTerm.objects.filter(brand=meta).values_list("term", flat=True))
                changes = []
                for nickname, brand in sorted(brands.items()):
                    wanted = {"accent_color": BRAND_ACCENT_COLORS[nickname]}
                    if nickname == "llama":
                        wanted.update(META_BRAND_NAMES)
                    changed = {key: value for key, value in wanted.items() if getattr(brand, key) != value}
                    if changed:
                        changes.append({"brand": nickname, "before": {key: getattr(brand, key) for key in changed}, "after": changed})
                        if commit:
                            Brand.objects.filter(pk=brand.pk).update(**changed)
                if commit:
                    for alias in sorted(aliases):
                        BrandSearchTerm.objects.get_or_create(brand=meta, term=alias)
                    register_publisher(
                        source="hf", identifier="meta-models", company_id="meta", confirmed=True,
                        discovered_via="https://huggingface.co/meta-models",
                    )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps({
            "mode": "commit" if commit else "preview",
            "brand_changes": changes,
            "aliases_added": sorted(aliases),
            "publisher": {"namespace": "meta-models", "company": "meta", "ownership_confirmed": True},
            "absent_brands": sorted(set(BRAND_ACCENT_COLORS) - set(brands)),
            "catalog_imported": False,
        }, ensure_ascii=False, sort_keys=True))
