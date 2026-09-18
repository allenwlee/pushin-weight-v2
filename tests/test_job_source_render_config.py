from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _service(path: str, name: str) -> dict:
    blueprint = yaml.safe_load((ROOT / path).read_text())
    matches = [item for item in blueprint["services"] if item.get("name") == name]
    assert len(matches) == 1
    return matches[0]


def test_production_job_sync_is_a_separate_credential_free_cron():
    service = _service("render.yaml", "pushinweight-jobs")
    assert service["type"] == "cron"
    assert service["schedule"] == "17 */6 * * *"
    assert service["startCommand"] == "python manage.py sync_job_sources"
    serialized = yaml.safe_dump(service)
    assert "run_cycle" not in serialized
    assert "TWITTER" not in serialized
    assert "DEEPSEEK_API_KEY" not in serialized
    assert "CELERY" not in serialized


def test_staging_job_sync_is_manual_only_and_tracks_staging_branch():
    service = _service("render-staging.yaml", "pushinweight-staging-jobs")
    assert service["type"] == "cron"
    assert service["branch"] == "staging"
    assert service["schedule"] == "0 0 31 2 *"
    assert service["startCommand"] == "python manage.py sync_job_sources"
