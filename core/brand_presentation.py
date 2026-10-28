"""Curated brand presentation shared by seeding and bounded data updates."""

# `llama` is the retained internal identifier for the broader Meta brand.
META_BRAND_NAMES = {
    "display_name": "Meta",
    "display_name_en": "Meta",
    "display_name_zh_cn": "Meta",
}

BRAND_ACCENT_COLORS = {
    "deepseek": "#2243e6",
    "qwen": "#ff7018",
    "minimax": "#eb3568",
    "glm": "#1c7ff8",
    "mimo": "#ff6900",
    "moonshot_kimi": "#047afe",
    "inclusionai": "#4fb5ff",
    "mistral": "#f32e02",
    "stepfun": "#00f5e7",
    "ernie": "#2436d8",
    "hunyuan": "#5cb9ff",
    "llama": "#0089f4",
    "nemo_megatron": "#76b900",
    "doubao": "#3c8bff",
    "exaone": "#df3b8a",
    "kuaishou": "#489034",
    "upstage": "#7c59f5",
    "yi": "#001a12",
    "sensechat": "#e83020",
    "sakana_ai": "#e00000",
    "dots": "#ff2442",
}


# Brand marks shown in the chart legend, post rows and General brand pills,
# under monitor/static/brand-logos/. Brands without an entry show text only.
BRAND_LOGO_FILES = {
    "deepseek": "deepseek.svg",
    "qwen": "qwen.svg",
    "minimax": "minimax.svg",
    "glm": "glm.svg",
    "mimo": "mimo.svg",
    "moonshot_kimi": "moonshot_kimi.jpg",
    "inclusionai": "inclusionai.jpg",
    "mistral": "mistral.svg",
    "stepfun": "stepfun.svg",
    "ernie": "ernie.svg",
    "hunyuan": "hunyuan.svg",
    "llama": "llama.svg",
    "nemo_megatron": "nemo_megatron.svg",
    "doubao": "doubao.svg",
    "exaone": "exaone.png",
    "kuaishou": "kuaishou.svg",
    "upstage": "upstage.svg",
    "yi": "yi.jpg",
    "sensechat": "sensechat.png",
    "sakana_ai": "sakana_ai.png",
    "dots": "dots.png",
}


def brand_logo_urls() -> dict[str, str]:
    """Return each logo's served static URL (hashed in production)."""
    from django.templatetags.static import static

    return {
        nickname: static(f"brand-logos/{filename}")
        for nickname, filename in BRAND_LOGO_FILES.items()
    }
