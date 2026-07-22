# classifier_tests/

Canonical artifact destination for post-fetch smoketest transcripts run via the
`pushin_weight_smoketest` skill (`~/.claude/skills/custom-claude-skills/pushin_weight_smoketest/SKILL.md`).

## Why this directory

Until 2026-07-07, smoketest transcripts were dumped under `/tmp/smoketest_*.txt`.
That's local-only and ephemeral — when a session ends the artifacts vanish with
the LLM context window. **This directory is the persistent, repo-local home for
post-fetch smoketest transcripts.** Fixtures (`v20_fixture.jsonl` etc.) still
live under `/tmp/` (per `.gitignore`) because they're regenerated per
regression-target.

## Layout convention

```
classifier_tests/
  smoketest_<purpose>_<phase>_<size>.txt
```

Examples (matches current contents):

- `smoketest_v20_post_merge.txt` — 20-post fixture, after the renderer
  cherry-pick landed on `main`, default `--sample 5` (truncated output).
- `smoketest_v20_post_merge_full.txt` — same run, `--sample 20` (full
  output, 374 lines).
- `smoketest_v20_post_fix_v2.txt` — 20-post fixture, after the parser-
  routing fix (commit `b213c47`) landed, `--sample 20`. **This is
  the post-fix baseline** for future runs to compare against.

## How to add a new run

```bash
cd x-monitoring
python3 -m scripts.post_fetch_smoketest \
  --source=fixture \
  --fixture=/tmp/v20_fixture.jsonl \
  --sample 20 \
  | tee tests/classifier_tests/smoketest_v20_<purpose>.txt
```

Diff against the prior baseline:

```bash
diff tests/classifier_tests/smoketest_v20_post_fix_v2.txt \
     tests/classifier_tests/smoketest_v20_<purpose>.txt \
  | grep -E "^\s*(us=|cn=|types=|sentiment=|cls_discourse=)"
```

That filters out LLM non-determinism on `literal_zh` / `cn_equivalent` and
surfaces the actual classification deltas (rule calibration signal).

## Pre-existing artifacts under /tmp/

| File | Status |
|---|---|
| `/tmp/smoketest_v12_full.pre-calibration.txt` | Pre-rules-16-19 baseline — keep |
| `/tmp/smoketest_v12_post_calibration.txt` | First post-rules-16-19 run (flat key=value layout, pre-cherry-pick) — keep for renderer-format diff |
| `/tmp/smoketest_v12_post_calibration_v2.txt` | Second post-rules-16-19 run, sub-name "v2" — keep |
| `/tmp/smoketest_v12_post_layout.txt` | v12 fixture under hierarchical layout (post-renderer-cherry-pick) — keep |
| `/tmp/v20_fixture.jsonl` | 20-post fixture (regenerated per regression target; `.gitignore`d here, so stays in `/tmp/`) |
