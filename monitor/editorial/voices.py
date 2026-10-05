"""Immutable locale profiles; routing and presentation stay separate."""

import json
import re
from pathlib import Path

from django.conf import settings
from pydantic import BaseModel, ConfigDict

from .contracts import digest


class Voice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    version: int
    track: str
    locale: str
    available: bool = True
    instructions: str

    @property
    def digest(self):
        return digest(self.model_dump())


def load_voice(profile_id: str) -> Voice:
    if not re.fullmatch(r"[a-z0-9-]{1,80}", profile_id):
        raise ValueError("invalid voice ID")
    path = Path(settings.BASE_DIR) / "config/editorial_voices" / f"{profile_id}.json"
    if not path.is_file():
        raise ValueError("voice unavailable")
    voice = Voice.model_validate(json.loads(path.read_text()))
    if voice.id != profile_id or not voice.available:
        raise ValueError("voice unavailable")
    return voice
