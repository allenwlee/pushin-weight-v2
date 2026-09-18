# Model task evidence export

This immutable archive preserves completed offline model trial evidence from
`.context/model-task-20260917` for the 2026-09-17 execution report.

The archive contains 63 files: 34 files from 17 completed
`model_task_experiment` trials (each `contract.json` and
`attempt-N.live/report.json`), 10 files from five completed classifier trials
(each `contract.json` and `attempt-1.consumed.json`), and `review-a.json`
through `review-r.json` plus `review-rubric.md`. The classifier consumptions
were included only when they contained final `calls` and `source_post_errors`.

These are public-post offline diagnostic artifacts. They do not constitute a
qualification result or pass, and the automated reviews are evidence from
reviewers rather than owner labels.

`evidence.tar.gz` is a gzip-compressed tar archive. Paths inside it retain
their `.context/model-task-20260917/...` relative paths. `MANIFEST.sha256`
is both included in the tar archive and copied beside it for convenient
verification. The manifest records the SHA-256 digest and relative path of
every archived file.

Restore and verify into a new directory:

```bash
mkdir restored-model-task-evidence
tar -xzf evidence.tar.gz -C restored-model-task-evidence
(cd restored-model-task-evidence && shasum -a 256 -c MANIFEST.sha256)
```

The source trial logs, request files, locks, prepared-only directories,
environment files, secrets, portfolio lock, and non-final classifier
consumptions are intentionally excluded. A scan of gathered structured
metadata found no key or header secret patterns.
