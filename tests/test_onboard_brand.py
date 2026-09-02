"""Focused contract tests for the CSV tracked-brand onboarding command."""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import (
    Account,
    Brand,
    BrandAccount,
    BrandCompany,
    BrandKeyword,
    Company,
    HFOrg,
    Product,
)
from monitor.cycle import _build_brand_index
from monitor.management.commands.onboard_brand import (
    _normalized_token,
    _policy_tokens,
    read_csv,
)
from x_monitor.attribution import detect_brand_mentions
from x_monitor.config import load_config
from x_monitor.specs_from_policy import normalize_policy_token

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


HEADER = (
    "brand_nickname,brand_display_name,brand_display_name_en,"
    "brand_display_name_zh_cn,accent_color,company_nickname,company_display_name,"
    "company_display_name_en,company_display_name_zh_cn,company_hq_country,hf_orgs,"
    "hf_product_repo_ids,keyword_primary,keyword_aliases,c_bare_aliases,"
    "official_x_handles,official_x_author_ids,staff_x_handles,staff_x_author_ids,"
    "harvest_paths,co_pack,version_family_prefix,"
    "version_family_current_major,version_family_lookback,version_family_lookahead,"
    "version_family_extra_suffixes,notes\n"
)


def _write_input(path: Path, rows: list[dict[str, str]]) -> None:
    fields = HEADER.rstrip("\n").split(",")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _row(**overrides: str) -> dict[str, str]:
    row = {field: "" for field in HEADER.rstrip("\n").split(",")}
    row.update(
        {
            "brand_nickname": "dots",
            "brand_display_name": "dots",
            "brand_display_name_en": "dots",
            "brand_display_name_zh_cn": "dots",
            "accent_color": "#0ea5e9",
            "keyword_primary": "dots3-note",
        }
    )
    row.update(overrides)
    return row


def _config_and_policy(
    tmp_path: Path,
    *,
    nickname: str = "dots",
    token: str = "dots3-note",
) -> tuple[Path, Path]:
    config = tmp_path / "config.yaml"
    config.write_text(f"enabled_models:\n  - {nickname}\n", encoding="utf-8")
    policy = tmp_path / "harvest_policy.yaml"
    policy.write_text(
        f"brands:\n  {nickname}:\n    paths: [bare]\n    tokens: [{token}]\n",
        encoding="utf-8",
    )
    return config, policy


def _run(
    csv_path: Path,
    config: Path,
    policy: Path,
    *,
    dry_run: bool = False,
    skip_search: bool = False,
) -> str:
    stdout = StringIO()
    args = ["--csv", str(csv_path), "--config", str(config), "--policy", str(policy)]
    if dry_run:
        args.append("--dry-run")
    if skip_search:
        args.append("--skip-search")
    call_command("onboard_brand", *args, stdout=stdout)
    return stdout.getvalue()


def test_template_is_rfc4180_input_and_skips_instruction_row():
    template = Path(__file__).parents[1] / "config/brands/brand-onboard.template.csv"
    with template.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["brand_nickname"] == "_TEMPLATE"


def test_dots_row_creates_identity_tables(tmp_path: Path):
    csv_path = tmp_path / "brands.csv"
    _write_input(
        csv_path,
        [
            _row(
                company_nickname="xiaohongshu",
                company_display_name="Xiaohongshu",
                company_hq_country="CN",
                hf_orgs="https://huggingface.co/dots-studio",
                hf_product_repo_ids="https://huggingface.co/dots-studio/dots3-note-prev",
                keyword_aliases="dots3|dots4|dots studio",
            )
        ],
    )
    config, policy = _config_and_policy(tmp_path)

    _run(csv_path, config, policy)

    brand = Brand.objects.get(nickname="dots")
    company = Company.objects.get(nickname="xiaohongshu")
    assert BrandCompany.objects.filter(brand=brand, company=company).exists()
    assert HFOrg.objects.get(namespace="dots-studio").company_id == company.nickname
    assert (
        Product.objects.get(repo_id="dots-studio/dots3-note-prev").brand_id
        == brand.nickname
    )
    assert (
        BrandKeyword.objects.get(brand=brand, pattern="dots3-note").is_primary is True
    )
    assert (
        BrandKeyword.objects.get(brand=brand, pattern="dots3-note").is_regex is False
    )


def test_csv_onboarding_repairs_regex_keyword_for_live_attribution(
    tmp_path: Path, seeded_policy_keywords
):
    """PostgreSQL regression: onboarding must make DB keywords literal.

    The live cycle compiles ``BrandKeyword`` rows, so a stale regex flag can
    make an otherwise valid keyword fail body attribution.
    """
    csv_path = tmp_path / "brands.csv"
    _write_input(
        csv_path,
        [
            _row(
                brand_nickname="moonshot_kimi",
                brand_display_name="Kimi",
                brand_display_name_en="Kimi",
                keyword_primary="Kimi",
            )
        ],
    )
    config, policy = _config_and_policy(
        tmp_path, nickname="moonshot_kimi", token="Kimi"
    )

    BrandKeyword.objects.filter(
        brand_id="moonshot_kimi", pattern__iexact="Kimi"
    ).delete()
    BrandKeyword.objects.create(
        brand_id="moonshot_kimi", pattern="Kimi", is_regex=True
    )

    _run(csv_path, config, policy)

    keyword = BrandKeyword.objects.get(brand_id="moonshot_kimi", pattern="Kimi")
    assert keyword.is_regex is False
    repo_root = Path(__file__).parents[1]
    enabled_models = load_config(repo_root / "config.yaml").enabled_models
    index = _build_brand_index(list(enabled_models))
    assert "moonshot_kimi" in detect_brand_mentions(
        "Moonshot AI's Kimi K3 climbed to third place", index
    )


def test_onboard_token_normalization_matches_policy_normalization():
    for value in ('  "Ox Alpha"  ', "  Moonshot   AI ", "Kimi"):
        assert _normalized_token(value) == normalize_policy_token(value)


def test_missing_policy_fails_before_any_identity_write(tmp_path: Path):
    csv_path = tmp_path / "brands.csv"
    _write_input(csv_path, [_row()])
    config = tmp_path / "config.yaml"
    config.write_text("enabled_models:\n  - dots\n", encoding="utf-8")
    policy = tmp_path / "harvest_policy.yaml"
    policy.write_text("brands: {}\n", encoding="utf-8")

    with pytest.raises(CommandError, match="not present in harvest policy"):
        _run(csv_path, config, policy)
    assert not Brand.objects.filter(nickname="dots").exists()


def test_hf_org_without_company_fails_before_any_write(tmp_path: Path):
    csv_path = tmp_path / "brands.csv"
    _write_input(csv_path, [_row(hf_orgs="dots-studio")])
    config, policy = _config_and_policy(tmp_path)

    with pytest.raises(CommandError, match="company_nickname"):
        _run(csv_path, config, policy)
    assert not Brand.objects.filter(nickname="dots").exists()


def test_invalid_later_row_rolls_back_first_row(tmp_path: Path):
    csv_path = tmp_path / "brands.csv"
    _write_input(
        csv_path, [_row(), _row(brand_nickname="bad_brand", accent_color="blue")]
    )
    config, policy = _config_and_policy(tmp_path)

    with pytest.raises(CommandError, match="accent_color"):
        _run(csv_path, config, policy)
    assert not Brand.objects.filter(nickname="dots").exists()
    assert not Brand.objects.filter(nickname="bad_brand").exists()


def test_second_apply_is_idempotent_and_handles_are_metadata_only(tmp_path: Path):
    csv_path = tmp_path / "brands.csv"
    _write_input(
        csv_path,
        [_row(official_x_handles="@dotsstudioai", staff_x_handles="researcher")],
    )
    config, policy = _config_and_policy(tmp_path)

    _run(csv_path, config, policy)
    counts = (
        Brand.objects.count(),
        BrandKeyword.objects.count(),
        Account.objects.count(),
    )
    output = _run(csv_path, config, policy)

    assert (
        Brand.objects.count(),
        BrandKeyword.objects.count(),
        Account.objects.count(),
    ) == counts
    assert "unchanged" in output
    assert Account.objects.count() == 0


def test_canonical_x_accounts_create_idempotent_role_links(tmp_path: Path):
    csv_path = tmp_path / "brands.csv"
    _write_input(
        csv_path,
        [
            _row(
                official_x_handles="@dotsstudioai",
                official_x_author_ids="2085289191609716736",
                staff_x_handles="ChaoQiao42",
                staff_x_author_ids="2040060892176601088",
            )
        ],
    )
    config, policy = _config_and_policy(tmp_path)

    first_output = _run(csv_path, config, policy)
    second_output = _run(csv_path, config, policy)

    assert "accounts=2" in first_output
    assert "brands_accounts=2" in first_output
    assert "accounts=0" in second_output
    assert "brands_accounts=0" in second_output
    assert Account.objects.get(author_id="2085289191609716736").handle == "dotsstudioai"
    assert Account.objects.get(author_id="2040060892176601088").handle == "ChaoQiao42"
    assert BrandAccount.objects.get(
        brand_id="dots", account_id="2085289191609716736"
    ).role_id == "official"
    assert BrandAccount.objects.get(
        brand_id="dots", account_id="2040060892176601088"
    ).role_id == "staff"
    assert not Account.objects.filter(
        author_id__regex=r"^(handle:|synthetic:)"
    ).exists()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {
                "official_x_handles": "dotsstudioai|ChaoQiao42",
                "official_x_author_ids": "2085289191609716736",
            },
            "must align",
        ),
        (
            {
                "official_x_handles": "dotsstudioai",
                "official_x_author_ids": "not-numeric",
            },
            "invalid canonical id",
        ),
        (
            {
                "official_x_handles": "dotsstudioai",
                "official_x_author_ids": "2085289191609716736",
                "staff_x_handles": "DOTSSTUDIOAI",
                "staff_x_author_ids": "2040060892176601088",
            },
            "duplicate X handle",
        ),
        (
            {
                "official_x_handles": "dotsstudioai",
                "official_x_author_ids": "2085289191609716736",
                "staff_x_handles": "ChaoQiao42",
                "staff_x_author_ids": "2085289191609716736",
            },
            "duplicate X author id",
        ),
    ],
)
def test_invalid_canonical_account_pairs_fail_before_write(
    tmp_path: Path,
    overrides: dict[str, str],
    message: str,
):
    csv_path = tmp_path / "brands.csv"
    _write_input(csv_path, [_row(**overrides)])
    config, policy = _config_and_policy(tmp_path)

    with pytest.raises(CommandError, match=message):
        _run(csv_path, config, policy)

    assert not Brand.objects.filter(nickname="dots").exists()
    assert not Account.objects.exists()


def test_existing_account_handle_conflict_fails_before_write(tmp_path: Path):
    Account.objects.create(author_id="999", handle="dotsstudioai")
    csv_path = tmp_path / "brands.csv"
    _write_input(
        csv_path,
        [
            _row(
                official_x_handles="dotsstudioai",
                official_x_author_ids="2085289191609716736",
            )
        ],
    )
    config, policy = _config_and_policy(tmp_path)

    with pytest.raises(CommandError, match="already bound to another author id"):
        _run(csv_path, config, policy)

    assert not Brand.objects.filter(nickname="dots").exists()
    assert not BrandAccount.objects.exists()


def test_dry_run_prints_normalized_handles_without_writing(tmp_path: Path):
    csv_path = tmp_path / "brands.csv"
    _write_input(
        csv_path,
        [_row(official_x_handles="@dotsstudioai", staff_x_handles="researcher")],
    )
    config, policy = _config_and_policy(tmp_path)

    output = _run(csv_path, config, policy, dry_run=True)

    assert "dotsstudioai" in output
    assert "researcher" in output
    assert not Brand.objects.filter(nickname="dots").exists()


def test_product_owned_by_another_brand_is_rejected(tmp_path: Path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    _write_input(
        first,
        [
            _row(
                company_nickname="owner",
                hf_orgs="owner-org",
                hf_product_repo_ids="owner-org/model",
            )
        ],
    )
    _write_input(
        second,
        [
            _row(
                brand_nickname="other",
                brand_display_name="Other",
                keyword_primary="other-model",
                company_nickname="owner",
                hf_orgs="owner-org",
                hf_product_repo_ids="owner-org/model",
            )
        ],
    )
    config, policy = _config_and_policy(tmp_path)
    _run(first, config, policy)
    config.write_text("enabled_models:\n  - dots\n  - other\n", encoding="utf-8")
    policy.write_text(
        "brands:\n"
        "  dots:\n    paths: [bare]\n    tokens: [dots3-note]\n"
        "  other:\n    paths: [bare]\n    tokens: [other-model]\n",
        encoding="utf-8",
    )

    with pytest.raises(CommandError, match="already owned"):
        _run(second, config, policy)
    assert Product.objects.filter(repo_id="owner-org/model", brand_id="dots").exists()


def test_country_must_be_in_authoritative_iso_alpha2_map(tmp_path: Path):
    csv_path = tmp_path / "brands.csv"
    _write_input(csv_path, [_row(company_nickname="owner", company_hq_country="ZZ")])
    config, policy = _config_and_policy(tmp_path)

    with pytest.raises(CommandError, match="company_hq_country"):
        _run(csv_path, config, policy)
    assert not Brand.objects.filter(nickname="dots").exists()


def test_version_family_suffixes_cover_current_and_lookahead(tmp_path: Path):
    csv_path = tmp_path / "brands.csv"
    _write_input(
        csv_path,
        [
            _row(
                keyword_primary="Hy4",
                keyword_aliases="Hy|Hy3|Hy4-preview|Hy5|Hy5-preview",
            )
        ],
    )
    config = tmp_path / "config.yaml"
    config.write_text("enabled_models:\n  - dots\n", encoding="utf-8")
    policy = tmp_path / "harvest_policy.yaml"
    policy.write_text(
        "brands:\n"
        "  dots:\n"
        "    paths: [bare]\n"
        "    tokens: [Hy]\n"
        "    version_family:\n"
        "      prefix: Hy\n"
        "      current_major: 4\n"
        "      lookback: 1\n"
        "      lookahead: 1\n"
        "      extra_suffixes: [-preview]\n",
        encoding="utf-8",
    )

    assert {"hy4-preview", "hy5-preview"} <= _policy_tokens(policy, "dots")
    _run(csv_path, config, policy)
    assert BrandKeyword.objects.filter(brand_id="dots", pattern="Hy5-preview").exists()


def test_skip_search_allows_missing_policy_but_keeps_enabled_model_gate(tmp_path: Path):
    csv_path = tmp_path / "brands.csv"
    _write_input(csv_path, [_row()])
    config = tmp_path / "config.yaml"
    config.write_text("enabled_models:\n  - dots\n", encoding="utf-8")

    _run(csv_path, config, tmp_path / "missing-policy.yaml", skip_search=True)

    assert Brand.objects.filter(nickname="dots").exists()


def test_skip_search_still_requires_enabled_model_membership(tmp_path: Path):
    csv_path = tmp_path / "brands.csv"
    _write_input(csv_path, [_row()])
    config = tmp_path / "config.yaml"
    config.write_text("enabled_models: []\n", encoding="utf-8")

    with pytest.raises(CommandError, match="enabled_models"):
        _run(csv_path, config, tmp_path / "missing-policy.yaml", skip_search=True)
    assert not Brand.objects.filter(nickname="dots").exists()


def test_product_repo_id_supplies_hf_org_when_org_cell_is_blank(tmp_path: Path):
    csv_path = tmp_path / "brands.csv"
    _write_input(
        csv_path,
        [_row(company_nickname="owner", hf_product_repo_ids="owner-org/model")],
    )
    config, policy = _config_and_policy(tmp_path)

    _run(csv_path, config, policy)

    assert HFOrg.objects.filter(namespace="owner-org", company_id="owner").exists()
    assert Product.objects.get(repo_id="owner-org/model").hf_org_id == "owner-org"


def test_unchanged_product_rerun_preserves_updated_at(tmp_path: Path):
    csv_path = tmp_path / "brands.csv"
    _write_input(
        csv_path,
        [
            _row(
                company_nickname="owner",
                hf_orgs="owner-org",
                hf_product_repo_ids="owner-org/model",
            )
        ],
    )
    config, policy = _config_and_policy(tmp_path)

    _run(csv_path, config, policy)
    product = Product.objects.get(repo_id="owner-org/model")
    original_updated_at = product.updated_at

    _run(csv_path, config, policy)
    product.refresh_from_db()

    assert product.updated_at == original_updated_at


def test_hf_org_values_are_normalized_and_deduplicated_after_url_parsing(
    tmp_path: Path,
):
    csv_path = tmp_path / "brands.csv"
    _write_input(
        csv_path,
        [
            _row(
                company_nickname="owner",
                hf_orgs="dots-studio|https://huggingface.co/dots-studio",
            )
        ],
    )

    parsed = read_csv(csv_path)[0]

    assert parsed.hf_orgs == ["dots-studio"]


def test_tracked_upgrade_csv_applies_idempotently_and_keeps_aliases_non_primary(
    seeded_policy_keywords,
):
    """The reviewed rollout input is a complete, repeatable identity load."""
    repo_root = Path(__file__).parents[1]
    csv_path = (
        repo_root
        / "config/brands/2026-08-31-013447-harvester-quality-upgrade.csv"
    )
    config_path = repo_root / "config.yaml"
    policy_path = repo_root / "config/harvest_policy.yaml"

    BrandKeyword.objects.filter(
        brand_id="upstage", pattern__in=("Solar LLM", "업스테이지")
    ).delete()
    first_output = _run(csv_path, config_path, policy_path)
    assert "onboard_brand complete" in first_output

    assert BrandKeyword.objects.get(
        brand_id="dots", pattern="dots3-note"
    ).is_primary
    for brand_id, pattern in (
        ("hunyuan", "Hy4"),
        ("hunyuan", "混元"),
        ("glm", "Ox Alpha"),
        ("upstage", "Solar LLM"),
        ("upstage", "업스테이지"),
    ):
        assert not BrandKeyword.objects.get(
            brand_id=brand_id, pattern=pattern
        ).is_primary

    brand_index = _build_brand_index(list(load_config(config_path).enabled_models))
    assert detect_brand_mentions("Solar LLM by 업스테이지", brand_index) == [
        "upstage"
    ]

    tracked_brands = ("dots", "hunyuan", "glm", "upstage")

    def identity_counts() -> dict[str, int]:
        return {
            "brands": Brand.objects.filter(nickname__in=tracked_brands).count(),
            "brand_companies": BrandCompany.objects.filter(
                brand_id__in=tracked_brands,
                company_id__in=("xiaohongshu", "tencent", "zhipu"),
            ).count(),
            "companies": Company.objects.filter(
                nickname__in=("xiaohongshu", "tencent", "zhipu")
            ).count(),
            "keywords": BrandKeyword.objects.filter(
                brand_id__in=tracked_brands
            ).count(),
            "hf_orgs": HFOrg.objects.filter(
                namespace__in=("dots-studio", "tencent", "zai-org")
            ).count(),
            "products": Product.objects.filter(
                repo_id="dots-studio/dots3-note-prev"
            ).count(),
        }

    snapshot = identity_counts()
    second_output = _run(csv_path, config_path, policy_path)
    assert "unchanged" in second_output
    assert snapshot == identity_counts()
