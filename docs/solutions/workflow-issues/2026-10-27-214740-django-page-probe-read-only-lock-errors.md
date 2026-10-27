---
title: Read-only Django page probes can hide lock errors behind HTTP 200
date: 2026-10-27
category: workflow-issues
module: pushin-weight-v2
problem_type: workflow_issue
component: development_workflow
severity: medium
root_cause: test_isolation
resolution_type: workflow_improvement
applies_when:
  - "An authenticated Django page probe wraps several requests in one database transaction"
  - "A page may acquire row locks while building optional content"
tags:
  - "django"
  - "page-probe"
  - "postgresql"
  - "deployment"
---

# Read-only Django page probes can hide lock errors behind HTTP 200

## Context

During the RG7 production cutover, an authenticated Django test-client probe put eleven GET requests inside one `SET TRANSACTION READ ONLY` transaction. All eleven responses were HTTP 200, but the probe job logged `cannot execute SELECT FOR UPDATE in a read-only transaction` while rendering several pages. The HTTP status alone missed those caught errors.

## Guidance

For a page smoke test that is meant to represent normal serving behavior, use the actual serving database role and its ordinary transaction mode. Keep the job bounded to named GET routes, assert the deployed commit and schema, record each response, and inspect the job logs for caught exceptions as well as HTTP status. If a read-only database check is needed, run it as a separate schema/data probe rather than imposing read-only mode on application page requests.

The RG7 probe was rerun on the same production commit with normal serving transactions. It returned eleven HTTP 200 responses and did not log the read-only lock errors. The later post-deletion probe repeated that result on the final commit while also checking that the old relations and proposal column were absent.

## Why This Matters

Application code may catch a database error and render a fallback response. A forced read-only test transaction can therefore create a failure absent from normal serving, while an HTTP-only assertion can still report success. Checking the probe's transaction mode and logs makes the result interpretable.

## When to Apply

- Testing authenticated pages after a schema or serving-role deployment.
- Using the Django test client inside a one-off job to exercise production data without provider calls.

## Related

- [RG7 release plan](../../plans/2026-10-09-063417-feat-g3-round2-chart-engine-plan.md) records the dossier cutover and page-check gate.
