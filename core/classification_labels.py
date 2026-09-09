"""Canonical active labels plus legacy English/Chinese compatibility copy."""

from __future__ import annotations

POST_TYPE_LABELS: dict[str, dict[str, str]] = {
    "releases_updates": {
        "en": "Releases & Updates",
        "zh-cn": "发布与更新",
        "ja": "リリース・アップデート",
    },
    "buzz_releases": {"en": "Releases & Updates", "zh-cn": "发布与更新"},
    "hands_on_usage": {
        "en": "Hands-On Usage",
        "zh-cn": "实际使用",
        "ja": "使用体験",
    },
    "results_evaluations": {
        "en": "Results and Evaluations",
        "zh-cn": "结果与评测",
        "ja": "結果・評価",
    },
    "performance_comparisons": {
        "en": "Results and Evaluations",
        "zh-cn": "结果与评测",
    },
    "questions_requests": {
        "en": "Questions & Requests",
        "zh-cn": "问题与请求",
        "ja": "質問・要望",
    },
    "feedback_questions": {"en": "Questions & Requests", "zh-cn": "问题与请求"},
    "advertising_marketing": {
        "en": "Advertising & Marketing",
        "zh-cn": "广告营销",
        "ja": "広告・マーケティング",
    },
    "events_opportunities": {
        "en": "Events & Opportunities",
        "zh-cn": "活动与机会",
        "ja": "イベント・機会",
    },
    "event_announcement": {"en": "Events & Opportunities", "zh-cn": "活动与机会"},
    "opinions_reactions": {
        "en": "Opinions & Reactions",
        "zh-cn": "观点与反应",
        "ja": "意見・反応",
    },
    "research_explanations": {
        "en": "Research & Explanations",
        "zh-cn": "研究与解释",
        "ja": "研究・解説",
    },
    "business_finance": {
        "en": "Business & Finance",
        "zh-cn": "商业与金融",
        "ja": "ビジネス・金融",
    },
    "other": {"en": "Other", "zh-cn": "其他", "ja": "その他"},
}

PRODUCT_LABEL_LABELS: dict[str, dict[str, str]] = {
    "bug": {"en": "Bug", "zh-cn": "缺陷", "ja": "バグ"},
    "complaint": {"en": "Complaint", "zh-cn": "投诉", "ja": "苦情"},
    "testimonial": {
        "en": "Testimonial",
        "zh-cn": "推荐评价",
        "ja": "推奨の声",
    },
    "ideas_requests": {
        "en": "Ideas & requests",
        "zh-cn": "想法与请求",
        "ja": "アイデア・要望",
    },
    "product_request": {"en": "Ideas & requests", "zh-cn": "想法与请求"},
    "misinformation": {
        "en": "Misinformation",
        "zh-cn": "可能误导的信息",
        "ja": "誤情報の可能性",
    },
}

SENTIMENT_LABELS: dict[str, dict[str, str]] = {
    "positive": {"en": "Positive", "zh-cn": "正面", "ja": "ポジティブ"},
    "negative": {"en": "Negative", "zh-cn": "负面", "ja": "ネガティブ"},
    "neutral": {"en": "Neutral", "zh-cn": "中性", "ja": "中立"},
    "mixed": {"en": "Mixed", "zh-cn": "混合", "ja": "賛否混在"},
}

DISCOURSE_LABELS: dict[str, dict[str, str]] = {
    "genuine_hype": {"en": "Genuine Hype", "zh-cn": "真实热度"},
    "sarcasm": {"en": "Sarcasm", "zh-cn": "讽刺"},
    "dunk_yingyang": {"en": "Dunk / Yingyang", "zh-cn": "阴阳怪气"},
    "self_deprecation": {"en": "Self-Deprecation", "zh-cn": "自嘲"},
    "cope": {"en": "Cope", "zh-cn": "自我安慰"},
    "fud": {"en": "FUD", "zh-cn": "恐惧不确定怀疑"},
    "distillation_accusation": {"en": "Distillation Accusation", "zh-cn": "蒸馏指控"},
    "ai_slop_critique": {"en": "AI Slop Critique", "zh-cn": "AI垃圾批评"},
    "absurdist_meme": {"en": "Absurdist Meme", "zh-cn": "荒诞梗"},
    "advertising-marketing": {"en": "Advertising / Marketing", "zh-cn": "广告营销"},
}

NATIONALISM_LABELS: dict[str, dict[str, str]] = {
    "none": {"en": "None", "zh-cn": "无", "ja": "なし"},
    "mild_pro": {"en": "Mild Pro", "zh-cn": "温和支持", "ja": "控えめな支持"},
    "pro": {"en": "Pro", "zh-cn": "支持", "ja": "支持"},
    "constructive_critical": {
        "en": "Constructive Critical",
        "zh-cn": "建设性批评",
        "ja": "建設的な批判",
    },
    "anti": {"en": "Anti", "zh-cn": "反对", "ja": "反対"},
    "mixed": {"en": "Mixed", "zh-cn": "混合", "ja": "賛否混在"},
}

ROLE_LABELS: dict[str, dict[str, str]] = {
    "official": {"en": "Official", "zh-cn": "官方"},
    "staff": {"en": "Staff", "zh-cn": "员工"},
    "community": {"en": "Community", "zh-cn": "社区"},
}

CLASSIFICATION_LABELS: dict[str, dict[str, dict[str, str]]] = {
    "post_type": POST_TYPE_LABELS,
    "product_label": PRODUCT_LABEL_LABELS,
    "sentiment": SENTIMENT_LABELS,
    "discourse": DISCOURSE_LABELS,
    "nationalism": NATIONALISM_LABELS,
    "role": ROLE_LABELS,
}
