from __future__ import annotations

from pathlib import Path

DEPLOY_RUNBOOK = Path("docs/deploy/render.md")
ACCEPTANCE_RECORD = Path(
    "docs/operations/2026-08-27-171845-staging-harvester-acceptance.md"
)
REFRESH_RUNBOOK = Path("docs/operations/staging-data-refresh.md")


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
