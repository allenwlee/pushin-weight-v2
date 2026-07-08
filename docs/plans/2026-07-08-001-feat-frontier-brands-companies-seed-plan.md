---
title: Seed frontier model companies, brands, and accounts (OpenAI, Anthropic, Google, xAI)
date: 2026-07-08
type: feat
status: ready
product_contract_source: ce-plan-bootstrap
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
---

# Context

We are not adding the frontier models (OpenAI, Anthropic, Grok, Gemini/Gemma)
to our TwitterAPI.io search queries — we only capture posts related to open-weight labs (mostly Chinese). But
because such tweets often *mention* the frontier vendors (e.g.,
"Kimi vs. GPT", "Claude code review", "Gemini 3 release watch"), we need
their `companies` / `brands` / `accounts` rows in the live DB so the
classifier's brand-attribution layer can route mentions of those brands to
real rows instead of dropping them.

The input is a CSV the user supplied at
`/tmp/frontier_models - Sheet1 (1).csv` with 4 rows (OpenAI, Anthropic,
Google, xAI) and a one-shot Python helper that materializes a static
re-application-safe migration. Operator also supplied a 16-row account table
linking each `handle` to its real X/Twitter `author_id`.

The migration lands a single SQLite file:
`x-monitoring/x_monitor/migrations/032_seed_frontier_companies_brands_accounts.sql`.
Source files are SVNicknamed by `lower(replace(display_name, ' ', '_'))`.

# Files to modify

| Path | Change |
|---|---|
| `x-monitoring/x_monitor/migrations/032_seed_frontier_companies_brands_accounts.sql` | **NEW.** Section-by-section inserts. |
| `x-monitoring/scripts/seed_frontier_csv.py` | **NEW.** One-shot CSV→static-SQL helper (kept as a regenerator for future CSVs of the same shape; idempotent on re-run). |
| `x-monitoring/tests/test_migration_032_frontier_seed.py` | **NEW.** Id-mapping and cross-product count assertions against an isolated SQLite DB. |

The live DB `x-monitoring/data/x_monitoring.db` is mutated only after the
test passes.

# Implementation

## U1. CSV → static-SQL helper (`scripts/seed_frontier_csv.py`)

**Why a script, not hand-typed SQL:** the CSV has trailing whitespace,
trailing commas, and a multi-brand row (Google → Gemini + Gemma). The user
explicitly asked for whitespace stripping, lockstep splitting of D/E/F/G/H,
and brand dedup. Hand-typed SQL would either drop columns silently or
require the operator to clean up by hand. A small Python helper emits a
checked-in, reproducible, re-derivable SQL block.

**Behavior:**
1. Read CSV with `csv.DictReader`. Strip whitespace on all string fields.
2. For each row:
   - derive `companies.nickname = lower(replace(display_name, ' ', '_'))`.
   - derive `brands.nickname = lower(replace(brand_display, ' ', '_'))`.
   - `brand_display_en_list = [s.strip() for s in en.split(',') if s.strip()]`
   - `brand_display_zh_cn_list = same for zh`
   - Assert `len(display_list) == len(en_list) == len(zh_list)` (raise loud
     on mismatch — a CSV typo should not silently truncate).
3. Group rows by `(brand.display_name)` to dedup brands across rows
   (defensive for future CSVs with overlap; this CSV has no overlap).
4. Emit a `.sql` file with `INSERT OR IGNORE … RETURNING` blocks ready
   to paste into the migration. The script is idempotent and re-runnable;
   the migration file is the durable artifact.
5. Also emit a `.json` sidecar with the canonical nickname-map so tests
   can assert ordering without re-parsing SQL.

**Test scenarios:**
- Happy path: golden file from a checked-in sample CSV matches the
  generated SQL byte-for-byte (snapshot-style test).
- Whitespace stripping: trailing commas, leading/trailing spaces, multiple
  internal spaces all collapse cleanly.
- Brand dedup: same display_name appearing twice (artificial fixture)
  collapses to one brand row.
- Mismatch raises: D has 3 entries, E has 2 → script raises loud.

## U2. Migration file (`migrations/032_*.sql`)

Header block matches migration 030/031: `{{AGENT_ATTRIBUTION}}` line, plan
reference, idempotency explanation, no `_migrations` INSERT (Store adds
that).

Six sections, all wrapped in a single `BEGIN; … COMMIT;`:

**Section 1 — companies (4 rows).**
`INSERT OR IGNORE INTO companies (nickname, display_name, created_at,
display_name_en, display_name_zh_cn) VALUES (…)`. hq_country stays NULL —
operator can backfill from a follow-up migration.

| nickname | display_name | display_name_en | display_name_zh_cn |
|---|---|---|---|
| openai   | OpenAI   | OpenAI   | OpenAI   |
| anthropic| Anthropic| Anthropic| Anthropic|
| google   | Google   | Google   | Google   |
| xai      | xAI      | xAI      | xAI      |

**Section 2 — brands (5 rows, one row per comma-split brand).**

| nickname | display_name | display_name_en | display_name_zh_cn |
|---|---|---|---|
| gpt    | GPT    | GPT    | GPT    |
| claude | Claude | Claude | Claude |
| gemini | Gemini | Gemini | Gemini |
| gemma  | Gemma  | Gemma  | Gemma  |
| grok   | Grok   | Grok   | Grok   |

`accent_color` left NULL (the DB default is fine; operator can tune later,
mirroring migration 024's `accent_color` placeholder note). `is_sentinel`
defaults to 0.

**Section 3 — `brands_companies` (5 rows; brand_id × company_id).**

```sql
INSERT OR IGNORE INTO brands_companies (brand_id, company_id) VALUES
  ((SELECT id FROM brands    WHERE nickname='gpt'),
   (SELECT id FROM companies WHERE nickname='openai')),
  ((SELECT id FROM brands    WHERE nickname='claude'),
   (SELECT id FROM companies WHERE nickname='anthropic')),
  ((SELECT id FROM brands    WHERE nickname='gemini'),
   (SELECT id FROM companies WHERE nickname='google')),
  ((SELECT id FROM brands    WHERE nickname='gemma'),
   (SELECT id FROM companies WHERE nickname='google')),
  ((SELECT id FROM brands    WHERE nickname='grok'),
   (SELECT id FROM companies WHERE nickname='xai'));
```

Subselect-by-nickname is the canonical pattern used elsewhere in migration
030 and later; it survives re-application without re-numbering surrogate
ids. The `INSERT OR IGNORE` makes the section itself re-application-safe.

**Section 4 — `accounts` (16 rows, keyed on the operator-supplied author_id table).**

`INSERT OR IGNORE INTO accounts (author_id, handle, display_name,
created_at, verified) VALUES (…)`. author_id is the X/Twitter numeric id
column; handle is the `@name`; display_name comes from the operator table.
`verified` defaults to NULL except where already known. bio left NULL.

Full row list (16):

| author_id            | handle            | display_name          |
|----------------------|-------------------|------------------------|
| 4398626122           | OpenAI            | Main official OpenAI account |
| 1633874951508721686  | OpenAIDevs        | Official developer/platform updates |
| 1605                 | sama              | Sam Altman             |
| 162124540            | gdb               | Greg Brockman          |
| 825088493764407298   | polynoamial       | Noam Brown             |
| 1353836358901501952  | AnthropicAI       | Official Anthropic     |
| 1943306828697550848  | claudeai          | Official Claude        |
| 874126509245476864   | DarioAmodei       | Dario Amodei           |
| 33836629             | karpathy          | Andrej Karpathy        |
| 1806359170830172162  | GeminiApp         | Google Gemini          |
| 1908326331609468928  | googlegemma       | Official Gemma         |
| 1482581556           | demishassabis     | Demis Hassabis         |
| 14130366             | sundarpichai      | Sundar Pichai          |
| 284333988            | OfficialLoganK    | Logan Kilpatrick       |
| 1720665183188922368  | grok              | Official Grok          |
| 44196397             | elonmusk          | Elon Musk              |

**Section 5 — `brands_accounts` role=official (cross-product: every brand × every official account for that row's company).**

Per row:
- OpenAI/GPT: 2 brands in that row? No, 1 (GPT). Cross-product against 2
  official handles (OpenAI, OpenAIDevs) → 2 rows.
- Anthropic/Claude: 1 brand × 2 official handles (AnthropicAI, claudeai) → 2 rows.
- Google/{Gemini, Gemma}: 2 brands × 2 official handles (GeminiApp,
  googlegemma) → 4 rows.
- xAI/Grok: 1 brand × 1 official handle (grok) → 1 row.

Total role=official cross-product rows: **9**.

All rows use `role_id=2` (the canonical `official` role; verified from
introspection: id=2 = `official`, id=3 = `staff`).

Re-application safety: `(brand_id, accounts_id)` is the primary key, so
`INSERT OR IGNORE` no-ops on re-apply.

**Section 6 — `brands_accounts` role=staff (cross-product).**

Per row:
- OpenAI/GPT: 1 brand × 3 staff handles (sama, gdb, polynoamial) → 3 rows.
- Anthropic/Claude: 1 brand × 2 staff handles (DarioAmodei, karpathy) → 2 rows.
- Google/{Gemini, Gemma}: 2 brands × 3 staff handles (demishassabis,
  sundarpichai, OfficialLoganK) → 6 rows.
- xAI/Grok: 1 brand × 1 staff handle (elonmusk) → 1 row.

Total role=staff cross-product rows: **12**.

All rows use `role_id=3`.

**Section 7 — `added_at` is implicit on insert.** SQLite default fills
`added_at` to NULL on `INSERT`, and we don't have a per-row timestamp the
operator cares about — section 6 last. Migration stores NULL for `added_at`.

## U3. Id-mapping test (`tests/test_migration_032_frontier_seed.py`)

Use a `tmp_path` SQLite DB built by running migration 032 against an empty
schema (migrations 000 through 031 applied first via the same `Store`
machinery the live system uses). Assertions:

- `SELECT COUNT(*) FROM companies WHERE nickname IN ('openai','anthropic','google','xai')` = 4.
- `SELECT COUNT(*) FROM brands WHERE nickname IN ('gpt','claude','gemini','gemma','grok')` = 5.
- `SELECT COUNT(*) FROM brands_companies` = 5.
- `SELECT COUNT(*) FROM accounts` = 16.
- `SELECT COUNT(*) FROM brands_accounts WHERE role_id=2` = 9.
- `SELECT COUNT(*) FROM brands_accounts WHERE role_id=3` = 12.
- Joint query: for each brand_id, exactly 1 company_id resolves (no orphan
  brands). For each brand × company pair in the cross-product graph, at
  least 1 staff + 1 official row exists where expected.

Idempotency assertion: rerun the migration on the same DB; row counts
unchanged.

# Verification

1. Run the new test file from `x-monitoring/`:
   `python3 -m pytest tests/test_migration_032_frontier_seed.py -v`
   — all assertions pass.
2. Run the migration loader against the live DB:
   ```
   cd x-monitoring
   python3 -c "from x_monitor.store import Store; \
       s = Store('data/x_monitoring.db', auto_migrate=True); \
       s.close(); print('OK')"
   ```
   — exit 0.
3. Live counts via `sqlite3 data/x_monitoring.db`:
   - `SELECT COUNT(*) FROM companies WHERE nickname IN ('openai','anthropic','google','xai');`  → 4.
   - `SELECT COUNT(*) FROM brands WHERE nickname IN ('gpt','claude','gemini','gemma','grok');`    → 5.
   - `SELECT COUNT(*) FROM accounts WHERE author_id IN (4398626122, …, 44196397);`                → 16.
4. Spot-check a join:
   ```
   SELECT b.nickname AS brand, c.nickname AS company, r.key AS role, COUNT(*)
     FROM brands_accounts ba
     JOIN brands b    ON ba.brand_id   = b.id
     JOIN accounts a  ON ba.accounts_id = a.id
     JOIN roles r     ON ba.role_id    = r.id
     JOIN brands_companies bc ON bc.brand_id = b.id
     JOIN companies c        ON bc.company_id = c.id
    WHERE c.nickname IN ('openai','anthropic','google','xai')
    GROUP BY b.nickname, c.nickname, r.key
    ORDER BY c.nickname, b.nickname, r.key;
   ```
   — should print (gpt × openai × official = 2, … × staff = 3), (claude ×
   anthropic × official = 2, … × staff = 2), (gemini × google × official =
   2, … × staff = 3), (gemma × google × official = 2, … × staff = 3),
   (grok × xai × official = 1, … × staff = 1).

# Commit strategy

One commit, message:

```
feat(x-monitor): migration 032 — seed frontier companies/brands/accounts

Land OpenAI, Anthropic, Google, xAI companies; GPT, Claude, Gemini,
Gemma, Grok brands; 16 official/staff accounts. Frontier vendors
are not in our TwitterAPI search queries (we only capture Chinese-
model posts), but Chinese-model posts frequently mention them, so
the attribution layer needs their brand rows to attach mentions to.

- migrations/032_seed_frontier_companies_brands_accounts.sql: section-
  by-section INSERT OR IGNORE blocks with subselect-by-nickname
  for the brand→company and account→role joins; re-application safe.
- scripts/seed_frontier_csv.py: regenerator for future CSVs of the
  same shape. Strips whitespace, splits comma-lists in lockstep,
  asserts zip-strict, dedups by brand display_name.
- tests/test_migration_032_frontier_seed.py: row-count assertions
  (4/5/5/16/9/12) plus re-apply idempotency check.
```

# Open Questions

1. **NVIDIA** — the operator did not include NVIDIA in the CSV. If the
   intent was to capture NVIDIA mentions in Chinese-model posts too, this
   migration is incomplete. **Defer**: ask operator if NVIDIA should be
   added in a follow-up apply (it would be a one-row addition since
   Nemo / Megatron / NeMo are non-frontier; but `nvidia` as a company
   alone might be the intended scope).
2. **`hq_country` is NULL** for all 4 frontier companies. The DB schema
   supports it; the prompt did not specify. Operator can backfill via a
   follow-up migration (US for all 4).
3. **`accent_color`** left NULL on brand rows. Other migrations leave a
   `#9ca3af` placeholder gray. Operator asked for "create brand insert/
   update … with id=, display_name=…" — no color mentioned. Conservative
   choice: NULL. If preferred, set `#9ca3af` to mirror migration 030's
   style.
