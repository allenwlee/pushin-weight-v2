"""Extract source assertions, never verified dates, without inference calls.

Version suffixes and repository creation times are deliberately not date evidence.
An observed announcement/access/usage instant is the source publication instant;
it is not a claim that this was the world's first announcement or usage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

METHOD = "product-release-milestones-v1"
_SENTENCES = re.compile(r"(?<=[.!?。！？])\s+|\n+")
_FUTURE = re.compile(
    r"\b(?:rumou?r|unconfirmed|reportedly|will|might|may|tomorrow|next week|coming soon)\b|即将|即將|传闻|傳聞|预计|預計",
    re.IGNORECASE,
)
_NEGATED = re.compile(
    r"\b(?:not|never|isn't|hasn't|haven't|won't|no)\b|尚未|未发布|未發布", re.IGNORECASE
)
_ANNOUNCE = re.compile(
    r"\b(?:we|I)\s+(?:(?:are|am|have|today)\s+)?(?:announc\w*|introduc\w*|unveil\w*)\b"
    r"|\b(?:excited|pleased|proud|thrilled)\s+to\s+announce\b|正式发布|正式發布",
    re.IGNORECASE,
)
_RELEASE = re.compile(
    r"\b(?:releas(?:e|ed|ing)|launch(?:ed)?)\b|发布|發布|上线|上線", re.IGNORECASE
)
_AVAILABLE = re.compile(
    r"\b(?:now available|available now|weights are live|download now)\b|现已开放|现已开源",
    re.IGNORECASE,
)
_USAGE = re.compile(
    r"\bI\s+(?:have\s+)?(?:used|tested|tried|ran|downloaded)\b|我试用|我用了",
    re.IGNORECASE,
)
_DAY = re.compile(r"(?<![\w-])(?:19|20)\d{2}-\d{2}-\d{2}(?![\w-])")


@dataclass(frozen=True)
class Milestone:
    kind: str
    excerpt: str
    precision: str = "unknown"
    effective_at: datetime | None = None
    effective_date: date | None = None
    access_channel: str | None = None
    source_timezone: str | None = None


def _stated_date(sentence, published_at, source_timezone):
    matches = _DAY.findall(sentence)
    if len(set(matches)) == 1:
        try:
            return date.fromisoformat(matches[0])
        except ValueError:
            return None
    if not matches and published_at and source_timezone:
        relative = re.findall(r"\b(today|yesterday)\b", sentence, re.IGNORECASE)
        if len({x.lower() for x in relative}) == 1:
            local_date = published_at.astimezone(ZoneInfo(source_timezone)).date()
            return local_date - timedelta(days=relative[0].lower() == "yesterday")
    return None


def extract_milestones(
    text: str, *, published_at: datetime | None, source_timezone: str | None = None
) -> tuple[Milestone, ...]:
    if published_at is not None and published_at.utcoffset() is None:
        raise ValueError("Publication timestamp must include a timezone")
    if source_timezone:
        ZoneInfo(source_timezone)
    result = []
    for sentence in _SENTENCES.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        if re.search(r"\b(?:says?|wrote|quot(?:e|ed))\s*:\s*[\"“]?", sentence, re.IGNORECASE):
            continue
        if _FUTURE.search(sentence):
            if _RELEASE.search(sentence) or _ANNOUNCE.search(sentence):
                result.append(Milestone("rumor", sentence))
            continue
        if _NEGATED.search(sentence) or "?" in sentence or "？" in sentence:
            continue
        stated = _stated_date(sentence, published_at, source_timezone)
        kinds = []
        if _ANNOUNCE.search(sentence):
            kinds.append("announcement")
        if _RELEASE.search(sentence):
            kinds.append("source_stated_release")
        if _AVAILABLE.search(sentence):
            kinds.append("availability")
        if _USAGE.search(sentence):
            kinds.append("first_observed_usage")
        for kind in kinds:
            channel = None
            if kind == "availability":
                if re.search(
                    r"\b(?:weights|hugging\s?face|gguf)\b", sentence, re.IGNORECASE
                ):
                    channel = "weights"
                elif re.search(r"\bapi\b", sentence, re.IGNORECASE):
                    channel = "api"
            instant = (
                published_at if kind != "source_stated_release" and not stated else None
            )
            result.append(
                Milestone(
                    kind,
                    sentence,
                    "day" if stated else "datetime" if instant else "unknown",
                    instant,
                    stated,
                    channel,
                    source_timezone if stated else None,
                )
            )
    return tuple(dict.fromkeys(result))
