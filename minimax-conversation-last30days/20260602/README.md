# 2026-06-02 Run — Reserved

Placeholder for the next research run, dated 2026-06-02.

## To Run

```bash
cd /Users/fuchitalee/development/minimax-marketing
mkdir -p minimax-conversation-last30days/20260602/{producer,consumer}
python3 minimax-conversation-last30days/engine/run_research.py \
    --out-dir minimax-conversation-last30days/20260602/producer
```

## Expected Outputs

`producer/` will receive 25 .md files (Units 2, 3, 4, 5, 7 from the plan).
`consumer/` will hold the synthesis: a fresh `INTELLIGENCE_BRIEF.md`,
`COMBINED_RESEARCH.md`, and the 25 -zh translations.

See `../20260526/consumer/` for the previous run's outputs as a reference.
