"""core app — Django models + migrations for x-monitor v2.

Houses the canonical schema (brands, companies, accounts, posts,
signals, lookups, etc.) as Django ORM models.  Models use natural keys
and composite PKs for i18n label tables, mirroring the pushin_weight
reference conventions.
"""
from __future__ import annotations

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "x-monitor Core"
