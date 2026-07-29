---
type: handoff
date: 2026-07-29
session: 2026-07-29 (fuchitalee, M3.0)
plan: docs/plans/2026-07-29-002-fix-zero-downtime-prod-db-ops-plan.md
issue: docs/issues/2026-07-29-internal-restore-failed-pg-restore-eof.md
branch_when_written: main
last_commit: c53afc2
resume_command: "cat docs/handoffs/2026-07-29-001-shadow-restore-in-progress.md && read it"
blocking_inputs_needed:
  - shadow_db_external_connection_string
---

# Handoff — Shadow restore paused waiting on shadow DB external connection string

## What was happening

This session was executing plan `2026-07-29-002` (zero-disruption prod DB
ops) to recover the 0-table prod DB caused by the failed
`fix/posts-restore-internal` restore-mode build.sh on 2026-07-29. The
plan's stated recovery path (shadow-first restore, verified pins, atomic
cutover) was the work; the session got to "shadow DB provisioned,
tooling shipped, recipe documented" and is now waiting on one input
from the user before continuing.

## What's done

| Unit | Status | Notes |
|---|---|---|
| U0 preflight + upgrade decision | ✅ complete | Decisions: use 141129 dump (not 200742 as plan says), upgrade Render Postgres, pause cron after recovery (not before) |
| U0.1 upgrade Render Postgres + create shadow | ✅ complete | Prod `pushinweight-db` upgraded free→basic_1gb (1GB disk). Shadow `pushinweight-db-shadow` (`dpg-d9koekqjobas73fvjqng-a`) created on basic_1gb (15GB disk, cannot shrink), region oregon, ipAllowList opened to `0.0.0.0/0` |
| U1 fix main build.sh + remove failed branch | ✅ complete | Verified `main`'s `build.sh` already has the safe advisory-lock pattern (no DROP SCHEMA). Deleted local + remote `fix/posts-restore-internal` branch (5 commits of the failed restore-mode build.sh) |
| U2 shadow restore tooling | ✅ partial (code done, restore pending) | `scripts/ops/shadow_restore.sh` + `scripts/ops/extract_dump.py` written, executable, env-driven (no secrets in repo), committed in `e7e53b8`. md5 verify + pg_restore `--no-owner --no-privileges --jobs=1` + post-restore row-count pin (EXPECTED_POSTS_COUNT default 28822). Refuses to clobber existing posts table. Restore itself not run yet — waiting on shadow external connection string. |
| U6 standing recipe doc | ✅ complete | `docs/solutions/operations/render-shadow-restore-and-cutover.md` written, committed in `c53afc2`. Captures forbidden patterns (DROP SCHEMA before restore, restore-mode build.sh, multi-hour txn on free-tier disk, --jobs=4 before dry-run), verification contract, and the full shadow→verify→cutover procedure. |

## What's not done — blocking the finish

- **U2 restore** — needs the **shadow external connection string** to actually run `pg_restore` against `dpg-d9koekqjobas73fvjqng-a` from this terminal.
- **U3 migrations on shadow** — needs U2 verified before running `manage.py migrate --noinput` on shadow. Expected migration order for the `posts.raw → typed columns` denormalization: `0001 → 0002 → 0003(no-op) → 0006(chunked backfill with autocommit) → 0004(drop raw) → 0005(FK SET NULL)`.
- **U4 cutover** — set `DATABASE_URL` on `pushinweight-web` (`srv-d9go2breo5us73cg6vqg`), `pushinweight-worker` (`srv-d9go2breo5us73cg6vr0`), `pushinweight-beat` (`srv-d9go2breo5us73cg6vrg`), and `pushinweight-harvest` cron (`crn-d9gv94o4n6ts739tqaug`) to the shadow URL. Redeploy / restart. Smoke `/feed` + harvest count.
- **U5 cleanup + issue close** — drop old `pushinweight-db` after ≥1 green harvest cycle; revert cron schedule from `"0 0 31 2 *"` back to `*/15` (only after cutover, not yet); close the originating issue with link to verified doc.

## Decisions the next session should NOT re-litigate

These were resolved interactively during this session. Don't re-ask.

1. **Source dump**: `~/Downloads/pushinweight-20260728-141129.dump` (40MB, md5 `8335a6955955b834d83008fad532606c`). The plan body names `200742` which has **0 posts** — the plan is mistaken. 141129 has the full 28,822 posts + raw column intact.
2. **Render upgrade**: yes, both prod and shadow on `basic_1gb`. User-confirmed 2026-07-29. Shadow disk came back 15GB not 1GB; shrinking later is rejected — accept it.
3. **Cron pause**: not now — wait until **after recovery + verify**. Currently still `*/15`.
4. **IP allowlist**: opened `0.0.0.0/0` on shadow (matches prod). Tighten post-recovery if desired.

## Exact commands to finish U2 (resume point)

Once you have the shadow external connection string, run from this checkout on fuchitalee:

```bash
cd /Users/fuchitalee/development/pushin-weight-v2

# 1. Restore into shadow. Verify md5 + posts count = 28822.
SHADOW_DATABASE_URL="<paste from Render dashboard>" \
DUMP_PATH=/Users/fuchitalee/Downloads/pushinweight-20260728-141129.dump \
EXPECTED_MD5=8335a6955955b834d83008fad532606c \
./scripts/ops/shadow_restore.sh

# 2. Verify pins on shadow.
render psql pushinweight-db-shadow -c "SELECT count(*) FROM posts;" --output text
# expect: 28822
render psql pushinweight-db-shadow -c "\d posts" --output text | grep -E "raw|denormalize"
# expect: "raw" column present (dump is pre-migration)

# 3. Run migrations on shadow.
# DJANGO_SETTINGS_MODULE=project.settings python manage.py migrate --noinput
# (against SHADOW_DATABASE_URL)

# 4. Verify post-migration pins on shadow.
render psql pushinweight-db-shadow -c "SELECT count(*) FROM posts WHERE raw IS NOT NULL;"
# expect: 0 (raw dropped by 0004)
render psql pushinweight-db-shadow -c "SELECT count(*) FROM posts WHERE author_handle IS NOT NULL;"
# expect: 28822 (typed cols populated by 0006)

# 5. Cutover: set DATABASE_URL on each Render service.
# (Use render env or dashboard; do not commit DATABASE_URL to git.)

# 6. Smoke /feed + harvest one cycle.
# 7. Pause cron (change schedule to "0 0 31 2 *" in render.yaml + push).
# 8. After 1 green cycle, drop old pushinweight-db and resume cron.
```

## State files for the next session

- Working tree clean (last commit `c53afc2 docs(operations): shadow-restore + cutover recipe (U6)`).
- Branch: `main`.
- No remote branches of `fix/posts-restore-internal` (deleted 2026-07-29).
- Cron schedule in render.yaml: still `"*/15 * * * *"` (not yet paused).
- 10 untracked items in working tree: `.claude/`, `AGENTS.md`, several `docs/plans/`, `docs/issues/`, `docs/ideation/`, `docs/reference/feed-ui-contract.md` — none are part of this work; ignore.

## Pitfalls encountered this session (don't repeat)

- The plan body's `200742` dump is wrong (0 posts). Always pg_restore -l + restore into a temp DB and `SELECT count(*)` before trusting any dump named in a doc.
- `case_insensitive` collation lives in `template1` on the local pg17; drop it from `template1` (not `postgres`) before re-creating test DBs.
- `dropdb && createdb` does NOT drop cluster-scope collations; explicit `DROP COLLATION` against the source template is required.
- Basic-tier Render Postgres `--disk-size-gb 1` is silently raised to 15 GB on creation; shrinking after is rejected with HTTP 400.
- Render API errors during this session were intermittent — likely the M3.0 proxy `[1m]` context-window tag pattern (see ~/.claude/projects/.../memory/feedback_minimax_m3_api_error_triage_2026-07-28.md). Retry with delay; not a config bug.