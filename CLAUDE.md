# Agent Rules (this repo)

Rules for AI agents (and humans) working in this repo. Honor these unless
explicitly told otherwise.

## Schema image regeneration

The x-monitor schema image at
`docs/reference/images/xmonitor-schema-post-batch.png` is generated from
`docs/reference/schema.dot` via `scripts/build_schema_image.sh`.

**Trigger:** when any file in `x-monitoring/x_monitor/migrations/*.sql`
changes, regenerate the image and co-commit it with the schema changes:

```bash
scripts/build_schema_image.sh
git add docs/reference/schema.dot docs/reference/images/xmonitor-schema-post-batch.png
git commit -m "docs(reference): regenerate schema image"
```

The `.dot` source is the single source of truth — edit the `.dot`, never
edit the PNG directly. The PNG must always be regenerated from the
committed `.dot` and committed in the same commit, so `scripts/build_schema_image.sh --check`
exits 0 on a clean tree.

## Documented solutions and shared vocabulary

`docs/solutions/` — documented solutions to past problems (bugs, best
practices, workflow patterns), organized by category with YAML
frontmatter (`module`, `tags`, `problem_type`). Relevant when
implementing or debugging in documented areas.

`CONCEPTS.md` — shared domain vocabulary (entities, named processes,
status concepts). Relevant when orienting to the codebase or
discussing domain concepts.
