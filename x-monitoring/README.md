# x-monitor

A daily dashboard for keeping tabs on what people are saying about Chinese AI models on X (formerly Twitter).

## What this is

x-monitor is a small tool that runs in the background, scans X every 15 minutes for posts about nine Chinese AI models — MiniMax, Qwen, DeepSeek, GLM, Xiaomi MiMo, Moonshot Kimi, and three InclusionAI models (Ling, Ring, Ming) — and shows you a summary of the day's conversation in a simple browser dashboard.

It was built for MiniMax's developer relations team so they always know what the public is saying about these models: who's excited, who's critical, who's asking questions, and what releases are being discussed.

## What it does

- **Finds posts about each model.** A curated list of search queries (in English and Chinese) runs every 15 minutes, pulling in posts that mention any of the nine models.
- **Filters out noise.** Pure retweets and off-topic mentions are deprioritized so the signal isn't drowned out.
- **Classifies each post.** Each post gets sorted into a category — release news, community question, criticism, praise, or other — and attributed to the brand(s) it mentions.
- **Tracks the community.** Identifies which accounts are official, which are staff, and which are regular commenters, and how they relate to each other.
- **Shows it on a dashboard.** A simple web page with one card per model. Each card shows recent volume, today's top posts, and the mix of opinion types.

## Who uses it

The MiniMax devrel team, plus anyone who wants a daily snapshot of public opinion about these models. The dashboard runs locally on a Mac and is meant for a single user.

## How to use it

1. Open the dashboard in a browser at `http://127.0.0.1:5000/`.
2. Look at the nine model cards. Each card gives you today's picture at a glance.
3. Click into a card to see recent posts, the community around that model, and other details.
4. Items that look off get flagged for review — check the review queue (`x-monitor review --list`) and resolve or dismiss them.

That's it. Everything else (the 15-minute scan, the storage, the error handling) runs automatically.

---

## Setup & Operations

The following is for whoever sets up or maintains the tool.

### Quickstart

```bash
# 1. Install (uses system Python; recommend venv)
cd x-monitoring
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Set cookies (one-time per cookie lifetime)
mkdir -p ~/.config/x-monitor
# Copy auth_token + ct0 from x.com dev tools into ~/.config/x-monitor/cookies.json
chmod 600 ~/.config/x-monitor/cookies.json
x-monitor setup cookies --validate

# 3. Add APIFY_API_TOKEN to ~/.env.secrets
echo 'export APIFY_API_TOKEN="..."' >> ~/.env.secrets
chmod 600 ~/.env.secrets

# 4. Run the migrations and a dry-run
x-monitor migrate
x-monitor run --dry-run

# 5. Start the dashboard
x-monitor dashboard start
# Open http://127.0.0.1:5000/ in a browser
```

### Daily Ops

1. `x-monitor dashboard start` (if not running) → open `http://127.0.0.1:5000/`.
2. Glance at the 9-card grid: sparklines = volume, signal bars = release/criticism/question mix, top-3 = today's signal.
3. Click a card → drill-down with Posts / Graph / Clusters / Roles tabs.
4. `x-monitor review --list` → `--resolve` or `--dismiss` items.
5. `x-monitor dashboard stop` when done.

### Layout

- `x_monitor/` — Python package (`x-monitor` CLI entry).
- `data/queries/<model>.yaml` — 5 curated X advanced-search queries per model.
- `data/accounts/<model>.yaml` — seeded official handle; commenters populated from posts.
- `data/runs/<run_id>.json` — per-run log; `LATEST.json` symlink = most recent.
- `data/x_monitoring.db` — SQLite (posts, accounts, account_post_appearances).
- `data/_review_queue.json` — review queue (single source of truth).
- `deploy/com.fuchitalee.x-monitor.plist` — LaunchAgent on fuchitalee.

### Troubleshooting

- **Red badge on every card** → `degraded:cookies: true` in `data/runs/LATEST.json`.
  Run `x-monitor setup cookies` to validate the cookie file, then re-run.
- **Yellow badge on a model card** → `degraded:query_rot: <query_id>` — query has returned
  zero results for 3+ consecutive days. Re-enable in the corresponding YAML after review.
- **Apify 5xx mid-run** → caught and logged in run JSON; ≥3 consecutive aborts the run.
- **Port 5000 conflict** → set `dashboard_port` in `config.yaml` or `lsof -nP -iTCP:5000 -sTCP:LISTEN` to find the conflict.
- **Dashboard server died** → `x-monitor dashboard status` shows last 50 lines of `data/dashboard.log`.
  Restart with `x-monitor dashboard start`.

See `deploy/README.md` for LaunchAgent install/uninstall and log locations.

### v1.8 — Call-Path Attribution

v1.8 (2026-06-19) replaces v1.7's first-match-wins single-brand
classifier with a multi-brand extraction pipeline. A single tweet
naming two brands now produces one row per detected brand in
`posts_brands` / `post_mentions` / `posts_brands_signals` (replaces the
old `posts.brand_id` + `posts.signal` columns).

#### New modules

- `x_monitor/attribution.py` — multi-brand extractors
  (`extract_user_mentions`, `extract_hashtag_mentions`,
  `extract_body_keywords`, `extract_search_term_match`),
  `compute_post_brands` consolidator, `classify_signal` per-brand
  signal classifier (Claude Haiku).
- `x_monitor/reattribute.py` — `python -m x_monitor reattribute
  --since YYYY-MM-DD` backfill subcommand for historical posts.
- `x_monitor/intent_classifier.py` — kept as a thin compat shim that
  re-exports the v1.8 names and emits `DeprecationWarning` on its
  legacy function bodies. A follow-up commit deletes it.

#### Public API

`from x_monitor import Store, attribute_to_brands, classify_signal, ...` —
see `x_monitor/__all__` for the stable import surface. See
`x_monitor/CHANGELOG.md` for the full v1.8 change list.

#### Operator deploy sequence

1. Apply migration 004 (already done 2026-06-19).
2. Land this code (Units 1-6).
3. Run `python -m x_monitor reattribute --since 2026-01-01` on the
   live DB. Expect 5-10 min for ~2,000 posts.
4. Verify the dashboard renders with real data.
5. Restart the LaunchAgent + dashboard.