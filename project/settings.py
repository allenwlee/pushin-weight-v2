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
DEBUG = True  # TEMP for Playwright testing
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", ".onrender.com"])

USE_TZ = True
TIME_ZONE = "UTC"

# ============================================================================
# i18n / l10n
# ============================================================================

USE_I18N = True
USE_L10N = True

LANGUAGE_CODE = "zh-hans"
LANGUAGES = [
    ("en", "English"),
    ("zh-hans", "简体中文"),
]

LOCALE_PATHS = [BASE_DIR / "locale"]

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
    "django.contrib.sites",  # required by django-allauth
    "django.contrib.postgres",  # for ArrayField, JSONField, CITEXT, etc.

    # Auth (django-allauth)
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",

    # Local
    "core",
    "monitor",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # LocaleMiddleware must be after SessionMiddleware and before
    # CommonMiddleware so it can parse the language from the session
    # or URL before the request is processed.
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware"
    "django.contrib.messages.middleware.MessageMiddleware",
    # django-allauth
    "allauth.account.middleware.AccountMiddleware",
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
                "core.context_processors.i18n_context",
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
        default="postgres://pushinweight:pushinweight@localhost:5432/pushinweight",
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
LOGOUT_REDIRECT_URL = "/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ============================================================================
# django-allauth — Google OAuth
# ============================================================================

SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# allauth account settings
ACCOUNT_EMAIL_VERIFICATION = "optional"  # "mandatory" for stricter
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]

# Google OAuth provider
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": env("GOOGLE_CLIENT_ID", default=""),
            "secret": env("GOOGLE_CLIENT_SECRET", default=""),
        },
        "SCOPE": [
            "profile",
            "email",
        ],
        "AUTH_PARAMS": {
            "access_type": "online",
        },
    },
}
SOCIALACCOUNT_LOGIN_ON_GET = True  # one-click sign-in flow

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
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ============================================================================
# Production / Render deployment
# ============================================================================

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Render terminates TLS at its load balancer and forwards to Gunicorn over HTTP.
# Tell Django to trust the X-Forwarded-Proto header so request.is_secure() works.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Security hardening (off in local DEBUG mode, on in production)
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

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

# x-monitor harvest pipeline — loaded from environment so Render can
# configure these without code changes.
X_MONITOR_LIST_ID = env.int("X_MONITOR_LIST_ID", default=None)

# Load x_query_specs from config.yaml for Call B (wide-net keyword search)
# and Call C (co-occurrence-constrained) queries. These are the same specs
# the v1 pipeline uses to produce ~200 posts per 15-min cycle.
_x_query_specs: list[dict] = []
_config_path = BASE_DIR / "config.yaml"
if _config_path.exists():
    try:
        import yaml as _yaml
        with open(_config_path) as _fh:
            _config = _yaml.safe_load(_fh)
        _x_query_specs = _config.get("x_query_specs") or []
    except Exception:
        pass
X_MONITOR_X_QUERY_SPECS = _x_query_specs

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

# ============================================================================
# SQLite local-dev: register case_insensitive collation
# ============================================================================
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    import sqlite3 as _sqlite3

    _orig_connect = _sqlite3.connect

    def _patched_connect(*args, **kwargs):
        conn = _orig_connect(*args, **kwargs)
        conn.create_collation(
            "case_insensitive",
            lambda a, b: (
                -1
                if (a or "").lower() < (b or "").lower()
                else 1
                if (a or "").lower() > (b or "").lower()
                else 0
            ),
        )
        return conn

    _sqlite3.connect = _patched_connect

    # Django's SQLite backend does `from sqlite3 import dbapi2 as Database`.
    # Patch that too so connections created via dbapi2 also get the collation.
    import sqlite3.dbapi2 as _dbapi2
    _dbapi2.connect = _patched_connect
