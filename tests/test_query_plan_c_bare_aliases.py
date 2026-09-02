"""U2 regression pins for mixed C queries with bare aliases.

The C renderer must keep a constrained pack and a bare-alias escape hatch in
one logical call.  These tests intentionally exercise policy loading,
specification derivation, planning, and the fake provider boundary.
"""

from __future__ import annotations

import pytest

from monitor.cycle import CycleRunner
from x_monitor.config import Config, SearchConfig
from x_monitor.harvest_policy import BrandPolicy, CoPack, HarvestPolicy, load_policy
from x_monitor.query_plan import XQuerySpec, _build_query, plan_calls
from x_monitor.specs_from_policy import specs_from_policy


def _c3_policy() -> HarvestPolicy:
    return HarvestPolicy(
        brands={
            "mimo": BrandPolicy(
                nickname="mimo",
                paths=frozenset({"co"}),
                tokens=("MiMo",),
                co=("llm",),
            ),
            "ernie": BrandPolicy(
                nickname="ernie",
                paths=frozenset({"co"}),
                tokens=("ERNIE",),
                co=("llm",),
            ),
            "doubao": BrandPolicy(
                nickname="doubao",
                paths=frozenset({"co"}),
                tokens=("Doubao", "ByteDance"),
                co=("llm", "model", "api", "agentic", "huggingface"),
            ),
            "kuaishou": BrandPolicy(
                nickname="kuaishou",
                paths=frozenset({"co"}),
                tokens=("Kuaishou", "KwaiYii"),
                co=("llm", "model", "api", "agentic", "huggingface"),
            ),
            "sensechat": BrandPolicy(
                nickname="sensechat",
                paths=frozenset({"co"}),
                tokens=("SenseChat", "SenseTime"),
                co=("llm", "model", "api", "agentic", "huggingface"),
            ),
            "glm": BrandPolicy(
                nickname="glm",
                paths=frozenset({"co"}),
                tokens=(
                    "glm",
                    "GLM-4",
                    "GLM-5",
                    "GLM-6",
                    "ChatGLM",
                    "Zhipu",
                    "智谱",
                    "Z.ai",
                ),
                co=("llm", "model", "api", "agentic", "huggingface"),
                c_bare_aliases=("\"Ox Alpha\"", "OxAlpha", "ox-alpha"),
            ),
        },
        co_packs=(
            CoPack(brand_nicknames=("mimo",)),
            CoPack(brand_nicknames=("ernie",)),
            CoPack(brand_nicknames=("doubao", "kuaishou", "sensechat", "glm")),
        ),
    )


def test_policy_loader_preserves_c_bare_aliases(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text(
        """brands:
  glm:
    paths: [co]
    tokens: [glm]
    co: [llm]
    c_bare_aliases: ['"Ox Alpha"', OxAlpha, ox-alpha]
co_packs:
  - [glm]
""",
        encoding="utf-8",
    )

    policy = load_policy(path)

    assert policy.brand("glm").c_bare_aliases == (
        '"Ox Alpha"',
        "OxAlpha",
        "ox-alpha",
    )


def test_policy_loader_rejects_c_bare_aliases_without_co_path(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text(
        """brands:
  glm:
    paths: [bare]
    tokens: [glm]
    c_bare_aliases: ['"Ox Alpha"']
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="c_bare_aliases.*co.*path"):
        load_policy(path)


def test_specs_union_c_bare_aliases_from_the_co_pack():
    spec = specs_from_policy(_c3_policy())[-1]

    assert spec.c_bare_aliases == ['"Ox Alpha"', "OxAlpha", "ox-alpha"]


def test_c3_fixture_renders_exact_appendix_shape():
    spec = specs_from_policy(_c3_policy())[-1]
    assert spec.call_id == "C3"

    rendered = _build_query(spec)
    assert rendered == (
        '(((Doubao OR ByteDance) OR (Kuaishou OR KwaiYii) OR '
        '(SenseChat OR SenseTime) OR (glm OR GLM-4 OR GLM-5 OR GLM-6 OR '
        'ChatGLM OR Zhipu OR 智谱 OR Z.ai)) (llm OR model OR api OR agentic OR '
        'huggingface) OR ("Ox Alpha" OR OxAlpha OR ox-alpha)) min_faves:0'
    )
    assert len(rendered) == 247


def test_c_renderer_without_aliases_byte_matches_existing_shape():
    spec = XQuerySpec(
        brands={"glm": ["glm", "GLM-5"]},
        co_occurrence=["llm", "model"],
        min_faves=0,
        call_id="C3",
    )

    assert _build_query(spec) == "(glm OR GLM-5) (llm OR model) min_faves:0"


def test_bare_alias_branch_remains_available_without_a_co_group():
    spec = XQuerySpec(
        brands={"glm": ["glm"]},
        c_bare_aliases=['"Ox Alpha"'],
        call_id="C3",
    )

    assert _build_query(spec) == '((glm) OR ("Ox Alpha")) min_faves:0'


def test_cycle_fetch_seam_captures_planned_query_before_fake_provider():
    spec = specs_from_policy(_c3_policy())[-1]
    calls = plan_calls(2067062923525275922, [spec])
    planned = calls[-1]

    class FakeApi:
        def __init__(self):
            self.calls: list[dict] = []

        def run_search(self, query, **kwargs):
            self.calls.append({"query": query, **kwargs})
            return [], False

    api = FakeApi()
    runner = CycleRunner(
        cfg=Config(
            enabled_models=["glm"],
            daily_ceiling=100,
            search=SearchConfig(max_results=20, max_pages=1, max_per_page=20),
        )
    )
    assert runner._fetch_tweets(planned, api, window=(100, 200)) == ([], "ok")

    assert api.calls[0]["query"] == _build_query(spec)
    assert api.calls[0]["query"] == planned.query_string

    too_long = XQuerySpec(
        brands={"glm": ["glm"]},
        co_occurrence=["x" * 600],
        c_bare_aliases=["Ox Alpha"],
        call_id="C3",
    )
    with pytest.raises(ValueError, match="query length"):
        plan_calls(2067062923525275922, [too_long])
    assert len(api.calls) == 1
