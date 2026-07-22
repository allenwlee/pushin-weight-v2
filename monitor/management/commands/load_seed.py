"""Seed the curated base layer: brands, companies, roles, and known accounts.

Plan: docs/plans/2026-07-22-150000-feat-x-probe-new-open-model-discovery-harvest-onboard-plan.md
Unit 5 of N (U5 — seed command).

Loads the 20 enabled brands from project.settings.KNOWN_MODELS, their
associated companies, brand-company links, roles, and a curated set of
known official/staff accounts. Modeled on the pushin_weight reference
seed scripts (2026-06-25-005-seed-companies-brands-from-csv.py and
seed_list_handles_to_db.py).

Usage:
    python manage.py load_seed [--dry-run] [--brands a,b,c]

All inserts are idempotent (get_or_create / update_or_create). Re-running
after a successful seed produces no net new rows.
"""
from __future__ import annotations

import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Account, Brand, BrandAccount, BrandCompany, Company, Role

# ---------------------------------------------------------------------------
# Curated data
# ---------------------------------------------------------------------------

# Brand -> Company mapping for the 20 enabled brands. Company nickname is the
# canonical slug used in brands_companies and other junction tables.
# Values sourced from the v1.7 x-monitoring DB and the pushin_weight reference.
BRAND_TO_COMPANY: dict[str, str] = {
    "minimax":       "minimax",
    "qwen":          "alibaba",
    "deepseek":      "deepseek",
    "glm":           "zhipu",
    "mimo":          "meituan",
    "moonshot_kimi": "moonshot",
    "inclusionai":   "inclusionai",
    "mistral":       "mistral_ai",
    "stepfun":       "stepfun_inc",
    "ernie":         "baidu",
    "hunyuan":       "tencent",
    "llama":         "meta",
    "nemo_megatron": "nvidia",
    "doubao":        "bytedance",
    "yi":            "01ai",
    "sensechat":     "sensetime",
    "exaone":        "lg_ai_research",
    "kuaishou":      "kuaishou",
    "sakana_ai":     "sakana",
    "upstage":       "upstage_inc",
}

# Display names for the 20 enabled brands. Used when upserting Brand rows.
BRAND_DISPLAY: dict[str, str] = {
    "minimax":       "MiniMax",
    "qwen":          "Qwen",
    "deepseek":      "DeepSeek",
    "glm":           "GLM / ChatGLM",
    "mimo":          "MiMo",
    "moonshot_kimi": "Moonshot AI / Kimi",
    "inclusionai":   "InclusionAI",
    "mistral":       "Mistral",
    "stepfun":       "StepFun",
    "ernie":         "ERNIE",
    "hunyuan":       "Hunyuan",
    "llama":         "Llama",
    "nemo_megatron": "NeMo / Megatron",
    "doubao":        "Doubao",
    "yi":            "Yi",
    "sensechat":     "SenseChat",
    "exaone":        "EXAONE",
    "kuaishou":      "Kling / Kuaishou",
    "sakana_ai":     "Sakana AI",
    "upstage":       "Upstage",
}

# Display names for the companies that own the brands.
COMPANY_DISPLAY: dict[str, str] = {
    "minimax":        "MiniMax",
    "alibaba":        "Alibaba Group",
    "deepseek":       "DeepSeek",
    "zhipu":          "Zhipu AI",
    "meituan":        "Meituan",
    "moonshot":       "Moonshot AI",
    "inclusionai":    "InclusionAI Co.",
    "mistral_ai":     "Mistral AI",
    "stepfun_inc":    "StepFun",
    "baidu":          "Baidu Inc.",
    "tencent":        "Tencent",
    "meta":           "Meta Platforms Inc.",
    "nvidia":         "NVIDIA",
    "bytedance":      "ByteDance",
    "01ai":           "01.AI",
    "sensetime":      "SenseTime",
    "lg_ai_research": "LG AI Research",
    "kuaishou":       "Kuaishou Technology",
    "sakana":         "Sakana",
    "upstage_inc":    "Upstage Inc.",
}

# Company HQ countries (ISO 3166-1 alpha-2).
COMPANY_HQ: dict[str, str] = {
    "minimax":        "CN",
    "alibaba":        "CN",
    "deepseek":       "CN",
    "zhipu":          "CN",
    "meituan":        "CN",
    "moonshot":       "CN",
    "inclusionai":    "CN",
    "mistral_ai":     "FR",
    "stepfun_inc":    "CN",
    "baidu":          "CN",
    "tencent":        "CN",
    "meta":           "US",
    "nvidia":         "US",
    "bytedance":      "CN",
    "01ai":           "CN",
    "sensetime":      "CN",
    "lg_ai_research": "KR",
    "kuaishou":       "CN",
    "sakana":         "JP",
    "upstage_inc":    "KR",
}

# Curated known accounts: (handle, company_nickname, role_key).
# Role keys: official, staff, community.
# Sourced from seed_list_handles_to_db.py DEFAULT_SEED and operator-confirmed
# triples from plan 005 U3 + 3c Summary table.
KNOWN_ACCOUNTS: list[tuple[str, str, str]] = [
    # minimax
    ("hailuo_ai",         "minimax",        "official"),
    # qwen / alibaba
    ("chujiezheng",       "alibaba",        "staff"),
    ("xuanmingzhangai",   "alibaba",        "staff"),
    ("xiong_hui_chen",    "alibaba",        "staff"),
    # glm / zhipu
    ("carolglms",         "zhipu",          "staff"),
    ("zrdianjiao",        "zhipu",          "staff"),
    ("CunxiangWang",      "zhipu",          "staff"),
    ("louszbd",           "zhipu",          "staff"),
    ("Zai_org",           "zhipu",          "official"),
    ("ZixuanLi_",         "zhipu",          "staff"),
    # doubao / bytedance
    ("bytedanceoss",      "bytedance",      "official"),
    ("doubaoai",          "bytedance",      "official"),
    ("BytePlusGlobal",    "bytedance",      "official"),
    # mistral
    ("mertunsal2020",     "mistral_ai",     "staff"),
    ("sophiamyang",       "mistral_ai",     "staff"),
    # stepfun
    ("stepfunai",         "stepfun_inc",    "official"),
    ("EileenTal",         "stepfun_inc",    "staff"),
    # ernie / baidu
    ("PaddlePaddle",      "baidu",          "official"),
    # llama / meta
    ("alexandr_wang",     "meta",           "staff"),
    # upstage
    ("echojuliett",       "upstage_inc",    "staff"),
    # sakana
    ("Stefania_druga",    "sakana",         "staff"),
]


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be seeded without writing to DB.",
        )
        parser.add_argument(
            "--brands",
            type=str,
            default=None,
            help="Comma-separated list of brand nicknames to seed (default: all 20).",
        )
        parser.add_argument(
            "--no-accounts",
            action="store_true",
            help="Skip account seeding (brands + companies + roles only).",
        )

    def handle(self, **options):
        dry_run: bool = options["dry_run"]
        brands_filter: str | None = options["brands"]
        no_accounts: bool = options["no_accounts"]

        target_brands = list(getattr(settings, "KNOWN_MODELS", frozenset()))
        if not target_brands:
            self.stderr.write("error: KNOWN_MODELS is empty in settings")
            sys.exit(1)

        if brands_filter:
            requested = {b.strip() for b in brands_filter.split(",") if b.strip()}
            target_brands = [b for b in target_brands if b in requested]
            if not target_brands:
                self.stderr.write(
                    f"error: no brands match filter {requested} in KNOWN_MODELS"
                )
                sys.exit(1)

        self.stdout.write("=" * 64)
        self.stdout.write("Seed x-monitor v2 — curated base layer")
        self.stdout.write(f"  Brands: {len(target_brands)}")
        self.stdout.write(f"  Dry run: {dry_run}")
        self.stdout.write(f"  Accounts: {not no_accounts}")
        self.stdout.write("=" * 64)

        stats: dict[str, int] = {"brands": 0, "companies": 0, "brands_companies": 0,
                                  "roles": 0, "accounts": 0, "brands_accounts": 0,
                                  "skipped": 0}

        with transaction.atomic():
            # ---- Step 1: Roles ----
            self.stdout.write("\n[1/5] Roles")
            role_keys = ["community", "official", "staff"]
            for key in role_keys:
                if dry_run:
                    self.stdout.write(f"  [dry-run] Role(key={key})")
                else:
                    Role.objects.get_or_create(key=key)
                stats["roles"] += 1
            self.stdout.write(f"  Seeded {len(role_keys)} roles")

            # ---- Step 2: Sentinel brand ----
            self.stdout.write("\n[2/5] Brands (including _unattributed sentinel)")
            if dry_run:
                self.stdout.write("  [dry-run] Brand(nickname=_unattributed, is_sentinel=True)")
            else:
                Brand.objects.update_or_create(
                    nickname="_unattributed",
                    defaults={
                        "display_name": "Unattributed",
                        "is_sentinel": True,
                    },
                )
            stats["brands"] += 1
            self.stdout.write("  _unattributed (sentinel)")

            # ---- Step 3: Brands + Companies + brands_companies ----
            self.stdout.write("\n[3/5] Brands + Companies + links")
            seen_companies: set[str] = set()

            for brand_nickname in target_brands:
                company_nickname = BRAND_TO_COMPANY.get(brand_nickname)
                if not company_nickname:
                    self.stderr.write(
                        f"  [warn] no company mapping for brand '{brand_nickname}' — skipping"
                    )
                    stats["skipped"] += 1
                    continue

                display_name = BRAND_DISPLAY.get(brand_nickname, brand_nickname)

                # Upsert brand
                if dry_run:
                    self.stdout.write(
                        f"  [dry-run] Brand(nickname={brand_nickname}, "
                        f"display_name={display_name})"
                    )
                else:
                    Brand.objects.update_or_create(
                        nickname=brand_nickname,
                        defaults={"display_name": display_name, "is_sentinel": False},
                    )
                stats["brands"] += 1

                # Upsert company (only once per unique company)
                if company_nickname not in seen_companies:
                    comp_display = COMPANY_DISPLAY.get(company_nickname, company_nickname)
                    comp_hq = COMPANY_HQ.get(company_nickname)
                    if dry_run:
                        self.stdout.write(
                            f"  [dry-run] Company(nickname={company_nickname}, "
                            f"display_name={comp_display})"
                        )
                    else:
                        Company.objects.update_or_create(
                            nickname=company_nickname,
                            defaults={
                                "display_name": comp_display,
                                "hq_country": comp_hq,
                            },
                        )
                    stats["companies"] += 1
                    seen_companies.add(company_nickname)

                # Upsert brand-company link
                if dry_run:
                    self.stdout.write(
                        f"  [dry-run] BrandCompany(brand={brand_nickname}, "
                        f"company={company_nickname})"
                    )
                else:
                    BrandCompany.objects.get_or_create(
                        brand_id=brand_nickname,
                        company_id=company_nickname,
                        defaults={"ownership_pct": 1.0},
                    )
                stats["brands_companies"] += 1

            self.stdout.write(
                f"  Seeded {len(target_brands)} brands, "
                f"{len(seen_companies)} companies, "
                f"{stats['brands_companies']} brand-company links"
            )

            # ---- Step 4: Known accounts ----
            if no_accounts:
                self.stdout.write("\n[4/5] Accounts — SKIPPED (--no-accounts)")
            else:
                self.stdout.write("\n[4/5] Known accounts + brand-account links")
                seen_accounts: set[str] = set()
                for handle, company_nickname, role_key in KNOWN_ACCOUNTS:
                    # The author_id for now is the lowercased handle as a
                    # placeholder. When TwitterAPI.io auth is available, a
                    # follow-up script can replace these with real numeric IDs.
                    author_id = handle.lower()

                    # Upsert account
                    if author_id not in seen_accounts:
                        if dry_run:
                            self.stdout.write(
                                f"  [dry-run] Account(author_id={author_id}, "
                                f"handle={handle})"
                            )
                        else:
                            try:
                                Account.objects.update_or_create(
                                    author_id=author_id,
                                    defaults={"handle": handle},
                                )
                            except Exception as exc:
                                self.stderr.write(
                                    f"  [warn] Account({author_id}): {exc}"
                                )
                                continue
                        stats["accounts"] += 1
                        seen_accounts.add(author_id)

                    # Find all brands linked to this company
                    if dry_run:
                        self.stdout.write(
                            f"  [dry-run] BrandAccount(brand=<{company_nickname} brands>, "
                            f"account={author_id}, role={role_key})"
                        )
                    else:
                        # Look up companies' brands
                        linked_brands = BrandCompany.objects.filter(
                            company_id=company_nickname
                        ).values_list("brand_id", flat=True)

                        for brand_nickname in linked_brands:
                            # Skip if brand not in our target set (if filtering)
                            if brands_filter and brand_nickname not in requested:
                                continue
                            try:
                                BrandAccount.objects.get_or_create(
                                    brand_id=brand_nickname,
                                    account_id=author_id,
                                    role_id=role_key,
                                )
                                stats["brands_accounts"] += 1
                            except Exception as exc:
                                self.stderr.write(
                                    f"  [warn] BrandAccount({brand_nickname}, "
                                    f"{author_id}): {exc}"
                                )

                self.stdout.write(
                    f"  Seeded {stats['accounts']} accounts, "
                    f"{stats['brands_accounts']} brand-account links"
                )

            if dry_run:
                # Roll back the transaction
                transaction.set_rollback(True)

        # ---- Summary ----
        self.stdout.write("\n" + "=" * 64)
        self.stdout.write(f"  Brands:            {stats['brands']}")
        self.stdout.write(f"  Companies:         {stats['companies']}")
        self.stdout.write(f"  Brand-Company:     {stats['brands_companies']}")
        self.stdout.write(f"  Roles:             {stats['roles']}")
        self.stdout.write(f"  Accounts:          {stats['accounts']}")
        self.stdout.write(f"  Brand-Account:     {stats['brands_accounts']}")
        if stats["skipped"]:
            self.stdout.write(f"  Skipped:           {stats['skipped']}")
        if dry_run:
            self.stdout.write("  ** DRY RUN — no writes performed **")
        self.stdout.write("=" * 64)
        self.stdout.write("\nSeed complete.")
