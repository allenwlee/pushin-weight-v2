"""Canonical English and Simplified-Chinese classification labels."""

from __future__ import annotations

POST_TYPE_LABELS: dict[str, dict[str, str]] = {
    "buzz_releases": {"en": "Buzz & Releases", "zh-cn": "热点发布"},
    "hands_on_usage": {"en": "Hands-On Usage", "zh-cn": "实际使用"},
    "performance_comparisons": {"en": "Performance Comparisons", "zh-cn": "性能对比"},
    "feedback_questions": {"en": "Feedback & Questions", "zh-cn": "反馈提问"},
    "advertising_marketing": {"en": "Advertising & Marketing", "zh-cn": "广告营销"},
    "event_announcement": {"en": "Event Announcement", "zh-cn": "活动公告"},
}

SENTIMENT_LABELS: dict[str, dict[str, str]] = {
    "positive": {"en": "Positive", "zh-cn": "正面"},
    "negative": {"en": "Negative", "zh-cn": "负面"},
    "neutral": {"en": "Neutral", "zh-cn": "中性"},
    "mixed": {"en": "Mixed", "zh-cn": "混合"},
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
    "none": {"en": "None", "zh-cn": "无"},
    "mild_pro": {"en": "Mild Pro", "zh-cn": "温和支持"},
    "pro": {"en": "Pro", "zh-cn": "支持"},
    "constructive_critical": {"en": "Constructive Critical", "zh-cn": "建设性批评"},
    "anti": {"en": "Anti", "zh-cn": "反对"},
    "mixed": {"en": "Mixed", "zh-cn": "混合"},
}

ROLE_LABELS: dict[str, dict[str, str]] = {
    "official": {"en": "Official", "zh-cn": "官方"},
    "staff": {"en": "Staff", "zh-cn": "员工"},
    "community": {"en": "Community", "zh-cn": "社区"},
}

CLASSIFICATION_LABELS: dict[str, dict[str, dict[str, str]]] = {
    "post_type": POST_TYPE_LABELS,
    "sentiment": SENTIMENT_LABELS,
    "discourse": DISCOURSE_LABELS,
    "nationalism": NATIONALISM_LABELS,
    "role": ROLE_LABELS,
}
