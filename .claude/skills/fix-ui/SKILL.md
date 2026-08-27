---
name: fix-ui
description: Use when fixing a visible UI defect, mockup mismatch, layout or style regression, broken browser interaction, locale-visible copy issue, or staging/production visual discrepancy in pushin-weight-v2.
---

# Fix UI — pushin-weight-v2

Turn a reported visible defect into a minimal, verified fix that cannot silently regress.

## Help the user report the right thing

When the request is vague, start reproducing it and ask only for the missing detail that could change the fix. Guide the user toward this compact format; do not require every field:

> **UI change request**
>
> - **Where:** page URL or area, such as “homepage top bar” or “chart under Filters”.
> - **Actual:** what is visible or happens now.
> - **Wanted:** what should be visible or happen instead.
> - **How to reproduce:** click, hover, filter, or resize steps for interactive defects.
> - **Reference:** screenshot, mockup HTML, or precise comparison.
> - **Conditions:** viewport/device, locale, login state, and browser when relevant.
> - **Keep unchanged:** nearby behavior or surfaces that must not change.
> - **Done means:** the visible outcome the user will judge.

Users need not identify files, CSS selectors, or a technical cause. The agent owns reproduction, tracing, and verification.

## Scope and reproduce

Before editing, state the exact **TOUCH**, **PRESERVE**, and **ASK FIRST** boundaries. Preserve unrelated routes (including `/internal/` unless named), supplied mockups, public-versus-auth intent, and nearby behavior. Do not commit, merge, deploy, alter the mockup, expand an allowlist, or perform unrelated cleanup unless requested.

Read `AGENTS.md`, `CONCEPTS.md`, and `avoiding-recurring-mistakes/SKILL.md`. Check `git status`, active worktrees, current branch, and recent `origin/main`; surface conflicting edits before touching shared UI files.

Reproduce in a real browser first. Record route, locale, viewport, auth state, branch/SHA, and environment. Trace the real path: URL → view → template → static assets → runtime endpoints. Do not establish a UI fix from regex checks, mocked HTML, or a helper-only test.

## Pin the defect before fixing it

Add or strengthen a regression pin that exercises the reported differentiator:

- Render through the real URL, view, and template call chain.
- Use a normal deterministic user only when the route is meant to require login; otherwise prove anonymous access.
- Feed deterministic fixture data through the page’s real data path. Keep authored shell strict and variable feed/chart data data-derived.
- If HTML mockup is supplied, treat it as the oracle; do not change it to fit current code.
- Test each applicable locale, including `zh_hans`; assert rendered text, not merely catalog presence.
- Resolve each local static reference and prove relevant JavaScript executes in a browser.
- Make zero selector matches, required-test skips, and setup errors fail loudly.

Never use live-page-derived expectations, silent skips, broad allowlists, or a weak screenshot threshold to make a failure green.

## Invoke the pinned stateful assurance profile

For homepage control, filter, preference, chart, feed, or request-lifecycle work, use the target declaration referenced by `bridgewright.yaml`; do not copy Bridgewright's generic protocol into this skill.

1. Run `uv run --extra dev bridgewright assurance-validate --project-root .` and `uv run --extra dev bridgewright assurance-prescribe --project-root .`. A build-identity mismatch, unknown control, invalid fixture digest, or declaration error blocks the fix.
2. Identify the controls touched by the defect and its inverse, applicable ordered actions, seeded regressions, and request races. The PushinWeight adapter owns those concrete mappings.
3. During the fix loop, run `uv run --extra dev python -m tests.ui_assurance.gate --scope affected`. It must exercise the real Playwright state model plus the target reducer/race checks; a required skip, error, zero-match selector, or failed seed is a failure.
4. Before release handoff, record the product-source revision in the declaration and run `uv run --extra dev python -m tests.ui_assurance.gate --scope candidate --candidate-revision <product-source-sha>`. Require every normalized obligation to pass and the generated Bridgewright assessment to report zero failed, skipped, errored, missing, or unknown obligations.

Bridgewright performs read-only structural validation, prescription, and assessment. It does not prove that target evidence is truthful and grants no permission to commit, push, merge, stage, deploy, or release. The parent workflow retains those decisions and separately verifies the exact release SHA.

## Make the smallest product fix

Change only the smallest surface that corrects the defect. Preserve all runtime endpoints that make the page work and retain compatibility selectors only for an explicitly preserved legacy surface.

Do not put iteration labels, agent notes, planning text, or implementation commentary in templates, static assets, or user-visible source. Product source describes the product; Git history describes the work.

## Definition of Done

- The reported failure is red before the product fix and green after it.
- A real caller → view → template → browser regression covers the changed behavior; function-only tests are insufficient.
- Browser verification checks the reported interaction/text, computed visibility, and on-screen nonzero geometry when relevant.
- Screenshot comparison uses the same locale, deterministic fixture, viewport, and state as the oracle. Any tolerance is narrow, reviewed, and explains the permitted difference.
- A source-hygiene regression rejects execution/meta commentary in public template source and rendered output.
- Static assets resolve and the required runtime behavior executes.
- Report required test executed/skipped/error counts; skips or errors are never called green.
- Report the affected/full assurance gate, declaration and control-model identity, obligation totals, and any replay IDs. Never infer obligation closure from a pytest count.
- Report exact branch/SHA, environment, and commands/results inspected.

Use an isolated worktree and disposable deterministic database for previews. Label preview URLs with their environment and SHA. Call something deployed only after the requested branch has been deployed successfully and the deployed URL has been checked; do not confuse local/staging evidence with production.
