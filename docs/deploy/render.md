# Render Runbook -- x-monitor v2 (Django + PostgreSQL)

Last updated: 2026-07-22

Deploys the v2 Django stack to Render with managed PostgreSQL, Redis,
Celery workers, and Google OAuth.

## Prerequisites

- A Render account with a connected GitHub/GitLab repo
- Access to the repo at `pushin-weight-v2`
- Google Cloud Console project for OAuth credentials
- TwitterAPI.io API key (same as v1)
- Anthropic API key (same as v1)

## Architecture

Six Render resources provisioned from `render.yaml` (Blueprint):

| Resource | Type | Purpose |
|---|---|---|
| `xmonitor-web` | Web service (`starter`) | gunicorn + Django, serves dashboard |
| `xmonitor-worker` | Worker (`starter`) | Celery worker, runs harvest cycles |
| `xmonitor-beat` | Worker (`starter`) | Celery beat scheduler, 15-min cadence |
| `xmonitor-db` | Managed PostgreSQL (`starter`) | Production database |
| `xmonitor-redis` | Managed Redis (`starter`) | Celery broker + result backend |
| `xmonitor-secrets` | Env group | API keys (Google, Twitter, Anthropic) |

## Step 1: Google OAuth credentials

Before deploying, create OAuth credentials in the Google Cloud Console:

1. Go to https://console.cloud.google.com/apis/credentials
2. Create a new OAuth 2.0 Client ID (Web application)
3. Add authorized redirect URIs:
   - `http://localhost:8000/accounts/google/login/callback/` (local dev)
   - `https://xmonitor-web.onrender.com/accounts/google/login/callback/` (prod)
     _Replace the hostname with whatever Render assigns if not using a custom domain._
4. Note the **Client ID** and **Client Secret**

## Step 2: Create the secrets env group in Render

1. Go to Render Dashboard > Env Groups
2. Create a new env group named `xmonitor-secrets`
3. Add these variables:

| Key | Value |
|---|---|
| `GOOGLE_CLIENT_ID` | From Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | From Google Cloud Console |
| `TWITTERAPI_IO_API_KEY` | Same key used by v1 (from `~/.env.secrets`) |
| `ANTHROPIC_API_KEY` | Same key used by v1 (from `~/.env.secrets`) |
| `ANTHROPIC_BASE_URL` | Optional -- set if using a gateway proxy |

## Step 3: Deploy via Blueprint

The `render.yaml` at the repo root defines the full service topology.

1. In Render Dashboard, go to **Blueprints**
2. Click **New Blueprint Instance**
3. Connect the repo and select the branch (e.g., `main`)
4. Render auto-detects `render.yaml` and provisions:
   - Managed PostgreSQL (`xmonitor-db`, plan: starter)
   - Managed Redis (`xmonitor-redis`, plan: starter)
   - Web service (`xmonitor-web`)
   - Worker (`xmonitor-worker`)
   - Beat scheduler (`xmonitor-beat`)
5. The first build runs `build.sh` which:
   - Installs Python deps (`pip install -e ".[dev]"`)
   - Collects static files (`manage.py collectstatic --noinput`)
   - Applies migrations (`manage.py migrate --noinput`)

### What `build.sh` does

```bash
#!/usr/bin/env bash
set -euo pipefail
pip install -e ".[dev]"
python manage.py collectstatic --noinput
python manage.py migrate --noinput
```

The `--noinput` flag on `collectstatic` and `migrate` ensures the build
doesn't block on prompts. Render runs `build.sh` on every deploy.

## Step 4: First-deploy setup

After the first successful deploy, run these one-time setup commands:

### 4a. Shell into the web service

In Render Dashboard > `xmonitor-web` > Shell:

```bash
# Seed the curated base layer (brands, companies, roles, accounts)
python manage.py load_seed

# Seed i18n taxonomy labels (post_type, sentiment, discourse, etc.)
python manage.py seed_i18n_labels

# Verify
python manage.py run_cycle --dry-run --limit-per-call 5
```

### 4b. Create a superuser (optional)

```bash
python manage.py createsuperuser
```

This gives access to `/admin/` for manual data inspection.

### 4c. Verify OAuth login

1. Visit `https://xmonitor-web.onrender.com/accounts/login/`
2. Click "Google" to sign in
3. On first login, a Django User + SocialAccount is created
4. You are redirected to the multi-brand home page

### 4d. Verify dashboard routes

After login, confirm these pages render:

| Route | Description |
|---|---|
| `/` | Multi-brand home |
| `/<company>/<brand>/` | Single-brand home (e.g., `/alibaba/qwen/`) |
| `/_/<brand>/` | Single-brand home for brands without a company entry |
| `/api/v1/home.chart.json` | Multi-brand chart JSON |
| `/api/v1/home.feed.json` | Paginated feed JSON |

## Step 5: Set ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS

After the first deploy, Render assigns a hostname like
`xmonitor-web.onrender.com`. Update the env vars on the web service:

1. In Render Dashboard > `xmonitor-web` > Environment
2. Set or update:

```
ALLOWED_HOSTS=.onrender.com
CSRF_TRUSTED_ORIGINS=https://xmonitor-web.onrender.com
```

`render.yaml` already includes `.onrender.com` in `ALLOWED_HOSTS`, but
if using a custom domain, add it here.

## Step 6: Verify Celery harvest

The beat scheduler runs the harvest cycle every 15 minutes.

### 6a. Check beat is scheduling

In Render Dashboard > `xmonitor-beat` > Logs, look for:

```
Scheduler: Sending due task monitor-run-cycle (monitor.tasks.run_cycle)
```

### 6b. Check worker is executing

In Render Dashboard > `xmonitor-worker` > Logs, look for:

```
Task monitor.tasks.run_cycle[...] received
Cycle ...: completed (N calls planned, M run, K inserted)
```

### 6c. Trigger a manual cycle

In Render Dashboard > `xmonitor-web` > Shell:

```bash
# Run one cycle directly (synchronous)
python manage.py run_cycle --limit-per-call 20

# Enqueue via Celery
python manage.py run_cycle --async
```

## Step 7: Production hardening checklist

- [ ] **DEBUG** is `False` on the web service (render.yaml sets this)
- [ ] **DJANGO_SECRET_KEY** is auto-generated by Render (`generateValue: true`)
- [ ] **DATABASE_URL** is pointing to `xmonitor-db` (set via `fromDatabase`)
- [ ] **ALLOWED_HOSTS** includes the Render hostname
- [ ] **CSRF_TRUSTED_ORIGINS** includes the Render hostname with `https://`
- [ ] Google OAuth redirect URIs match the deployed hostname
- [ ] `xmonitor-secrets` env group has all four API keys populated
- [ ] `manage.py check --deploy` exits clean (run from web shell)

## Local dev against Render PG

To connect a local Django dev server to the Render PostgreSQL instance
(for debugging or manual data inspection):

1. In Render Dashboard > `xmonitor-db` > Info, find the **External Connection** URL
2. Set it in your local `.env`:

```
DATABASE_URL=postgres://xmonitor:<password>@<host>:5432/xmonitor
```

3. Run locally as normal:

```bash
python manage.py runserver
```

**Security:** Render's external connections are IP-whitelisted. Add your
local IP in Render Dashboard > `xmonitor-db` > Settings.

## Troubleshooting

**Build fails with "could not translate host name".**
The `DATABASE_URL` or `CELERY_BROKER_URL` is not yet provisioned. Ensure
the PostgreSQL and Redis instances are created before the web service
builds. Blueprint handles this ordering automatically.

**OAuth redirect_uri_mismatch.**
The redirect URI in Google Cloud Console doesn't match the Render hostname.
Update both the Google Cloud Console entry and the Render env var
`CSRF_TRUSTED_ORIGINS`.

**Celery worker can't connect to Redis.**
Check that `xmonitor-redis` is running and the `CELERY_BROKER_URL` env
var on the worker service matches the Redis connection string. Blueprint
sets this via `fromDatabase`.

**Migrations pending but not applied.**
Shell into `xmonitor-web` and run:
```bash
python manage.py migrate --noinput
```

**Static files not served.**
Ensure `collectstatic` ran during build. If not, run from web shell:
```bash
python manage.py collectstatic --noinput
```
WhiteNoise serves from `STATIC_ROOT` (`staticfiles/`).

**Cycle run returns 0 inserted.**
Check that `TWITTERAPI_IO_API_KEY` is set in the `xmonitor-secrets` env
group and is not expired. Verify with a manual `--dry-run` to confirm
the API key works.
