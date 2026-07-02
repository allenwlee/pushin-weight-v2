---
title: "deterministic schema image build pipeline (.dot + build script + trigger rule)"
type: feat
status: completed
date: 2026-06-26
---

# deterministic schema image build pipeline

## Overview

Persist the post-023 schema image as a **committed source of truth** + a **single build command** + a **discoverable trigger rule**, so every future regeneration produces a byte-identical image. The current image at `docs/reference/images/xmonitor-schema-post-batch.png` was rendered ad-hoc (matplotlib, hand-tuned layout) and there is no committed source for it; the next regeneration would re-invent the layout. This plan locks the look-and-feel down.

Three pieces land:
1. **`docs/reference/schema.dot`** — graphviz source describing the 24 tables + FK edges + legend + cluster groupings.
2. **`scripts/build_schema_image.sh`** — one-command rebuild (`dot -Tpng ... > image.png`), plus a `--check` flag that exits 1 when the image is stale relative to the source (for future CI use).
3. **Trigger rule** in `CLAUDE.md` (repo root) + a one-liner note in `docs/reference/db-schema.md` pointing at the build script, so any contributor touching `x-monitoring/x_monitor/migrations/*.sql` knows to regenerate.

The CI drift check is explicitly **deferred** — no `.github/workflows/` exists in this repo today, and standing one up is out of scope for this small change.

## Problem Frame

Each prior regeneration of the schema image looked different:
- `825850c` (2026-06-23-ish): plain image
- `ba3b6ae` (2026-06-26 10:00): "20 tables across 4 rows" — different layout
- `3e951cc` (2026-06-26 10:06): "all columns 3200x2400" — different layout again
- `7038356` (current): matplotlib, 3200x3000, different style entirely

There is no committed `.dot`, `.mmd`, `.drawio`, or Python source for any of these — the images were generated externally (likely OmniGraffle or similar) and committed as binary blobs. A new contributor regenerating the image today has nothing to start from and would produce a different visual.

Graphviz (`dot`) gives us a deterministic, diff-able, declarative source. Output is stable across runs and machines (modulo font availability, which we lock with a `fontname` attribute).

## Requirements Trace

- **R1.** A committed `docs/reference/schema.dot` exists that, when rendered with `dot -Tpng`, produces an image showing every table + column + FK edge in the post-023 schema (24 tables: brands, companies, accounts, hf_orgs, post_type_keys/labels, sentiment_keys/labels, roles/role_labels, posts, products, account_post_appearances, search_queries, posts_brands, brands_accounts, brands_companies, companies_accounts, posts_brands_mentions, posts_brands_signals, brand_search_terms, brand_hashtags, brand_keywords, _migrations).
- **R2.** The `.dot` reflects post-023 column renames: `brands.nickname`, `companies.nickname`, no `signal_id` in `posts_brands_signals`, no `signals` / `signal_labels` tables. The composite PK of `posts_brands_signals` is `(post_id, brand_id)` (both `INTEGER NOT NULL` with FKs to `posts.id` and `brands.id` respectively).
- **R3.** A `scripts/build_schema_image.sh` rebuilds the image in one command and supports a `--check` flag that exits non-zero when the image is stale.
- **R4.** `CLAUDE.md` at repo root contains a trigger rule: when `x-monitoring/x_monitor/migrations/*.sql` changes, run the build script and commit the regenerated image.
- **R5.** `docs/reference/db-schema.md` contains a one-liner note near the image pointing at the build script.

## Scope Boundaries

- **In scope:** the `.dot` source, the build script, the CLAUDE.md rule, the db-schema.md note.
- **Out of scope:** a `.github/workflows/*.yml` CI check (no workflow file exists in the repo today; standing up CI is a separate concern). The build script's `--check` mode is built so this can be added later without touching the script.
- **Out of scope:** graphviz install. This is a manual one-time setup documented in the plan's prerequisites; the build script will fail with a helpful `brew install graphviz` message if `dot` is missing.
- **Out of scope:** regenerating the image to a different visual style. The current matplotlib image at `7038356` will be **replaced** by the graphviz render. Visual differences are acceptable; what matters is that the next regeneration produces a byte-identical image (modulo graphviz version).

## Context & Research

### Relevant Code and Patterns

- **`docs/reference/db-schema.md`** — owner of the image; already references it with `![x-monitor schema after migration batch 011-023](images/xmonitor-schema-post-batch.png)`.
- **`x-monitoring/scripts/*.sh`** uses the `{{AGENT_ATTRIBUTION}}` header convention. The new `scripts/build_schema_image.sh` at the **repo root** (not under `x-monitoring/`) follows the same header convention but lives at root because it operates on `docs/`, not `x-monitoring/`.
- **`docs/plans/2026-06-26-001-refactor-brand-id-to-nickname-plan.md`** — the prior plan that updated `db-schema.md` for migrations 020–023. Its `db-schema.md` update at commit `d406a52` is the doc this plan extends with the regeneration note.

### Institutional Learnings

- The x-monitor migration ledger (`_migrations`) has a per-version test pattern (`test_migration_NNN_<topic>.py`). The schema image is the **visual** companion to that ledger and should be regenerated whenever a new migration lands.
- Public Store API contract preservation is done via SQL aliasing (`b.nickname AS brand_id`). The schema image's `brand_hashtags` / `brand_keywords` tables hold TEXT FKs to `brands.nickname` (not refactored by migration 020) — the `.dot` must preserve this asymmetry rather than "fixing" it.

### External References

- Graphviz `dot` user guide: https://graphviz.org/doc/info/lang.html
- `dot` HTML-like labels: https://graphviz.org/doc/info/shapes.html#html
- `brew install graphviz` is the standard install on macOS.

## Key Technical Decisions

- **graphviz over alternatives:** graphviz is the de-facto ER diagram tool with deterministic output and a stable text source. Mermaid CLI requires Node + Chromium (~200MB). matplotlib (the previous ad-hoc approach) requires committing both a script and a declarative spec — more moving parts than a single `.dot` file.
- **Source-of-truth lives next to the image:** `docs/reference/schema.dot` sits next to the PNG it generates. Anyone editing the image edits the `.dot` and runs the build script.
- **`--check` compares git-tracked hashes, not file mtimes:** mtimes break under `git checkout`, `git reset`, branch switches, etc. Hash diff is robust against all of those.
- **CLAUDE.md is created (not modified):** no `CLAUDE.md` exists at repo root today. This plan creates it with a single trigger rule and a one-line header explaining its purpose. Future agent-facing rules grow here.
- **db-schema.md note is a single sentence:** points at the build script. Does not duplicate the CLAUDE.md rule.

## Prerequisites

- graphviz installed locally: `brew install graphviz`. The build script checks for `dot` and fails with a helpful message if it's missing, so this is not blocking for the plan's success — only for actually running the build.

## Open Questions

### Resolved During Planning

- *Where does the trigger rule live?* **Both** — CLAUDE.md at root (discoverable to agents) + a one-liner in db-schema.md (next to the image).
- *Run `brew install graphviz` as part of the plan?* **No** — document it as a prerequisite; the script's error path handles the missing-`dot` case.

### Deferred to Implementation

- *Exact node layout algorithm (`dot` vs `neato` vs `fdp`)?* — implementer picks; `dot` (hierarchical) is the safe default and produces the most readable ER-style layout for ~24 nodes. Switch to `neato` only if the first render is unreadable.
- *Font choice for the `.dot`?* — pin `fontname="Helvetica"` in the `.dot` header (cross-platform-ish; macOS has it natively, Linux substitutes). The Risks table documents the cross-platform caveat.
- *`--check` semantics:* **commit-hash comparison** — `git log -1 --format=%H -- <path>` for each file; equality = clean. Requires `.dot` and `.png` to be co-committed for `--check` to report clean. U2 co-commits the first render alongside the script.
- *Source recipe for the `.dot`:* **hand-author from migrations + R1 table list**. The implementation walks `x-monitoring/x_monitor/migrations/0*.sql` (migrations 1–20, 22, 23), applies them to an in-memory SQLite (using the existing migration files), introspects via `sqlite3 :memory: ...`, and emits `.dot` directly. No `/tmp` artifacts required; reproducible from the repo alone.
- *Output dimension target for the `.dot`:* **accept default `dot` output (~1000×1500 px for this schema)**. The goal is deterministic regeneration, not pixel parity with the prior matplotlib image at 3200×3000.

## High-Level Technical Design

> *Directional guidance, not implementation specification. The implementing agent treats this as shape context.*

**`docs/reference/schema.dot` shape:**

- One `digraph` with `rankdir=LR` (left-to-right) or `TB` (top-to-bottom). TB is more conventional for ER diagrams with clusters.
- Each table is a `node` with an HTML-like label: a `<table>` whose `<tr>`s are the columns. PK columns get `bgcolor="#FADBD8"` (red wash); FK columns get `bgcolor="#D6EAF8"` (blue wash). Columns are `<td>` cells with the column name + type.
- Edges drawn from FK columns to parent PK columns, labeled with the FK constraint name where available. Edge style: thin solid arrows in `#7F8C8D`.
- 7 `subgraph cluster_X` blocks matching the prior layout's clusters. Each cluster's contents:
  - `lookup` → `brands`, `companies`, `accounts`, `hf_orgs`
  - `enum_i18n` → `post_type_keys`, `post_type_labels`, `sentiment_keys`, `sentiment_labels`, `roles`, `role_labels`
  - `fact` → `posts`, `products`
  - `edges` → `account_post_appearances`, `search_queries`
  - `mn` → `posts_brands`, `brands_accounts`, `brands_companies`, `companies_accounts`
  - `signal` → `posts_brands_mentions`, `posts_brands_signals` (named for historical reasons; no `signals`/`signal_labels` tables post-022)
  - `meta` → `_migrations`
  Clusters are styled with `style=filled; fillcolor="#FAFAFA"` and a labeled `label`.
- A footer subgraph holds the legend.

**`scripts/build_schema_image.sh` shape:**

```
#!/usr/bin/env bash
# {{AGENT_ATTRIBUTION}}
# Regenerate docs/reference/images/xmonitor-schema-post-batch.png from
# docs/reference/schema.dot.
#
# Usage:
#   scripts/build_schema_image.sh          # rebuild the image
#   scripts/build_schema_image.sh --check  # exit 1 if image is stale (for CI)
#
# Requires: brew install graphviz (provides the `dot` binary).

set -euo pipefail

# Resolve repo root (script lives at <root>/scripts/, dot lives at <root>/docs/reference/)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOT="$ROOT/docs/reference/schema.dot"
IMG="$ROOT/docs/reference/images/xmonitor-schema-post-batch.png"

if ! command -v dot >/dev/null 2>&1; then
  echo "error: 'dot' not found. Install with: brew install graphviz" >&2
  exit 2
fi

if [[ ! -f "$DOT" ]]; then
  echo "error: $DOT not found" >&2
  exit 2
fi

if [[ "${1:-}" == "--check" ]]; then
  # git hash of .dot vs .png HEAD. If different commits, image is stale.
  DOT_HASH="$(git -C "$ROOT" rev-parse HEAD:"docs/reference/schema.dot" 2>/dev/null || echo none)"
  IMG_HASH="$(git -C "$ROOT" rev-parse HEAD:"docs/reference/images/xmonitor-schema-post-batch.png" 2>/dev/null || echo none)"
  if [[ "$DOT_HASH" == "$IMG_HASH" ]]; then
    exit 0
  fi
  echo "schema image is stale: schema.dot at $DOT_HASH, image at $IMG_HASH" >&2
  exit 1
fi

mkdir -p "$(dirname "$IMG")"
dot -Tpng "$DOT" > "$IMG"
echo "wrote $IMG"
```

**`CLAUDE.md` shape:**

```markdown
# Agent Rules (this repo)

Rules for AI agents (and humans) working in this repo. Honor these unless
explicitly told otherwise.

## Schema image regeneration

The x-monitor schema image at
`docs/reference/images/xmonitor-schema-post-batch.png` is generated from
`docs/reference/schema.dot` via `scripts/build_schema_image.sh`.

**Trigger:** when any file in `x-monitoring/x_monitor/migrations/*.sql`
changes, regenerate the image:

```bash
scripts/build_schema_image.sh
git add docs/reference/images/xmonitor-schema-post-batch.png
git commit -m "docs(reference): regenerate schema image"
```

The `.dot` source is the single source of truth — edit the `.dot`, never
edit the PNG directly.
```

## Implementation Units

- [ ] U1. **Commit `docs/reference/schema.dot` as the schema image source**

**Goal:** make `docs/reference/schema.dot` the canonical, version-controlled source for the schema image.

**Requirements:** R1, R2.

**Files:**
- Create: `docs/reference/schema.dot`

**Approach:**
- Generate by walking `x-monitoring/x_monitor/migrations/0*.sql` (migrations 1–20, 22, 23; skip 21 reserved), applying each in order to an in-memory `sqlite3 :memory:` database, then introspecting with `PRAGMA table_info` + `PRAGMA foreign_key_list` per table. The output is `.dot`, written directly to `docs/reference/schema.dot`. No external scripts committed; the introspection is part of the `.dot` build.
- 24 nodes (one per table), 7 cluster subgraphs, FK edges from child to parent PK.
- HTML-like node labels: `<table>` with one `<tr>` per column; PK cells `bgcolor="#FADBD8"` (red), FK cells `bgcolor="#D6EAF8"` (blue), normal cells white.
- FK edges land on **specific cells**, not just the node boundary: each `<td>` for a column that participates in an edge needs `PORT="col_name"` (e.g., `PORT="id"` on the PK cell of every parent table; `PORT="brand_id"` on FK cells in child tables). Without `PORT=`, graphviz emits "port unrecognized" warnings and edges float to the node perimeter, which is hard to read.
- Include the legend at the bottom and the title at the top as text labels (not separate nodes).

**Patterns to follow:**
- The `.dot` HTML-label convention from https://graphviz.org/doc/info/shapes.html#html.
- Layout in 7 clusters matching the prior image's cluster names: lookup, enum_i18n, fact, edges, mn, signal, meta.

**Test scenarios:**
- *Happy path:* `dot -Tsvg docs/reference/schema.dot` produces a valid SVG (no parse errors, non-empty output).
- *Schema coverage:* every one of the 24 expected tables appears as a node — verify by grepping the `.dot` source for each table name (e.g., `grep -c '\bbrands\b' schema.dot`, repeated for all 24).
- *PK/FK coloring:* post-023 PK columns (every `id` column in a parent table; the `(post_id, brand_id)` composite in `posts_brands_signals`) appear with the red PK wash; FK columns (`author_id`, `brand_id`, `company_id`, `post_type`, `sentiment` in their respective tables) appear with the blue FK wash.
- *023-specific:* the rendered image shows `nickname` (not `brand_id` or `company_id`) as the slug column in `brands` and `companies`; `posts_brands_signals` has 4 columns (no `signal_id`); `signals` and `signal_labels` tables are absent.
- *Integration:* `dot -Tpng docs/reference/schema.dot > /tmp/test.png` produces a non-empty PNG.

**Verification:**
- `dot -Tpng docs/reference/schema.dot > /tmp/test.png && file /tmp/test.png` returns `PNG image data` (using the macOS-builtin `file`; no ImageMagick dependency).
- All 24 table names are findable in the `.dot` source (grep each name and confirm ≥1 hit).
- The `.dot` source is < 200 KB (so it stays human-readable).
- The output PNG is ≥ 1500px on the long edge (default `dot` output is ~1000×1500 for this schema; the prior matplotlib image at `3200×3000` is not the target — the `.dot` produces a different layout by design).

---

- [ ] U2. **Add `scripts/build_schema_image.sh`**

**Goal:** one-command rebuild + `--check` drift detection.

**Requirements:** R3.

**Files:**
- Create: `scripts/build_schema_image.sh`
- Create: `scripts/` (the repo-root `scripts/` directory does not exist today; this unit creates it)
- This unit also **renders and commits the PNG** for the first time, so the `--check` flag has a baseline to compare against. Subsequent regenerations (future migrations) re-run the script and commit `.dot` + `.png` together.

**Approach:**
- Bash script with `set -euo pipefail`, `{{AGENT_ATTRIBUTION}}` header convention.
- Resolve paths relative to the script (`ROOT="$(cd "$(dirname "$0")/.." && pwd)"`) so the script works from any cwd.
- Happy path: `dot -Tpng "$DOT" > "$IMG"`, print a one-line confirmation.
- Error path 1 (no `dot`): print `error: 'dot' not found. Install with: brew install graphviz` and exit 2.
- Error path 2 (no `$DOT`): print `error: $DOT not found` and exit 2.
- `--check` mode: compare the **most recent commit hash** that touched the `.dot` vs the **most recent commit hash** that touched the PNG. Equality means a single commit updated both → clean. Exit 0 if same commit, exit 1 if different (stale), exit 2 if either is untracked. The semantics is git-commit-level (not blob-level) — see Open Question "Deferred to Implementation" for the chosen design.
- Make executable: `chmod +x scripts/build_schema_image.sh`.
- After committing this unit's source, run the script once and commit the resulting PNG alongside, so U3's verification (running `--check` on a clean tree) has a real baseline.

**Patterns to follow:**
- The `set -euo pipefail` + `{{AGENT_ATTRIBUTION}}` header from `x-monitoring/scripts/run_hf_products.sh`.
- The path-resolution idiom (`cd "$(dirname "$0")/.." && pwd`) for repo-relative paths.

**Test scenarios:**
- *Happy path:* `scripts/build_schema_image.sh` regenerates the PNG; the new file's byte size is within 10% of the prior version's size (sanity check that the render produced something meaningful, not a stub).
- *Error: dot missing:* temporarily mask `dot` (e.g., `PATH=/usr/bin:/bin scripts/build_schema_image.sh`) and verify exit code 2 + the `brew install graphviz` message.
- *Error: source missing:* temporarily rename `schema.dot` and verify exit code 2 + a path-in-message error.
- *`--check` clean:* commit both files, run `scripts/build_schema_image.sh --check`, expect exit 0.
- *`--check` stale:* modify `schema.dot`, run `scripts/build_schema_image.sh --check` *without* regenerating, expect exit 1 and the "stale" message.
- *Idempotent:* run the build script twice in a row without changing the source; the second run's output PNG is byte-identical to the first (this is the load-bearing guarantee).

**Verification:**
- `scripts/build_schema_image.sh --check` exits 0 after committing U1 and U2.
- `scripts/build_schema_image.sh --check` exits 1 after editing `schema.dot` without committing.
- The script is `chmod +x` and runs from any cwd.

---

- [ ] U3. **Add `CLAUDE.md` with the schema-image trigger rule**

**Goal:** make the regeneration trigger discoverable to any agent (or human) working on migrations.

**Requirements:** R4.

**Files:**
- Create: `CLAUDE.md` (at repo root; no CLAUDE.md or AGENTS.md exists in the repo today)

**Approach:**
- Short header explaining what `CLAUDE.md` is.
- One rule block titled "Schema image regeneration" that names the trigger condition (`x-monitoring/x_monitor/migrations/*.sql` changes), the command to run (`scripts/build_schema_image.sh`), and the commit convention.
- Note that the `.dot` is the single source of truth — never edit the PNG directly.

**Patterns to follow:**
- The terse rule-style of the project's existing agent rules (per memory: terse, no fluff).
- The "trigger + command + commit" pattern documented at the top of this plan.

**Test scenarios:**
- *Existence + placement:* `CLAUDE.md` exists at the repo root (not under `x-monitoring/`, not under `docs/`).
- *Content:* `grep -E 'schema.*image|migrations.*\\*\\.sql|build_schema_image' CLAUDE.md` matches all three required phrases.
- *No duplicates:* the rule lives only in `CLAUDE.md`, not also in `AGENTS.md` (which doesn't exist either).

**Verification:**
- `test -f CLAUDE.md && grep -c 'scripts/build_schema_image.sh' CLAUDE.md` returns 1.
- Manual review: a contributor reading `CLAUDE.md` alone can identify the trigger + the command without opening any other file.

---

- [ ] U4. **Add regeneration note to `docs/reference/db-schema.md`**

**Goal:** surface the trigger at the artifact itself, so anyone reading the doc knows how the image got there and how to refresh it.

**Requirements:** R5.

**Files:**
- Modify: `docs/reference/db-schema.md`

**Approach:**
- Add a single sentence immediately after the image line: `*This image is generated from \`docs/reference/schema.dot\` via \`scripts/build_schema_image.sh\` — regenerate after any migration change.*`
- Do not duplicate the full CLAUDE.md rule — just point at the build script.

**Patterns to follow:**
- The doc's existing italicized explanatory paragraphs.

**Test scenarios:**
- *Placement:* the note appears within 3 lines of the image line.
- *Pointer, not duplicate:* the note contains a single in-repo path (`scripts/build_schema_image.sh`); the full trigger rule stays in `CLAUDE.md`.

**Verification:**
- `grep -B 1 -A 1 'xmonitor-schema-post-batch' docs/reference/db-schema.md` shows the regeneration note on the line immediately following the image line (matches the actual filename `images/xmonitor-schema-post-batch.png`).

## System-Wide Impact

- **No production code changes.** This plan touches `docs/reference/` (image source), `scripts/` (build script), and a new `CLAUDE.md`. No consumer code, no migration files, no DB schema.
- **Future migration work is the main beneficiary.** Any contributor landing a new migration SQL will be told (via `CLAUDE.md`) to regenerate the image as part of their normal flow.
- **Tooling dependency:** graphviz is the only new external dep. Install is one-time per machine; CI machines would need it too (when CI gets stood up).
- **Unchanged invariants:** the image content (post-023 schema with 24 tables, nickname slugs, no `signal_id`) is preserved as a hard requirement. Visual style will change from the prior matplotlib look to graphviz's default — that is the intentional point of the plan.

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Graphviz font rendering differs across machines | Low | Low (cosmetic) | Pin `fontname="Helvetica"` in `.dot`. macOS has Helvetica; Linux CI runners will fall back to a substitute — accept minor metric variation as long as `.dot` source is stable. `--check` is gated on git state, not image bytes, so cross-platform output diffs do not produce false-positives. |
| `.dot` becomes large (~200KB) | Medium | Low | Group very wide tables (`posts`, `products`) with HTML `<tr>` cells at fixed widths; this keeps the file readable in git diffs. |
| Contributor forgets to regenerate after a migration | Medium | Medium (image goes stale) | The `--check` flag is built now so a future pre-commit hook or CI check can catch it. `CLAUDE.md` carries the discovery load. |
| Graphviz not installed on a contributor's machine | Low | Low (build fails) | The script's `brew install graphviz` error path makes the fix obvious. |

## Documentation / Operational Notes

- The new `CLAUDE.md` is itself documentation; no additional doc updates are required.
- The one-line note in `db-schema.md` is the only doc edit.
- Future-work note (not part of this plan): when `.github/workflows/` is added, wire `scripts/build_schema_image.sh --check` into a CI job that runs on PRs touching `x-monitoring/x_monitor/migrations/*.sql`. That CI check is out of scope here because no workflow file exists yet.

## Sources & References

- **Prior plan:** [docs/plans/2026-06-26-001-refactor-brand-id-to-nickname-plan.md](2026-06-26-001-refactor-brand-id-to-nickname-plan.md) — for migration 023's column renames that this plan's `.dot` must reflect.
- **Image history:** commits `825850c`, `ba3b6ae`, `3e951cc` (on `docs/u8-remediation-plan-update`) and `7038356` (on `main`, the current image).
- **graphviz docs:** https://graphviz.org/doc/info/lang.html, https://graphviz.org/doc/info/shapes.html#html