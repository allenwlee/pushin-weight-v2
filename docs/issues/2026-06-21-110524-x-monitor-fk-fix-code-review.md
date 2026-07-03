# Code Review: x-monitor FK hot-path fix (commits 421248e, 43035b0)

**Review verdict: Not ready.** 3 P1 + 5 P2 + 7 P3 findings across 9 reviewers. The two commits ship a real fix for the documented FK crash, but the review surfaced three concrete new issues that warrant attention before declaring this done.

**Scope:** 2 commits on main at `~/development/minimax-marketing/`, base `32a463a..HEAD`, run id `20260620-203832-217d1a4c`.
**Plan:** `docs/plans/2026-06-19-005-feat-fix-x-monitor-cron-runtime-plan.md` (explicit).
**Reviewers:** correctness, testing, maintainability, project-standards, agent-native-reviewer, learnings-researcher, reliability, adversarial, kieran-python.

---

## Intent

Two surgical fixes for the x-monitor cron hot path:

- **`421248e`** — Default `_resolve_signal_model()` to `MiniMax-M3.0` (was M2.7, which emitted 150-token thinking blocks per call, making the proxy path 5.5× slower).
- **`43035b0`** — Drop hallucinated brand_ids before INSERT into `post_brand_signals`, preventing `sqlite3.IntegrityError: FOREIGN KEY constraint failed` from aborting `insert_posts`.

---

## Findings

### P1 — High

| # | File | Issue | Reviewer(s) | Conf | Route |
|---|---|---|---|---|---|
| 1 | `x_monitor/store.py:837` + `reattribute.py:332-340` | **`Store.insert_post_brand_signals` has no brand_id guard; the reattribute path can still raise `IntegrityError`, which gets silently swallowed by `try/except Exception`** — so a brand drift mid-run corrupts the post counter without crashing. Adversarial F1: reattribute.py:307-326 calls `Store.insert_post_brand_signals` directly (not through `insert_posts`), bypassing the new filter. The reattribute's own `try/except Exception` (line 332-340) catches and continues. Net effect: a reattribute run can drop 100% of signal rows and report success. | adversarial, agent-native | 0.85 | gated_auto → downstream-resolver |
| 2 | `x_monitor/attribution.py:709` | **No regression test for `_resolve_signal_model` resolution ladder** — the exact scenario that caused the silent 5.5× slowdown (operator's `ANTHROPIC_MODEL=MiniMax-M2.7`) has no guard. A future change that breaks env-var resolution will silently regress perf. | testing, adversarial | 0.85 | gated_auto → downstream-resolver |
| 3 | `x_monitor/store.py:298` | **Cross-mention signals dropped silently** — `_extract_per_brand_signals` returns the LLM's keys verbatim for the v1.8 `signals: dict` path, but the new `if b not in valid_brands: continue` filter drops any signal whose `brand_id` is not in the *post's* own `valid_brands`. A post attributed to `{qwen}` can legitimately carry a signal for `deepseek` ("Qwen > DeepSeek"); that signal is now lost. The new test (`test_insert_posts_drops_hallucinated_brand_signals`) encodes this as the contract — it asserts `len(rows) == 2`, locking in the wrong behavior. | maintainability (M-01), adversarial (F4) | 0.80 | gated_auto → downstream-resolver |

### P2 — Moderate

| # | File | Issue | Reviewer(s) | Conf | Route |
|---|---|---|---|---|---|
| 4 | `x_monitor/store.py:297-298` | **Silent drop with no log/counter/return-value change** — `if b not in valid_brands: continue` removes any observability that the LLM is hallucinating. `store.py` has no `import logging`. `insert_posts` returns only `n_new`. The regression test passes even if 99/100 signals were dropped. v1.8's MON-09 monitoring cannot distinguish "LLM never returns signals" from "LLM returns signals but all hallucinate." | correctness, learnings, reliability, adversarial | 0.85 | gated_auto → review-fixer (safe: add `import logging; log = logging.getLogger(__name__); log.warning(...)` before `continue`) |
| 5 | `x_monitor/store.py:316-354` | **Cascading FK unguarded at `post_mentions`** — same `insert_posts` transaction contains a second loop writing `post_mentions.brand_id` from the same LLM-derived MentionRow source. Schema has the same FK (`post_mentions.brand_id REFERENCES brands(brand_id)`, migration 004 lines 116-117). Next LLM hallucination in mentions crashes at line 348 with the same `IntegrityError`. attribution.py:9 docstring claims hallucinated brand_ids are "dropped (R8)" — misleading because R8 only applies to the `post_brand_signals` path. | reliability (REL-3) | 0.85 | gated_auto → downstream-resolver |
| 6 | `tests/test_store.py:259` | **Test coverage gaps in `test_insert_posts_drops_hallucinated_brand_signals`:** (a) the legacy `signal=str` broadcast path through `_extract_per_brand_signals` (store.py:408-411); (b) all-unknown signals dict (zero real brands); (c) ON CONFLICT DO UPDATE re-insert with mixed known/unknown. | testing | 0.80 | gated_auto → review-fixer |
| 7 | `x_monitor/store.py:200-213, 298` | **Pre-existing drift: `valid_brands` is per-post `KNOWN_MODELS` intersect (7 brands), but v1.8 migration 004 seeded 12 brands** (adds mistral, stepfun, ernie, hunyuan). A signal for a v1.8 brand not in `KNOWN_MODELS` is silently dropped. Both reviewed commits inherit this gap. | correctness | 0.85 | advisory → downstream-resolver (pre-existing, owned by v1.8 detection-tables workstream — task #109) |
| 8 | `x_monitor/run.py:740-770` + `deploy/run-pipeline-with-notify.sh` | **No operator-visible signal for degraded runs** — `summary.totals` only reports `n_inserted`. After the fix, the cron returns 0 even when 100% of signals were hallucinated. `osascript` notification in `run-pipeline-with-notify.sh` fires on `$RC -ne 0` only. MTTR for silent LLM degradation = "next time the operator opens the dashboard." | reliability (REL-2, REL-5) | 0.80 | manual → downstream-resolver |
| 9 | `x_monitor/attribution.py:730` | **`ANTHROPIC_MODEL` env var still wins over the M3.0 default** — if any shell process re-sources the old `~/.env.secrets` (or a wrapper script overrides), the slow M2.7 path silently returns. Operator must permanently clear the env var. | correctness, learnings, adversarial | 0.75 | advisory → release |
| 10 | `x_monitor/store.py:296` | **Pre-existing: v1.8 detection-tables-not-seeded** masks this fix's signal coverage. Verified cycle 20260620T113441_0000-3801fe2a: 50 posts inserted, 0 signal rows (all _unattributed). Tracked as task #109. | learnings | 0.92 | advisory → human (pre-existing, tracked) |

### P3 — Low

| # | File | Issue | Reviewer(s) | Conf | Route |
|---|---|---|---|---|---|
| 11 | `x_monitor/store.py:296-304` | 9-line comment block breaks the file's `# R9:` / `# R11:` / `# Decision 15:` tag convention. Either tag it (`# Decision 16: …`) and trim, or shrink to one line. | project-standards, maintainability | 0.75 | gated_auto → review-fixer |
| 12 | `x_monitor/reattribute.py:324` | `insert_post_brand_signals` callers bypass new filter; upstream `_parse_signal_response` already drops invalid brand_ids, so this is defense-in-depth asymmetry. One-line comment would help future maintainers. | agent-native | 0.62 | advisory → human |
| 13 | `tests/test_store.py:264` | Test bypasses the existing `_make_post` factory and constructs the post dict inline (15+ keys). After loosening the factory's annotation, this would be more maintainable. | maintainability | 0.65 | advisory → human |
| 14 | `tests/test_store.py:265` | Test couples to `KNOWN_MODELS` containing `qwen`/`deepseek` — acceptable but worth documenting. | testing, correctness | 0.80 | advisory → human |
| 15 | `x_monitor/attribution.py:739` | `_SIGNAL_MODEL` is a module-level constant frozen at import. The M2.7→M3.0 default swap silently changes behavior for any operator who had `ANTHROPIC_MODEL` unset and was getting M2.7 transparently; commit message doesn't call this out. (Note: reliability reviewer (REL-6) corrected my mental model — `_resolve_signal_model` is called at import AND at function-call site, so env-var rotation within a process *would* take effect on next call. Still worth documenting.) | adversarial, reliability | 0.65 | advisory → human |
| 16 | — | **Pre-existing reliability:** `pipeline_lock` (`fcntl.flock`) is non-blocking; contended cycles exit 0 silently. A second cycle started 1m2s after the first during the failed state — pre-existing, not regressed. | reliability (REL-4) | 0.70 | advisory → human |
| 17 | — | **Pre-existing:** `_unattributed` skip at `store.py:284-286` is also silent (same observability gap as the new fix). Worth fixing together with #4. | adversarial (F2) | 0.75 | advisory → human |

---

## Requirements Completeness

Plan source: **explicit** (`plan:docs/plans/2026-06-19-005-feat-fix-x-monitor-cron-runtime-plan.md`).

| Req | Status | Note |
|---|---|---|
| R1 (cron exits 0) | **Met** (Units 1-3 landed 2026-06-19) | Verified end-to-end on cycle 20260620T113441 |
| R2 (LaunchAgent loaded) | **Met** | `lsof -nP -iTCP:5000 -sTCP:LISTEN` confirms dashboard running |
| R3 (dry-run exits 0) | **Met** | `python -m x_monitor run --dry-run` runs clean |
| R4 (≥1 post in 24h) | **Met** | 50 new posts in cycle 20260620T113441 |
| R5 (post_brand_signals > 0, matches ±5%) | **Partially met** | post_brand_signals=2,010 from reattribute backfill (Unit 4); but **all 50 new posts are _unattributed** — see P2 #10 |
| R6 (dashboard polarity non-zero) | **Met for 7 brands** | Pre-existing treemap data; live cron path doesn't add new signals yet |
| R7 (plist edits idempotent) | **Met** | Both plists reloaded without duplication |

| Unit | Status | Note |
|---|---|---|
| Unit 1 (WatchPaths patch) | Met | Committed earlier |
| Unit 2 (scheduled 15-min LaunchAgent) | Met | Committed earlier |
| Unit 3 (config + dry-run) | Met | Committed earlier |
| Unit 4 (signal backfill) | Met | 2,010/2,700 brand-rows classified |

**The two reviewed commits (421248e, 43035b0) are not in the plan's unit list** — they're post-execution follow-ups discovered when the cron fired. The FK crash is a related new limitation not covered by the plan's "Operational Notes." **Worth updating the plan's "Operational Notes" section to document the new limitation** (FK filter in store.py, M3.0 default, M2.7 deprecation, reattribute path's analogous unguarded site).

---

## Applied Fixes

None — this is an interactive review, no autofix mode. The diff is already committed.

---

## Residual Actionable Work

| Finding | Action | Owner |
|---|---|---|
| #1 (P1) reattribute path bypasses FK filter | Extend the `valid_brands` filter to `insert_post_brand_signals` and the `post_mentions` loop in `insert_posts`. Also fix the reattribute-side `try/except Exception` that silently swallows IntegrityError. ~10 lines. | downstream-resolver |
| #2 (P1) no test for `_resolve_signal_model` | Add parametrized test: `(env unset, proxy URL) → M3.0`; `(env=M2.7, proxy URL) → M2.7`; `(env=haiku, no proxy) → haiku`. ~30 lines. | downstream-resolver |
| #3 (P1) cross-mention signals dropped | Change `if b not in valid_brands` to `if b not in KNOWN_MODELS` (or a new `cross_mention_valid` set) and update the regression test to assert cross-mention case. | downstream-resolver |
| #4 (P2) silent drop no log | `import logging; log = logging.getLogger(__name__); log.warning("insert_posts: dropping signal for unknown brand_id=%r (post_id=%s, signal=%r)", b, tweet_id_str, sig)`. Mirrors `attribution.py:814` style. 1-line. | review-fixer (safe_auto if approved) |
| #5 (P2) cascading FK at post_mentions | Same 3-line filter pattern as #4 applied to the mentions loop. | downstream-resolver |
| #6 (P2) test coverage gaps | Add 2 more test cases: legacy `signal=str` broadcast + all-unknown signals. | review-fixer |
| #8 (P2) operator observability | Add `n_signals_written` / `n_signals_dropped` to `summary.totals`; add threshold check in `run-pipeline-with-notify.sh` (e.g. notify if `n_signals_dropped / n_inserted > 0.5`). | downstream-resolver |
| #9 (P2) env precedence | Document the operator step: clear `ANTHROPIC_MODEL` from `~/.env.secrets` and `~/.zshrc` / `~/.zshenv` after merging. (Done in this session — both `~/.zshrc:80` and `~/.zshenv:13` now point to M3.0.) | release |
| #10 (P2) v1.8 detection-tables-not-seeded | Run `scripts/2026-06-19-180000-seed-detection-tables.py`. Already tracked as task #109. | human (operator) |
| #11 (P3) comment style | Trim the 9-line comment to one line: `# R11: drop LLM-hallucinated brand_ids before INSERT (regression: cycle 20260620T081403 FK crash).` | review-fixer |
| Update plan `Operational Notes` | Document: M3.0 default, M2.7 deprecation, FK filter at `store.py:296`, reattribute path's analogous gap (finding #1). | human |

---

## Pre-existing

- #7 (P2) `valid_brands` drift — pre-existing, advisory.
- #10 (P2) detection-tables-not-seeded — pre-existing, tracked.
- #16 (P3) pipeline_lock non-blocking — pre-existing.
- #17 (P3) `_unattributed` skip silent — pre-existing.
- #15 (P3) `_SIGNAL_MODEL` is module-level — pre-existing, no change in this diff.

---

## Learnings & Past Solutions

| Pattern | Source | Why it matters |
|---|---|---|
| FK hot-path crash on LLM hallucination | `feedback_xmonitor_fk_hot_path_2026-06-20.md` | Defines the canonical pattern: always intersect LLM output against source-of-truth registry before INSERT. The fix in 43035b0 implements this. Findings #1, #3, #5 extend the pattern to other INSERT sites. |
| minimax proxy M2.7 → M3.0 | `feedback_minimax_proxy_anthropic_compat.md` | The 5.5× speedup rationale for 421248e. M3.0 emits no thinking block (6 vs 150 output tokens/req). |
| store.py is intentionally log-free | `x_monitor/store.py` (no `import logging` anywhere) | The fix author's choice (memory UPDATE 20:35) was explicit. But findings #4, #17 argue this is a maintenance liability, not a feature. |
| v1.8 detection tables NOT auto-seeded by migration 004 | `project_x_monitoring_v18_2026-06-19.md` | Pre-existing blocker (task #109) that the FK fix doesn't address. |
| Top-Gun HF audit: ON CONFLICT only updates INSERT-listed columns | `project_top_gun_hf_audit_2026-05-18.md` | Positive pattern note: `store.py:300` INSERT correctly includes all 3 columns. |
| x-monitor v1.7 list-gate ValueError | `feedback_xmonitor_cron_v17_list_gate.md` | Same wedge class as FK crash (cron silently stuck), different gate. |
| M3 thinking-block performance (compositional) | `feedback_m3_multimodal_terminology.md` + `project_m3_no_oversell_finding.md` | M3.0 was already known to skip thinking for structured JSON (validated 2026-06-01). The docstring update in 421248e aligns with prior finding. |

---

## Agent-Native Gaps

None. The fix is internal to `insert_posts`; `x_monitor run` and `x_monitor reattribute` CLI surfaces unchanged. The reattribute path's bypass of the new filter is noted under finding #1.

---

## Schema Drift Check

Not applicable — no migration file in the diff. The FK is on `post_brand_signals.brand_id` and `post_mentions.brand_id` (migration 004), which is unchanged.

---

## Deployment Notes

The fix is already on main. Operational validation:

```bash
# Confirm env is M3.0:
ssh fuchitalee 'source ~/.zshrc 2>/dev/null; source ~/.env.secrets; echo "ANTHROPIC_MODEL=$ANTHROPIC_MODEL"'

# Confirm code default is M3.0:
ssh fuchitalee 'cd ~/development/minimax-marketing/x-monitoring && source ~/.env.secrets && env -u ANTHROPIC_MODEL PYTHONPATH=. .venv/bin/python -c "from x_monitor.attribution import _resolve_signal_model; print(_resolve_signal_model())"'

# Confirm cron no longer crashes:
ssh fuchitalee 'cd ~/development/minimax-marketing/x-monitoring && source ~/.env.secrets && .venv/bin/python -m x_monitor run'   # expect exit 0
```

**Healthy signal:** `LATEST.running.json` reaches `status: "completed"` within 15 min, `n_inserted > 0`, and DB counts grow by ~50 posts/cycle.

**Failure signals:** `status: "failed"` in any cycle summary; `LATEST.running.json` stuck at `status: "running"` past 1h; `n_inserted = 0` for >2 cycles.

**Pre-deploy roll-forward:** if findings #1, #3, or #5 regress, the cron will crash with the same `IntegrityError` — the only rollback is to revert 43035b0 (re-introduce the crash). Mitigation: keep the v1.8 detection-tables seed work (task #109) in flight so `_unattributed` is a smaller proportion of `valid_brands` fallbacks.

---

## Coverage

- Suppressed: 0 findings (no sub-0.60 P1-P3 entries)
- Untracked files excluded: many doc files in `docs/{plans,brainstorms,reference,issues}/` (none in scope for this review)
- Failed reviewers: 0
- Cross-reviewer agreement: 4 reviewers converged on the silent-drop gap (cluster A); 3 on env precedence (cluster C); 2 on cross-mention drop (cluster B); 2 on test coverage gaps (cluster D).

---

## Verdict

**Not ready.** Three P1 findings must be addressed before this is safe to leave running unattended:

1. **#1 (reattribute path bypasses FK filter):** Direct path to silent data corruption. The reattribute CLI is the only tool that re-classifies historical data; if it silently drops 100% of signals due to a brand drift, the dashboard polarity stops reflecting reality without any alert. **Fix is a 1-3 line guard in `insert_post_brand_signals`** plus removing the `try/except Exception` that swallows the error in reattribute.
2. **#2 (no test for `_resolve_signal_model` resolution ladder):** The whole point of 421248e is that the env-driven default avoids the M2.7 slowdown. A future refactor that breaks env resolution silently regresses performance. **Fix is a 30-line parametrized test.**
3. **#3 (cross-mention signals dropped):** The fix encodes a wrong contract — that signals can only exist for the post's own `brand_id`. The test asserts this. If the v1.8 architecture ever wants to surface "Qwen > DeepSeek" posts with both signals, the fix is in the way. **Fix is changing the filter from `valid_brands` to `KNOWN_MODELS` and adding a cross-mention test case.**

The two P2 findings worth addressing in the same change:

- **#4 (silent drop no log):** trivial 1-line addition, restores observability without adding scope. **safe_auto** if approved.
- **#5 (cascading FK at post_mentions):** same crash class as the original fix, same fix shape. Apply alongside #1.

**Fix order (if proceeding in this session):**
1. Safe auto: add `log.warning` to the new filter (finding #4) — 1 line, no behavior change.
2. Gated: extend filter to `insert_post_brand_signals` and `post_mentions` (findings #1, #5) — 6 lines, restores the same crash defense to other sites.
3. Gated: switch filter from `valid_brands` to `KNOWN_MODELS` + add cross-mention test (finding #3) — semantic change, must be reviewed.
4. Gated: add `_resolve_signal_model` parametrized test (finding #2) — 30 lines, no production code change.
5. Manual: surface dropped-signal counts in `summary.totals` and add threshold check to `run-pipeline-with-notify.sh` (finding #8) — operator-visible.

The P2 pre-existing findings (#7, #10) and P3 findings are advisory; defer to follow-up.

---

## Reviewer Outputs (full)

- correctness: `.context/compound-engineering/ce-review/20260620-203832-217d1a4c/correctness.json`
- testing: `.context/compound-engineering/ce-review/20260620-203832-217d1a4c/testing.json`
- maintainability: `.context/compound-engineering/ce-review/20260620-203832-217d1a4c/maintainability.json`
- project-standards: `.context/compound-engineering/ce-review/20260620-203832-217d1a4c/project-standards.json`
- agent-native-reviewer: `.context/compound-engineering/ce-review/20260620-203832-217d1a4c/agent-native-reviewer.json`
- learnings-researcher: `.context/compound-engineering/ce-review/20260620-203832-217d1a4c/learnings-researcher.json`
- reliability: `.context/compound-engineering/ce-review/20260620-203832-217d1a4c/reliability.json`
- adversarial: `.context/compound-engineering/ce-review/20260620-203832-217d1a4c/adversarial.json`
- kieran-python: `.context/compound-engineering/ce-review/20260620-203832-217d1a4c/kieran-python.json`
