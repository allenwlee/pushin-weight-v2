---
date: 2026-08-12
source_sha: de32daed0a2a7e53bdcda9b557b7659774c3c746
scope: headline-trend-narrative-u0
data_policy: aggregate-only-no-post-text
---

# Headline trend narrative implementation baseline

This is the pre-implementation evidence required by U0 of
`2026-08-12-121455-feat-v22-headline-trend-narratives.md`. It records the
measured state only; it does not enable a worker, enqueue a task, call an LLM,
alter harvesting, or change a Render resource.

## Workspace and migration slot

- Isolated worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/v22-headline-trend-narratives`
- Branch: `feat/v22-headline-trend-narratives`
- Implementation base: `origin/main@de32daed0a2a7e53bdcda9b557b7659774c3c746`
- Plan source: `origin/main@2538801dcc63b35b70c1b17b4b6f4679009000b3`
- Fresh refetch: `origin/main@8c5bae6e48c42208c8fdc528fc9352bca501abbf`.
  The implementation worktree reconciles the intervening mainline iOS control
  fix touching `monitor/static/home-v20.css`, `monitor/static/pw-filter-pills.js`,
  and `tests/test_home_v22_browser.py`; the dirty primary checkout was not
  overwritten.
- Current migration leaf: `core.0012_twitter_list_sync_state`.
- Allocated additive migration: `core.0013_trend_narrative_version`.
- No active worktree has unmerged commits on a scoped headline or harvester
  file. The old `feat/v20-homepage-phase-a` branch has no active worktree and
  is behind current main; it is not an implementation owner.

## Render release manifest

Observed read-only with Render CLI on 2026-08-12. Credentials and secret
values were not inspected or recorded. Live deployed commits, region, repo,
auto-deploy mode, and service commands were recorded so the candidate can be
reconciled without applying it.

| Resource | ID | Type/state/region | Repo/branch/SHA | Command or schedule | Auto-deploy | Env/broker/queue identity | Ownership conclusion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `pushinweight-harvest` | `crn-d9gv94o4n6ts739tqaug` | cron / active / oregon | `allenwlee/pushin-weight-v2`, `main@8c5bae6` | `python manage.py run_cycle`, `*/15 * * * *` | commit | `pushinweight-secrets`; no live Pushin Weight broker or queue | Sole active scheduler |
| `pushinweight-web` | `srv-d9go2breo5us73cg6vqg` | web / active / oregon | `allenwlee/pushin-weight-v2`, `main@8c5bae6` | `gunicorn project.wsgi:application --log-file -` | commit | `pushinweight-secrets`; serving only | Serving path only |
| `pushinweight-worker` | `srv-d9go2breo5us73cg6vr0` | worker / suspended / oregon | `allenwlee/pushin-weight-v2`, `main@2630e0e` | generic Celery worker, concurrency one | commit | legacy/default queue; no headline namespace | Legacy; do not reactivate |
| `pushinweight-beat` | `srv-d9go2breo5us73cg6vrg` | worker / suspended / oregon | `allenwlee/pushin-weight-v2`, `main@2630e0e` | `celery -A project beat -l INFO` | commit | legacy scheduler; no headline namespace | Legacy; do not reactivate |
| `pushinweight-db-shadow` | `dpg-d9koekqjobas73fvjqng-a` | PostgreSQL 18 / active / oregon | n/a | n/a | n/a | `DATABASE_URL` secret not recorded | Current application database |

The live resource owner is the Push in Weight Render workspace. The release,
observer, and rollback operators for a future canary are intentionally
unassigned until deployment is separately authorized. The candidate's owned
broker identity is `pushinweight-headlines-broker`; its queue namespace is
`trend-narratives`; its worker is `pushinweight-headlines`. Neither exists
live yet. The only live Key Value resource is `scrolls-redis` (Scrolls-owned)
and was excluded from the candidate.

There is no Pushin Weight-owned Key Value/Redis resource and no headline
consumer. The only visible Key Value instance belongs to Scrolls and must not
be reused. Therefore provider calls, enqueueing, serving, Blueprint apply, and
resource creation remain deployment-gated. Local implementation may proceed
with all three feature controls off.

The checked-in Blueprint and deployment runbook do not match live topology:
the Blueprint declares only web, cron, and a database, while the runbook still
describes active Celery beat/worker scheduling. U6 must make the current-state
topology explicit without enabling beat or reactivating either legacy worker.

## Harvester external-call baseline

`plan_calls_for_cycle(load_config(config.yaml))` produces exactly seven search
lines in the current code: `A`, `B1`, `C1`, `C2`, `C3`, `B2`, and `B3`.
The one-shot metrics refresh is enabled with a cap of 200 tweet IDs per cycle.
The narrative feature must not add, repeat, or reorder any TwitterAPI request;
its only harvest-path change is one isolated post-completion dispatch attempt.

The latest committed cost fixture (`tests/harvester_costs/2026-08-10-162500-ae1-smoke.md`)
records seven search lines plus one metrics line, 3,915 credits total for its
sample cycle. That fixture is a comparator, not a claim that every current
cycle has the same result volume. The ignored local `data/runs` directory is
stale and is not used as current production evidence.

## Aggregate-only threshold calibration

The production aggregate was anchored at `2026-08-12 04:29:49+00`. It selected
only timestamps, brand keys, counts, and distinct author counts; it did not
select or emit post text, URLs, or account content.

| Window | Coverage from earliest associated post | Recent top three `(posts/authors)` | Earlier count for recent leader |
| --- | ---: | --- | ---: |
| `1d` | 1.000 | DeepSeek `946/795`; Qwen `527/441`; MiniMax `488/387` | 1,260 |
| `7d` | 1.000 | DeepSeek `4,495/3,246`; Qwen `2,539/1,835`; MiniMax `2,450/1,574` | 8,535 |
| `30d` | 1.000 | DeepSeek `27,241/14,056`; MiniMax `11,064/5,385`; Qwen `9,499/5,842` | 9,005 |
| `365d` | 1.000 | DeepSeek `37,266/18,797`; Qwen `16,032/9,027`; MiniMax `13,211/6,552` | 14 |

The earliest associated non-sentinel post is dated 2025-01-15, so the current
literal R5 earliest-post coverage formula reports full 365-day coverage. The
365-day half distribution is nevertheless sharply asymmetric; this reinforces
the need for exact eligibility and momentum rules rather than an LLM-inferred
story. Fixture coverage must still pin the below-75-percent and exact-75-percent
branches.

The configured defaults remain suitable and are frozen for implementation:
20 recent posts, 10 recent authors, contested at 0.80, coverage-limited below
0.75, and momentum cut points 1.50, 1.15, and 0.85. These are configurable
product thresholds; changing them after rollout requires new evidence.

## Verification environment

PostgreSQL is available locally through the `fuchitalee` role. The disposable
test configuration is
`DATABASE_URL=postgresql://fuchitalee@localhost/pushinweight_test`; an eight-test
PostgreSQL smoke executed with zero skips and zero errors. The repo's documented
`pushinweight` local role is absent, so verification must use the explicit
disposable URL and must never point pytest at production.
