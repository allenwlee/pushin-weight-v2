# Stage 0 enrichment baseline

This is a passive evidence record. It contains no spend estimate and no
production mutation.

The captured command was:

```text
render logs -r crn-d9gv94o4n6ts739tqaug --tail 120 --output text
```

Capture time: `2026-09-08T20:06:37+0900`.

- Deploy SHA reported by the logs: `b184276cc6ec4e7d1a9eba83357e824848dc8f94`.
- Run `20260908T103029_0000-508c7fc6` at `10:30:29Z`: 28 claimed, 28 succeeded, 82.853 seconds post-fetch.
- Run `20260908T100053_0000-c1ed2294` at `10:00:53Z`: 42 claimed, 40 succeeded, 2 pending, 108.909 seconds post-fetch.

A separate read-only `git ls-remote` receipt resolved both remote `main` and
remote `staging` to `b184276cc6ec4e7d1a9eba83357e824848dc8f94`. This is separate
from the production log receipt. Existing headline ledger input/output and
latency fields are present; actual per-role translator, classifier, relevancy,
Headline rows already persist basic input/output/latency fields, while aggregate
and extended headline usage remain unmeasured. Current cost, percentile, worker-liveness, and
usage totals are therefore unreported rather than zero or estimated.

Stage 0 preserves current taxonomy, runtime behavior, schema, scheduling,
prompts, retries, model configuration, and outputs. Staging verification and
the fake-provider probe remain pending the parent delivery workflow.
