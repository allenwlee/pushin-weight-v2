"""Contract tests for deterministic classification-analysis documents."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from io import StringIO

import pytest

import core.classification_analysis as analysis
from core.classification_analysis import (
    ANALYSIS_SCHEMA_VERSION,
    AnalysisInputError,
    AnalysisRequest,
    analyze_classifications,
    safe_error_document,
)
from core.management.commands.analyze_classifications import Command

START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 9, 2, tzinfo=UTC)
REAL_RESOLVE_SOURCE_IDENTITY = analysis._resolve_source_identity


def _request(policy: str = "current_definition", **changes) -> AnalysisRequest:
    values = {
        "history_policy": policy,
        "start": START,
        "end": END,
    }
    values.update(changes)
    return AnalysisRequest(**values)


@pytest.fixture(autouse=True)
def _fixed_source_identity(monkeypatch):
    monkeypatch.setattr(
        analysis,
        "_resolve_source_identity",
        lambda: analysis._SourceIdentity("a" * 40, "local_git_head", False),
    )


def _rows() -> list[dict]:
    def row(kind: str, **values):
        result = {
            "row_kind": kind,
            "family": None,
            "key": None,
            "contract_version": None,
            "taxonomy_version": None,
            "prompt_version": None,
            "model": None,
            "outcome": None,
            "count_a": None,
            "count_b": None,
            "count_c": None,
            "min_at": None,
            "max_at": None,
        }
        result.update(values)
        return result

    return [
        row("observation", min_at=START),
        row("exact_summary", count_a=2, count_b=2, count_c=1),
        row(
            "exact_provenance",
            contract_version="stage1-v1",
            taxonomy_version="stage1-taxonomy-v1",
            prompt_version="stage1-prompt-v2",
            model="test-model",
            count_a=1,
            count_b=1,
            count_c=0,
            min_at=START,
            max_at=START,
        ),
        row(
            "exact_provenance",
            contract_version="stage1-v1",
            taxonomy_version="stage1-taxonomy-v2",
            prompt_version="stage1-prompt-v3",
            model="test-model",
            count_a=1,
            count_b=1,
            count_c=1,
            min_at=END,
            max_at=END,
        ),
        row("exact_membership", family="post_type", key="releases_updates", count_a=1),
        row(
            "exact_membership", family="product_label", key="ideas_requests", count_a=1
        ),
        row(
            "provenance_membership",
            family="post_type",
            key="releases_updates",
            contract_version="stage1-v1",
            taxonomy_version="stage1-taxonomy-v1",
            prompt_version="stage1-prompt-v2",
            model="test-model",
            count_a=1,
        ),
        row(
            "invalid_summary",
            count_a=1,
            count_b=1,
        ),
        row(
            "invalid_state",
            contract_version="unknown",
            taxonomy_version="unknown",
            prompt_version="unknown",
            model="unknown",
            outcome="pending",
            count_a=1,
            count_b=1,
            min_at=START,
            max_at=START,
        ),
        row("legacy_summary", count_a=1, count_b=1),
        row(
            "legacy_membership", family="post_type", key="questions_requests", count_a=1
        ),
        row(
            "unversioned_edge_exclusion",
            family="post_type",
            key="opinions_reactions",
            count_a=1,
            count_b=1,
        ),
        row("null_timestamp", count_a=1, count_b=2),
    ]


def test_policies_keep_exact_population_identical_and_isolate_legacy(monkeypatch):
    monkeypatch.setattr(analysis, "_query_rows", lambda _request: _rows())

    current = analyze_classifications(_request())
    historical = analyze_classifications(_request("historical_inclusive"))

    assert current["exact_stage1"] == historical["exact_stage1"]
    assert "legacy_unversioned_approximate" not in current
    assert historical["legacy_unversioned_approximate"]["product_labels"] == {
        "availability": "unavailable"
    }
    assert historical["legacy_unversioned_approximate"]["post_types"] == {
        "total": 1,
        "by_key": {"questions_requests": 1},
    }
    assert current["exclusions"]["legacy_unversioned_omitted"]["post_brand_pairs"] == 1
    assert "legacy_unversioned_omitted" not in historical["exclusions"]


def test_count_units_provenance_and_timestamp_scope_are_explicit(monkeypatch):
    monkeypatch.setattr(analysis, "_query_rows", lambda _request: _rows())

    result = analyze_classifications(_request())

    assert result["query"]["range"] == {
        "start": "2026-09-01T00:00:00Z",
        "end": "2026-09-02T00:00:00Z",
        "interval": "[start,end)",
        "timezone": "UTC",
    }
    assert result["query"]["range_basis"] == "post_created_at"
    assert result["exact_stage1"]["classified_post_brand_denominator"] == 2
    assert result["exact_stage1"]["context_missing_post_brands"] == 1
    assert result["exact_stage1"]["memberships"]["post_types"]["by_key"] == {
        "releases_updates": 1
    }
    provenance = result["exact_stage1"]["by_stored_provenance"][0]
    assert provenance["taxonomy_version"] == "stage1-taxonomy-v1"
    assert provenance["classified_at"]["role"] == "provenance_only"
    assert (
        result["exclusions"]["unrecognized_or_invalid_state"]["post_brand_states"] == 1
    )
    assert result["exclusions"]["null_post_created_at"] == {
        "scope": "brand_scope_all_dates_missing_timestamp",
        "unique_posts": 1,
        "post_brand_pairs": 2,
    }
    assert result["exclusions"]["unversioned_edges_outside_legacy_population"] == [
        {
            "family": "post_type",
            "source_key": "opinions_reactions",
            "unique_posts": 1,
            "post_brand_pairs": 1,
        }
    ]
    assert result["observation"] == {
        "observed_at": "2026-09-01T00:00:00Z",
        "clock": "postgresql_statement_timestamp",
        "database_snapshot_identity": "not_recorded",
    }
    assert "latest state visible at query time" in result["latest_state_limitation"]


def test_result_json_and_query_identity_are_deterministic(monkeypatch):
    monkeypatch.setattr(analysis, "_query_rows", lambda _request: _rows())

    first = analyze_classifications(_request())
    second = analyze_classifications(_request())

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["identity"]["query_identity"].startswith("sha256:")
    assert first["identity"]["source_revision"] == "a" * 40


def test_render_revision_identity_normalizes_without_invoking_git(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", f"  {'A' * 40}\n")
    monkeypatch.setattr(
        analysis, "_resolve_source_identity", REAL_RESOLVE_SOURCE_IDENTITY
    )
    monkeypatch.setattr(
        analysis.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("Git must not run for a Render SHA"),
    )

    assert analysis._resolve_source_identity() == analysis._SourceIdentity(
        "a" * 40, "render_deploy", False
    )


def test_invalid_render_revision_is_explicit_without_invoking_git(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", " not-a-full-sha ")
    monkeypatch.setattr(
        analysis, "_resolve_source_identity", REAL_RESOLVE_SOURCE_IDENTITY
    )
    monkeypatch.setattr(
        analysis.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail(
            "Git must not run for an invalid Render SHA"
        ),
    )
    monkeypatch.setattr(analysis, "_query_rows", lambda _request: _rows())

    result = analyze_classifications(_request())

    assert result["identity"]["source_revision"] == "unavailable"
    assert result["identity"]["source_revision_kind"] == "invalid_render_environment"
    assert result["identity"]["source_worktree_dirty"] is None
    assert {"code": "source_revision_unavailable"} in result["warnings"]


def test_nested_archive_does_not_borrow_parent_repository_identity(
    monkeypatch, tmp_path
):
    repository = tmp_path / "containing-worktree"
    archive = repository / ".context" / "release-a-archive"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    (repository / "tracked.txt").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "tracked.txt"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "-c",
            "user.name=U8 Test",
            "-c",
            "user.email=u8-test@example.invalid",
            "commit",
            "--no-gpg-sign",
            "-q",
            "-m",
            "test fixture",
        ],
        check=True,
    )
    parent_revision = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert analysis._FULL_REVISION.fullmatch(parent_revision)
    archive.mkdir(parents=True)
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    monkeypatch.setattr(analysis.settings, "BASE_DIR", archive)
    monkeypatch.setattr(
        analysis, "_resolve_source_identity", REAL_RESOLVE_SOURCE_IDENTITY
    )

    identity = analysis._resolve_source_identity()

    assert identity == analysis._SourceIdentity(
        "unavailable", "parent_git_repository_ignored", None
    )


def test_valid_empty_query_exits_as_empty_document(monkeypatch):
    monkeypatch.setattr(
        analysis,
        "_query_rows",
        lambda _request: _rows()[:1],
    )

    result = analyze_classifications(_request())

    assert result["status"] == "empty"
    assert result["exact_stage1"]["unique_posts"] == 0


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"history_policy": "implicit"}, "invalid_history_policy"),
        (
            {"schema_version": "classification-analysis/v0"},
            "unsupported_schema_version",
        ),
        ({"start": START.replace(tzinfo=None)}, "invalid_utc_timestamp"),
        ({"start": END}, "invalid_range"),
        ({"brands": ("minimax", "MiniMax")}, "invalid_brand_scope"),
    ],
)
def test_invalid_inputs_are_safe_structured_errors(changes, code):
    with pytest.raises(AnalysisInputError) as caught:
        analyze_classifications(_request(**changes))

    document = safe_error_document(caught.value)
    assert document["schema_version"] == ANALYSIS_SCHEMA_VERSION
    assert document["status"] == "error"
    assert document["error"]["code"] == code
    assert "exact_stage1" not in document


def test_crosswalk_collision_fails_before_query(monkeypatch):
    real_helper = analysis.taxonomy_crosswalk_rows

    def collision(family):
        if family == "post_type":
            return (("buzz_releases", "releases_updates"),) * 2
        return real_helper(family)

    monkeypatch.setattr(analysis, "taxonomy_crosswalk_rows", collision)
    monkeypatch.setattr(
        analysis,
        "_query_rows",
        lambda _request: pytest.fail("query must not run after crosswalk collision"),
    )

    with pytest.raises(AnalysisInputError) as caught:
        analyze_classifications(_request())
    assert caught.value.code == "invalid_taxonomy_crosswalk"


def test_missing_legacy_dashboard_key_fails_before_query(monkeypatch):
    real_helper = analysis.taxonomy_crosswalk_rows
    missing_key = analysis.LEGACY_DASHBOARD_POST_TYPE_KEYS[0]

    def incomplete(family):
        rows = real_helper(family)
        return tuple(row for row in rows if row[0] != missing_key)

    monkeypatch.setattr(analysis, "taxonomy_crosswalk_rows", incomplete)
    monkeypatch.setattr(
        analysis,
        "_query_rows",
        lambda _request: pytest.fail("query must not run with an incomplete crosswalk"),
    )

    with pytest.raises(AnalysisInputError) as caught:
        analyze_classifications(_request())
    assert caught.value.code == "invalid_taxonomy_crosswalk"


def test_command_failure_writes_one_error_document_and_no_partial_stdout():
    stdout = StringIO()
    stderr = StringIO()
    command = Command(stdout=stdout, stderr=stderr)
    with pytest.raises(SystemExit) as caught:
        command.handle(
            history_policy="implicit",
            start="2026-09-01T00:00:00Z",
            end="2026-09-02T00:00:00Z",
            brands=[],
            schema_version=ANALYSIS_SCHEMA_VERSION,
        )

    assert caught.value.code == 2
    assert stdout.getvalue() == ""
    error = json.loads(stderr.getvalue())
    assert error["status"] == "error"
    assert error["error"]["code"] == "invalid_history_policy"
    assert "exact_stage1" not in error


def test_command_parser_errors_are_structured_json(capsys):
    parser = Command().create_parser("manage.py", "analyze_classifications")

    with pytest.raises(SystemExit) as caught:
        parser.parse_args(["--history-policy", "current_definition"])

    assert caught.value.code == 2
    error = json.loads(capsys.readouterr().err)
    assert error["status"] == "error"
    assert error["error"]["code"] == "invalid_arguments"


def test_command_rejects_impossible_calendar_date_as_safe_error():
    stdout = StringIO()
    stderr = StringIO()
    command = Command(stdout=stdout, stderr=stderr)
    with pytest.raises(SystemExit) as caught:
        command.handle(
            history_policy="current_definition",
            start="2026-02-30T00:00:00Z",
            end="2026-03-02T00:00:00Z",
            brands=[],
            schema_version=ANALYSIS_SCHEMA_VERSION,
        )

    assert caught.value.code == 2
    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue())["error"]["code"] == "invalid_utc_timestamp"
