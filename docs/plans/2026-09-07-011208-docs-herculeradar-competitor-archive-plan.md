---
title: docs/herculeradar-competitor-archive plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: docs-herculeradar-competitor-archive-2026-09-07-011208
  branch: docs/herculeradar-competitor-archive
  workflow: plan
  delivery_target: on-request
  delivery_selected_by_user: false
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Put a user-directed exception in the editable Delivery Exceptions section below.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/herculeradar-competitor-archive`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/herculeradar-competitor-archive/docs/plans/2026-09-07-011208-docs-herculeradar-competitor-archive-plan.md`
- Change: `docs-herculeradar-competitor-archive-2026-09-07-011208`
- Branch: `docs/herculeradar-competitor-archive`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/herculeradar-competitor-archive/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/herculeradar-competitor-archive/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `plan`
- Delivery target: `on-request`
- Owner selection recorded: `false`

Target is not authorized until the owner selects it. Wait for a later explicit release request; do not commit, push, stage, or promote on this guide alone.

### Failure handling

- Never promote a staging candidate whose automated checks failed.
- Implementation failures return to the parent implementation workflow for diagnosis, correction, recommit, and restaging.
- SSH, shell, environment, or multi-machine failures use the repository infra/multi-machine skill first.
- The change ledger is advisory; do not validate or enforce it.
- Never force-remove a worktree. Retain staging-only, failed, dirty, locked,
  noncanonical, or candidate-mismatched worktrees for diagnosis or later
  delivery.
- Do not run an endless retry loop or start a persistent Ollija process.
<!-- END OLLIJA DELIVERY GUIDE -->

## Delivery Exceptions

- Owner explicitly authorized on 2026-09-07 committing this documentation-only
  archive and pushing the unchanged candidate directly to `main`. Do not stage
  or deploy, and do not modify product code or unrelated worktrees.

# Goal

Create a reproducible, source-attributed archive of HerculeRadar's public web
presence under `docs/external_vendors/herculeradar`, including a complete
inventory of public MCP documentation and advertised MCP endpoints.

## Product Contract

- Follow the existing `docs/external_vendors/brand24` convention: keep captured
  first-party material in an `official/` tree and add a concise archive index.
- Use Firecrawl as the primary discovery/capture source, Context7 as an
  independent documentation lookup, and direct web/HTTP inspection for
  robots, sitemaps, well-known metadata, JavaScript-disclosed routes, and
  coverage reconciliation.
- Include every publicly discoverable same-owner page available without login;
  record blocked, duplicate, redirected, or failed URLs explicitly rather than
  silently omitting them.
- Inventory every MCP transport URL, HTTP method, authentication requirement,
  setup instruction, tool/resource/prompt surface, schema, and example that is
  publicly documented or directly observable. Distinguish verified endpoints
  from inferred candidates.
- Preserve source URLs, retrieval timestamps, HTTP status/content type, and
  capture provenance. Do not store credentials, authenticated content, or
  third-party tracking payloads.
- Change only this plan and `docs/external_vendors/herculeradar/**`.

## Units

### U1 — Discovery baseline

- Run Firecrawl map/crawl against `https://herculeradar.com`.
- Query Context7 for a HerculeRadar library/documentation corpus.
- Inspect robots, sitemaps, search results, page links, well-known metadata,
  and shipped JavaScript for additional first-party URLs and MCP references.

### U2 — Public-site archive

- Save normalized Markdown captures for the reconciled public page set.
- Create machine-readable URL and capture manifests with canonical URL,
  redirect, status, content type, title, and provenance fields.

### U3 — MCP archive

- Save all public MCP documentation in a dedicated `mcp/` subtree.
- Produce a verified endpoint/tool inventory that cites the exact first-party
  evidence and labels any inaccessible or unresolved details.

### U4 — Coverage and delivery

- Add a README explaining structure, capture date, tools, scope, limitations,
  reproduction commands, and the reconciled coverage counts.
- Validate manifest/file parity, internal links, JSON syntax, duplicate
  canonical URLs, unexpected domains, secrets, and the Git diff scope.
- Commit the scoped archive, fast-forward the same candidate SHA onto current
  remote `main`, and verify `refs/heads/main` resolves to that SHA. Do not
  deploy.

## Definition of Done

- Firecrawl, Context7, robots/sitemap, direct-link, search, and JavaScript
  discoveries are reconciled in the manifest.
- Every accepted public same-owner URL has a saved capture or an explicit
  failure record, and every saved capture maps back to one manifest row.
- The MCP inventory separates verified transport endpoints from discovery
  candidates and cites first-party evidence for each verified claim.
- Automated archive checks pass, the scoped diff contains no product code or
  secrets, and remote `main` equals the committed candidate SHA.
