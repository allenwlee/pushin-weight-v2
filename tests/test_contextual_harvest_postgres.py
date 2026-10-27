"""Real shared writers and PostgreSQL; only external transports/enrichment are faked."""
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.management import call_command

from core.models import BrandKeyword, Post, PostBrand, PostBrandMention
from monitor import cycle
from monitor.cycle import CycleRunner, _build_brand_index
from tests.test_backfill_pipeline import page
from tests.test_backfill_prefetch import http_pages, pipeline  # noqa: F401
from tests.test_backfill_staging import staged_job
from x_monitor.config import load_config

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def labels(post_id):
    return set(PostBrand.objects.filter(post_id=post_id).values_list("brand_id", flat=True))


def test_keyword_reconciliation_is_scoped_idempotent_and_preflight_required(seeded_policy_keywords):
    BrandKeyword.objects.filter(brand_id="llama", pattern__in=["meta", "muse", "muse voice"]).delete()
    with pytest.raises(ValueError, match="coverage is incomplete"):
        _build_brand_index(["llama"])
    before = set(BrandKeyword.objects.values_list("brand_id", "pattern", "is_primary", "is_regex"))
    call_command("onboard_brand", sync_policy_keywords=["llama"], dry_run=True, stdout=StringIO())
    assert set(BrandKeyword.objects.values_list("brand_id", "pattern", "is_primary", "is_regex")) == before
    call_command("onboard_brand", sync_policy_keywords=["llama"], stdout=StringIO())
    after = set(BrandKeyword.objects.values_list("brand_id", "pattern", "is_primary", "is_regex"))
    assert after - before == {("llama", t, False, False) for t in ["meta", "muse", "muse voice"]}
    out = StringIO()
    call_command("onboard_brand", sync_policy_keywords=["llama"], stdout=out)
    assert '"additions": []' in out.getvalue()
    _build_brand_index(["llama"])


@pytest.mark.parametrize("dry_run", [False, True])
def test_keyword_reconciliation_rejects_regex_collision_without_partial_writes(seeded_policy_keywords, dry_run):
    from django.core.management.base import CommandError

    BrandKeyword.objects.filter(brand_id="llama", pattern__in=["meta", "muse"]).delete()
    BrandKeyword.objects.create(brand_id="llama", pattern="muse", is_regex=True, is_primary=False)
    before = set(BrandKeyword.objects.values_list("brand_id", "pattern", "is_regex"))
    with pytest.raises(CommandError, match="Existing regex conflicts"):
        call_command("onboard_brand", sync_policy_keywords=["llama"], dry_run=dry_run, stdout=StringIO())
    assert set(BrandKeyword.objects.values_list("brand_id", "pattern", "is_regex")) == before


def test_scheduled_cycle_persists_context_and_deduplicates_c1_c4(monkeypatch, seeded_policy_keywords):
    seen, cohorts = [], []
    now = datetime.now(UTC)
    cfg = load_config(Path("config.yaml"))
    cfg.discovery.rare_types.enabled = False
    cfg.discovery.rare_types.targeted_extraction_enabled = False
    calls = cycle.plan_calls_for_cycle(cfg, scheduled_exclusions=True)
    by_query = {c.query_string: c.call_id for c in calls}
    texts = {"B1": [("81001", "Qwen Code 海螺贝壳"), ("81002", "Qwen 混元太極拳"),
                    ("81003", "海螺H3 视频"), ("81004", "腾讯混元")],
             "C1": [("81005", "Kimi model and Muse Wonder invite code")],
             "C4": [("81005", "Kimi model and Muse Wonder invite code"),
                    ("2113940624651006275", "Meta Muse AIへの招待 code") ]}

    class Api:
        timeout_s = 1
        max_retries = 0
        def run_search(self, query, **kwargs):
            cid = by_query[query]
            seen.append(cid)
            return [{"id": tid, "text": text, "created_at": now.isoformat(),
                     "author_id": "u10-" + tid, "author_handle": "u10test"}
                    for tid, text in texts.get(cid, [])], False

    monkeypatch.setattr(cycle.XClient, "from_env", classmethod(lambda cls, purpose: Api()))
    monkeypatch.setattr(CycleRunner, "_replay_backlog", lambda self, **kwargs: [])
    monkeypatch.setattr(CycleRunner, "_run_post_fetch", lambda self, items, **kwargs: cohorts.extend(str(i.get("id") or i.get("tweet_id")) for i in items) or {})
    monkeypatch.setattr(cycle, "run_due_reconciliation", lambda **kwargs: SimpleNamespace(status="not_due", observed=0, activated=0, deactivated=0, snapshot_id=None, degraded=[]))
    monkeypatch.setattr(CycleRunner, "_request_synthesis_prewarm", lambda *args, **kwargs: None)
    result = CycleRunner(cfg=cfg, cycle_kind="scheduled").run()
    assert seen == ["A", "B1", "C1", "C2", "C3", "C4", "B2", "B3"]
    assert result["totals"]["n_calls_run"] == 8
    assert labels("81001") == labels("81002") == {"qwen"}
    assert labels("81003") == {"minimax"}
    assert labels("81004") == {"hunyuan"}
    assert labels("81005") == {"moonshot_kimi", "llama"}
    assert labels("2113940624651006275") == {"llama"}
    assert Post.objects.filter(pk="81005").count() == 1
    assert {"81001", "81002", "81005", "2113940624651006275"} <= set(cohorts)
    assert not PostBrandMention.objects.filter(post_id__in=["81001", "81002"], brand_id__in=["minimax", "hunyuan"]).exists()


def test_staging_backfill_uses_same_policy_and_persists_memberships(http_pages, monkeypatch):  # noqa: F811
    from monitor.backfill_collection import execute_job
    job = staged_job(monkeypatch, 1)
    import copy

    from core.collection_jobs import register_job, set_job_state
    definition = copy.deepcopy(job.definition)
    definition["scope"]["brands"] = ["qwen", "minimax", "hunyuan", "llama"]
    job = register_job(job_key="u10-context-staging", source=job.source, purpose="content",
                       operation="x_backfill", mode="historical", definition=definition)
    job = set_job_state(job.pk, "ready")
    body = page("82001")
    body["tweets"][0]["text"] = "Qwen Code 海螺贝壳 混元太極拳"
    quoted = page("82002")["tweets"][0]
    quoted["text"] = "Muse Voice 招待"
    body["tweets"][0]["quoted_tweet"] = quoted
    with http_pages(lambda params: body) as state:
        result = execute_job(job.pk)
    assert result["collection_drained"]
    assert len(state["requests"]) == 1
    assert labels("82001") == {"qwen", "llama"}
    assert not PostBrandMention.objects.filter(post_id="82001", brand_id__in=["minimax", "hunyuan"]).exists()
