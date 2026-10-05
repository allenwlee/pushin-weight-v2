"""Explicit operator configuration; importing or reading never spends money."""

from pathlib import Path
from typing import Literal

import yaml
from django.conf import settings
from pydantic import BaseModel, ConfigDict, Field, model_validator

PictureMode = Literal["off", "select_only", "derive"]


class Route(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    model: str = Field(min_length=1, max_length=160)
    endpoint: Literal[
        "https://openrouter.ai/api/v1/chat/completions",
        "https://api.deepinfra.com/v1/openai/chat/completions",
    ]
    key_env: Literal["OPENROUTER_API_KEY", "DEEPINFRA_API_KEY"]
    reasoning: Literal["medium", "high", "xhigh", "ultra"] | None = None
    vision: bool = False
    image_token_ceiling: int = Field(default=16384, ge=1024, le=65536)
    input_usd_per_million: float = Field(gt=0)
    output_usd_per_million: float = Field(gt=0)
    max_output_tokens: int = Field(default=2048, ge=256, le=16384)

    @model_validator(mode="after")
    def match_credential(self):
        expected = (
            "OPENROUTER_API_KEY"
            if "openrouter.ai" in self.endpoint
            else "DEEPINFRA_API_KEY"
        )
        if self.key_env != expected:
            raise ValueError("credential must match explicit provider route")
        return self


class EditorialConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    enabled: bool = False
    public_enabled: bool = False
    daily_usd: float = Field(default=0, ge=0, le=1000)
    assessment_usd: float = Field(default=0, ge=0, le=100)
    daily_calls: int = Field(default=0, ge=0, le=1000)
    assessment_calls: int = Field(default=4, ge=1, le=20)
    media_daily_calls: int = Field(default=0, ge=0, le=96)
    media_cost_ceiling_usd: float = Field(default=0, ge=0, le=100)
    media_duration: int = Field(default=6, ge=4, le=15)
    media_max_polls: int = Field(default=40, ge=1, le=60)
    max_posts: int = Field(default=160, ge=1, le=1000)
    max_context_posts: int = Field(default=40, ge=0, le=200)
    max_packet_bytes: int = Field(default=120000, ge=4000, le=300000)
    max_images: int = Field(default=3, ge=1, le=8)
    half_life_hours: float = Field(default=6, gt=0, le=48)
    replacement_margin: float = Field(default=5, ge=0, le=100)
    pulse_limit: int = Field(default=1, ge=0, le=15)
    routes: dict[Literal["editor", "chatter", "pulse"], Route] = Field(
        default_factory=dict
    )
    voices: dict[str, str] = Field(
        default_factory=lambda: {
            "chatter:en": "chatter-en-v1",
            "pulse:en": "pulse-en-v1",
        }
    )
    pictures: dict[str, PictureMode] = Field(default_factory=dict)
    permitted_reuse: list[Literal["permitted", "unknown"]] = Field(
        default_factory=lambda: ["permitted"]
    )

    @model_validator(mode="after")
    def validate_activation(self):
        kinds = {"atomic", "current_headline", "chatter", "pulse"}
        if any(key.split(":")[0] not in kinds for key in self.pictures):
            raise ValueError("unknown picture content kind")
        if self.enabled and (
            set(self.routes) != {"editor", "chatter", "pulse"}
            or not self.daily_usd
            or not self.assessment_usd
            or not self.daily_calls
        ):
            raise ValueError("generation requires explicit routes and positive budgets")
        if (
            self.enabled
            and "derive" in self.pictures.values()
            and (not self.media_daily_calls or not self.media_cost_ceiling_usd)
        ):
            raise ValueError("derivatives require explicit media budgets")
        return self

    def picture_mode(self, content_kind: str, source_platform: str = "") -> PictureMode:
        return self.pictures.get(
            f"{content_kind}:{source_platform}", self.pictures.get(content_kind, "off")
        )


def load_editorial_config(path: Path | None = None) -> EditorialConfig:
    # One file for every worker/reader/CLI. No environment-specific silent model fallback.
    path = path or Path(settings.BASE_DIR) / "config/editorial.yaml"
    with path.open() as stream:
        return EditorialConfig.model_validate(yaml.safe_load(stream) or {})
