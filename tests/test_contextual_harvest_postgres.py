"""Real shared writers and PostgreSQL; only external transports/enrichment are faked."""
import json
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


@pytest.mark.parametrize("brand,missing", [
    ("llama", ["meta", "muse", "muse voice"]),
    ("nemo_megatron", ["tensorrt", "cosmos"]),
])
def test_keyword_reconciliation_is_scoped_idempotent_and_preflight_required(seeded_policy_keywords, brand, missing):
    BrandKeyword.objects.filter(brand_id=brand, pattern__in=missing).delete()
    with pytest.raises(ValueError, match="coverage is incomplete"):
        _build_brand_index([brand])
    before = set(BrandKeyword.objects.values_list("brand_id", "pattern", "is_primary", "is_regex"))
    call_command("onboard_brand", sync_policy_keywords=[brand], dry_run=True, stdout=StringIO())
    assert set(BrandKeyword.objects.values_list("brand_id", "pattern", "is_primary", "is_regex")) == before
    call_command("onboard_brand", sync_policy_keywords=[brand], stdout=StringIO())
    after = set(BrandKeyword.objects.values_list("brand_id", "pattern", "is_primary", "is_regex"))
    assert after - before == {(brand, t, False, False) for t in missing}
    out = StringIO()
    call_command("onboard_brand", sync_policy_keywords=[brand], stdout=out)
    assert '"additions": []' in out.getvalue()
    _build_brand_index([brand])


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
    # Select the owning block, not an obsolete hard-coded C5/C6 slot. Assertions
    # below remain independent expected labels and actual persisted evidence.
    from x_monitor.harvest_policy import load_policy
    from x_monitor.specs_from_policy import specs_from_policy
    owner = {n: s.call_id for s in specs_from_policy(load_policy("config/harvest_policy.yaml")) for n in s.component_names}
    rows = [
        ("qwen", "81001", "Qwen Code 海螺贝壳"),
        ("qwen", "81002", "Qwen 混元太極拳"),
        ("minimax", "81003", "海螺H3 视频"),
        ("hunyuan", "81004", "腾讯混元"),
        ("moonshot_kimi", "81005", "Kimi model and Muse Wonder invite code"),
        ("llama", "81005", "Kimi model and Muse Wonder invite code"),
        ("llama", "2113940624651006275", "Meta Muse AIへの招待 code"),
        ("nemo_megatron/models", "81006", "Nemotron 3 Ultra released"),
        ("nemo_megatron/company", "81007", "NVIDIA Cosmos released"),
        ("nemo_megatron/models", "81008", "Canary ASR benchmark"),
        ("nemo_megatron/company", "81009", "NVIDIA stock split tomorrow"),
        ("nemo_megatron/product-names", "81010", "Cosmos staking rewards"),
        ("nemo_megatron/software", "81011", "NVIDIA/TensorRT-LLM brings up DeepSeek-V4.1-Flash-NVFP4"),
        ("deepseek", "81011", "NVIDIA/TensorRT-LLM brings up DeepSeek-V4.1-Flash-NVFP4"),
        ("nemo_megatron/software", "81012", "Hand data questions to an agent https://t.co/example"),
        ("nemo_megatron/software", "81013", "cuDNN improves attention"),
        ("nemo_megatron/product-names", "81014", "Isaac Lab robot training"),
        ("hunyuan", "81101", "Hy4真的比deepseek-v4.1-flash 强么？"),
        ("moonshot_kimi", "81102", "K3.1 Pro from Modal"),
        ("ernie", "81103", "文心才是世界上最好的 AI！"),
        ("kuaishou", "81104", "Kling 4.0 Flash is now live on fal"),
        ("doubao", "81105", "Seedance 2.5 vs MiniMax H3"),
        ("mistral", "81106", "Llama 4 和 Codestral"),
        ("stepfun", "81107", "@StepFun_ai thanks for this"),
        ("sakana_ai", "81108", "SakanaAI released Namazu"),
        ("llama", "81109", "Meta model F1"),
        ("llama", "81110", "Meta model F1 with Cosmos"),
        ("llama", "81111", "Meta model F1 @AIatMeta"),
        ("mimo", "81112", "Xiaomi AI research"),
        ("mimo", "81113", "小米大模型更新"),
        ("mimo", "81114", "@XiaomiMiMoDevs thanks for this"),
        ("dots", "81115", "@dotsstudioai thanks for this"),
        ("dots", "81116", "DotsOCR model and Meta model F1 comparison"),
    ]
    texts = {}
    for block, tid, text in rows:
        texts.setdefault(owner[block], []).append((tid, text))


    class Api:
        base_url = "https://api.twitterapi.io"
        timeout_s = 1
        max_retries = 0
        def run_search(self, query, **kwargs):
            cid = by_query[query]
            seen.append(cid)
            results = [{"id": tid, "text": text, "created_at": now.isoformat(),
                     "author_id": "u10-" + tid, "author_handle": "u10test"}
                    for tid, text in texts.get(cid, [])]
            for item in results:
                if item["id"] == "81012":
                    item["entities"] = {"urls": [{"url": "https://t.co/example",
                        "expanded_url": "https://github.com/NVIDIA/auto-ontology"}]}
            exchange = self.on_exchange_start(
                "/twitter/tweet/advanced_search", {"query": query},
            )
            self.on_exchange_finish(exchange, {
                "outcome": "received", "status_code": 200,
                "body": json.dumps({"tweets": results}).encode(), "error_type": None,
            })
            return results, False

    monkeypatch.setattr(cycle.XClient, "from_env", classmethod(lambda cls, purpose: Api()))
    monkeypatch.setattr(CycleRunner, "_replay_backlog", lambda self, **kwargs: [])
    monkeypatch.setattr(CycleRunner, "_run_post_fetch", lambda self, items, **kwargs: cohorts.extend(str(i.get("id") or i.get("tweet_id")) for i in items) or {})
    monkeypatch.setattr(cycle, "run_due_reconciliation", lambda **kwargs: SimpleNamespace(status="not_due", observed=0, activated=0, deactivated=0, snapshot_id=None, degraded=[]))
    monkeypatch.setattr(CycleRunner, "_request_synthesis_prewarm", lambda *args, **kwargs: None)
    result = CycleRunner(cfg=cfg, cycle_kind="scheduled").run()
    assert seen == ["A", "B1", "C1", "C2", "C3", "C4", "B2", "B3", "B4"]
    assert result["totals"]["n_calls_run"] == 9
    assert labels("81001") == {"qwen"}
    assert labels("81002") == {"qwen"}
    assert labels("81003") == {"minimax"}
    assert labels("81004") == {"hunyuan"}
    assert labels("81005") == {"moonshot_kimi", "llama"}
    assert labels("2113940624651006275") == {"llama"}
    assert labels("81006") == labels("81007") == labels("81008") == {"nemo_megatron"}
    # Owner chose broad recall: ambiguous terms are deliberately retained.
    assert labels("81009") == labels("81010") == {"nemo_megatron"}
    assert labels("81011") == {"deepseek", "nemo_megatron"}
    assert Post.objects.filter(pk="81011").count() == 1
    assert labels("81012") == labels("81013") == labels("81014") == {"nemo_megatron"}
    assert Post.objects.get(pk="81012").text == "Hand data questions to an agent https://t.co/example"
    assert PostBrandMention.objects.get(post_id="81012", brand_id="nemo_megatron", source="url_keyword").raw_token == "https://github.com/NVIDIA/auto-ontology"
    assert Post.objects.filter(pk="81005").count() == 1
    assert {"81001", "81002", "81005", "2113940624651006275"} <= set(cohorts)
    assert not PostBrandMention.objects.filter(post_id__in=["81001", "81002"], brand_id__in=["minimax", "hunyuan"]).exists()
    for post_id, brand in [("81101","hunyuan"), ("81102","moonshot_kimi"), ("81103","ernie"),
                           ("81104","kuaishou"), ("81105","doubao"), ("81106","mistral"),
                           ("81107","stepfun"), ("81108","sakana_ai")]:
        assert brand in labels(post_id)
    assert PostBrandMention.objects.filter(post_id="81107", brand_id="stepfun", source="user_mention").exists()

    assert not Post.objects.filter(pk="81109").exists()
    assert labels("81110") == {"llama", "nemo_megatron"}
    assert labels("81111") == {"llama"}
    assert labels("81112") == labels("81113") == labels("81114") == {"mimo"}
    assert PostBrandMention.objects.filter(post_id="81114", brand_id="mimo", source="user_mention").exists()
    assert "dots" in labels("81116")
    assert labels("81115") == {"dots"}
    assert PostBrandMention.objects.filter(post_id="81115", brand_id="dots", source="user_mention").exists()


def test_staging_backfill_uses_same_policy_and_persists_memberships(http_pages, monkeypatch):  # noqa: F811
    from monitor.backfill_collection import execute_job
    job = staged_job(monkeypatch, 1)
    import copy

    from core.collection_jobs import register_job, set_job_state
    definition = copy.deepcopy(job.definition)
    definition["scope"]["brands"] = ["qwen", "minimax", "hunyuan", "llama", "nemo_megatron"]
    job = register_job(job_key="u10-context-staging", source=job.source, purpose="content",
                       operation="x_backfill", mode="historical", definition=definition)
    job = set_job_state(job.pk, "ready")
    body = page("82001")
    body["tweets"][0]["text"] = "Qwen Code 海螺贝壳 混元太極拳"
    quoted = page("82002")["tweets"][0]
    quoted["text"] = "Muse Voice 招待"
    body["tweets"][0]["quoted_tweet"] = quoted
    body["tweets"][0]["entities"] = {"urls": [{"url": "https://t.co/example",
        "expanded_url": "https://github.com/NVIDIA/auto-ontology"}]}
    with http_pages(lambda params: body) as state:
        result = execute_job(job.pk)
    assert result["collection_drained"]
    assert len(state["requests"]) == 1
    assert labels("82001") == {"qwen", "llama", "nemo_megatron"}
    assert PostBrandMention.objects.filter(post_id="82001", source="url_keyword", brand_id="nemo_megatron").exists()
    assert not PostBrandMention.objects.filter(post_id="82001", brand_id__in=["minimax", "hunyuan"]).exists()
