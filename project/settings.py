"""Django settings for x-monitor v2.

v1 (x_monitor): local Flask + SQLite + macOS launchd (still live).
v2 (this file): Django + PostgreSQL on Render, Google OAuth, full i18n.

This file is structured so v2 additions (auth, i18n, Celery, dashboard
routes) are append-only — no early-decision lock-in.

Mirrors the pushin_weight reference shape: env-driven via django-environ,
PostgreSQL as the default database, Celery for background harvest cycles,
WhiteNoise for static in production.
"""
from __future__ import annotations

import os
from pathlib import Path

import environ

# ============================================================================
# Paths
# ============================================================================

BASE_DIR = Path(__file__).resolve().parents[1]

# ============================================================================
# Environment
# ============================================================================

env = environ.Env(
    DEBUG=(bool, False),
    XMONITOR_DRY_RUN=(bool, False),
    XMONITOR_LOG_JSON=(bool, False),
)

# Read .env if present (does not override real env vars)
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

# ============================================================================
# Core
# ============================================================================

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-only-change-in-production-xmonitor-v2")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

USE_TZ = True
TIME_ZONE = "UTC"

# ============================================================================
# Apps
# ============================================================================
# v2 baseline: auth/sessions/contenttypes for the User table and OAuth.
# core = models + migrations (the new source of truth for schema).
# monitor = dashboard views + harvest management command.

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",  # for ArrayField, JSONField, CITEXT, etc.

    # Local
    "core",
    "monitor",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "project.wsgi.application"
ASGI_APPLICATION = "project.asgi.application"

# ============================================================================
# Database
# ============================================================================

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://xmonitor:xmonitor@localhost:5432/xmonitor",
    ),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = False  # harvest wants explicit tx control

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ============================================================================
# Auth
# ============================================================================
# v2 baseline: Django's built-in User model. Will wire Google OAuth via
# django-allauth in U3. Login wall on all dashboard routes.

AUTH_USER_MODEL = "auth.User"

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ============================================================================
# Celery
# ============================================================================

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 min hard cap per cycle

# Beat schedule: harvest runs every 15 minutes (mirrors launchd cadence)
CELERY_BEAT_SCHEDULE = {
    "monitor-run-cycle": {
        "task": "monitor.tasks.run_cycle",
        "schedule": 15 * 60.0,  # 15 min
    },
}

# ============================================================================
# Static files
# ============================================================================

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ============================================================================
# Logging
# ============================================================================

if env("XMONITOR_LOG_JSON"):
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "structlog.stdlib.ProcessorFormatter",
                "processor": "structlog.stdlib.ProcessorFormatter.wrap_for_formatter",
            },
        },
        "handlers": {
            "console": {"class": "logging.StreamHandler", "formatter": "json"},
        },
        "root": {"handlers": ["console"], "level": "INFO"},
    }
else:
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "console": {"class": "logging.StreamHandler"},
        },
        "root": {"handlers": ["console"], "level": "INFO"},
    }

# ============================================================================
# x-monitor specific
# ============================================================================

XMONITOR_DRY_RUN = env("XMONITOR_DRY_RUN")
XMONITOR_DATA_DIR = Path(env("XMONITOR_DATA_DIR", default=str(BASE_DIR / "data")))

# Canonical brand registry (20 brands, post-U5-rename).
# TODO(U2): derive from `core.models.Brand.objects.values_list('nickname', flat=True)`
# once the ORM is wired; remove this placeholder then.
KNOWN_MODELS: frozenset[str] = frozenset(
    {
        "minimax",
        "qwen",
        "deepseek",
        "glm",
        "mimo",
        "moonshot_kimi",
        "inclusionai",
        "mistral",
        "stepfun",
        "ernie",
        "hunyuan",
        "llama",
        "nemo_megatron",
        "doubao",
        "yi",
        "sensechat",
        "exaone",
        "kuaishou",
        "sakana_ai",
        "upstage",
    }
)

# Third-party API keys
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
TWITTERAPI_IO_API_KEY = env("TWITTERAPI_IO_API_KEY", default="")
TWITTERAPI_BASE_URL = env("TWITTERAPI_BASE_URL", default="https://api.twitterapi.io")
