---
name: ollija
description: Coach the repo-specific PushinWeight staging and beta-release workflow. Use when the owner asks what is next, starts a change, refreshes review data, opens local or hosted staging, records desktop or physical-iPhone review, stages a candidate, releases a beta, verifies production, or diagnoses/resumes a failed Ollija transition.
---

# Ollija

Treat `./bin/ollija` as the workflow authority. Keep all repository, database,
browser-proof, and receipt artifacts on `fuchitalee`; never create them on
`allenwlee`.

## Begin from observed state

Run this read-only command first, even when the requested transition seems
obvious:

```bash
./bin/ollija status --json
```

Read `status`, `state`, `next_action`, warnings, evidence, and resource/SHA
identities. If state is blocked or unknown, follow the reported next action.
Use `./bin/ollija doctor --json` for setup failures. Do not bypass a failed
guard with direct Git, Render, PostgreSQL, receipt, or tag operations.

## Map owner language to one transition

| Owner intent | Command |
|---|---|
| “What’s next?” | `./bin/ollija status` |
| “Check the setup” | `./bin/ollija doctor` |
| “Start this beta/change” | `./bin/ollija start` |
| “Refresh review data” | `./bin/ollija refresh-local` |
| “Show local staging” | `./bin/ollija preview` |
| “Stop local staging” | `./bin/ollija preview-stop` |
| “Refresh hosted staging” | `./bin/ollija refresh-staging` |
| “Stage this” | `./bin/ollija stage` |
| “Assess the UI” | `./bin/ollija assess-ui` |
| “Desktop looks good” | `./bin/ollija approve desktop` |
| “Physical iPhone looks good” | `./bin/ollija approve iphone` |
| “Release the beta” | `./bin/ollija release` |
| “Verify production” | `./bin/ollija verify-production` |

Run only the transition the owner requested or the current read-only status
recommends. State the external effect before a mutation. Re-run status after
the command and report its one next action.

## Preserve human and deployment authority

- Record desktop or iPhone approval only after the owner explicitly says that
  exact hosted staging deployment looks good. A simulator, screenshot, agent
  inspection, or Bridgewright assessment is not physical-iPhone approval.
- Treat Bridgewright as assessment evidence only. It cannot approve, deploy,
  release, or replace owner review.
- Treat every receipt as bound to the candidate SHA and deployment ID. After a
  code change or replacement deploy, re-run status and repeat stale steps.
- Run `release` only for an explicit release request. It may fast-forward
  `main`; never substitute `git push`, a manual Render deploy, or force push.
- Do not report a release complete until `verify-production` confirms every
  configured Render service at one exact SHA, the authenticated production
  headline is visibly present, DSV4 is configured, and the beta tag exists.
- Never print connection URLs, provider keys, OAuth secrets, browser storage,
  or receipt contents containing private values.

## Recover without inventing success

On interruption or failure, run status again. Resume the idempotent command
when the candidate is unchanged. If code changed, freeze and stage a new
candidate and obtain new approvals. Preserve last-known-good evidence; never
copy staging data to production, hand-edit receipt JSON, force a ref, or tag a
failed/unverified deploy.

Read `docs/operations/ollija.md` for one-time setup, database refresh details,
browser-session capture, and recovery. Read `docs/deploy/render.md` when live
Render topology or DSV4 configuration is involved.
