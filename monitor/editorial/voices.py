"""Immutable locale profiles; routing and presentation stay separate."""

import json
import re
from pathlib import Path
from typing import Literal

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
    instructions: str = ""
    shared_prompt: str | None = None
    publication_voice: str | None = None
    headline_attribution: Literal["supporting_copy"] | None = None

    @property
    def digest(self):
        # Absent new references must not change historical inline-voice hashes.
        return digest(self.model_dump(exclude_none=True))


def shared_instructions(voice: Voice) -> str:
    if not re.fullmatch(r"[a-z0-9-]{1,80}", voice.shared_prompt or ""):
        raise ValueError("invalid shared prompt ID")
    path = (
        Path(settings.BASE_DIR)
        / "config/editorial_prompts"
        / f"{voice.shared_prompt}.json"
    )
    if not path.is_file():
        raise ValueError("shared prompt unavailable")
    contract = json.loads(path.read_text())
    if not isinstance(contract, dict) or contract.get("status") != "owner-locked":
        raise ValueError("shared prompt is not locked")
    try:
        paragraph = contract["instructions"][voice.locale]
        publication = contract["voices"][f"{voice.locale}|{voice.publication_voice}"]
        task = publication["task"][voice.locale]
        output_language = publication["output_language"]
    except (KeyError, TypeError) as exc:
        raise ValueError("shared prompt voice unavailable") from exc
    if output_language != voice.locale or voice.track != "chatter":
        raise ValueError("shared prompt locale/track mismatch")
    if any(not isinstance(text, str) or not text.strip() for text in (paragraph, task)):
        raise ValueError("shared prompt is empty")
    return paragraph + "\n" + task


def load_voice(profile_id: str) -> Voice:
    if not re.fullmatch(r"[a-z0-9-]{1,80}", profile_id):
        raise ValueError("invalid voice ID")
    path = Path(settings.BASE_DIR) / "config/editorial_voices" / f"{profile_id}.json"
    if not path.is_file():
        raise ValueError("voice unavailable")
    voice = Voice.model_validate(json.loads(path.read_text()))
    if voice.id != profile_id or not voice.available:
        raise ValueError("voice unavailable")
    if voice.shared_prompt is not None or voice.publication_voice is not None:
        if not voice.shared_prompt or not voice.publication_voice or voice.instructions:
            raise ValueError("invalid shared prompt reference")
        voice = voice.model_copy(update={"instructions": shared_instructions(voice)})
    elif not voice.instructions.strip():
        raise ValueError("voice instructions missing")
    return voice


def load_bound_voices(cfg):
    """Reject unavailable or mismatched locale profiles before any paid work."""
    voices = {}
    for binding, profile in cfg.voices.items():
        voice = load_voice(profile)
        if f"{voice.track}:{voice.locale}" != binding:
            raise ValueError("voice binding mismatch")
        voices[binding] = voice
    if "chatter:en" not in voices or (cfg.pulse_limit and "pulse:en" not in voices):
        raise ValueError("English track profiles are required")
    return voices
