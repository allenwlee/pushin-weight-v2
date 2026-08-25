"""Contract tests for the read-only latest-N harvester health skill."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).parents[1]
    / ".claude/skills/harvester-latest-n-health-check/scripts/check.py"
)
SKILL_PATH = SCRIPT_PATH.parents[1] / "SKILL.md"
OPENAI_YAML_PATH = SCRIPT_PATH.parents[1] / "agents/openai.yaml"
CHANGE_HARVESTER_SKILL_PATH = (
    Path(__file__).parents[1] / ".claude/skills/change-harvester/SKILL.md"
)


def _load_checker():
    spec = importlib.util.spec_from_file_location("harvester_health_check", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load harvester health-check helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def checker():
    return _load_checker()


def _post(**overrides):
    row = {
        "tweet_id": "100",
        "fetched_at": "2026-08-25T00:00:00+00:00",
        "age_seconds": 60,
        "has_text": True,
        "has_lang_detected": True,
        "has_text_en": True,
        "has_text_zh_cn": True,
        "translation_status": "succeeded",
        "translation_error_code": "",
        "classification_status": "succeeded",
        "classification_error_code": "",
        "brands": [
            {
                "brand_id": "minimax",
                "signals": [{"post_type": "announcement", "sentiment": "positive"}],
                "discourses": [{"discourse": "genuine_hype", "act_id": 0}],
            }
        ],
    }
    row.update(overrides)
    return row


def _snapshot(*posts, read_only="on"):
    return {"transaction_read_only": read_only, "posts": list(posts)}


def test_cli_defaults_to_latest_twenty_and_rejects_out_of_range(checker):
    assert checker.parse_args([]).latest == 20
    assert checker.parse_args(["--latest", "1"]).latest == 1
    assert checker.parse_args(["--latest", "200"]).latest == 200

    for invalid in ("0", "201"):
        with pytest.raises(checker.HealthCheckError) as exc_info:
            checker.parse_args(["--latest", invalid])
        assert exc_info.value.code == "invalid_arguments"


def test_cli_accepts_ordered_exact_ids_and_rejects_unsafe_values(checker):
    args = checker.parse_args(["--tweet-id", "200", "--tweet-id", "100"])
    assert args.latest is None
    assert args.tweet_ids == ["200", "100"]

    for invalid in ("abc", "1); DROP TABLE posts; --"):
        with pytest.raises(checker.HealthCheckError) as exc_info:
            checker.parse_args(["--tweet-id", invalid])
        assert exc_info.value.code == "invalid_arguments"


def test_query_is_bounded_before_joins_and_declares_read_only_mode(checker):
    sql = checker.build_query(latest=20, tweet_ids=None)

    assert "BEGIN TRANSACTION READ ONLY" in sql
    assert "statement_timeout" in sql
    assert "lock_timeout" in sql
    assert "current_setting('transaction_read_only')" in sql
    assert "ORDER BY p.fetched_at DESC, p.tweet_id DESC" in sql
    assert "LIMIT 20" in sql
    assert "CURRENT_TIMESTAMP - es.created_at" in sql
    assert "CURRENT_TIMESTAMP - p.fetched_at" not in sql
    assert sql.index("LIMIT 20") < sql.index("posts_brands")

    command = checker.build_command(sql)
    assert command[:3] == ["render", "psql", "pushinweight-db-shadow"]
    assert command.count(sql) == 1
    assert "--no-align" in command
    assert "--tuples-only" in command
    assert "ON_ERROR_STOP=1" in " ".join(command)


def test_exact_query_uses_validated_ids_in_requested_order(checker):
    sql = checker.build_query(latest=None, tweet_ids=["200", "100"])

    assert "('200', 0)" in sql
    assert "('100', 1)" in sql
    assert sql.index("('200', 0)") < sql.index("('100', 1)")
    assert "JOIN selected_ids" in sql


def test_complete_and_fresh_pending_rows_exit_zero_with_distinct_counts(checker):
    pending = _post(
        tweet_id="101",
        translation_status="pending",
        classification_status="pending",
        has_lang_detected=False,
        has_text_en=False,
        has_text_zh_cn=False,
        brands=[{"brand_id": "glm", "signals": [], "discourses": []}],
    )

    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(_post(), pending),
        latest=20,
        requested_ids=None,
        grace_hours=24,
    )

    assert exit_code == 0
    assert payload["status"] == "healthy_with_pending"
    assert payload["regression_gate"] == "inconclusive"
    assert payload["summary"] == {
        "total": 2,
        "complete": 1,
        "pending": 1,
        "unhealthy": 0,
    }
    assert payload["cohort_tweet_ids"] == ["100", "101"]
    assert payload["posts"][1]["state"] == "pending"
    assert payload["posts"][1]["reasons"] == []


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("has_lang_detected", "missing_lang_detected"),
        ("has_text_en", "missing_text_en"),
        ("has_text_zh_cn", "missing_text_zh_cn"),
    ],
)
def test_succeeded_translation_requires_each_persisted_fact(checker, field, reason):
    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(_post(**{field: False})),
        latest=20,
        requested_ids=None,
        grace_hours=24,
    )

    assert exit_code == 1
    assert payload["posts"][0]["reasons"] == [
        {"stage": "translation", "reason": reason}
    ]


@pytest.mark.parametrize(
    ("brands", "reason"),
    [
        ([], "missing_brand"),
        (
            [{"brand_id": "minimax", "signals": [], "discourses": [{}]}],
            "missing_signal",
        ),
        (
            [
                {
                    "brand_id": "minimax",
                    "signals": [{"post_type": "", "sentiment": "positive"}],
                    "discourses": [{}],
                }
            ],
            "missing_post_type",
        ),
        (
            [
                {
                    "brand_id": "minimax",
                    "signals": [{"post_type": "announcement", "sentiment": ""}],
                    "discourses": [{}],
                }
            ],
            "missing_sentiment",
        ),
        (
            [
                {
                    "brand_id": "minimax",
                    "signals": [{"post_type": "announcement", "sentiment": "positive"}],
                    "discourses": [],
                }
            ],
            "missing_discourse",
        ),
    ],
)
def test_succeeded_classification_requires_per_brand_facts(checker, brands, reason):
    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(_post(brands=brands)),
        latest=20,
        requested_ids=None,
        grace_hours=24,
    )

    assert exit_code == 1
    assert payload["posts"][0]["reasons"][0]["reason"] == reason


def test_failed_and_overdue_stages_are_unhealthy(checker):
    failed = _post(
        translation_status="failed",
        translation_error_code="translation_incomplete",
    )
    overdue = _post(
        tweet_id="101",
        age_seconds=24 * 60 * 60 + 1,
        classification_status="pending",
    )

    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(failed, overdue),
        latest=20,
        requested_ids=None,
        grace_hours=24,
    )

    assert exit_code == 1
    assert payload["posts"][0]["reasons"] == [
        {
            "stage": "translation",
            "reason": "failed",
            "error_code": "translation_incomplete",
        }
    ]
    assert {r["reason"] for r in payload["posts"][1]["reasons"]} == {"pending_overdue"}


def test_missing_enrichment_state_and_invalid_status_are_unhealthy(checker):
    missing_state = _post(
        translation_status=None,
        classification_status=None,
    )
    invalid_status = _post(
        tweet_id="101",
        translation_status="complete",
    )

    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(missing_state, invalid_status),
        latest=20,
        requested_ids=None,
        grace_hours=24,
    )

    assert exit_code == 1
    assert payload["posts"][0]["reasons"] == [
        {"stage": "persistence", "reason": "missing_enrichment_state"}
    ]
    assert payload["posts"][1]["reasons"] == [
        {"stage": "translation", "reason": "invalid_status"}
    ]


def test_exact_cohort_reports_requested_ids_missing_from_database(checker):
    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(_post(tweet_id="200")),
        latest=None,
        requested_ids=["200", "100"],
        grace_hours=24,
    )

    assert exit_code == 1
    assert payload["cohort_tweet_ids"] == ["200", "100"]
    assert payload["returned_tweet_ids"] == ["200"]
    assert payload["missing_tweet_ids"] == ["100"]
    assert payload["posts"][1] == {
        "tweet_id": "100",
        "state": "unhealthy",
        "translation_status": "missing",
        "classification_status": "missing",
        "brand_count": 0,
        "reasons": [{"stage": "persistence", "reason": "missing_post"}],
    }


def test_empty_snapshot_and_read_write_transaction_are_unhealthy(checker):
    empty, empty_code = checker.evaluate_snapshot(
        _snapshot(), latest=20, requested_ids=None, grace_hours=24
    )
    writable, writable_code = checker.evaluate_snapshot(
        _snapshot(_post(), read_only="off"),
        latest=20,
        requested_ids=None,
        grace_hours=24,
    )

    assert empty_code == 1
    assert empty["summary"]["total"] == 0
    assert writable_code == 2
    assert writable["error"] == {"class": "query", "code": "transaction_not_read_only"}


def test_render_failure_is_sanitized_and_never_retried(checker):
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="password=secret SELECT * FROM private_schema at /tmp/private.py",
        )

    stdout = StringIO()
    stderr = StringIO()
    exit_code = checker.main(["--json"], runner=runner, stdout=stdout, stderr=stderr)

    assert exit_code == 2
    assert len(calls) == 1
    assert json.loads(stdout.getvalue())["error"] == {
        "class": "transport",
        "code": "render_command_failed",
    }
    combined = stdout.getvalue() + stderr.getvalue()
    for secret in ("password", "secret", "SELECT", "private_schema", "/tmp"):
        assert secret not in combined


@pytest.mark.parametrize(
    ("stdout_text", "expected_code"),
    [
        ("", "render_output_invalid"),
        ("BEGIN\nnot-json\nCOMMIT\n", "render_output_invalid"),
    ],
)
def test_invalid_render_output_uses_stable_error(checker, stdout_text, expected_code):
    def runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=stdout_text, stderr="")

    stdout = StringIO()
    exit_code = checker.main(
        ["--json"], runner=runner, stdout=stdout, stderr=StringIO()
    )

    assert exit_code == 2
    assert json.loads(stdout.getvalue())["error"]["code"] == expected_code


def test_render_timeout_and_invalid_config_use_stable_errors(checker, monkeypatch):
    def timeout_runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    timeout_output = StringIO()
    assert (
        checker.main(
            ["--json"],
            runner=timeout_runner,
            stdout=timeout_output,
            stderr=StringIO(),
        )
        == 2
    )
    assert json.loads(timeout_output.getvalue())["error"] == {
        "class": "transport",
        "code": "render_timeout",
    }

    monkeypatch.setattr(checker.Path, "read_text", lambda _path: "harvest: {}")
    with pytest.raises(checker.HealthCheckError) as exc_info:
        checker.load_grace_hours()
    assert exc_info.value.code == "config_invalid"


def test_operator_grace_override_cannot_loosen_configured_policy(checker, monkeypatch):
    monkeypatch.setattr(checker, "load_grace_hours", lambda: 24)
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    stdout = StringIO()
    assert (
        checker.main(
            ["--grace-hours", "25", "--json"],
            runner=runner,
            stdout=stdout,
            stderr=StringIO(),
        )
        == 2
    )
    assert calls == []
    assert json.loads(stdout.getvalue())["error"] == {
        "class": "invocation",
        "code": "invalid_arguments",
    }


def test_human_and_json_output_never_include_source_text(checker):
    source_text = "private full post body"
    snapshot_json = json.dumps(_snapshot(_post()))

    def runner(command, **kwargs):
        assert source_text not in " ".join(command)
        return subprocess.CompletedProcess(command, 0, stdout=snapshot_json, stderr="")

    for argv in ([], ["--json"]):
        stdout = StringIO()
        assert checker.main(argv, runner=runner, stdout=stdout, stderr=StringIO()) == 0
        assert source_text not in stdout.getvalue()
        assert "tweet_id" in stdout.getvalue() or "tweet=100" in stdout.getvalue()
        if not argv:
            assert "mode=latest" in stdout.getvalue()
            assert "grace_hours=24" in stdout.getvalue()


def test_skill_is_discoverable_and_metadata_matches():
    import yaml

    skill_text = SKILL_PATH.read_text()
    frontmatter = skill_text.split("---", 2)[1]
    metadata = yaml.safe_load(frontmatter)
    openai_metadata = yaml.safe_load(OPENAI_YAML_PATH.read_text())

    assert metadata["name"] == "harvester-latest-n-health-check"
    assert "Use when" in metadata["description"]
    for trigger in (
        "latest production posts",
        "post-fetch health",
        "enrichment verification",
    ):
        assert trigger in metadata["description"]
    assert openai_metadata["interface"]["display_name"] == (
        "Harvester Latest-N Health Check"
    )
    assert (
        "$harvester-latest-n-health-check"
        in openai_metadata["interface"]["default_prompt"]
    )


def test_skill_defines_immediate_and_exact_cohort_routes():
    skill_text = SKILL_PATH.read_text()

    for required in (
        "--latest 20 --json",
        "--tweet-id",
        "30 minutes",
        "regression_gate=complete",
        "regression_gate=inconclusive",
        "literal latest cohort",
        "exact cohort",
    ):
        assert required in skill_text
    for safety_rule in (
        "Never run harvesting",
        "Never call TwitterAPI",
        "Never invoke an LLM",
        "Never mutate production",
        "Do not halt the harvest cron",
        "Do not retry",
    ):
        assert safety_rule in skill_text


def test_documented_helper_resolves_outside_the_repository(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--latest" in result.stdout
    assert "--tweet-id" in result.stdout


def test_change_harvester_routes_to_latest_n_health_check():
    text = CHANGE_HARVESTER_SKILL_PATH.read_text()
    section = text.split("## Persisted latest-N health verification", 1)[1].split(
        "\n## ", 1
    )[0]

    assert "$harvester-latest-n-health-check" in section
    assert "immediate route" in section
    assert "enrichment-relevant route" in section
    assert "30-minute" in section
    assert "exact cohort" in section
    for relevant_path in (
        "monitor/cycle.py",
        "core/models.py",
        "x_monitor/translator.py",
        "x_monitor/attribution.py",
        "x_monitor/reattribute.py",
        "config.yaml",
        "x_monitor/config.py",
        "render.yaml",
    ):
        assert relevant_path in section


def test_change_harvester_health_route_preserves_existing_guardrails():
    text = CHANGE_HARVESTER_SKILL_PATH.read_text()
    section = text.split("## Persisted latest-N health verification", 1)[1].split(
        "\n## ", 1
    )[0]

    for rule in (
        "does not authorize a cron halt",
        "does not authorize a harvest run",
        "does not authorize provider calls",
        "does not authorize production mutation",
        "avoiding-recurring-mistakes/SKILL.md",
    ):
        assert rule in section
