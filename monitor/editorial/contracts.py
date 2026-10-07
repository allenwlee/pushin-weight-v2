"""Closed, provider-independent contracts. Source IDs are validated against evidence."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ProviderReplyError(ValueError):
    """A fixed failure code and whitelisted metadata, never raw provider text."""

    def __init__(self, code, diagnostics):
        super().__init__(code)
        self.code = code
        self.diagnostics = diagnostics


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceClaim(ClosedModel):
    post_id: str
    span_ids: list[str] = Field(min_length=1, max_length=4)
    brand_keys: list[str] = Field(default_factory=list, max_length=10)
    source_field: Literal["original_text", "stored_quote", "local_parent"] | None = None
    actor: str = Field(min_length=1, max_length=300)
    action: str = Field(min_length=1, max_length=500)
    target: str = Field(min_length=1, max_length=300)
    status: Literal[
        "announcement", "source_report", "opinion", "allegation", "plan", "unknown"
    ]
    number_ownership: str = Field(default="none", max_length=1000)


class Event(ClosedModel):
    key: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    summary: str = Field(min_length=1, max_length=2000)
    post_ids: list[str] = Field(min_length=1, max_length=50)
    brand_keys: list[str] = Field(default_factory=list, max_length=10)
    occurred_at: AwareDatetime
    chatter: bool
    pulse: bool
    importance: float = Field(ge=0, le=100, allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=2000)
    change: Literal["new", "update", "unchanged"] = "new"
    story_id: UUID | None = None
    subject_kind: Literal[
        "company_direction", "model_release", "agent_release", "person", "other"
    ] = "other"
    person_ids: list[UUID] = Field(default_factory=list, max_length=5)
    visual_essential: bool = False
    source_image_url: str = Field(default="", max_length=4096)
    chart_fact_ids: list[str] = Field(default_factory=list, max_length=10)
    chart_support: Literal["supported", "unavailable", "not_supported"] = "unavailable"
    source_check: list[SourceClaim] = Field(default_factory=list, max_length=8)


class Decisions(ClosedModel):
    events: list[Event] = Field(default_factory=list, max_length=20)


class SupportedCopy(ClosedModel):
    headline: str = Field(min_length=1, max_length=160)
    byline: str = Field(min_length=1, max_length=500)
    article: str = Field(min_length=1, max_length=12000)


class Copy(ClosedModel):
    headline: str = Field(min_length=1, max_length=160)
    byline: str = Field(min_length=1, max_length=500)
    article: str = Field(min_length=1, max_length=12000)
    locale: Literal["en", "zh-cn", "ja"]
    post_ids: list[str] = Field(min_length=1, max_length=50)
    visual_brief: str = Field(default="", max_length=1500)
    source_check: list[SourceClaim] = Field(default_factory=list, max_length=12)
    supported_copy: SupportedCopy | None = None


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def interval_start(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("aware cutoff required")
    value = value.astimezone(UTC)
    return value.replace(minute=value.minute // 15 * 15, second=0, microsecond=0)
