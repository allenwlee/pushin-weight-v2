-- {{AGENT_ATTRIBUTION}}
-- x-monitor migration 025: main-loop since= cursor persistence
--
-- Plan: docs/plans/2026-07-02-001-feat-configurable-search-limits-and-backlog-plan.md
-- Unit 2 of 6 (U2 — Wire since= cursor for main-loop search).
--
-- Why this table exists:
-- Today the main loop calls apify.run_search(...) without a `since:`
-- operator on every cycle, paying the full TwitterAPI.io "Latest"
-- window cost each time even though only a small slice (posts since
-- the last successful cycle) is new. Once a cycle completes
-- successfully, we want to remember "we already fetched through this
-- moment" so the next cycle can restrict `since=<yesterday>` and
-- avoid re-downloading tweets from older windows.
--
-- Key shape — we store the cursor per PlannedCall so two parallel
-- calls in the same cycle don't step on each other's cursor. The
-- natural composite key is the same one used to name the raw dump
-- file:
--
--   (brand_id, call_id, call_kind, bucket, query_id)
--
--   - brand_id  = the call's brand (or "*" for Call A list-based
--                 fan-in). Identifies which brand's bucket of posts
--                 the cursor belongs to.
--   - call_id   = the stable per-cycle call label ("A", "B", "C1",
--                 "C2", ...). Two Call C specs with different call_ids
--                 are different cursors even if they share call_kind.
--   - call_kind = "account" | "brand_wide" (v1.7 schema). Retained
--                 for symmetry with the migration 020 era shape.
--   - bucket    = NULL for both v1.7 call kinds (retained from the
--                 v1.6 multi-bucket contract — see query_plan.py
--                 PlannedCall.bucket doc).
--   - query_id  = the Q1-Q6 source_query_id derived for the call.
--                 Recorded because the same logical call may emit
--                 different query_ids across cycles if the planner
--                 rotates.
--
-- We deliberately keep call_id in the key (not just call_kind +
-- bucket + query_id) because two Call C specs CAN coexist in one
-- cycle with the same kind/bucket/query_id tuple — they differ
-- only in call_id. The store helpers below use the full 5-tuple.
--
-- last_completed_at is stored as an ISO-8601 timestamp with timezone
-- (TEXT). The pipeline subtracts `CURSOR_OVERLAP_HOURS` (1 hour, see
-- x_monitor/run.py) before emitting it as the `since=` operator, so
-- near-boundary posts don't fall between cycles.
--
-- _migrations ledger is updated by Store._apply_migration AFTER this
-- script's COMMIT. Do NOT add an INSERT INTO _migrations here.

BEGIN;

CREATE TABLE IF NOT EXISTS call_state (
    brand_id           TEXT    NOT NULL,
    call_id            TEXT    NOT NULL,
    call_kind          TEXT    NOT NULL,
    bucket             TEXT,
    query_id           TEXT    NOT NULL,
    last_completed_at  TEXT,
    updated_at         TEXT    NOT NULL,
    PRIMARY KEY (brand_id, call_id, call_kind, bucket, query_id)
);

CREATE INDEX IF NOT EXISTS idx_call_state_completed_at
    ON call_state(last_completed_at);

COMMIT;