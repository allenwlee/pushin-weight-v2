"""Preserve the deployed maintenance entry point while refreshing both datasets."""

from monitor.management.commands.refresh_materializations import Command

__all__ = ["Command"]
