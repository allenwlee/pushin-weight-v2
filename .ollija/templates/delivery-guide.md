## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `${canonical_host}`
- Authoritative repository: `${repository_root}`
- ${release_worktree_label}: `${release_worktree_area}`
- Active worktree: `${active_worktree}`
- Plan: `${plan_path}`
- Change: `${change_id}`
- Branch: `${branch}`
- Staging branch and blueprint: `${staging_branch}`, `${staging_blueprint}`
- Production branch and blueprint: `${production_branch}`, `${production_blueprint}`
- Staging URL: `${staging_url}`
- Production URL: `${production_url}`

### Placement

${placement}

### Delivery scope

- Workflow: `${workflow}`
- Delivery target: `${delivery_target}`
- Owner selection recorded: `${delivery_selected_by_user}`
- Delivery route: `${delivery_route}`

${delivery_actions}

### Failure handling

- Complete applicable, unwaived checks for the selected route. A waived check is waived, never passed. Owner-selected direct production does not require staging.
- Product defects return to the ${code_failure_route}; repeat only checks invalidated by the fix. Environment failures require repairing the environment, not a new source commit. Retry only after a relevant fact changes.
- SSH, shell, environment, or multi-machine failures use the ${infra_failure_route} first.
- The change ledger is advisory; do not validate or enforce it.
- Never force-remove a worktree. Retain staging-only, failed, dirty, locked,
  noncanonical, or candidate-mismatched worktrees for diagnosis or later
  delivery.
- Do not run an endless retry loop or start a persistent Ollija process.
