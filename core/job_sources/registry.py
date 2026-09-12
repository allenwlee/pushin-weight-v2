from __future__ import annotations

from .types import SourceDefinition

SOURCES: dict[str, SourceDefinition] = {
    "qwen": SourceDefinition(
        key="qwen",
        brand_nickname="qwen",
        display_name="Qwen",
        careers_url="https://talent.quark.cn/off-campus/position-list?lang=zh",
        allowed_hosts=frozenset({"talent.quark.cn"}),
        adapter="qwen",
    ),
    "deepseek": SourceDefinition(
        key="deepseek",
        brand_nickname="deepseek",
        display_name="DeepSeek",
        careers_url="https://talent.deepseek.com/",
        allowed_hosts=frozenset({"talent.deepseek.com", "app.mokahr.com"}),
        adapter="deepseek",
        adapter_options={
            "moka_org": "high-flyer",
            "moka_site": "140576",
            "moka_url": "https://app.mokahr.com/social-recruitment/high-flyer/140576#/jobs",
        },
    ),
    "minimax": SourceDefinition(
        key="minimax",
        brand_nickname="minimax",
        display_name="MiniMax",
        careers_url="https://vrfi1sk8a0.jobs.feishu.cn/379481/",
        allowed_hosts=frozenset({"www.minimax.cn", "vrfi1sk8a0.jobs.feishu.cn"}),
        adapter="feishu",
        adapter_options={"website_path": "379481"},
    ),
    "zhipu": SourceDefinition(
        key="zhipu",
        brand_nickname="glm",
        display_name="Z.ai / Zhipu AI",
        careers_url="https://app.mokahr.com/social-recruitment/zphz/148983?locale=zh-CN#/jobs",
        allowed_hosts=frozenset({"www.zhipuai.cn", "app.mokahr.com"}),
        adapter="moka",
        adapter_options={"moka_org": "zphz", "moka_site": "148983"},
    ),
    "kimi": SourceDefinition(
        key="kimi",
        brand_nickname="moonshot_kimi",
        display_name="Kimi / Moonshot AI",
        careers_url="https://app.mokahr.com/social-recruitment/moonshot/148506#/jobs",
        allowed_hosts=frozenset({"careers.kimi.com", "app.mokahr.com"}),
        adapter="moka",
        adapter_options={"moka_org": "moonshot", "moka_site": "148506"},
    ),
}


def get_source(source_key: str) -> SourceDefinition:
    try:
        return SOURCES[source_key]
    except KeyError as exc:
        raise ValueError(f"unknown job source: {source_key}") from exc
