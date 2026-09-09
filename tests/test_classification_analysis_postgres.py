"""PostgreSQL and process-boundary proof for classification analysis."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import pytest
from django.db import connection

from core.classification_analysis import AnalysisRequest, analyze_classifications
from core.classification_contract import (
    CANONICAL_PROMPT_VERSION,
    CANONICAL_TAXONOMY_VERSION,
    CONTRACT_VERSION,
    LEGACY_STAGE1_PROMPT_VERSION,
    LEGACY_STAGE1_TAXONOMY_VERSION,
)
from core.models import (
    Brand,
    Post,
    PostBrand,
    PostBrandClassificationState,
    PostBrandProductLabel,
    PostBrandSignal,
    PostTypeKey,
    ProductLabelKey,
    SentimentKey,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]

START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 9, 2, tzinfo=UTC)
REPO_ROOT = Path(__file__).resolve().parents[1]


def _post(tweet_id: str, created_at: datetime | None) -> Post:
    return Post.objects.create(tweet_id=tweet_id, text=tweet_id, created_at=created_at)


def _pair(post: Post, brand: Brand) -> None:
    PostBrand.objects.create(post=post, brand=brand)


def _state(
    post: Post,
    brand: Brand,
    *,
    taxonomy: str,
    prompt: str,
    outcome: str = "classified",
    contract: str = CONTRACT_VERSION,
    classified_at: datetime,
) -> None:
    state = PostBrandClassificationState.objects.create(
        post=post,
        brand=brand,
        contract_version=contract,
        taxonomy_version=taxonomy,
        prompt_version=prompt,
        model="u8-postgres-proof",
        input_context_fingerprint=(post.tweet_id + brand.nickname).ljust(64, "0")[:64],
        outcome=outcome,
        sentiment_id="neutral" if outcome == "classified" else None,
    )
    PostBrandClassificationState.objects.filter(pk=state.pk).update(
        classified_at=classified_at
    )


def _signal(post: Post, brand: Brand, key: str) -> None:
    PostBrandSignal.objects.create(
        post=post,
        brand=brand,
        post_type_id=key,
        sentiment_id="neutral",
    )


def _product(post: Post, brand: Brand, key: str) -> None:
    PostBrandProductLabel.objects.create(
        post=post,
        brand=brand,
        product_label_id=key,
    )


def _seed_analysis_matrix() -> None:
    SentimentKey.objects.get_or_create(key="neutral")
    for key in (
        "buzz_releases",
        "releases_updates",
        "hands_on_usage",
        "opinions_reactions",
        "u8-unknown-exact",
    ):
        PostTypeKey.objects.get_or_create(key=key)
    for key in ("product_request", "ideas_requests", "bug"):
        ProductLabelKey.objects.get_or_create(key=key)

    alpha = Brand.objects.create(nickname="u8-alpha", display_name="U8 Alpha")
    beta = Brand.objects.create(nickname="u8-beta", display_name="U8 Beta")

    collision = _post("u8-at-start", START)
    for brand in (alpha, beta):
        _pair(collision, brand)
    _state(
        collision,
        alpha,
        taxonomy=LEGACY_STAGE1_TAXONOMY_VERSION,
        prompt=LEGACY_STAGE1_PROMPT_VERSION,
        classified_at=END + timedelta(hours=1),
    )
    _state(
        collision,
        beta,
        taxonomy=CANONICAL_TAXONOMY_VERSION,
        prompt=CANONICAL_PROMPT_VERSION,
        classified_at=END + timedelta(hours=2),
    )
    for key in ("buzz_releases", "releases_updates"):
        _signal(collision, alpha, key)
    _signal(collision, beta, "releases_updates")
    for key in ("product_request", "ideas_requests"):
        _product(collision, alpha, key)

    missing = _post("u8-context-missing", START + timedelta(hours=1))
    _pair(missing, alpha)
    _state(
        missing,
        alpha,
        taxonomy=CANONICAL_TAXONOMY_VERSION,
        prompt=CANONICAL_PROMPT_VERSION,
        outcome="context_missing",
        classified_at=END + timedelta(hours=3),
    )

    invalid = _post("u8-invalid-state", START + timedelta(hours=2))
    _pair(invalid, alpha)
    _state(
        invalid,
        alpha,
        taxonomy=LEGACY_STAGE1_TAXONOMY_VERSION,
        prompt=LEGACY_STAGE1_PROMPT_VERSION,
        contract="unsupported-stage1-contract",
        classified_at=END + timedelta(hours=4),
    )
    _signal(invalid, alpha, "buzz_releases")

    unknown_taxonomy = _post("u8-unknown-taxonomy", START + timedelta(hours=2, minutes=10))
    _pair(unknown_taxonomy, alpha)
    _state(
        unknown_taxonomy,
        alpha,
        taxonomy="unsupported-stage1-taxonomy",
        prompt=CANONICAL_PROMPT_VERSION,
        classified_at=END + timedelta(hours=5),
    )
    _signal(unknown_taxonomy, alpha, "buzz_releases")

    invalid_outcome = _post("u8-invalid-outcome", START + timedelta(hours=2, minutes=20))
    _pair(invalid_outcome, alpha)
    _state(
        invalid_outcome,
        alpha,
        taxonomy=CANONICAL_TAXONOMY_VERSION,
        prompt=CANONICAL_PROMPT_VERSION,
        outcome="pending",
        classified_at=END + timedelta(hours=6),
    )
    _signal(invalid_outcome, alpha, "buzz_releases")

    unknown_edge = _post("u8-unknown-exact-edge", START + timedelta(hours=2, minutes=30))
    _pair(unknown_edge, alpha)
    _state(
        unknown_edge,
        alpha,
        taxonomy=CANONICAL_TAXONOMY_VERSION,
        prompt=CANONICAL_PROMPT_VERSION,
        classified_at=END + timedelta(hours=7),
    )
    _signal(unknown_edge, alpha, "u8-unknown-exact")

    legacy = _post("u8-unversioned", START + timedelta(hours=3))
    _pair(legacy, alpha)
    _signal(legacy, alpha, "buzz_releases")
    _signal(legacy, alpha, "hands_on_usage")
    _signal(legacy, alpha, "opinions_reactions")
    _product(legacy, alpha, "bug")

    for tweet_id, created_at in (
        ("u8-before-start", START - timedelta(microseconds=1)),
        ("u8-at-end", END),
    ):
        outside = _post(tweet_id, created_at)
        _pair(outside, alpha)
        _state(
            outside,
            alpha,
            taxonomy=CANONICAL_TAXONOMY_VERSION,
            prompt=CANONICAL_PROMPT_VERSION,
            classified_at=END + timedelta(hours=8),
        )
        _signal(outside, alpha, "releases_updates")

    no_timestamp = _post("u8-null-created-at", None)
    _pair(no_timestamp, alpha)
    _pair(no_timestamp, beta)


def _request(policy: str) -> AnalysisRequest:
    return AnalysisRequest(history_policy=policy, start=START, end=END)


def test_postgres_population_boundaries_units_dedup_and_history_policy() -> None:
    _seed_analysis_matrix()

    observation_lower_bound = datetime.now(UTC)
    current = analyze_classifications(_request("current_definition"))
    observation_upper_bound = datetime.now(UTC)
    historical = analyze_classifications(_request("historical_inclusive"))

    assert current["exact_stage1"] == historical["exact_stage1"]
    exact = current["exact_stage1"]
    assert exact["unique_posts"] == 3
    assert exact["classified_post_brand_denominator"] == 3
    assert exact["context_missing_post_brands"] == 1
    assert exact["memberships"]["post_types"] == {
        "total": 2,
        "by_key": {"releases_updates": 2},
    }
    assert exact["memberships"]["product_labels"] == {
        "total": 1,
        "by_key": {"ideas_requests": 1},
    }

    exclusions = current["exclusions"]
    assert exclusions["unrecognized_or_invalid_state"]["unique_posts"] == 3
    assert exclusions["unrecognized_or_invalid_state"]["post_brand_states"] == 3
    assert exclusions["unknown_edge_keys"] == [
        {
            "family": "post_type",
            "source_key": "u8-unknown-exact",
            "unique_posts": 1,
            "post_brand_pairs": 1,
        }
    ]
    assert exclusions["legacy_unversioned_omitted"]["unique_posts"] == 1
    assert exclusions["legacy_unversioned_omitted"]["post_brand_pairs"] == 1
    assert exclusions["null_post_created_at"] == {
        "scope": "brand_scope_all_dates_missing_timestamp",
        "unique_posts": 1,
        "post_brand_pairs": 2,
    }
    assert exclusions["unversioned_edges_outside_legacy_population"] == [
        {
            "family": "post_type",
            "source_key": "opinions_reactions",
            "unique_posts": 1,
            "post_brand_pairs": 1,
        },
        {
            "family": "product_label",
            "source_key": "bug",
            "unique_posts": 1,
            "post_brand_pairs": 1,
        },
    ]

    legacy = historical["legacy_unversioned_approximate"]
    assert legacy["unique_posts"] == 1
    assert legacy["approximate_post_brand_pairs"] == 1
    assert legacy["post_types"] == {
        "total": 2,
        "by_key": {"hands_on_usage": 1, "releases_updates": 1},
    }
    assert legacy["product_labels"] == {"availability": "unavailable"}
    assert "legacy_unversioned_omitted" not in historical["exclusions"]

    provenance = exact["by_stored_provenance"]
    assert provenance == [
        {
            "contract_version": CONTRACT_VERSION,
            "taxonomy_version": LEGACY_STAGE1_TAXONOMY_VERSION,
            "prompt_version": LEGACY_STAGE1_PROMPT_VERSION,
            "model": "u8-postgres-proof",
            "unique_posts": 1,
            "classified_post_brands": 1,
            "context_missing_post_brands": 0,
            "memberships": {
                "post_types": {"total": 1, "by_key": {"releases_updates": 1}},
                "product_labels": {"total": 1, "by_key": {"ideas_requests": 1}},
            },
            "classified_at": {
                "min": "2026-09-02T01:00:00Z",
                "max": "2026-09-02T01:00:00Z",
                "role": "provenance_only",
            },
        },
        {
            "contract_version": CONTRACT_VERSION,
            "taxonomy_version": CANONICAL_TAXONOMY_VERSION,
            "prompt_version": CANONICAL_PROMPT_VERSION,
            "model": "u8-postgres-proof",
            "unique_posts": 3,
            "classified_post_brands": 2,
            "context_missing_post_brands": 1,
            "memberships": {
                "post_types": {"total": 1, "by_key": {"releases_updates": 1}},
                "product_labels": {"total": 0, "by_key": {}},
            },
            "classified_at": {
                "min": "2026-09-02T02:00:00Z",
                "max": "2026-09-02T07:00:00Z",
                "role": "provenance_only",
            },
        },
    ]
    assert exclusions["unrecognized_or_invalid_state"]["by_stored_provenance"] == [
        {
            "contract_version": CONTRACT_VERSION,
            "taxonomy_version": CANONICAL_TAXONOMY_VERSION,
            "prompt_version": CANONICAL_PROMPT_VERSION,
            "model": "u8-postgres-proof",
            "outcome": "pending",
            "unique_posts": 1,
            "post_brand_states": 1,
            "classified_at_min": "2026-09-02T06:00:00Z",
            "classified_at_max": "2026-09-02T06:00:00Z",
        },
        {
            "contract_version": CONTRACT_VERSION,
            "taxonomy_version": "unsupported-stage1-taxonomy",
            "prompt_version": CANONICAL_PROMPT_VERSION,
            "model": "u8-postgres-proof",
            "outcome": "classified",
            "unique_posts": 1,
            "post_brand_states": 1,
            "classified_at_min": "2026-09-02T05:00:00Z",
            "classified_at_max": "2026-09-02T05:00:00Z",
        },
        {
            "contract_version": "unsupported-stage1-contract",
            "taxonomy_version": LEGACY_STAGE1_TAXONOMY_VERSION,
            "prompt_version": LEGACY_STAGE1_PROMPT_VERSION,
            "model": "u8-postgres-proof",
            "outcome": "classified",
            "unique_posts": 1,
            "post_brand_states": 1,
            "classified_at_min": "2026-09-02T04:00:00Z",
            "classified_at_max": "2026-09-02T04:00:00Z",
        },
    ]
    observed_at = datetime.fromisoformat(current["observation"]["observed_at"])
    assert observation_lower_bound <= observed_at <= observation_upper_bound
    assert current["observation"]["clock"] == "postgresql_statement_timestamp"

    scoped = analyze_classifications(
        AnalysisRequest(
            history_policy="current_definition",
            start=START,
            end=END,
            brands=("u8-beta",),
        )
    )
    assert scoped["query"]["brands"] == ["u8-beta"]
    assert scoped["exact_stage1"]["unique_posts"] == 1
    assert scoped["exact_stage1"]["classified_post_brand_denominator"] == 1
    assert scoped["exact_stage1"]["context_missing_post_brands"] == 0
    assert scoped["exact_stage1"]["memberships"]["post_types"] == {
        "total": 1,
        "by_key": {"releases_updates": 1},
    }
    assert scoped["exclusions"]["null_post_created_at"]["post_brand_pairs"] == 1


def _database_url_for_name(name: str) -> str:
    configured = urlsplit(os.environ["DATABASE_URL"])
    return urlunsplit(
        (
            configured.scheme,
            configured.netloc,
            "/" + quote(name, safe=""),
            configured.query,
            configured.fragment,
        )
    )


def _dotenv_free_settings(tmp_path: Path) -> tuple[str, Path]:
    module_name = "u8_subprocess_settings_" + uuid.uuid4().hex
    module_path = tmp_path / f"{module_name}.py"
    module_path.write_text(
        "import environ\n"
        "environ.Env.read_env = classmethod(lambda cls, *args, **kwargs: None)\n"
        "from project.settings import *\n",
        encoding="utf-8",
    )
    return module_name, module_path.parent


def _minimal_subprocess_env(
    tmp_path: Path, *, database_url: str
) -> dict[str, str]:
    module_name, module_dir = _dotenv_free_settings(tmp_path)
    return {
        "PATH": os.environ["PATH"],
        "HOME": os.environ["HOME"],
        "PYTHONPATH": os.pathsep.join((str(module_dir), str(REPO_ROOT))),
        "DJANGO_SETTINGS_MODULE": module_name,
        "DJANGO_SECRET_KEY": "u8-subprocess-test-only",
        "DATABASE_URL": database_url,
        "DEBUG": "0",
        "OLLIJA_STAGING_MODE": "0",
    }


def _run_command(tmp_path: Path, *arguments: str, database_url: str):
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "manage.py"), *arguments],
        cwd=REPO_ROOT,
        env=_minimal_subprocess_env(tmp_path, database_url=database_url),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_management_process_success_empty_and_invalid_arguments(tmp_path: Path) -> None:
    database_url = _database_url_for_name(connection.settings_dict["NAME"])
    success = _run_command(
        tmp_path,
        "analyze_classifications",
        "--history-policy",
        "current_definition",
        "--start",
        "2030-01-01T00:00:00Z",
        "--end",
        "2030-01-02T00:00:00Z",
        database_url=database_url,
    )

    assert success.returncode == 0
    assert success.stderr == ""
    document = json.loads(success.stdout)
    assert document["status"] == "empty"
    expected_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert document["identity"]["source_revision_kind"] == "local_git_head"
    assert document["identity"]["source_revision"] == expected_head

    invalid = _run_command(
        tmp_path,
        "analyze_classifications",
        "--history-policy",
        "current_definition",
        "--start",
        "2030-01-01T00:00:00Z",
        database_url=database_url,
    )
    assert invalid.returncode == 2
    assert invalid.stdout == ""
    error = json.loads(invalid.stderr)
    assert error["status"] == "error"
    assert error["error"]["code"] == "invalid_arguments"


def test_management_process_database_failure_is_atomic_json(tmp_path: Path) -> None:
    missing_database_url = _database_url_for_name("u8_missing_" + uuid.uuid4().hex)
    failed = _run_command(
        tmp_path,
        "analyze_classifications",
        "--history-policy",
        "current_definition",
        "--start",
        "2030-01-01T00:00:00Z",
        "--end",
        "2030-01-02T00:00:00Z",
        database_url=missing_database_url,
    )

    assert failed.returncode == 3
    assert failed.stdout == ""
    error = json.loads(failed.stderr)
    assert error["status"] == "error"
    assert error["error"]["code"] == "analysis_query_failed"
    assert "exact_stage1" not in error
