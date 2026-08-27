# allenwlee SSH GUI automation

Recorded and functionally verified on 2026-08-27.

## What the owner allowed

macOS asked the owner to allow a process labeled `sshkeygen`. In this context,
that label refers to Apple's incoming SSH service wrapper, commonly displayed
as `sshd-keygen-wrapper`. It is the process ancestry used by commands arriving
through SSH; the action did not generate, replace, reveal, or authorize an SSH
private key.

The permission is macOS Accessibility/TCC permission. It allows an
authenticated SSH session on `allenwlee` to ask `System Events` to inspect GUI
windows and send keyboard or mouse input. Immediately after the owner allowed
it, a previously rejected AppleScript successfully read the active Visual
Studio Code window name.

## Persistence and scope

- macOS stores this grant in its TCC privacy database, so it normally survives
  application and machine restarts.
- The grant follows the permitted Apple SSH wrapper's code identity, not a
  Claude, Codex, OpenClaw, or terminal session. Agents using the same incoming
  SSH path can use the capability.
- An OS update, binary identity change, TCC reset, or owner revocation can
  remove the grant. Agents must test before depending on it.
- It permits GUI automation only. It does not make `allenwlee` an authoritative
  project host, alter repository permissions, or bypass normal SSH login.
- Because the wrapper serves authenticated SSH sessions broadly, the grant is
  security-sensitive: anyone who can authenticate to the applicable account
  may be able to drive that account's visible GUI.

## Agent procedure

Use the repository's infra/multi-machine skill before diagnosing or driving a
remote GUI. Keep PushinWeight source, worktrees, plans, receipts, screenshots,
and durable diagnostic artifacts on `fuchitalee`; `allenwlee` remains only the
keyboard/browser endpoint.

Before sending input:

1. Require an explicit owner request for the GUI action.
2. Confirm the target host and logged-in user.
3. Read the visible process and target window names through `System Events`.
4. Continue only when the intended app/window is unambiguous.
5. Activate that app explicitly, use the smallest bounded action, and verify
   the resulting application state.

Do not type secrets, approve security prompts, dismiss owner-approval dialogs,
or issue destructive commands through GUI automation. If more than one window
could receive the input, stop and ask the owner to focus or identify it.

## Capability check

This read-only check confirms that the SSH-launched process can inspect visible
applications:

```bash
ssh allenwlee@100.94.210.38 \
  'osascript -e '\''tell application "System Events" to get name of every process whose visible is true'\'''
```

A response containing visible application names means Accessibility access is
working. An `osascript is not allowed assistive access` error means it is not.

## Revocation

On `allenwlee`, open **System Settings → Privacy & Security → Accessibility**
and disable the Apple SSH wrapper entry (`sshd-keygen-wrapper` or the displayed
`sshkeygen` label). The owner can also reset the relevant TCC permission, but
agents must not do that without an explicit request because it affects every
SSH-launched GUI automation session.
