"""Contract tests for the read-only latest-N harvester health skill."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime
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
        "lang_detected": "en",
        "has_text": True,
        "has_lang_detected": True,
        "has_text_en": True,
        "has_text_zh_cn": True,
        "has_commentary_en": True,
        "has_commentary_zh_cn": True,
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


def _snapshot(*posts, read_only="on", schema_profile=None):
    snapshot = {"transaction_read_only": read_only, "posts": list(posts)}
    if schema_profile is not None:
        snapshot["schema_profile"] = schema_profile
    return snapshot


def test_current_language_validator_accepts_vietnamese(checker):
    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(_post(lang_detected="vi")), latest=1,
        requested_ids=None, grace_hours=24,
    )
    assert exit_code == 0
    assert payload["acceptance"]["lang_detected_present"]["numerator"] == 1


def test_literal_v2_requires_current_artifact_instead_of_eager_commentary(checker):
    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(_literal_post()), latest=1, requested_ids=None, grace_hours=24,
        translation_contract="literal-v2",
    )
    assert exit_code == 0
    assert payload["posts"][0]["synthesis_status"] == "not_requested"
    assert payload["acceptance"]["literal_artifact_complete"]["numerator"] == 1
    assert payload["acceptance"]["requested_synthesis_complete"]["denominator"] == 0
    assert payload["posts"][0]["synthesis_complete"] is False


def _literal_post():
    from monitor.post_artifacts import source_text_fingerprint

    return _post(
        has_commentary_en=False, has_commentary_zh_cn=False,
        artifact_source={
            "text": 'Source 中文 & <tag> "quote"\nline', "stored_quote": "引用",
            "local_parent": "Parent context", "text_en": "English literal",
            "text_zh_cn": "中文翻译",
        },
        literal_artifact={
            "id": 1, "state": "succeeded", "is_current": True,
            "source_content_fingerprint": source_text_fingerprint('Source 中文 & <tag> "quote"\nline'),
            "source_language": "en",
            "texts": {"en": "English literal", "zh-cn": "中文翻译", "ja": "日本語訳"},
        },
        synthesis_demand=None, synthesis_artifact=None,
    )


def _requested_synthesis_post(state="succeeded"):
    from types import SimpleNamespace

    from monitor.post_artifacts import synthesis_context_fingerprint

    row = _literal_post()
    source = row["artifact_source"]
    fingerprint = synthesis_context_fingerprint(
        SimpleNamespace(text=source["text"], quoted_text=source["stored_quote"]),
        parent_text=source["local_parent"],
    )
    identity = {
        "input_context_fingerprint": fingerprint, "prompt_version": "synthesis-v1",
        "model": "test", "output_schema_version": "v1",
    }
    row["synthesis_demand"] = {
        **identity, "id": 1, "state": state, "artifact_id": 2 if state == "succeeded" else None,
        "age_seconds": 60, "expired": False,
    }
    if state == "succeeded":
        row["synthesis_artifact"] = {
            **identity, "id": 2, "state": "succeeded", "is_current": True,
            "texts": {"en": "Useful context", "zh-cn": "有用的背景", "ja": "役立つ背景"},
            "demand": dict(row["synthesis_demand"]),
        }
    return row


@pytest.mark.parametrize("defect", [
    "missing", "stale_source", "noncurrent", "failed", "missing_locale", "blank_locale",
    "invalid_language",
])
def test_literal_v2_rejects_broken_artifact_despite_populated_compatibility_columns(checker, defect):
    row = _literal_post()
    row.update(has_commentary_en=True, has_commentary_zh_cn=True)
    artifact = row["literal_artifact"]
    if defect == "missing":
        row["literal_artifact"] = None
    elif defect == "stale_source":
        row["artifact_source"]["text"] += " edited"
    elif defect == "noncurrent":
        artifact["is_current"] = False
    elif defect == "failed":
        artifact["state"] = "failed"
    elif defect == "missing_locale":
        artifact["texts"].pop("ja")
    elif defect == "blank_locale":
        artifact["texts"]["ja"] = " \n "
    else:
        artifact["source_language"] = "not-a-language"
    payload, code = checker.evaluate_snapshot(
        _snapshot(row), latest=1, requested_ids=None, grace_hours=24,
        translation_contract="literal-v2",
    )
    assert code == 1
    assert payload["posts"][0]["state"] == "unhealthy"
    assert payload["acceptance"]["literal_artifact_complete"]["numerator"] == 0


@pytest.mark.parametrize(("state", "status", "denominator", "complete", "code"), [
    ("pending", "pending", 1, False, 1),
    ("processing", "processing", 1, False, 1),
    ("cancelled", "cancelled", 0, False, 0),
    ("failed", "failed", 1, False, 1),
    ("succeeded", "complete", 1, True, 0),
])
def test_literal_v2_synthesis_reports_actual_requested_work(checker, state, status, denominator, complete, code):
    payload, observed_code = checker.evaluate_snapshot(
        _snapshot(_requested_synthesis_post(state)), latest=1, requested_ids=None,
        grace_hours=24, translation_contract="literal-v2",
    )
    assert observed_code == code
    assert payload["posts"][0]["synthesis_status"] == status
    assert payload["posts"][0]["synthesis_complete"] is complete
    metric = payload["acceptance"]["requested_synthesis_complete"]
    assert metric["denominator"] == denominator
    assert metric["numerator"] == int(complete)
    if state in {"pending", "processing"}:
        assert payload["status"] == "healthy_with_pending"
        assert payload["regression_gate"] == "inconclusive"


@pytest.mark.parametrize("state", ["pending", "cancelled"])
def test_literal_v2_previous_published_synthesis_does_not_fail_new_demand(checker, state):
    row = _requested_synthesis_post()
    row["synthesis_artifact"]["demand"] = dict(row["synthesis_demand"])
    row["synthesis_demand"].update(
        id=10, state=state, prompt_version="synthesis-v2", artifact_id=None,
    )
    payload, code = checker.evaluate_snapshot(
        _snapshot(row), latest=1, requested_ids=None, grace_hours=24,
        translation_contract="literal-v2",
    )
    assert code == (1 if state == "pending" else 0)
    assert payload["posts"][0]["synthesis_status"] == state
    assert payload["posts"][0]["reasons"] == []
    assert payload["posts"][0]["synthesis_complete"] is False
    assert payload["posts"][0]["synthesis_published_complete"] is True
    metric = payload["acceptance"]["requested_synthesis_complete"]
    assert metric["numerator"] == 0
    assert metric["denominator"] == (1 if state == "pending" else 0)


@pytest.mark.parametrize("defect", [
    "missing", "noncurrent", "failed", "context", "demand_identity", "artifact_id",
    "missing_locale", "sentinel", "source_copy", "literal_copy", "duplicate_locale",
    "unrequested_artifact",
    "missing_publication_demand", "wrong_publication_demand",
])
def test_literal_v2_rejects_invalid_requested_or_published_synthesis(checker, defect):
    row = _requested_synthesis_post()
    artifact = row["synthesis_artifact"]
    if defect == "missing":
        row["synthesis_artifact"] = None
    elif defect == "noncurrent":
        artifact["is_current"] = False
    elif defect == "failed":
        artifact["state"] = "failed"
    elif defect == "context":
        row["artifact_source"]["local_parent"] = "changed parent"
    elif defect == "demand_identity":
        row["synthesis_demand"]["model"] = "different model"
    elif defect == "artifact_id":
        row["synthesis_demand"]["artifact_id"] = 99
    elif defect == "missing_locale":
        artifact["texts"].pop("ja")
    elif defect == "sentinel":
        artifact["texts"]["en"] = " n/A "
    elif defect == "source_copy":
        artifact["texts"]["en"] = row["artifact_source"]["text"]
    elif defect == "literal_copy":
        artifact["texts"]["ja"] = row["literal_artifact"]["texts"]["ja"]
    elif defect == "duplicate_locale":
        artifact["texts"]["ja"] = artifact["texts"]["en"].upper()
    elif defect == "unrequested_artifact":
        row["synthesis_demand"] = None
    elif defect == "missing_publication_demand":
        artifact["demand"] = None
    else:
        artifact["demand"]["prompt_version"] = "unrelated"
    payload, code = checker.evaluate_snapshot(
        _snapshot(row), latest=1, requested_ids=None, grace_hours=24,
        translation_contract="literal-v2",
    )
    assert code == 1
    assert payload["posts"][0]["synthesis_complete"] is False
    assert payload["posts"][0]["state"] == "unhealthy"


def test_literal_v2_preserves_grace_exact_order_and_normal_output_redaction(checker):
    row = _requested_synthesis_post("pending")
    row["synthesis_demand"].update(age_seconds=24 * 3600 + 1, expired=True)
    payload, code = checker.evaluate_snapshot(
        _snapshot(row), latest=None, requested_ids=["200", "100"], grace_hours=24,
        translation_contract="literal-v2",
    )
    assert code == 1
    assert payload["cohort_tweet_ids"] == ["200", "100"]
    assert payload["missing_tweet_ids"] == ["200"]
    assert {reason["reason"] for reason in payload["posts"][1]["reasons"]} == {"overdue"}
    assert payload["posts"][1]["synthesis_expired"] is True
    output = json.dumps(payload) + checker._render_human(payload)
    assert row["artifact_source"]["text"] not in output
    assert "English literal" not in output
    assert "input_context_fingerprint" not in output


def test_literal_v2_requires_explicit_selection_and_reports_mode(checker):
    assert checker.parse_args([]).translation_contract == "legacy"
    assert checker.parse_args(["--translation-contract", "literal-v2"]).translation_contract == "literal-v2"
    payload, code = checker.evaluate_snapshot(
        _snapshot(_literal_post()), latest=1, requested_ids=None, grace_hours=24,
    )
    assert code == 1
    assert "commentary_en" in payload["acceptance"]
    assert "literal_artifact_complete" not in payload["acceptance"]


def test_literal_v2_cli_uses_one_read_only_call_and_preserves_report_evidence(checker, tmp_path):
    row = _requested_synthesis_post()
    row.update(text=row["artifact_source"]["text"])
    snapshot = _snapshot(row)
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        assert "BEGIN TRANSACTION READ ONLY" in command[command.index("--command") + 1]
        assert "post_translation_artifacts" in command[command.index("--command") + 1]
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(snapshot), stderr="")

    output = StringIO()
    assert checker.main(
        ["--translation-contract", "literal-v2", "--json"], runner=runner,
        stdout=output, stderr=StringIO(),
    ) == 0
    assert len(commands) == 1
    payload = json.loads(output.getvalue())
    assert payload["translation_contract"] == "literal-v2"
    assert row["artifact_source"]["text"] not in output.getvalue()
    report = checker.render_detailed_report(
        snapshot, payload, sql="READ ONLY SQL", invocation="health --translation-contract literal-v2",
        generated_at=datetime(2026, 11, 7, tzinfo=UTC), repo_root=tmp_path,
        request_reconstructions=[], script_source="checker source", script_sha256="abc",
        repo_commit="abc", python_version="test",
    )
    assert "Normalized literal-v2 and synthesis evidence" in report
    assert "legacy combined translation/commentary prompts do not apply" in report
    assert "Useful context" in report
    assert "日本語訳" in report
    assert "input_context_fingerprint" in report


def _current_state(**overrides):
    state = {
        "contract_version": "stage1-v1",
        "taxonomy_version": "stage1-taxonomy-v1",
        "prompt_version": "stage1-prompt-v2",
        "outcome": "classified",
        "sentiment": "positive",
        "china_nationalism": "none",
        "us_nationalism": None,
    }
    state.update(overrides)
    return state


def _stage1_brand(**overrides):
    brand = {
        "brand_id": "minimax",
        "signals": [
            {"post_type": "releases_updates", "sentiment": "positive"}
        ],
        "product_labels": [],
        "classification_state": _current_state(),
        "legacy_sentiments": ["negative"],
        "legacy_china_nationalisms": ["anti"],
        "legacy_us_nationalisms": ["pro"],
        "discourses": [],
    }
    brand.update(overrides)
    return brand


def _detailed_post(**overrides):
    row = _post(
        text="Full source post with `inline code` and a ``` fence.",
        lang="ja",
        lang_detected="ja",
        text_en="Full English translation.",
        text_zh_cn="完整中文翻译。",
        commentary_en="English analyst commentary.",
        commentary_zh_cn="中文语境说明。",
        source_query_id="C1",
        author_id="author-1",
        author_handle="example",
        author_name="Example Author",
        created_at="2026-08-24T23:58:00+00:00",
        tweet_url="https://x.com/example/status/100",
        like_count=12,
        retweet_count=3,
        reply_count=2,
        quote_count=1,
        translation_attempts=1,
        translation_first_attempt_at="2026-08-25T00:00:01+00:00",
        translation_last_attempt_at="2026-08-25T00:00:01+00:00",
        translation_next_attempt_at=None,
        classification_attempts=1,
        classification_first_attempt_at="2026-08-25T00:00:02+00:00",
        classification_last_attempt_at="2026-08-25T00:00:02+00:00",
        classification_next_attempt_at=None,
        enrichment_created_at="2026-08-25T00:00:00+00:00",
        enrichment_updated_at="2026-08-25T00:00:03+00:00",
        unsanctioned_flags={
            "flags": "[]",
            "flag_set": [],
            "evidence": "No unsanctioned signals.",
            "decided_at": "2026-08-25T00:00:02+00:00",
        },
        brands=[
            {
                "brand_id": "minimax",
                "weight": 1.0,
                "mentions": [
                    {
                        "source": "query",
                        "raw_token": "MiniMax",
                        "mentioned_at": "2026-08-25T00:00:00+00:00",
                    }
                ],
                "signals": [
                    {"post_type": "announcement", "sentiment": "positive"}
                ],
                "discourses": [
                    {
                        "discourse": "genuine_hype",
                        "act_id": 0,
                        "china_nationalism": "none",
                        "us_nationalism": "none",
                    }
                ],
            }
        ],
    )
    row.update(overrides)
    return row


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


def test_cli_supports_opt_in_detailed_report_and_rejects_json_combination(checker):
    args = checker.parse_args(["--latest", "3", "--report"])

    assert args.report is True
    assert args.as_json is False

    with pytest.raises(checker.HealthCheckError) as exc_info:
        checker.parse_args(["--report", "--json"])
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
    assert "NULLIF(BTRIM(p.lang_detected), '') IS NOT NULL" in sql
    assert "BTRIM(p.lang_detected) IN" not in sql
    assert "LOWER(BTRIM(p.commentary_en)) NOT IN ('n/a', 'na')" in sql
    assert "IS DISTINCT FROM LOWER(BTRIM(p.text_zh_cn))" in sql
    assert sql.index("LIMIT 20") < sql.index("FROM posts_brands")
    assert "to_regclass(relation_name)" in sql
    assert "WHEN stage1_relation_count = 0" in sql
    assert "WHEN stage1_relation_count = 4" in sql
    assert "query_to_xml(chosen_query.sql, false, true, '')" in sql
    assert "COLUMNS snapshot text PATH 'snapshot/text()'" in sql
    assert "RAISE NOTICE" not in sql
    assert "posts_brands_classification_states" in sql
    assert sql.count("BEGIN TRANSACTION READ ONLY") == 1

    command = checker.build_command(sql)
    assert command[:3] == ["render", "psql", "pushinweight-db-shadow"]
    assert command.count(sql) == 1
    assert "--no-psqlrc" in command
    assert "--no-align" in command
    assert "--tuples-only" in command
    assert "ON_ERROR_STOP=1" in " ".join(command)


def test_exact_query_uses_validated_ids_in_requested_order(checker):
    sql = checker.build_query(latest=None, tweet_ids=["200", "100"])

    assert "('200', 0)" in sql
    assert "('100', 1)" in sql
    assert sql.index("('200', 0)") < sql.index("('100', 1)")
    assert "JOIN selected_ids" in sql


def test_detailed_query_adds_report_facts_without_expanding_default_snapshot(checker):
    default_sql = checker.build_query(latest=20, tweet_ids=None)
    detailed_sql = checker.build_query(latest=20, tweet_ids=None, detailed=True)

    for detailed_fact in (
        "'text', p.text",
        "'text_en', p.text_en",
        "'commentary_en', p.commentary_en",
        "'commentary_zh_cn', p.commentary_zh_cn",
        "'translation_attempts', es.translation_attempts",
        "'classification_last_attempt_at', es.classification_last_attempt_at",
        "'weight', pb.weight",
        "'china_nationalism', discourse.china_nationalism",
        "'unsanctioned_flags'",
    ):
        assert detailed_fact in detailed_sql
        assert detailed_fact not in default_sql
    assert detailed_sql.count("BEGIN TRANSACTION READ ONLY") == 1
    assert detailed_sql.index("LIMIT 20") < detailed_sql.index("FROM posts_brands")


def test_complete_and_fresh_pending_rows_exit_zero_with_distinct_counts(checker):
    pending = _post(
        tweet_id="101",
        lang_detected=None,
        translation_status="pending",
        classification_status="pending",
        has_lang_detected=False,
        has_text_en=False,
        has_text_zh_cn=False,
        has_commentary_en=False,
        has_commentary_zh_cn=False,
        brands=[{"brand_id": "glm", "signals": [], "discourses": []}],
    )

    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(_post(), pending),
        latest=20,
        requested_ids=None,
        grace_hours=24,
    )

    assert exit_code == 1
    assert payload["status"] == "healthy_with_pending"
    assert payload["regression_gate"] == "inconclusive"
    assert payload["acceptance_gate"] == "failed"
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
        ("has_commentary_en", "missing_commentary_en"),
        ("has_commentary_zh_cn", "missing_commentary_zh_cn"),
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


def test_succeeded_classification_accepts_empty_discourse_as_uncategorized(checker):
    post = _post(
        brands=[
            {
                "brand_id": "minimax",
                "signals": [{"post_type": "announcement", "sentiment": "positive"}],
                "discourses": [],
            }
        ]
    )

    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(post),
        latest=20,
        requested_ids=None,
        grace_hours=24,
    )

    assert exit_code == 0
    assert payload["posts"][0]["state"] == "complete"
    assert payload["posts"][0]["reasons"] == []


def test_stage1_classified_accepts_empty_products_and_no_discourse(checker):
    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(
            _post(brands=[_stage1_brand()]),
            schema_profile="stage1",
        ),
        latest=1,
        requested_ids=None,
        grace_hours=24,
    )

    assert exit_code == 0
    assert payload["schema_profile"] == "stage1"
    assert payload["posts"][0]["state"] == "complete"
    classification = payload["posts"][0]["brand_classifications"][0]
    assert classification["state"] == "current"
    assert classification["outcome"] == "classified"
    assert classification["product_labels"] == []
    assert classification["prompt_version"] == "stage1-prompt-v2"
    assert payload["posts"][0]["reasons"] == []


def test_stage1_context_missing_accepts_empty_edges_and_nullable_scalars(checker):
    brand = _stage1_brand(
        signals=[],
        product_labels=[],
        classification_state=_current_state(
            outcome="context_missing",
            sentiment=None,
            china_nationalism=None,
            us_nationalism="none",
        ),
    )
    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(_post(brands=[brand]), schema_profile="stage1"),
        latest=1,
        requested_ids=None,
        grace_hours=24,
    )

    assert exit_code == 0
    classification = payload["posts"][0]["brand_classifications"][0]
    assert classification["outcome"] == "context_missing"
    assert classification["sentiment"] is None
    assert classification["us_nationalism"] == "none"
    assert payload["posts"][0]["reasons"] == []


@pytest.mark.parametrize(
    ("brand", "reason"),
    [
        (
            _stage1_brand(
                classification_state=_current_state(sentiment="joy"),
                signals=[{"post_type": "buzz_releases", "sentiment": "joy"}],
            ),
            "invalid_sentiment",
        ),
        (
            _stage1_brand(
                signals=[{"post_type": "announcement", "sentiment": "positive"}]
            ),
            "invalid_post_type",
        ),
        (
            _stage1_brand(
                signals=[
                    {"post_type": "other", "sentiment": "positive"},
                    {"post_type": "opinions_reactions", "sentiment": "positive"},
                ]
            ),
            "other_not_exclusive",
        ),
        (_stage1_brand(product_labels=["unknown"]), "invalid_product_label"),
        (
            _stage1_brand(
                classification_state=_current_state(china_nationalism="unknown")
            ),
            "invalid_china_nationalism",
        ),
        (
            _stage1_brand(
                classification_state=_current_state(outcome="context_missing"),
            ),
            "context_missing_has_edges",
        ),
        (
            _stage1_brand(signals=[]),
            "missing_post_type",
        ),
        (
            _stage1_brand(
                signals=[], classification_state=_current_state(sentiment=None)
            ),
            "missing_sentiment",
        ),
    ],
)
def test_stage1_invalid_current_rows_fail_closed(checker, brand, reason):
    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(_post(brands=[brand]), schema_profile="stage1"),
        latest=1,
        requested_ids=None,
        grace_hours=24,
    )

    assert exit_code == 1
    assert payload["status"] == "unhealthy"
    assert reason in {item["reason"] for item in payload["posts"][0]["reasons"]}


def test_stage1_stale_state_is_not_treated_as_current(checker):
    brand = _stage1_brand(
        classification_state=_current_state(
            contract_version="stage0-legacy",
            sentiment="positive",
            china_nationalism="pro",
            us_nationalism="pro",
        ),
        legacy_sentiments=["negative"],
        legacy_china_nationalisms=["anti", "pro"],
        legacy_us_nationalisms=[],
    )
    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(_post(brands=[brand]), schema_profile="stage1"),
        latest=1,
        requested_ids=None,
        grace_hours=24,
    )

    assert exit_code == 1
    classification = payload["posts"][0]["brand_classifications"][0]
    assert classification["state"] == "stale"
    assert classification["contract_version"] == "stage0-legacy"
    assert classification["taxonomy_version"] == "stage1-taxonomy-v1"
    assert classification["prompt_version"] == "stage1-prompt-v2"
    assert classification["stale_outcome"] == "classified"
    assert classification["outcome"] is None
    assert classification["post_types"] == []
    assert classification["product_labels"] == []
    assert classification["scalar_source"] == "unrecognized"
    assert classification["sentiment"] is None
    assert classification["china_nationalism"] is None
    assert classification["us_nationalism"] is None
    assert classification["legacy_conflicts"] == []
    assert payload["posts"][0]["reasons"] == [
        {
            "stage": "classification",
            "reason": "stale_state",
            "brand_id": "minimax",
        }
    ]


def test_stage1_canonical_taxonomy_state_is_current_compatible(checker):
    brand = _stage1_brand(
        signals=[{"post_type": "releases_updates", "sentiment": "positive"}],
        classification_state=_current_state(
            taxonomy_version="stage1-taxonomy-v2",
            prompt_version="stage1-prompt-v3",
        ),
    )
    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(_post(brands=[brand]), schema_profile="stage1"),
        latest=1,
        requested_ids=None,
        grace_hours=24,
    )

    assert exit_code == 0
    classification = payload["posts"][0]["brand_classifications"][0]
    assert classification["state"] == "current"
    assert classification["taxonomy_version_current_compatible"] is True
    assert classification["active_write_taxonomy_version"] == "stage1-taxonomy-v4"
    assert classification["latest_taxonomy_version"] == "stage1-taxonomy-v4"
    assert classification["active_write_prompt_version"] == "stage1-prompt-v4"
    assert classification["latest_prompt_version"] == "stage1-prompt-v4"


def test_stage1_current_null_scalars_suppress_legacy_fallback(checker):
    brand = _stage1_brand(
        signals=[],
        classification_state=_current_state(
            outcome="context_missing",
            sentiment=None,
            china_nationalism=None,
            us_nationalism=None,
        ),
    )
    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(_post(brands=[brand]), schema_profile="stage1"),
        latest=1,
        requested_ids=None,
        grace_hours=24,
    )

    assert exit_code == 0
    classification = payload["posts"][0]["brand_classifications"][0]
    assert classification["scalar_source"] == "current"
    assert classification["sentiment"] is None
    assert classification["china_nationalism"] is None
    assert classification["us_nationalism"] is None


def test_stage1_absent_current_uses_only_unambiguous_legacy_scalars(checker):
    brand = _stage1_brand(
        classification_state=None,
        legacy_sentiments=["positive", "positive"],
        legacy_china_nationalisms=["pro", "anti"],
        legacy_us_nationalisms=[],
    )
    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(_post(brands=[brand]), schema_profile="stage1"),
        latest=1,
        requested_ids=None,
        grace_hours=24,
    )

    assert exit_code == 0
    classification = payload["posts"][0]["brand_classifications"][0]
    assert classification["state"] == "historical_untyped"
    assert classification["post_types"] == []
    assert classification["product_labels"] == []
    assert classification["sentiment"] == "positive"
    assert classification["china_nationalism"] is None
    assert classification["us_nationalism"] is None
    assert classification["legacy_conflicts"] == ["china_nationalism"]


def test_partial_stage1_schema_is_a_stable_operational_error(checker):
    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(schema_profile="partial"),
        latest=1,
        requested_ids=None,
        grace_hours=24,
    )

    assert exit_code == 2
    assert payload == {
        "schema_version": 1,
        "status": "error",
        "error": {"class": "query", "code": "stage1_schema_partial"},
    }


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
            "lang_detected": None,
            "has_text_zh_cn": False,
            "has_commentary_en": False,
            "has_commentary_zh_cn": False,
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


def test_latest_fifty_acceptance_requires_all_commentary_rows(checker):
    posts = [_post(tweet_id=str(1000 + index)) for index in range(50)]

    passing, passing_code = checker.evaluate_snapshot(
        _snapshot(*posts), latest=50, requested_ids=None, grace_hours=24
    )
    failing_posts = list(posts)
    failing_posts[-1] = _post(
        tweet_id="1049",
        has_commentary_en=False,
    )
    failing, failing_code = checker.evaluate_snapshot(
        _snapshot(*failing_posts), latest=50, requested_ids=None, grace_hours=24
    )

    assert passing_code == 0
    assert passing["acceptance_gate"] == "complete"
    assert passing["acceptance"]["commentary_en"] == {
        "numerator": 50,
        "denominator": 50,
        "rate": 1.0,
        "percentage": 100.0,
        "threshold": 0.99,
        "passed": True,
    }
    assert failing_code == 1
    assert failing["acceptance_gate"] == "failed"
    assert failing["acceptance"]["commentary_en"]["rate"] == 0.98
    assert failing["acceptance"]["commentary_en"]["percentage"] == 98.0
    assert failing["acceptance"]["commentary_en"]["passed"] is False


def test_human_output_exposes_each_acceptance_percentage(checker):
    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(_post()), latest=1, requested_ids=None, grace_hours=24
    )

    rendered = checker._render_human(payload)

    assert exit_code == 0
    assert "non_zh_hans_text_zh_cn=1/1(100.0%)" in rendered
    assert "commentary_en=1/1(100.0%)" in rendered
    assert "commentary_zh_cn=1/1(100.0%)" in rendered


def test_non_zh_hans_translation_rate_uses_only_eligible_posts(checker):
    posts = [
        _post(tweet_id="1", lang_detected="zh-Hans", has_text_zh_cn=True),
        _post(tweet_id="2", lang_detected="en", has_text_zh_cn=True),
        _post(tweet_id="3", lang_detected="ja", has_text_zh_cn=False),
    ]

    payload, _exit_code = checker.evaluate_snapshot(
        _snapshot(*posts), latest=3, requested_ids=None, grace_hours=24
    )

    metric = payload["acceptance"]["non_zh_hans_text_zh_cn"]
    assert metric["numerator"] == 1
    assert metric["denominator"] == 2
    assert metric["rate"] == 0.5
    assert metric["passed"] is False


def test_noncanonical_language_cannot_satisfy_acceptance(checker):
    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(_post(lang_detected="english")),
        latest=1,
        requested_ids=None,
        grace_hours=24,
    )

    assert exit_code == 1
    assert payload["acceptance"]["lang_detected_present"]["numerator"] == 0
    assert payload["acceptance_gate"] == "failed"


def test_zero_non_zh_hans_posts_is_not_a_translation_failure(checker):
    payload, exit_code = checker.evaluate_snapshot(
        _snapshot(_post(lang_detected="zh-Hans")),
        latest=1,
        requested_ids=None,
        grace_hours=24,
    )

    metric = payload["acceptance"]["non_zh_hans_text_zh_cn"]
    assert metric["denominator"] == 0
    assert metric["rate"] is None
    assert metric["passed"] is True
    assert exit_code == 0


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


def test_render_text_table_transport_uses_one_bounded_subprocess(checker):
    calls = []
    snapshot = _snapshot(_post(), schema_profile="legacy")
    snapshot_json = json.dumps(snapshot)

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                "BEGIN\nSET\nSET\nSET\n"
                " snapshot\n"
                "----------\n"
                f" {snapshot_json}\n"
                "(1 row)\nCOMMIT\n"
            ),
            stderr="render update warning",
        )

    result = checker.execute_query("READ ONLY SQL", runner=runner)

    assert result == snapshot
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command.count("READ ONLY SQL") == 1
    assert kwargs["timeout"] == checker.QUERY_TIMEOUT_SECONDS
    assert kwargs["check"] is False


def test_successful_notice_only_output_is_rejected(checker):
    snapshot = _snapshot(_post(), schema_profile="legacy")

    def runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="BEGIN\nDO\nCOMMIT\n",
            stderr="NOTICE:  PW_HEALTH_SNAPSHOT:" + json.dumps(snapshot),
        )

    with pytest.raises(checker.HealthCheckError) as exc_info:
        checker.execute_query("READ ONLY SQL", runner=runner)

    assert exc_info.value.code == "render_output_invalid"


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_literal_v2_stdout_query_round_trips_current_schema_and_canonical_artifacts(checker, monkeypatch):
    from django.db import connection
    from django.utils import timezone

    from core.models import (
        Brand,
        Post,
        PostBrand,
        PostEnrichmentState,
        PostSynthesisDemand,
        PostSynthesisText,
        PostTranslationText,
    )
    from monitor.post_artifacts import (
        literal_translation_artifact_complete,
        publish_literal_translation,
        publish_post_synthesis,
        source_text_fingerprint,
        synthesis_context_fingerprint,
    )

    # Only the optional queue boundary is inert; all storage and writers are real.
    monkeypatch.setattr("monitor.editorial.dispatch.dispatch_picture", lambda *_args: None)
    now = timezone.now()
    parent = Post.objects.create(tweet_id="9100", text='Parent 日本語 & "quoted"\nline')
    post = Post.objects.create(
        tweet_id="9101", text='Nguồn tiếng Việt 中文 & <tag> "quote"\nline',
        quoted_text="引用文", in_reply_to_id=parent.pk,
    )
    brand = Brand.objects.create(nickname="health-literal-v2")
    PostBrand.objects.create(post=post, brand=brand)
    PostEnrichmentState.objects.create(
        post=post, translation_status="succeeded", classification_status="succeeded",
    )
    artifact = publish_literal_translation(
        post=post, row={"lang_detected": "vi", "text_en": "English literal",
                       "text_zh_cn": "中文翻译", "text_ja": "日本語訳"},
        prompt_version="literal-v2", model="test",
        expected_source_fingerprint=source_text_fingerprint(post.text),
    )
    assert artifact is not None
    post.refresh_from_db()
    assert literal_translation_artifact_complete(post)

    def observe(*, detailed=False):
        sql = checker.build_query(
            latest=None, tweet_ids=[post.pk], translation_contract="literal-v2", detailed=detailed,
        )
        with connection.cursor() as cursor:
            cursor.execute(sql)
            snapshots = []
            while True:
                if cursor.description is not None:
                    snapshots.extend(cursor.fetchall())
                if not cursor.nextset():
                    break
        assert len(snapshots) == 1
        snapshot = checker.parse_snapshot(str(snapshots[0][0]))
        assert snapshot["transaction_read_only"] == "on"
        payload, code = checker.evaluate_snapshot(
            snapshot, latest=None, requested_ids=[post.pk], grace_hours=24,
            translation_contract="literal-v2",
        )
        return snapshot, payload, code

    snapshot, payload, code = observe()
    assert code == 0
    observed = snapshot["posts"][0]
    assert observed["literal_artifact"]["source_content_fingerprint"] == source_text_fingerprint(post.text)
    assert observed["artifact_source"]["local_parent"] == parent.text
    assert payload["posts"][0]["synthesis_status"] == "not_requested"
    assert payload["acceptance"]["lang_detected_present"]["numerator"] == 1
    detailed_snapshot, _, detailed_code = observe(detailed=True)
    assert detailed_code == 0
    assert detailed_snapshot["posts"][0]["text"] == post.text
    assert detailed_snapshot["posts"][0]["literal_artifact"]["texts"]["ja"] == "日本語訳"

    # A compatibility mirror cannot hide a missing normalized locale.
    PostTranslationText.objects.filter(artifact=artifact, locale="ja").delete()
    assert observe()[2] == 1
    PostTranslationText.objects.create(artifact=artifact, locale="ja", text="日本語訳")
    artifact.is_current = False
    artifact.save(update_fields=["is_current"])
    assert observe()[2] == 1
    artifact.is_current = True
    artifact.save(update_fields=["is_current"])
    Post.objects.filter(pk=post.pk).update(text="Changed source")
    assert observe()[2] == 1
    Post.objects.filter(pk=post.pk).update(text=post.text)

    context_fingerprint = synthesis_context_fingerprint(post, parent_text=parent.text)
    demand = PostSynthesisDemand.objects.create(
        post=post, input_context_fingerprint=context_fingerprint,
        prompt_version="synthesis-v1", model="test", output_schema_version=1,
        reason="operator", priority=100, first_requested_at=now,
        last_requested_at=now, not_before=now,
    )
    snapshot, payload, code = observe()
    assert code == 1
    assert payload["status"] == "healthy_with_pending"
    assert payload["posts"][0]["synthesis_status"] == "pending"
    assert snapshot["posts"][0]["synthesis_demand"]["input_context_fingerprint"] == context_fingerprint
    rich = publish_post_synthesis(
        post=post, values={"en": "Useful context", "zh-cn": "有用的背景", "ja": "役立つ背景"},
        context_fingerprint=context_fingerprint, prompt_version="synthesis-v1",
        model="test", output_schema_version=1,
    )
    assert rich is not None
    demand.state = "succeeded"
    demand.artifact = rich
    demand.save(update_fields=["state", "artifact", "updated_at"])
    snapshot, payload, code = observe()
    assert code == 0
    assert payload["posts"][0]["synthesis_status"] == "complete"
    Post.objects.filter(pk=parent.pk).update(text="Changed local parent")
    assert observe()[2] == 1
    Post.objects.filter(pk=parent.pk).update(text=parent.text)
    demand.model = "wrong identity"
    demand.save(update_fields=["model"])
    assert observe()[2] == 1
    demand.model = "test"
    demand.save(update_fields=["model"])
    PostSynthesisText.objects.filter(artifact=rich, locale="ja").update(text="日本語訳")
    assert observe()[2] == 1
    PostSynthesisText.objects.filter(artifact=rich, locale="ja").update(text="役立つ背景")
    assert observe()[2] == 0

    newer = PostSynthesisDemand.objects.create(
        post=post, input_context_fingerprint=context_fingerprint,
        prompt_version="synthesis-v2", model="test", output_schema_version=1,
        reason="operator", priority=100, first_requested_at=now,
        last_requested_at=now, not_before=now,
    )
    snapshot, payload, code = observe()
    assert code == 1
    assert payload["status"] == "healthy_with_pending"
    assert payload["posts"][0]["synthesis_status"] == "pending"
    assert payload["posts"][0]["synthesis_published_complete"] is True
    assert payload["acceptance"]["requested_synthesis_complete"]["numerator"] == 0
    assert snapshot["posts"][0]["synthesis_artifact"]["demand"]["id"] == demand.pk
    newer.state = "cancelled"
    newer.save(update_fields=["state", "updated_at"])
    snapshot, payload, code = observe()
    assert code == 0
    assert payload["posts"][0]["synthesis_status"] == "cancelled"
    assert payload["posts"][0]["synthesis_published_complete"] is True
    assert payload["posts"][0]["synthesis_complete"] is False
    assert payload["acceptance"]["requested_synthesis_complete"]["denominator"] == 0


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "migration_rehearsal_schema", [("core", "0027_account_country_foreign_key")], indirect=True
)
def test_schema_aware_stdout_query_round_trips_real_schema_profiles(checker, migration_rehearsal_schema):
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    before = [("core", "0027_account_country_foreign_key")]
    stage1 = [("core", "0028_ai_enrichment_stage1_taxonomy")]
    renamed_table = "posts_brands_product_labels_health_test"

    def execute_snapshot(sql):
        with connection.cursor() as cursor:
            cursor.execute(sql)
            result_rows = []
            while True:
                if cursor.description is not None:
                    result_rows.extend(cursor.fetchall())
                if not cursor.nextset():
                    break
        rendered = (
            "BEGIN\nSET\nSET\nSET\n snapshot\n----------\n"
            + "\n".join(f" {row[0]}" for row in result_rows)
            + "\n(1 row)\nCOMMIT\n"
        )
        return checker.parse_snapshot(rendered)

    # The fixture owns only a temporary namespace; public history stays untouched.
    executor = MigrationExecutor(connection)
    legacy_apps = executor.loader.project_state(before).apps
    Post = legacy_apps.get_model("core", "Post")
    Post.objects.create(
        tweet_id="xml-carrier-100",
        text='XML & <tag> > "quotes" 中文',
        text_en="English & <translation>",
        text_zh_cn="中文 & <翻译>",
        commentary_en='Commentary & <context> "quoted"',
        commentary_zh_cn="语境 & <说明>",
        lang_detected="en",
    )

    legacy_snapshot = execute_snapshot(
        checker.build_query(latest=1, tweet_ids=None, detailed=True)
    )
    assert legacy_snapshot["schema_profile"] == "legacy"
    assert legacy_snapshot["transaction_read_only"] == "on"
    assert legacy_snapshot["posts"][0]["tweet_id"] == "xml-carrier-100"
    assert legacy_snapshot["posts"][0]["text"] == 'XML & <tag> > "quotes" 中文'
    assert legacy_snapshot["posts"][0]["commentary_zh_cn"] == "语境 & <说明>"

    executor = MigrationExecutor(connection)
    executor.migrate(stage1)
    with connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE posts_brands_product_labels "
            f"RENAME TO {renamed_table}"
        )
    try:
        partial_snapshot = execute_snapshot(
            checker.build_query(latest=1, tweet_ids=None)
        )
        assert partial_snapshot == {
            "transaction_read_only": "on",
            "schema_profile": "partial",
            "posts": [],
        }
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE {renamed_table} "
                "RENAME TO posts_brands_product_labels"
            )

    stage1_snapshot = execute_snapshot(
        checker.build_query(latest=1, tweet_ids=None, detailed=True)
    )
    assert stage1_snapshot["schema_profile"] == "stage1"
    assert stage1_snapshot["transaction_read_only"] == "on"
    assert stage1_snapshot["posts"][0]["tweet_id"] == "xml-carrier-100"
    assert stage1_snapshot["posts"][0]["text"] == 'XML & <tag> > "quotes" 中文'
    assert stage1_snapshot["posts"][0]["commentary_zh_cn"] == "语境 & <说明>"

    stage1_apps = executor.loader.project_state(stage1).apps
    Brand = stage1_apps.get_model("core", "Brand")
    Post = stage1_apps.get_model("core", "Post")
    PostBrand = stage1_apps.get_model("core", "PostBrand")
    PostTypeKey = stage1_apps.get_model("core", "PostTypeKey")
    SentimentKey = stage1_apps.get_model("core", "SentimentKey")
    ProductLabelKey = stage1_apps.get_model("core", "ProductLabelKey")
    EnrichmentState = stage1_apps.get_model("core", "PostEnrichmentState")
    Signal = stage1_apps.get_model("core", "PostBrandSignal")
    ProductEdge = stage1_apps.get_model("core", "PostBrandProductLabel")
    State = stage1_apps.get_model("core", "PostBrandClassificationState")
    brand = Brand.objects.create(nickname="health-crosswalk")
    post = Post.objects.create(
        tweet_id="101",
        text="health crosswalk",
        text_en="health crosswalk en",
        text_zh_cn="health crosswalk zh",
        commentary_en="health commentary en",
        commentary_zh_cn="health commentary zh",
        lang_detected="en",
    )
    PostBrand.objects.create(post=post, brand=brand)
    EnrichmentState.objects.create(
        post=post,
        translation_status="succeeded",
        classification_status="succeeded",
    )
    SentimentKey.objects.get_or_create(key="positive")
    for key in ("buzz_releases", "health_unknown_type"):
        PostTypeKey.objects.get_or_create(key=key)
        Signal.objects.create(
            post=post, brand=brand, post_type_id=key, sentiment_id="positive"
        )
    for key in ("product_request", "health_unknown_product"):
        ProductLabelKey.objects.get_or_create(key=key)
        ProductEdge.objects.create(post=post, brand=brand, product_label_id=key)
    State.objects.create(
        post=post,
        brand=brand,
        contract_version="stage1-v1",
        taxonomy_version="stage1-taxonomy-v1",
        prompt_version="stage1-prompt-v2",
        model="test",
        input_context_fingerprint="b" * 64,
        outcome="classified",
        sentiment_id="positive",
    )
    crosswalk_snapshot = execute_snapshot(
        checker.build_query(latest=None, tweet_ids=["101"], detailed=True)
    )
    observed = crosswalk_snapshot["posts"][0]["brands"][0]
    assert observed["signals"] == [
        {"post_type": "releases_updates", "sentiment": "positive"}
    ]
    assert observed["product_labels"] == ["ideas_requests"]
    assert observed["stored_post_type_keys"] == [
        "buzz_releases",
        "health_unknown_type",
    ]
    assert observed["stored_product_label_keys"] == [
        "health_unknown_product",
        "product_request",
    ]
    evaluated, exit_code = checker.evaluate_snapshot(
        crosswalk_snapshot,
        latest=None,
        requested_ids=["101"],
        grace_hours=24,
    )
    assert exit_code == 1
    reasons = evaluated["posts"][0]["reasons"]
    assert {reason["reason"] for reason in reasons} >= {
        "invalid_post_type",
        "invalid_product_label",
    }


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


def test_request_reconstruction_uses_selected_text_and_brands_without_clients(
    checker, tmp_path
):
    builder_inputs = []

    def translation_builder(tweets, locales):
        builder_inputs.append(("translation", tweets, locales))
        return "TRANSLATION PROMPT\n" + tweets[0]["text"]

    def classification_builder(tweets):
        builder_inputs.append(("classification", tweets))
        return "CLASSIFICATION PROMPT\n" + tweets[0]["text"]

    calls = checker.build_request_reconstructions(
        [_detailed_post()],
        repo_root=tmp_path,
        config_data={
            "llm": {
                "translator_model": "translator-model",
                "classifier_model": "classifier-model",
            }
        },
        prompt_builders=(
            translation_builder,
            classification_builder,
            lambda size: min(65536, max(16384, 1500 * size)),
        ),
    )

    assert [call[0] for call in builder_inputs] == [
        "translation",
        "classification",
    ]
    assert builder_inputs[0][1] == [
        {
            "tweet_id": "100",
            "text": _detailed_post()["text"],
            "brand_ids": ["minimax"],
        }
    ]
    assert builder_inputs[0][2] == ["en", "zh_cn"]
    assert builder_inputs[1][1][0]["brand_ids"] == ["minimax"]
    assert len(calls) == 2
    assert calls[0]["stage"] == "translation"
    assert calls[0]["known_request_kwargs"]["model"] == "translator-model"
    assert calls[0]["known_request_kwargs"]["max_tokens"] == 16384
    assert calls[0]["known_request_kwargs"]["messages"][0]["content"].startswith(
        "TRANSLATION PROMPT"
    )
    assert calls[1]["stage"] == "classification"
    assert calls[1]["known_request_kwargs"]["model"] == "classifier-model"
    assert calls[1]["known_request_kwargs"]["max_tokens"] == 4096
    assert all("client" not in json.dumps(call).lower() for call in calls)
    assert all(call["historical_wire_call"] is False for call in calls)
    assert all("thinking" in call["runtime_only_kwargs"] for call in calls)


def test_request_reconstruction_remains_bounded_at_two_hundred_posts(
    checker, tmp_path
):
    posts = [
        _detailed_post(tweet_id=str(1000 + index), text=f"post {index}")
        for index in range(200)
    ]

    calls = checker.build_request_reconstructions(
        posts,
        repo_root=tmp_path,
        config_data={
            "llm": {
                "translator_model": "translator-model",
                "classifier_model": "classifier-model",
            }
        },
        prompt_builders=(
            lambda tweets, locales: f"translate {len(tweets)} {locales}",
            lambda tweets: f"classify {len(tweets)}",
            lambda size: min(65536, max(16384, 1500 * size)),
        ),
    )

    assert len(calls) == 20
    assert sum(call["stage"] == "translation" for call in calls) == 10
    assert sum(call["stage"] == "classification" for call in calls) == 10
    assert all(len(call["tweet_ids"]) == 20 for call in calls)


def test_real_prompt_builders_are_pure_and_include_selected_post(checker):
    from x_monitor.translator import _max_tokens_for_batch_size

    calls = checker.build_request_reconstructions(
        [_detailed_post(text="REAL BUILDER SENTINEL")],
        repo_root=Path(__file__).parents[1],
        config_data={
            "llm": {
                "translator_model": "deepseek-v4-flash",
                "classifier_model": "deepseek-v4-flash",
            }
        },
    )

    assert [call["stage"] for call in calls] == ["translation", "classification"]
    assert calls[0]["known_request_kwargs"]["max_tokens"] == (
        _max_tokens_for_batch_size(1)
    )
    for call in calls:
        request_json = json.dumps(call["known_request_kwargs"], ensure_ascii=False)
        assert "REAL BUILDER SENTINEL" in request_json
        assert '"tweet_id"' in call["known_request_kwargs"]["messages"][0]["content"]
        assert '"100"' in call["known_request_kwargs"]["messages"][0]["content"]


def test_detailed_report_contains_full_evidence_and_explicit_provenance(
    checker, monkeypatch, tmp_path
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ENV-SECRET-MUST-NOT-LEAK")
    snapshot = _snapshot(_detailed_post())
    payload, _ = checker.evaluate_snapshot(
        snapshot,
        latest=1,
        requested_ids=None,
        grace_hours=24,
    )
    request_reconstructions = [
        {
            "stage": "translation",
            "historical_wire_call": False,
            "batch_index": 1,
            "tweet_ids": ["100"],
            "known_request_kwargs": {
                "model": "deepseek-v4-flash",
                "max_tokens": 16384,
                "messages": [
                    {"role": "user", "content": "VERBATIM PROMPT SENTINEL"}
                ],
            },
            "runtime_only_kwargs": {"thinking": "unavailable"},
        }
    ]

    report = checker.render_detailed_report(
        snapshot,
        payload,
        sql="BEGIN TRANSACTION READ ONLY; SELECT exact_sql; COMMIT;",
        invocation="python check.py --latest 1 --report",
        generated_at=datetime(2026, 8, 26, 1, 2, 3, tzinfo=UTC),
        repo_root=tmp_path,
        request_reconstructions=request_reconstructions,
        script_source="print('CHECKER SOURCE SENTINEL')\n",
        script_sha256="abc123",
        repo_commit="deadbeef",
        python_version="3.14.0",
    )

    for expected in (
        "Harvester latest-N health report",
        "Full source post with `inline code` and a ``` fence.",
        "Full English translation.",
        "English analyst commentary.",
        "完整中文翻译。",
        "中文语境说明。",
        "minimax",
        "genuine_hype",
        "No unsanctioned signals.",
        "Calls made by this health checker",
        "[]",
        "Current-code LLM request reconstructions",
        "not historical wire evidence",
        "VERBATIM PROMPT SENTINEL",
        "BEGIN TRANSACTION READ ONLY; SELECT exact_sql; COMMIT;",
        "abc123",
        "deadbeef",
        "3.14.0",
        "CHECKER SOURCE SENTINEL",
    ):
        assert expected in report
    assert "ENV-SECRET-MUST-NOT-LEAK" not in report
    assert report.count("```python") == 1


def test_exact_report_renders_requested_post_missing_from_database(checker, tmp_path):
    snapshot = _snapshot(_detailed_post(tweet_id="200"))
    payload, exit_code = checker.evaluate_snapshot(
        snapshot,
        latest=None,
        requested_ids=["200", "100"],
        grace_hours=24,
    )

    report = checker.render_detailed_report(
        snapshot,
        payload,
        sql="BEGIN TRANSACTION READ ONLY; COMMIT;",
        invocation="python check.py --tweet-id 200 --tweet-id 100 --report",
        generated_at=datetime(2026, 8, 26, 1, 2, 3, tzinfo=UTC),
        repo_root=tmp_path,
        request_reconstructions=[],
        script_source="print('checker')\n",
        script_sha256="abc123",
        repo_commit="deadbeef",
        python_version="3.14.0",
    )

    assert exit_code == 1
    assert "## Post 2: `100`" in report
    assert "No persisted post row was returned" in report
    assert '"reason": "missing_post"' in report


def test_detailed_report_write_is_atomic_and_cleans_failed_temp(
    checker, monkeypatch, tmp_path
):
    generated_at = datetime(2026, 8, 26, 1, 2, 3, tzinfo=UTC)
    path = checker.write_report_atomic(
        "report body", repo_root=tmp_path, generated_at=generated_at
    )

    assert path == (
        tmp_path
        / "docs/analysis/harvester/2026-08-26-010203-harvester-latest-n-health-report.md"
    )
    assert path.read_text() == "report body"
    assert list(path.parent.glob(".*.tmp")) == []

    monkeypatch.setattr(checker.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError()))
    with pytest.raises(checker.HealthCheckError) as exc_info:
        checker.write_report_atomic(
            "new report body", repo_root=tmp_path, generated_at=generated_at
        )
    assert exc_info.value.code == "report_write_failed"
    assert path.read_text() == "report body"
    assert list(path.parent.glob(".*.tmp")) == []


def test_main_report_mode_uses_detailed_snapshot_and_prints_saved_path(
    checker, monkeypatch, tmp_path
):
    snapshot_json = json.dumps(_snapshot(_detailed_post()))
    captured = {}

    def runner(command, **kwargs):
        captured["sql"] = command[4]
        return subprocess.CompletedProcess(command, 0, stdout=snapshot_json, stderr="")

    monkeypatch.setattr(checker, "load_grace_hours", lambda: 24)
    monkeypatch.setattr(
        checker,
        "build_request_reconstructions",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        checker,
        "write_report_atomic",
        lambda report, **_kwargs: captured.setdefault(
            "report", tmp_path / "saved-report.md"
        ),
    )
    stdout = StringIO()

    exit_code = checker.main(
        ["--latest", "1", "--report"],
        runner=runner,
        stdout=stdout,
        stderr=StringIO(),
    )

    assert exit_code == 0
    assert "'text', p.text" in captured["sql"]
    assert "report=" + str(tmp_path / "saved-report.md") in stdout.getvalue()
    assert "Full source post" not in stdout.getvalue()


def test_main_unhealthy_report_still_writes_and_retains_exit_one(
    checker, monkeypatch, tmp_path
):
    unhealthy = _detailed_post(
        brands=[
            {
                "brand_id": "minimax",
                "weight": 1.0,
                "mentions": [],
                "signals": [],
                "discourses": [],
            }
        ]
    )
    snapshot_json = json.dumps(_snapshot(unhealthy))
    captured = {}

    def runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=snapshot_json, stderr="")

    monkeypatch.setattr(checker, "load_grace_hours", lambda: 24)
    monkeypatch.setattr(
        checker, "build_request_reconstructions", lambda *_args, **_kwargs: []
    )
    monkeypatch.setattr(
        checker,
        "write_report_atomic",
        lambda report, **_kwargs: captured.setdefault(
            "report", tmp_path / "unhealthy-report.md"
        ),
    )
    stdout = StringIO()

    exit_code = checker.main(
        ["--latest", "1", "--report"],
        runner=runner,
        stdout=stdout,
        stderr=StringIO(),
    )

    assert exit_code == 1
    assert "status=unhealthy" in stdout.getvalue()
    assert "report=" + str(tmp_path / "unhealthy-report.md") in stdout.getvalue()


def test_unexpected_report_exception_is_sanitized(checker, monkeypatch):
    snapshot_json = json.dumps(_snapshot(_detailed_post()))
    writes = []

    def runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=snapshot_json, stderr="")

    monkeypatch.setattr(checker, "load_grace_hours", lambda: 24)
    monkeypatch.setattr(
        checker, "build_request_reconstructions", lambda *_args, **_kwargs: []
    )
    monkeypatch.setattr(
        checker,
        "render_detailed_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            TypeError("internal renderer secret")
        ),
    )
    monkeypatch.setattr(
        checker,
        "write_report_atomic",
        lambda *_args, **_kwargs: writes.append(True),
    )
    stdout = StringIO()
    stderr = StringIO()

    exit_code = checker.main(
        ["--latest", "1", "--report"],
        runner=runner,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert writes == []
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == (
        "harvester-health error class=report code=report_generation_failed\n"
    )
    assert "internal renderer secret" not in stderr.getvalue()


def test_report_reconstruction_failure_is_stable_and_writes_no_partial(
    checker, monkeypatch
):
    snapshot_json = json.dumps(_snapshot(_detailed_post()))
    writes = []

    def runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=snapshot_json, stderr="")

    def fail_prompt_builder(*_args, **_kwargs):
        raise RuntimeError("provider-shaped internal detail")

    monkeypatch.setattr(checker, "load_grace_hours", lambda: 24)
    monkeypatch.setattr(
        checker,
        "_prompt_builders",
        lambda _repo_root: (
            fail_prompt_builder,
            fail_prompt_builder,
            lambda size: 16384,
        ),
    )
    monkeypatch.setattr(
        checker,
        "write_report_atomic",
        lambda *_args, **_kwargs: writes.append(True),
    )
    stdout = StringIO()
    stderr = StringIO()

    exit_code = checker.main(
        ["--latest", "1", "--report"],
        runner=runner,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert writes == []
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == (
        "harvester-health error class=report code=prompt_reconstruction_failed\n"
    )
    assert "provider-shaped" not in stderr.getvalue()


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
    for report_contract in (
        "--latest 20 --report",
        "docs/analysis/harvester/YYYY-MM-DD-HHMMSS-harvester-latest-n-health-report.md",
        "historical wire calls",
        "complete checker source",
    ):
        assert report_contract in skill_text


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
