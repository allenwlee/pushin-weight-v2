## x-monitor v1.8 `AnthropicClaudeClient` routes through minimax proxy — M2.7 emits thinking blocks, M3.0 doesn't

### TL;DR

The v1.8 `AnthropicClaudeClient` now supports the minimax proxy (`api.minimax.io/anthropic`) by reading `ANTHROPIC_BASE_URL` and swapping to `MINIMAX_API_TOKEN`. The fix works end-to-end. **The original "25× slowdown" turned out to be the operator's env defaulting to M2.7, not the proxy itself** — M2.7 emits a 150-token thinking block per call (even for trivial JSON), while M3.0 returns 6 output tokens in ~0.9s. Env + code default now both point at M3.0. The proxy path is now the operator's preferred route; M2.7 is no longer used. Issue is also tracking a separate, blocker-level bug: the cron hot path crashes on a FK violation at `store.py:294` before any LLM call fires.

### Context

**Shipped 2026-06-19** (commit `cc02a63`): the x-monitor cron unblock + post_brand_signals backfill. Backfill ran via direct Anthropic API (operator's `ANTHROPIC_API_KEY` resolved to `api.anthropic.com`) using `claude-haiku-4-5`. Result: 2,010/2,700 brand-rows classified (74.4%), 0 errors, ~$0.10-0.30 Haiku 4.5 spend, 47 minutes wall clock.

**Shipped 2026-06-20** (commit `49a2ab7`): `AnthropicClaudeClient` now honors the operator's `ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic` and `ANTHROPIC_MODEL=MiniMax-M2.7` shell config. Two changes:
1. `x_monitor/attribution.py:_resolve_signal_model()` — model id resolves from `ANTHROPIC_MODEL` env → proxy default → `claude-haiku-4-5` default
2. `x_monitor/reattribute.py:build_anthropic_client_from_env()` — detects minimax proxy via URL substring, swaps to `MINIMAX_API_TOKEN`, forwards `base_url` to `Anthropic()`

**Tested end-to-end** with `classify_signal(text="Just tried MiniMax M3.0 for code review...", brand_ids=["minimax","deepseek"], ...)` → returns `{"minimax": "praise"}` correctly. 55/55 tests pass on `test_attribution.py`, `test_reattribute.py`, `test_translator.py`. Full suite: 509 pass, 2 pre-existing `test_headlines` failures unrelated.

### What we discovered about the "25× slowdown" — it was M2.7, not the proxy

I re-ran the proxy path on a trivial `Reply with JSON: {"hi": 1}` prompt and compared model ids:

| Model | Latency | Content blocks | output_tokens | Note |
|---|---|---|---|---|
| `MiniMax-M2.7` | **4.91s** | **2** | **156** | Emits a thinking block + tiny text |
| `MiniMax-M3.0` | **0.89s** | 1 | 6 | No thinking, ~5.5× faster |
| `MiniMax-M3.0-mini` | 0.91s | 1 | 6 | |
| `MiniMax-M2.5-Flash` | 1.36s | 1 | 6 | |

M2.7 generates 150 tokens of internal reasoning to produce 8 characters of JSON. M3.0 returns the same JSON in 6 tokens. The 25× slowdown in the original backfill estimate was 156/6 ≈ **26×** — exactly the ratio we saw. **The proxy itself is fine. The model choice is the cost.**

The class `AnthropicClaudeClient` is generic inference — it just calls `messages.create(model=..., messages=...)` and concatenates text blocks. Nothing in the code is Anthropic-specific; the same code path works against the proxy unchanged.

### Resolution

**1. Operator env flipped to M3.0** (2026-06-20):
- `~/.zshrc:80` → `export ANTHROPIC_MODEL=minimax/MiniMax-M3.0`
- `~/.zshenv:13` → `export ANTHROPIC_MODEL="MiniMax-M3.0"`
- `MINIMAX_API_TOKEN` and `ANTHROPIC_BASE_URL` unchanged

**2. Code default updated to M3.0** (commit pending):
- `x_monitor/attribution.py:_resolve_signal_model()` proxy default: `MiniMax-M2.7` → `MiniMax-M3.0`
- Env var `ANTHROPIC_MODEL` still wins if set (operator's choice); the default only fires when env is unset

**3. M2.7 retired from this project** — env, code default, and any new test fixtures. Docstrings still mention M2.7 as historical context (e.g., "M2.7 emits ~150 tokens of thinking") but no config or code path depends on it.

### The blocker: cron hot path crashes before any LLM call

While validating the M3.0 path, I ran the production pipeline end-to-end (`python -m x_monitor run` on fuchitalee, 2026-06-20 17:14:03 JST). The cycle crashed at the DB-write stage with `sqlite3.IntegrityError: FOREIGN KEY constraint failed` from `x_monitor/store.py:294`. The crash:

- **Happens before any LLM signal call** — we never get to exercise the M3.0 path
- **Crashes the cron entirely** — `LATEST.running.json` is left at `status: "running"` with `finished_at: null`, dashboard never updates
- **0 new posts land in `posts`** for the cycle day — but the rollback appears to hold (counts confirmed clean on 2026-06-20)
- **Call A succeeds (50 tweets from `(list:<x_monitor_list_id>) min_faves:1`)** — but Call B never fires, translation never runs, `attribute_to_brand` never runs

The root cause: `insert_posts` writes `post_brand_signals(post_id, brand_id, signal)` for every brand the LLM classified. The `brand_id` column has a FK to `brands(brand_id)`, and **the LLM sometimes returns a brand_id that is not in the brands table** (a hallucination — `_unattributed`, a brand that exists in filter YAML but not the DB, or a typo). When that happens sqlite3 raises `IntegrityError: FOREIGN KEY constraint failed` and the Python process exits.

Memory: `feedback_xmonitor_fk_hot_path_2026-06-20.md` captures the full run, root cause, and proposed fix.

### Files touched

- `~/.zshrc:80` (env, operator)
- `~/.zshenv:13` (env, operator)
- `x_monitor/attribution.py:709-737` — `_resolve_signal_model()` now defaults to M3.0
- `x_monitor/reattribute.py:360-405` — `build_anthropic_client_from_env()` proxy detection + token swap (unchanged from #5)
- `x_monitor/store.py:294` — **the FK crash, NOT YET FIXED**

### Open questions / next steps

1. **Fix the FK hot path**: intersect `per_brand_signals` against `valid_brands` before INSERT into `post_brand_signals` in `x_monitor/store.py:286-300`. One-line change. See `feedback_xmonitor_fk_hot_path_2026-06-20.md` for the patch shape.
2. **Investigate the pipeline_lock failure** — a second cycle (`20260620T081505_0000-c44bf860`) started 1m2s after the first. The `fcntl.flock` on `data/runs/LOCK` is supposed to prevent this. The lock may not be acquired in the right scope, or the cron plist may be re-launching the wrapper while the first cycle's lock state is ambiguous (zombie?).
3. **Re-validate M3.0 end-to-end** once the FK is fixed — measure actual signal classification latency on production prompts (not just `{"hi": 1}`). Expect ~0.9s per call based on the trivial probe.
4. **Backfill decision** from the original issue body: still open. Options A (skip), B (direct API), C (proxy overnight) are unchanged. With M3.0 in play, option C's ETA drops from ~26h to ~50min (M3.0 is ~5.5× faster than M2.7). Option B is now redundant unless the operator wants to avoid the proxy entirely.

### Verification

```bash
# Confirm env is M3.0
ssh fuchitalee 'source ~/.zshrc 2>/dev/null; source ~/.env.secrets; echo "ANTHROPIC_MODEL=$ANTHROPIC_MODEL"'

# Confirm code default is M3.0
ssh fuchitalee 'cd ~/development/minimax-marketing/x-monitoring && \
  source ~/.env.secrets && env -u ANTHROPIC_MODEL PYTHONPATH=. .venv/bin/python -c \
  "from x_monitor.attribution import _resolve_signal_model; print(_resolve_signal_model())"'

# Both should print: MiniMax-M3.0
```

### Related

- Plan: `docs/plans/2026-06-19-005-feat-fix-x-monitor-cron-runtime-plan.md`
- Commits: `cc02a63` (cron unblock + first backfill), `49a2ab7` (proxy path)
- Memory: `feedback_minimax_proxy_anthropic_compat.md` (proxy contract), `feedback_xmonitor_fk_hot_path_2026-06-20.md` (FK crash), `feedback_reattribute_with_llm_required.md` (--with-llm three preconditions), `feedback_xmonitor_cron_v17_list_gate.md` (cron runtime fix)
