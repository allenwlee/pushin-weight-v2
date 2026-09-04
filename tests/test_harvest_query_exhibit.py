"""Current seven-call query exhibit and offline spend sensitivity.

This is the single exact-string exhibit for the live policy planner.  The
planner currently derives co-packs before handle tiers, so its stable logical
order is ``A, B1, C1, C2, C3, B2, B3``.  Keeping that order here documents the
runtime surface without changing the planner to match an older appendix
ordering.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from scripts.harvest_cost.engine import cost_cycle_from_summary
from scripts.harvest_cost.pricing import PricingRates
from x_monitor.harvest_policy import load_policy
from x_monitor.query_plan import plan_calls
from x_monitor.specs_from_policy import (
    primary_keywords_from_policy,
    specs_from_policy,
    validate_derived_call_ids,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "config" / "harvest_policy.yaml"
SMOKE_SUMMARY_PATH = REPO_ROOT / "tests" / "harvester_costs" / "_smoke" / "ae1.json"

# This is intentionally the planner's order, not the historical Appendix
# presentation order.  Call order is stable because specs_from_policy emits
# B1, C packs, then handle tiers.
EXPECTED_PLANNER_CALL_ORDER = ("A", "B1", "C1", "C2", "C3", "B2", "B3")

EXPECTED_QUERY_EXHIBIT = {
    "A": "(list:2067062923525275922) min_faves:0",
    "B1": (
        "((DeepSeek OR 深度求索) OR (dots3-note OR dots studio OR \"dots 3 note\" "
        "OR \"dots-3-note\" OR \"dots.3-note\" OR \"dots3 note\" OR "
        "\"dots-studio\" OR dots.ocr OR dots.tts OR dots.llm1 OR dots.vlm OR "
        "dots.mocr OR dots3 OR dots4) "
        "OR (Hunyuan OR 混元 OR 腾讯混元 OR Hy3 OR Hy4 OR Hy5 OR Hy4-preview "
        "OR Hy5-preview) OR (Hailuo OR MiniMax OR 海螺) OR (Qwen OR Qwen3 OR "
        "通义千问) OR (StepFun OR 阶跃星辰)) min_faves:0"
    ),
    "C1": (
        "((Llama OR Llama 3 OR Llama 4 OR Meta Llama OR Code Llama) OR "
        "(MiMo OR Xiaomi MiMo OR 小米 MiMo) OR (Mistral OR Mixtral) OR "
        "(Kimi OR Moonshot AI OR 月之暗面 OR 暗面 OR MoonshotAI) OR "
        "(Yi OR 01.AI OR 零一万物 OR Yi LLM OR Yi-VL OR Yi-Coder)) "
        "(llm OR model OR api OR agentic OR huggingface) min_faves:0"
    ),
    "C2": (
        "((ERNIE OR 文心一言) OR (Upstage OR Solar Pro OR Solar LLM OR 업스테이지)) "
        "(llm OR model OR api OR agentic OR huggingface OR baidu OR 文心) "
        "min_faves:0"
    ),
    "C3": (
        '(((Doubao OR ByteDance) OR (Kuaishou OR KwaiYii) OR '
        '(SenseChat OR SenseTime) OR (glm OR ChatGLM OR Zhipu OR 智谱 OR Z.ai '
        'OR GLM-4 OR GLM-5 OR GLM-6)) (llm OR model OR api OR agentic OR huggingface) '
        'OR ("Ox Alpha" OR OxAlpha OR ox-alpha)) min_faves:0'
    ),
    "B2": (
        "(@MiniMaxAgent OR @MiniMax_AI OR @hailuo_ai OR @Ali_TongyiLab OR "
        "@Alibaba_Qwen OR @deepseek_ai OR @AntLingAGI OR @TheInclusionAI OR "
        "@ZhihuFrontier OR @robbyant_brain OR @MistralAI OR @StepFun_ai OR "
        "@stepfunai OR @TencentHunyuan OR @NVIDIAAI OR @NVIDIAAIDev OR "
        "@LG_AI_Research OR @SakanaAILabs) min_faves:0"
    ),
    "B3": (
        "(@XiaomiMiMo OR @XiaomiMiMoDevs OR @Kimi_Moonshot OR @ErnieforDevs OR "
        "@PaddlePaddle OR @AIatMeta OR @BytePlusGlobal OR @bytedanceoss OR "
        "@doubaoai OR @01AI_Yi OR @Kling_ai OR @SenseTime_AI OR @upstageai) "
        "min_faves:0"
    ),
}


def _planned_calls():
    policy = load_policy(POLICY_PATH)
    specs = validate_derived_call_ids(specs_from_policy(policy))
    return plan_calls(
        2067062923525275922,
        specs,
        primary_keywords=primary_keywords_from_policy(policy),
    )


def test_current_planner_order_and_exact_queries_match_exhibit() -> None:
    """The exact strings sent by the policy-derived planner stay reviewable."""
    calls = _planned_calls()
    assert tuple(call.call_id for call in calls) == EXPECTED_PLANNER_CALL_ORDER
    assert {call.call_id: call.query_string for call in calls} == EXPECTED_QUERY_EXHIBIT
    assert all(call.query_length == len(call.query_string) for call in calls)


def test_dots_family_tokens_are_on_b1_and_in_onboard_csv() -> None:
    """Call-chain pin: family product names ride B1; bare 'dots' does not."""
    import csv

    calls = _planned_calls()
    b1 = next(call.query_string for call in calls if call.call_id == "B1")
    for token in (
        '"dots 3 note"',
        '"dots-3-note"',
        '"dots.3-note"',
        '"dots3 note"',
        '"dots-studio"',
        "dots.ocr",
        "dots.tts",
        "dots.llm1",
        "dots.vlm",
        "dots.mocr",
    ):
        assert token in b1
    policy = load_policy(POLICY_PATH)
    assert "dots" not in policy.brands["dots"].tokens

    csv_path = REPO_ROOT / "config/brands/2026-08-31-013447-harvester-quality-upgrade.csv"
    with csv_path.open(newline="", encoding="utf-8") as stream:
        dots_row = next(
            row for row in csv.DictReader(stream) if row["brand_nickname"] == "dots"
        )
    aliases = dots_row["keyword_aliases"].split("|")
    for token in (
        "dots 3 note",
        "dots-3-note",
        "dots.3-note",
        "dots3 note",
        "dots-studio",
        "dots.ocr",
        "dots.tts",
        "dots.llm1",
        "dots.vlm",
        "dots.mocr",
    ):
        assert token in aliases
    assert "dots" not in aliases
    assert "dots" != dots_row["keyword_primary"]


def test_exhibit_keeps_the_seven_logical_call_contract() -> None:
    calls = _planned_calls()
    assert len(calls) == 7
    assert {call.call_id for call in calls} == {
        "A", "B1", "B2", "B3", "C1", "C2", "C3"
    }
    assert all(call.query_length < 512 for call in calls)


def test_smoke_cost_sensitivity_is_offline_and_keeps_seven_calls() -> None:
    """B1/C3 volume changes are visible without provider or DB access."""
    summary = json.loads(SMOKE_SUMMARY_PATH.read_text(encoding="utf-8"))
    assert len(summary["calls"]) == 7

    rates = PricingRates(
        tweet_credits=15.0,
        call_floor_credits=15.0,
        credits_per_usd=100_000.0,
    )
    baseline = cost_cycle_from_summary(summary, rates)

    sensitivity = deepcopy(summary)
    deltas = {"B1": 7, "C3": 4}
    for call in sensitivity["calls"]:
        call["n_results"] += deltas.get(call["call_id"], 0)
    changed = cost_cycle_from_summary(sensitivity, rates)

    assert len(sensitivity["calls"]) == 7
    assert changed.total_credits - baseline.total_credits == (
        sum(deltas.values()) * 15
    )
    assert changed.total_credits > baseline.total_credits
