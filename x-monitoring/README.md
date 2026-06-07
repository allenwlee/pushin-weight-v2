# {{AGENT_ATTRIBUTION}}
# x-monitor — Chinese Models X Monitoring

Daily, multi-language, signal-first view of X conversation around the nine v1 Chinese AI models
(MiniMax, Qwen, DeepSeek, GLM, Xiaomi MiMo, Moonshot Kimi, InclusionAI Ling, InclusionAI Ring,
InclusionAI Ming), built from a curated query library and a living community account graph.

## Quickstart

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

## Daily Ops

1. `x-monitor dashboard start` (if not running) → open `http://127.0.0.1:5000/`.
2. Glance at the 9-card grid: sparklines = volume, signal bars = release/criticism/question mix, top-3 = today's signal.
3. Click a card → drill-down with Posts / Graph / Clusters / Roles tabs.
4. `x-monitor review --list` → `--resolve` or `--dismiss` items.
5. `x-monitor dashboard stop` when done.

## Layout

- `x_monitor/` — Python package (`x-monitor` CLI entry).
- `data/queries/<model>.yaml` — 5 curated X advanced-search queries per model.
- `data/accounts/<model>.yaml` — seeded official handle; commenters populated from posts.
- `data/runs/<run_id>.json` — per-run log; `LATEST.json` symlink = most recent.
- `data/x_monitoring.db` — SQLite (posts, accounts, account_post_appearances).
- `data/_review_queue.json` — review queue (single source of truth).
- `deploy/com.fuchitalee.x-monitor.plist` — LaunchAgent on fuchitalee.

## Troubleshooting

- **Red badge on every card** → `degraded:cookies: true` in `data/runs/LATEST.json`.
  Run `x-monitor setup cookies` to validate the cookie file, then re-run.
- **Yellow badge on a model card** → `degraded:query_rot: <query_id>` — query has returned
  zero results for 3+ consecutive days. Re-enable in the corresponding YAML after review.
- **Apify 5xx mid-run** → caught and logged in run JSON; ≥3 consecutive aborts the run.
- **Port 5000 conflict** → set `dashboard_port` in `config.yaml` or `lsof -nP -iTCP:5000 -sTCP:LISTEN` to find the conflict.
- **Dashboard server died** → `x-monitor dashboard status` shows last 50 lines of `data/dashboard.log`.
  Restart with `x-monitor dashboard start`.

See `deploy/README.md` for LaunchAgent install/uninstall and log locations.
