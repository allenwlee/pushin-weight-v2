"""monitor app — dashboard + harvest management command for x-monitor v2.

Houses the Pushin' Weight dashboard views, JSON APIs, and the harvest
management command (`manage.py run_cycle`).  The x_monitor/ package
remains the legacy path; this app is the new primary surface.
"""
from __future__ import annotations

from django.apps import AppConfig


class MonitorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "monitor"
    verbose_name = "x-monitor Dashboard & Harvest"
