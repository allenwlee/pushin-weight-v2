"""Compatibility name for the existing offline saved job-history preview."""

from core.management.commands.create_or_update_person import (
    SavedPreviewCommand as Command,
)

__all__ = ["Command"]
