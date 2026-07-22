"""Celery app for x-monitor v2.

Usage::

    celery -A project worker -l INFO
    celery -A project beat -l INFO
"""
from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")

app = Celery("xmonitor")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
