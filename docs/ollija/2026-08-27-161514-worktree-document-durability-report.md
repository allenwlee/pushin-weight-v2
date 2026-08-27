---
title: Ollija worktree and document durability review
date: 2026-08-27
type: report
component: ollija
status: verified
---

# Ollija worktree and document durability review

## Purpose

This report records the August 27 review of how Compound Engineering (CE),
Ollija, Git worktrees, plans, and the primary checkout interact. The review was
prompted by concern that LFG implementation work was reaching `main` while its
plans and related documents remained only in long-lived worktrees.

The investigation found that Ollija's canonical worktree location is sound.
Most plans were already committed to `main`. The apparent loss was primarily a
combination of an outdated local `main`, older worktree snapshots, and a small
number of genuinely unfinished branches or uncommitted plan edits.

## Work completed

The primary checkout initially contained four local documentation changes and
was not current with `origin/main`. To preserve those changes without mixing
them into the stale local `main`, the work was placed on
`docs/preserve-local-records` based on the then-current `origin/main`.

Three logical commits preserved:

- the owner-approved SSH GUI automation boundary and its `AGENTS.md` link;
- the dynamic model-alias discovery research handoff; and
- the why-first headline validation and event-anchor reference.

The branch was pushed and merged through
[PR #24](https://github.com/allenwlee/pushin-weight-v2/pull/24). Before the
merge, GitHub reported the exact expected head, a clean merge state, and no
failing checks. The owner explicitly waived Compound Engineering's optional
five-minute PR cooling-off period, so the PR was merged immediately. The four
files were then verified on remote `main`.

Finally, the primary checkout was switched from
`docs/preserve-local-records` to `main` and updated with:

```bash
git pull --ff-only origin main
```

The update fast-forwarded local `main` by 23 commits, from `c2c713d` to
`c423ce8`. At the end of the operation, local `main` matched `origin/main` and
the working tree was clean.

## First-principles model

A Git worktree is a disposable checkout of one branch or commit. Its physical
location does not determine which branch owns its files.

For example, these are separate working files even though one directory is
nested inside the other:

```text
pushin-weight-v2/docs/plans/example.md
pushin-weight-v2/.worktrees/feat/example/docs/plans/example.md
```

The two checkouts share Git's underlying object database, but they do not share
their checked-out files. A new commit on `main` does not automatically update
an older feature worktree, and a file created in a feature worktree does not
appear in `main` until it is committed and merged.

The directory normally called the "main checkout" is also not permanently
bound to the `main` branch. It displays whichever branch is currently checked
out there. During this review, the primary directory first displayed
`docs/preserve-local-records`; it displayed `main` only after the explicit
switch.

## CE and Ollija responsibilities

CE does not assume that work happens directly on `main`. Its worktree workflow
explicitly expects modern coding harnesses to provide isolated worktrees. Its
planning workflow resolves the current checkout with
`git rev-parse --show-toplevel` and writes plans beneath that checkout's
configured documentation root, normally `docs/plans/`.

The effective CE assumption is therefore not "work on main." It is:

> The current checkout and branch form one coherent unit whose selected plan,
> implementation, review fixes, and shipping commits remain connected.

Ollija improves this model by requiring release-eligible linked worktrees to
live beneath the authoritative repository's `.worktrees/` directory. That
solves location discovery and prevents agents from scattering authoritative
checkouts across local and remote machines. It does not—and should not—make
nested worktrees share their checked-out files.

Ollija remains a deterministic plan guide. The parent workflow owns commits,
pull requests, merges, deployments, and guarded worktree removal.

## Repository evidence

The registered worktrees were inspected against the refreshed `origin/main`.
At that point:

- remote `main` contained 87 files in `docs/plans/`;
- recent CE and Ollija plan commits were visible in remote `main` history;
- most older worktrees contained only 74–80 plans because their branches were
  created before newer plans reached `main`; and
- all but two committed plan paths found in registered worktree heads were
  already represented on `origin/main`.

The two committed exceptions had ordinary branch-state explanations:

1. `docs/plans/2026-08-17-163801-selective-gap-backfiller-plan.md` was on
   `feat/backfiller-selective-gaps`, whose PR #16 was still open.
2. `docs/plans/2026-08-26-173100-feat-per-brand-ai-trend-narratives-plan.md`
   was on `integrate/why-first-trend-headlines-20260824`, which had no matching
   PR and had an unresolved plan-file conflict in its working tree.

Two additional worktrees held uncommitted plan modifications:

- `feat/mockup-v23` modified
  `docs/plans/2026-08-19-043225-feat-mockup-v23-plan.md`;
- `release/cdb7e0b` modified
  `docs/plans/2026-08-24-104432-feat-deepseek-v4-flash-model-plan.md`.

These exceptions should not be described as CE confusing the canonical
directory. They are unfinished branch or working-tree state and must be
resolved, deliberately retained, or discarded by an authorized workflow
before those worktrees are removed.

## Conclusion

Ollija's canonical `.worktrees/` design is technically sound and should remain
in place. CE recognizes linked worktrees correctly, writes plans relative to
the active checkout, and has successfully delivered most plan files to
`main`.

The remaining risk is lifecycle clarity, not directory placement. A worktree
must never be treated as the archive. Git history, merged pull requests, and
tracked repository documents are the durable record.

## Recommended cleanup invariant

Before the parent workflow removes an Ollija worktree, it should establish all
of the following:

1. The worktree is registered, canonical, clean, unlocked, and still at the
   exact verified candidate SHA required by the existing Ollija guide.
2. Every plan or related artifact intended to be durable is tracked and
   committed on an identified branch.
3. The corresponding PR is merged, still intentionally open, or explicitly
   abandoned; an unfinished branch must not be mistaken for completed work.
4. For merged work, the selected durable artifacts are verified on remote
   `main`, not merely found somewhere inside the worktree directory.
5. Only ephemeral scratch output may disappear with worktree removal.

Because Ollija is guidance rather than a release controller, this invariant
belongs in Ollija's generated guidance and repository instructions, while the
parent workflow performs and reports the actual Git and filesystem checks.

## Recordkeeping policy

The accepted plan, important architectural or product decisions, and reusable
technical lessons should travel with the feature branch and PR. Detailed
review conversation can remain in GitHub's PR history; only conclusions that
will help future work need a repository document. Temporary prompts, agent
scratchpads, and duplicate review output should remain disposable.

No Ollija behavior or rule was changed during this review. This file records
the verified current behavior and a recommended future invariant; a later
implementation of that invariant should receive its own plan, tests, and
`docs/ollija/CHANGES.md` entry.
