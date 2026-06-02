# MiniMax Conversation Research — Scripts

Reusable tooling for the MiniMax conversation intelligence research run.
Originally executed 2026-05-26 (results in `../20260526/`).

## Contents

- **`last30days.py`** — the data-collection tool. Copied from
  `~/.claude/plugins/cache/last30days-skill/last30days/<ver>/skills/last30days/scripts/last30days.py`
  for self-containment. If the plugin updates upstream, refresh this copy.
- **`run_research.py`** — orchestrator. Runs the queries defined in the
  8-unit plan and writes results into a target `producer/` dir.

## Methodology

The full plan lives at:
`../20260526/consumer/2026-05-26-001-feat-minimax-conversation-research-plan.md`

8 implementation units; this runner covers data-collection units 2, 3, 4, 5, 7
(Unit 1 is a diagnostic, Unit 6 was skipped, Unit 8 is manual synthesis).

## Quick Start

```bash
# Run the full data-collection set into a new run dir
mkdir -p ../20260602/producer ../20260602/consumer
python3 run_research.py --out-dir ../20260602/producer

# Run a single unit
python3 run_research.py --unit 2 --out-dir ../20260602/producer

# Faster run (less coverage) for time-boxed iteration
python3 run_research.py --quick --out-dir ../20260602/producer
```

## Adding Queries

Edit `UNITS` in `run_research.py`. Each unit maps a logical label to a
`(query_string, output_filename)` tuple. The output filename is what
the synthesis step expects, so don't rename it without updating
`20260526/consumer/INTELLIGENCE_BRIEF.md` and friends.

## Known Limitations (as of 2026-05-26 run)

- **Reddit is broken** — `last30days.py` Reddit search times out at 90s.
  Excluded from all queries. Compare against X+YouTube+Web only.
- **YouTube transcripts not available** — relies on titles and view counts.
- **5-min bash timeout** — use `--quick` for the full set; serial runs help
  if a single query blows the budget.

## Source Hierarchy

1. **X (via xAI/Grok)** — highest signal (engagement metrics, real-time)
2. **YouTube** — high signal (view counts, transcript-backed when available)
3. **Web (Brave Search)** — lower signal (no engagement data)
4. **Reddit** — excluded (see Known Limitations)
