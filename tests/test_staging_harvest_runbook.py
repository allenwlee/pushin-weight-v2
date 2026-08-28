from __future__ import annotations

from pathlib import Path

DEPLOY_RUNBOOK = Path("docs/deploy/render.md")
ACCEPTANCE_RECORD = Path(
    "docs/operations/2026-08-27-171845-staging-harvester-acceptance.md"
)
REFRESH_RUNBOOK = Path("docs/operations/staging-data-refresh.md")


def _fenced_block_after(text: str, heading: str) -> str:
    section = text[text.index(heading) :]
    start = section.index("```text") + len("```text")
    end = section.index("```", start)
    return section[start:end]


def test_render_runbook_names_every_staging_owned_resource_and_boundary() -> None:
    text = DEPLOY_RUNBOOK.read_text(encoding="utf-8")

    for name in (
        "pushinweight-staging-web",
        "pushinweight-staging-harvest",
        "pushinweight-staging-headlines",
        "pushinweight-staging-headlines-broker",
        "pushinweight-staging-db",
    ):
        assert name in text
    assert "0 0 31 2 *" in text
    assert "shared provider quota" in text.lower()
    assert "plain `python manage.py run_cycle`" in text
    assert "production must remain running" in text.lower()


def test_acceptance_record_separates_stage_success_from_production_continuity() -> None:
    text = ACCEPTANCE_RECORD.read_text(encoding="utf-8")

    assert "## Staging acceptance evidence" in text
    assert "## Production continuity evidence" in text
    assert "RENDER_GIT_COMMIT" in text
    assert "current_database()" in text
    assert "call_state" in text
    assert "post_enrichment_states" in text
    assert "trend_narrative_provider_calls" in text
    assert "database_name_web" in text
    assert "database_name_harvester" in text
    assert "database_name_worker" in text
    assert "headline_budget_authorized_at_utc" in text
    assert "headline_per_brand_cost_cap_usd" in text
    assert "headline_provider_calls_delta" in text
    assert "max(fetched_at)" in text
    assert "redacted" in text.lower()
    assert "accepted|inconclusive|failed" in text


def test_same_cycle_staging_evidence_pins_lanes_identity_outputs_and_feed() -> None:
    text = ACCEPTANCE_RECORD.read_text(encoding="utf-8")

    for field in (
        "enrichment_claim_cap_aggregate: 5",
        "enrichment_claim_cap_current_cycle: 5",
        "enrichment_claim_cap_carryover: 0",
        "n_enrichment_claimed_current_cycle:",
        "n_enrichment_claimed_carryover:",
        "n_enrichment_succeeded_current_cycle:",
        "n_enrichment_succeeded_carryover:",
        "n_enrichment_pending_current_cycle:",
        "n_enrichment_pending_carryover:",
        "n_enrichment_failed_current_cycle:",
        "n_enrichment_failed_carryover:",
        "n_enrichment_deferred:",
        "n_enrichment_quarantined:",
        "inserted_post_ids:",
        "enrichment_current_cycle_post_ids:",
        "enrichment_carryover_post_ids:",
        "enrichment_state_facts:",
        "translation_status",
        "classification_status",
        "output_complete",
        "feed_hidden_before_terminal_success:",
        "feed_visible_after_terminal_success:",
        "translator_effective_model_redacted:",
        "translator_effective_host_redacted:",
        "classifier_effective_model_redacted:",
        "classifier_effective_host_redacted:",
    ):
        assert field in text

    assert "inserted_post_ids == enrichment_current_cycle_post_ids" in text
    assert "enrichment_carryover_post_ids == []" in text
    assert "Every inserted ID" in text
    assert "zero-result" in text.lower()
    assert "update-only" in text.lower()
    assert "no automatic retry" in text.lower()


def test_production_continuity_ledger_is_closed_correlated_and_fail_closed() -> None:
    text = ACCEPTANCE_RECORD.read_text(encoding="utf-8")

    assert "B0" in text
    assert "B1...Bn" in text
    assert "Bn+1" in text
    for field in (
        "boundary_label: B0|B1...Bn|Bn+1",
        "scheduled_boundary_utc:",
        "render_execution_id:",
        "render_trigger: schedule",
        "render_started_at:",
        "render_finished_at:",
        "render_status:",
        "render_service_id:",
        "render_deploy_sha:",
        "summary_run_id:",
        "summary_started_at:",
        "summary_finished_at:",
        "summary_status:",
        "summary_service_id:",
        "summary_deploy_sha:",
        "summary_hash:",
        "correlation_result: pass|fail",
    ):
        assert field in text

    assert "exactly one scheduled Render execution" in text
    assert "exactly one terminal canonical `HARVEST_SUMMARY`" in text
    assert "timestamps are supplemental" in text.lower()
    for permanent_failure in (
        "missing",
        "duplicate",
        "aborted",
        "lock-skipped",
        "manual",
        "uncorrelatable",
    ):
        assert permanent_failure in text
    assert "fails permanently" in text.lower()
    assert "summary schema v2" in text
    assert "historical v1" in text
    assert "counts-only" in text


def test_production_acceptance_binds_exact_cohort_quality_and_safe_rollback() -> None:
    text = ACCEPTANCE_RECORD.read_text(encoding="utf-8")

    for phrase in (
        "production caps `100/50/50`",
        "staging caps `5/5/0`",
        "same `CycleRunner`",
        "first of at most two natural candidate-SHA cycles",
        "first nonempty inserted cohort is immutable",
        "exactly one `HARVEST_COHORT` receipt",
        "candidate_cycle_cohort_receipt_hash:",
        "candidate_cycle_cohort_summary_hash:",
        "non_zh_hans_text_zh_cn_numerator:",
        "non_zh_hans_text_zh_cn_denominator:",
        "non_zh_hans_text_zh_cn_percentage:",
        "commentary_en_valid_numerator:",
        "commentary_zh_cn_valid_numerator:",
        "quality_gate: pass|fail",
        "N=50 requires 50/50",
        "docs/analysis/harvester/",
        "--latest 50 --json",
        "--tweet-id",
        "--report",
        "exactly twice",
        "full source text",
        "persisted translations and commentaries",
        "durable enrichment states",
        "provider-call evidence",
        "pre_promotion_sha:",
        "rollback_route:",
        "release_operator:",
        "continuity_observer:",
        "rollback_decider:",
        "incident_owner:",
        "production_web_service: pushinweight-web",
        "production_harvester_service: pushinweight-harvest",
        "production_database_resource: pushinweight-db-shadow",
        "production_translator_effective_model_redacted:",
        "production_translator_effective_host_redacted:",
        "production_classifier_effective_model_redacted:",
        "production_classifier_effective_host_redacted:",
    ):
        assert phrase in text

    assert "ordinary auto-deploy" in text
    assert "natural cron" in text
    assert "Never reconstruct the cohort from timestamps" in text
    assert "Do not suspend production" in text
    assert "Do not reschedule production" in text
    assert "Do not manually trigger production" in text
    assert "Do not apply a production Blueprint" in text


def test_pre_promotion_feed_blast_radius_is_read_only_and_thresholded() -> None:
    text = ACCEPTANCE_RECORD.read_text(encoding="utf-8")

    for field in (
        "feed_eligible_global_count:",
        "feed_default_limit: 50",
        "feed_default_page_count:",
        "feed_page_fill_result: pass|fail",
        "feed_query_round_trips:",
        "feed_candidate_median_ms:",
        "feed_candidate_max_ms:",
        "feed_blast_radius_result: pass|fail",
    ):
        assert field in text
    assert "read-only" in text.lower()
    assert "fewer than 50 rows when at least 50 eligible rows exist" in text
    assert "fails promotion" in text.lower()


def test_evidence_examples_are_secret_free() -> None:
    text = ACCEPTANCE_RECORD.read_text(encoding="utf-8")
    staging = _fenced_block_after(text, "## Staging acceptance evidence")
    production = _fenced_block_after(text, "## Production release evidence")

    for block in (staging, production):
        assert "https://" not in block
        assert "postgresql://" not in block
        assert "DATABASE_URL" not in block
        assert "Bearer " not in block
        assert "api_key" not in block.lower()
        assert "token:" not in block.lower()


def test_render_runbook_points_to_zero_disruption_same_cycle_release_contract() -> None:
    text = DEPLOY_RUNBOOK.read_text(encoding="utf-8")

    assert "staging `5/5/0`" in text
    assert "production `100/50/50`" in text
    assert "same `CycleRunner`" in text
    assert "closed continuity ledger" in text
    assert "exactly one scheduled Render execution" in text
    assert "terminal canonical `HARVEST_SUMMARY`" in text
    assert "bounded `HARVEST_COHORT`" in text
    assert "No production suspension, schedule change, manual run, or Blueprint" in text
    assert "ordinary auto-deploy and natural cron" in text


def test_secret_rotation_verifies_replacement_before_revoking_prior_value() -> None:
    text = ACCEPTANCE_RECORD.read_text(encoding="utf-8")
    replacement = text.index("Install the replacement")
    verification = text.index("Verify the guarded staging path")
    revocation = text.index("Revoke the prior value")

    assert replacement < verification < revocation
    assert "Never paste" in text
    assert "suspected exposure" in text


def test_refresh_runbook_requires_quiescence_before_and_resume_after_verify() -> None:
    text = REFRESH_RUNBOOK.read_text(encoding="utf-8")

    quiesce = text.index("## Quiesce the staging work boundary")
    refresh = text.index("## Preflight and refresh")
    resume = text.index("Only after `verify`")
    assert quiesce < refresh < resume
    assert "staging_headline_worker_active" in text
    assert "staging_headline_queue_not_empty" in text
    assert "staging_headline_envelope_present" in text
    assert "unacked_index" in text
    assert "trend-narratives*" in text
    assert "harvest_lock_unavailable" in text
