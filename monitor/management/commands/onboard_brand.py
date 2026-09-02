"""Atomically onboard tracked brand identity from an operator-authored CSV."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Brand, BrandCompany, BrandKeyword, Company, HFOrg, Product
from monitor.country_codes import COUNTRY_NAMES
from x_monitor.harvest_policy import load_policy
from x_monitor.specs_from_policy import active_policy_tokens, normalize_policy_token

CSV_FIELDS = (
    "brand_nickname",
    "brand_display_name",
    "brand_display_name_en",
    "brand_display_name_zh_cn",
    "accent_color",
    "company_nickname",
    "company_display_name",
    "company_display_name_en",
    "company_display_name_zh_cn",
    "company_hq_country",
    "hf_orgs",
    "hf_product_repo_ids",
    "keyword_primary",
    "keyword_aliases",
    "c_bare_aliases",
    "official_x_handles",
    "staff_x_handles",
    "harvest_paths",
    "co_pack",
    "version_family_prefix",
    "version_family_current_major",
    "version_family_lookback",
    "version_family_lookahead",
    "version_family_extra_suffixes",
    "notes",
)
_NICKNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
_HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
_INTEGER_FIELDS = (
    "version_family_current_major",
    "version_family_lookback",
    "version_family_lookahead",
)


class OnboardValidationError(ValueError):
    """A user-correctable CSV or configuration error."""


def _split(value: str | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in (value or "").split("|"):
        item = item.strip()
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _normalized_token(value: str) -> str:
    return normalize_policy_token(value)


def _normalize_handles(
    value: str | None, field_name: str, row_number: int
) -> list[str]:
    handles: list[str] = []
    for handle in _split(value):
        normalized = handle.lstrip("@")
        if not _HANDLE_RE.fullmatch(normalized):
            raise OnboardValidationError(
                f"row {row_number}: {field_name} has invalid X handle {handle!r}"
            )
        if normalized.casefold() not in {h.casefold() for h in handles}:
            handles.append(normalized)
    return handles


def _hf_path(value: str, *, product: bool) -> str:
    value = value.strip().rstrip("/")
    if not value:
        raise OnboardValidationError("empty Hugging Face value")
    if value.startswith(("https://", "http://")):
        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or parsed.netloc.casefold() != "huggingface.co"
            or parsed.query
            or parsed.fragment
        ):
            raise OnboardValidationError(f"invalid Hugging Face URL {value!r}")
        pieces = [p for p in parsed.path.split("/") if p]
    else:
        pieces = [p for p in value.split("/") if p]
    if not pieces or len(pieces) > 2 or (product and len(pieces) != 2):
        raise OnboardValidationError(f"invalid Hugging Face value {value!r}")
    return "/".join(pieces) if product else pieces[0]


def _parse_nonnegative_int(value: str, field_name: str, row_number: int) -> int | None:
    if not value.strip():
        return None
    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise OnboardValidationError(
            f"row {row_number}: {field_name} must be an integer"
        ) from exc
    if parsed < 0:
        raise OnboardValidationError(
            f"row {row_number}: {field_name} must be non-negative"
        )
    return parsed


@dataclass
class BrandRow:
    row_number: int
    nickname: str
    display_name: str
    display_name_en: str
    display_name_zh_cn: str
    accent_color: str
    company_nickname: str
    company_display_name: str
    company_display_name_en: str
    company_display_name_zh_cn: str
    company_hq_country: str
    hf_orgs: list[str] = field(default_factory=list)
    products: list[str] = field(default_factory=list)
    keyword_primary: str = ""
    keyword_aliases: list[str] = field(default_factory=list)
    c_bare_aliases: list[str] = field(default_factory=list)
    official_x_handles: list[str] = field(default_factory=list)
    staff_x_handles: list[str] = field(default_factory=list)
    harvest_paths: list[str] = field(default_factory=list)
    co_pack: str = ""
    version_family_prefix: str = ""
    version_family_current_major: int | None = None
    version_family_lookback: int | None = None
    version_family_lookahead: int | None = None
    version_family_extra_suffixes: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def keywords(self) -> list[tuple[str, bool]]:
        return [
            (self.keyword_primary, True),
            *((v, False) for v in self.keyword_aliases),
            *((v, False) for v in self.c_bare_aliases),
        ]


def _parse_row(raw: dict[str, str], row_number: int) -> BrandRow | None:
    value = lambda name: (raw.get(name) or "").strip()
    nickname = value("brand_nickname")
    if not nickname or nickname.startswith("_"):
        return None
    if not _NICKNAME_RE.fullmatch(nickname):
        raise OnboardValidationError(
            f"row {row_number}: invalid brand_nickname {nickname!r}"
        )
    display_name = value("brand_display_name")
    if not display_name:
        raise OnboardValidationError(
            f"row {row_number}: brand_display_name is required"
        )
    accent = value("accent_color")
    if not _COLOR_RE.fullmatch(accent):
        raise OnboardValidationError(f"row {row_number}: accent_color is invalid")
    company = value("company_nickname")
    if company and not _NICKNAME_RE.fullmatch(company):
        raise OnboardValidationError(
            f"row {row_number}: invalid company_nickname {company!r}"
        )
    country = value("company_hq_country")
    if country and (not _COUNTRY_RE.fullmatch(country) or country not in COUNTRY_NAMES):
        raise OnboardValidationError(f"row {row_number}: company_hq_country is invalid")
    hf_orgs: list[str] = []
    seen_hf_orgs: set[str] = set()
    for raw_value in _split(raw.get("hf_orgs")):
        namespace = _hf_path(raw_value, product=False)
        if namespace.casefold() not in seen_hf_orgs:
            hf_orgs.append(namespace)
            seen_hf_orgs.add(namespace.casefold())
    products = [
        _hf_path(v, product=True) for v in _split(raw.get("hf_product_repo_ids"))
    ]
    if (hf_orgs or products) and not company:
        raise OnboardValidationError(
            f"row {row_number}: company_nickname is required for HF orgs/products"
        )
    primary = value("keyword_primary")
    if not primary:
        raise OnboardValidationError(f"row {row_number}: keyword_primary is required")
    keywords = [
        primary,
        *_split(raw.get("keyword_aliases")),
        *_split(raw.get("c_bare_aliases")),
    ]
    normalized = [_normalized_token(v) for v in keywords]
    if len(normalized) != len(set(normalized)):
        raise OnboardValidationError(f"row {row_number}: duplicate keyword")
    ints = {
        field_name: _parse_nonnegative_int(value(field_name), field_name, row_number)
        for field_name in _INTEGER_FIELDS
    }
    return BrandRow(
        row_number=row_number,
        nickname=nickname,
        display_name=display_name,
        display_name_en=value("brand_display_name_en"),
        display_name_zh_cn=value("brand_display_name_zh_cn"),
        accent_color=accent,
        company_nickname=company,
        company_display_name=value("company_display_name"),
        company_display_name_en=value("company_display_name_en"),
        company_display_name_zh_cn=value("company_display_name_zh_cn"),
        company_hq_country=country,
        hf_orgs=hf_orgs,
        products=products,
        keyword_primary=primary,
        keyword_aliases=_split(raw.get("keyword_aliases")),
        c_bare_aliases=_split(raw.get("c_bare_aliases")),
        official_x_handles=_normalize_handles(
            raw.get("official_x_handles"), "official_x_handles", row_number
        ),
        staff_x_handles=_normalize_handles(
            raw.get("staff_x_handles"), "staff_x_handles", row_number
        ),
        harvest_paths=_split(raw.get("harvest_paths")),
        co_pack=value("co_pack"),
        version_family_prefix=value("version_family_prefix"),
        version_family_current_major=ints["version_family_current_major"],
        version_family_lookback=ints["version_family_lookback"],
        version_family_lookahead=ints["version_family_lookahead"],
        version_family_extra_suffixes=_split(raw.get("version_family_extra_suffixes")),
        notes=value("notes"),
    )


def read_csv(path: Path) -> list[BrandRow]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            if tuple(reader.fieldnames or ()) != CSV_FIELDS:
                raise OnboardValidationError(
                    "CSV header must match brand-onboard.template.csv exactly"
                )
            rows = []
            for row_number, raw in enumerate(reader, start=2):
                if None in raw:
                    raise OnboardValidationError(
                        f"row {row_number}: too many CSV fields"
                    )
                if any(value is None for value in raw.values()):
                    raise OnboardValidationError(
                        f"row {row_number}: too few CSV fields"
                    )
                parsed = _parse_row(raw, row_number)
                if parsed is not None:
                    rows.append(parsed)
    except FileNotFoundError as exc:
        raise OnboardValidationError(f"CSV file not found: {path}") from exc
    except csv.Error as exc:
        raise OnboardValidationError(f"invalid RFC4180 CSV: {exc}") from exc
    seen: set[str] = set()
    for row in rows:
        if row.nickname in seen:
            raise OnboardValidationError(f"duplicate brand_nickname {row.nickname!r}")
        seen.add(row.nickname)
    return rows


def _policy_tokens(policy_path: Path, nickname: str) -> set[str]:
    policy = load_policy(policy_path)
    return active_policy_tokens(policy).get(nickname, set())


def _enabled_models(config_path: Path) -> set[str]:
    try:
        with config_path.open("r", encoding="utf-8") as stream:
            raw = yaml.safe_load(stream) or {}
    except FileNotFoundError as exc:
        raise OnboardValidationError(f"config file not found: {config_path}") from exc
    values = raw.get("enabled_models")
    if not isinstance(values, list):
        raise OnboardValidationError("config.yaml enabled_models must be a list")
    return {str(v).strip() for v in values}


def _validate(
    rows: list[BrandRow], config_path: Path, policy_path: Path, *, skip_search: bool
) -> list[str]:
    enabled = _enabled_models(config_path)
    policy = None
    policy_tokens: dict[str, set[str]] = {}
    if not skip_search:
        try:
            policy = load_policy(policy_path)
            policy_tokens = active_policy_tokens(policy)
        except (OSError, ValueError, TypeError) as exc:
            raise OnboardValidationError(f"invalid harvest policy: {exc}") from exc
    warnings: list[str] = []
    for row in rows:
        if row.nickname not in enabled:
            raise OnboardValidationError(
                f"brand {row.nickname!r} is not in config.yaml enabled_models"
            )
        if policy is None:
            warnings.append(f"{row.nickname}: skipped harvest-policy membership gate")
            continue
        if row.nickname not in policy.brands:
            raise OnboardValidationError(
                f"brand {row.nickname!r} is not present in harvest policy"
            )
        expected = policy_tokens.get(row.nickname, set())
        actual = {_normalized_token(value) for value, _ in row.keywords}
        actual.update(
            _normalized_token(value)
            for value in BrandKeyword.objects.filter(brand_id=row.nickname).values_list(
                "pattern", flat=True
            )
        )
        missing = sorted(expected - actual)
        if missing:
            raise OnboardValidationError(
                f"brand {row.nickname!r} keyword coverage is incomplete: {', '.join(missing)}"
            )
        policy_handles = {
            h.casefold().lstrip("@") for h in policy.brands[row.nickname].handles
        }
        supplied_handles = {
            h.casefold() for h in (*row.official_x_handles, *row.staff_x_handles)
        }
        if supplied_handles != policy_handles:
            warnings.append(f"{row.nickname}: CSV X handles differ from harvest policy")
        if row.harvest_paths and set(row.harvest_paths) != set(
            policy.brands[row.nickname].paths
        ):
            warnings.append(f"{row.nickname}: harvest_paths differ from harvest policy")
        if row.co_pack:
            expected_pack = next(
                (
                    f"C{index}"
                    for index, pack in enumerate(policy.co_packs, start=1)
                    if row.nickname in pack.brand_nicknames
                ),
                "",
            )
            if row.co_pack != expected_pack:
                warnings.append(f"{row.nickname}: co_pack differs from harvest policy")
    company_values: dict[str, tuple[str, str, str, str]] = {}
    hf_ownership: dict[str, str] = {}
    for row in rows:
        if row.company_nickname:
            company_data = (
                row.company_display_name or row.company_nickname,
                row.company_display_name_en,
                row.company_display_name_zh_cn,
                row.company_hq_country,
            )
            prior = company_values.setdefault(
                row.company_nickname.casefold(), company_data
            )
            if prior != company_data:
                raise OnboardValidationError(
                    f"company {row.company_nickname!r} has conflicting rows"
                )
        namespaces = [
            *row.hf_orgs,
            *(repo_id.split("/", 1)[0] for repo_id in row.products),
        ]
        for namespace in dict.fromkeys(namespaces):
            prior_company = hf_ownership.setdefault(
                namespace.casefold(), row.company_nickname
            )
            if prior_company.casefold() != row.company_nickname.casefold():
                raise OnboardValidationError(
                    f"HF org {namespace!r} has conflicting ownership"
                )
            existing_hf = HFOrg.objects.filter(namespace=namespace).first()
            if (
                existing_hf
                and existing_hf.company_id.casefold() != row.company_nickname.casefold()
            ):
                raise OnboardValidationError(
                    f"HF org {namespace!r} is already owned by another company"
                )
    ownership: dict[str, tuple[str, str]] = {}
    for row in rows:
        for repo_id in row.products:
            owner = (row.nickname, repo_id.split("/", 1)[0])
            previous = ownership.setdefault(repo_id.casefold(), owner)
            if previous != owner:
                raise OnboardValidationError(
                    f"product {repo_id!r} has conflicting ownership"
                )
            existing = Product.objects.filter(repo_id=repo_id).first()
            if existing and (
                existing.brand_id not in (None, row.nickname)
                or (
                    existing.hf_org_id
                    and existing.hf_org_id.casefold() != owner[1].casefold()
                )
            ):
                raise OnboardValidationError(
                    f"product {repo_id!r} is already owned by another brand or HF org"
                )
    return warnings


def _update(obj, defaults: dict[str, object]) -> bool:
    changed = any(getattr(obj, key) != value for key, value in defaults.items())
    if changed:
        for key, value in defaults.items():
            setattr(obj, key, value)
        obj.save(update_fields=list(defaults))
    return changed


class Command(BaseCommand):
    help = "Atomically onboard tracked brands from an RFC4180 CSV file."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--csv", required=True, type=Path, dest="csv_path")
        parser.add_argument("--config", type=Path, default=Path("config.yaml"))
        parser.add_argument(
            "--policy", type=Path, default=Path("config/harvest_policy.yaml")
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--skip-search",
            action="store_true",
            help="Skip harvest-policy membership/coverage checks.",
        )

    def handle(self, **options) -> None:
        try:
            rows = read_csv(options["csv_path"])
            warnings = _validate(
                rows,
                options["config"],
                options["policy"],
                skip_search=options["skip_search"],
            )
        except OnboardValidationError as exc:
            raise CommandError(str(exc)) from exc
        for warning in warnings:
            self.stdout.write(self.style.WARNING(f"warning: {warning}"))
        if options["dry_run"]:
            self.stdout.write(
                f"dry-run: {len(rows)} row(s), no writes or external calls"
            )
            for row in rows:
                handles = (
                    ",".join((*row.official_x_handles, *row.staff_x_handles))
                    or "(none)"
                )
                self.stdout.write(
                    f"  {row.nickname}: company={row.company_nickname or '(none)'} hf_orgs={','.join(row.hf_orgs) or '(none)'} products={','.join(row.products) or '(none)'} handles={handles}"
                )
            return
        counts = {
            key: 0
            for key in (
                "brands",
                "companies",
                "brands_companies",
                "hf_orgs",
                "brand_keywords",
                "products",
                "unchanged",
            )
        }
        with transaction.atomic():
            for row in rows:
                brand, created = Brand.objects.get_or_create(nickname=row.nickname)
                defaults = {
                    "display_name": row.display_name,
                    "display_name_en": row.display_name_en or None,
                    "display_name_zh_cn": row.display_name_zh_cn or None,
                    "accent_color": row.accent_color,
                    "is_sentinel": False,
                }
                if created:
                    _update(brand, defaults)
                    counts["brands"] += 1
                else:
                    counts[
                        "unchanged" if not _update(brand, defaults) else "brands"
                    ] += 1
                company = None
                if row.company_nickname:
                    company, company_created = Company.objects.get_or_create(
                        nickname=row.company_nickname
                    )
                    company_defaults = {
                        "display_name": row.company_display_name
                        or row.company_nickname,
                        "display_name_en": row.company_display_name_en or None,
                        "display_name_zh_cn": row.company_display_name_zh_cn or None,
                        "hq_country": row.company_hq_country or None,
                    }
                    if company_created:
                        _update(company, company_defaults)
                        counts["companies"] += 1
                    else:
                        counts[
                            "unchanged"
                            if not _update(company, company_defaults)
                            else "companies"
                        ] += 1
                    _, link_created = BrandCompany.objects.get_or_create(
                        brand=brand, company=company
                    )
                    counts["brands_companies"] += int(link_created)
                hf_by_namespace: dict[str, HFOrg] = {}
                namespaces = [
                    *row.hf_orgs,
                    *(repo_id.split("/", 1)[0] for repo_id in row.products),
                ]
                for namespace in dict.fromkeys(namespaces):
                    assert company is not None
                    hf_org, hf_created = HFOrg.objects.get_or_create(
                        namespace=namespace, defaults={"company": company}
                    )
                    if not hf_created and hf_org.company_id != company.nickname:
                        raise CommandError(
                            f"HF org {namespace!r} is already owned by another company"
                        )
                    hf_by_namespace[namespace.casefold()] = hf_org
                    counts["hf_orgs"] += int(hf_created)
                for pattern, is_primary in row.keywords:
                    keyword, keyword_created = BrandKeyword.objects.get_or_create(
                        brand=brand,
                        pattern=pattern,
                        defaults={"is_primary": is_primary, "is_regex": False},
                    )
                    if keyword_created:
                        counts["brand_keywords"] += 1
                    else:
                        counts[
                            "unchanged"
                            if not _update(
                                keyword,
                                {"is_primary": is_primary, "is_regex": False},
                            )
                            else "brand_keywords"
                        ] += 1
                for repo_id in row.products:
                    namespace = repo_id.split("/", 1)[0]
                    product, product_created = Product.objects.get_or_create(
                        repo_id=repo_id
                    )
                    if not product_created and product.brand_id not in (
                        None,
                        brand.nickname,
                    ):
                        raise CommandError(
                            f"product {repo_id!r} is already owned by another brand"
                        )
                    next_hf_org = hf_by_namespace.get(namespace.casefold())
                    if product_created or (
                        product.brand_id != brand.nickname
                        or (product.hf_org_id or "").casefold()
                        != (next_hf_org.namespace if next_hf_org else "").casefold()
                    ):
                        product.brand = brand
                        product.hf_org = next_hf_org
                        product.save(update_fields=["brand", "hf_org", "updated_at"])
                        counts["products"] += 1
                    else:
                        counts["unchanged"] += 1
        self.stdout.write("onboard_brand complete")
        self.stdout.write(
            "  " + " ".join(f"{key}={value}" for key, value in counts.items())
        )
