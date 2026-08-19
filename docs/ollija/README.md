# Ollija plan guide

Ollija is a small planning aid for PushinWeight. It gives every agent and
person working on one change the same delivery instructions in the same plan.
It solves a coordination problem—not a product or deployment problem: without
one shared plan, an implementation can be built in one place, reviewed against
different assumptions, and delivered without a clear record of what was
intended.

Ollija sits beside Git (the code-history system) and Render (the hosting
platform). It does not replace either. Git records commits; Render deploys
them; the parent workflow performs those actions. Ollija only writes the
concrete guide that tells that workflow what its selected delivery path is.

## The one command

```bash
./bin/ollija annotate-plan [optional-plan-path]
```

Run it before selecting or creating a plan. With no path, it finds the one plan
for the active branch or creates a minimal shared stub. Its JSON result includes
the exact `plan_path`; use that same file for planning. Do not start a second
plan for the branch.

After the final plan write or document review, refresh the same file:

```bash
./bin/ollija annotate-plan <plan-path>
```

Before Git or deployment mutations, check that the guide is current:

```bash
./bin/ollija annotate-plan <plan-path> --check
```

The command uses tracked configuration, the Git branch, and the active
worktree to write one generated block between `BEGIN OLLIJA DELIVERY GUIDE` and
`END OLLIJA DELIVERY GUIDE`. Text outside those markers is preserved. Put a
human or owner-directed exception in `## Delivery Exceptions`, which is outside
the generated block and survives every refresh.

## Where work belongs

The Ollija release worktree area is:

```text
<authoritative-repo>/.worktrees/<branch>
```

For this repository, the authoritative host is `fuchitalee` and the base path
is `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`. A worktree
outside that area receives relocation guidance in its plan. Ollija does not
prompt, move, reject, or block it.

The tracked post-checkout hook is deliberately nonblocking. In a named linked
worktree it runs the same annotation command to create or reuse the shared
stub; primary and detached checkouts are skipped. If annotation fails, Git
continues and the hook prints the recovery command.

## Delivery choices

Ordinary planning is `on-request`: making a plan does not authorize a commit,
push, staging deployment, or production promotion.

LFG and goal ask the owner once, before implementation, whether the change
stops after staging or continues through production. The planner stores that
choice in the shared plan as `delivery_target: staging|production` and
`delivery_selected_by_user: true`, then annotates it. Ollija never infers
production authority from the branch or a conversation, and it does not ask a
second delivery question later.

Before acting, the parent workflow reads the selected target, generated guide,
and Delivery Exceptions. It then implements, tests, commits, pushes the
feature, stages the exact candidate, and—when the recorded target is
production—promotes that same candidate to `main` after staging passes.

## What Ollija does not do

Ollija does not approve, commit, push, deploy, supervise agents, start a
background process, retry forever, copy databases, capture browser state, or
persist release state. It is a deterministic guide, not a gatekeeper.

If a guide is wrong, correct the tracked configuration, template, or agent
instructions that supplied the bad fact, then rerun annotation. Record material
Ollija behavior changes in [CHANGES.md](CHANGES.md); it is an advisory human
history, not an enforcement mechanism.
