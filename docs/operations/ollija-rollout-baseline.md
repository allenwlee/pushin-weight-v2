> **Superseded Ollija workflow — historical record.** This baseline preserves
> the former stateful-release rollout. For current behavior, read the
> [Ollija plan guide](../ollija/README.md).

# ollija rollout baseline

Recorded on 2026-08-14 while establishing the safety baseline for ollija.

## Authoritative checkout

- Host: `fuchitalee`
- Repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Reconciled source baseline: `origin/main` at `d21ecd9e792ea358a20efac65db534c2df6817c3`
- Credential-rotation audit commit on `main`: `986d7b803ca22fd0a3d545cb2128cc34d6795478` (same tree as the reconciled baseline)
- Implementation branch: `feat/ollija-staging-release`
- Remote visibility: public; preservation refs containing raw research or screenshots remain local-only.

### Current task-worktree authority

The preservation list below is historical. Current bounded agent work uses one
canonical hierarchy only:

```text
/Users/fuchitalee/development/pushin-weight-v2/.worktrees/<branch>
```

Every entry must be a registered worktree sharing the canonical `.git`
directory. `fuchitalee` owns the shared `.ollija/state/tasks.sqlite3` ledger,
incident records, runtime links, and release receipts. No client machine may
hold a checkout or recovery copy. A task branch is never shared by two
worktrees; active or dirty recovery worktrees are not moved or removed.

Loss of a client session does not transfer authority because the detached
supervisor already runs on `fuchitalee`. Loss of `fuchitalee` does not promote
another host or auto-resume a task; use the authority-transfer procedure below
and then issue a new explicit `go`.

## Preserved working state

| Original state | Preservation ref | Commit | Disposition |
|---|---|---|---|
| Dirty root checkout at `fb027c6` | `preserve/pre-ollija-root-20260814` | `d907e72` | Source, tests, docs, Bridgewright contracts, research, and screenshots checkpointed locally. The ollija plan was separated and cherry-picked onto the implementation branch. |
| Allen Trash checkout fragments | `preserve/allen-trash-20260814` | `1a0f527` | Fifty-nine files overlaid on `origin/main` in a local-only preservation ref after an exact checksum transfer. |
| Allen Claude note and Downloads mockups | `preserve/allen-residuals-20260814` | `8d79aba` | Historical note and mockups preserved locally; exact fuchitalee backup also retained. |
| `fix/harvester-near-real-time` untracked handoff | `fix/harvester-near-real-time` | `539fa11` | Handoff committed; branch retained after worktree removal. |
| `fix/ios-brand-pill-locale-overflow` dirty source and Bridgewright config | `fix/ios-brand-pill-locale-overflow` | `082396e` | Source/config committed; runtime database and receipt backed up separately. |

The remaining registered branches—`fix/once-metrics-refresh`, `release/v22-shell-match`, `feat/v22-headline-trend-narratives`, `fix/harvester-lang-detected`, and `fix/v22-homepage-parity`—had no commits beyond `origin/main` and clean worktrees. Their linked worktree directories were removed after verification. The stale agent worktree registration was pruned. Branch refs remain until post-beta cleanup.

## Runtime-only backups

These files are intentionally outside Git at `/Users/fuchitalee/development/pushin-weight-v2-runtime-backups/2026-08-14/`:

- `root-django_dev-pre-ollija.db` — root development database before restoring the tracked baseline; SHA-256 `8c21fd582c47da30b7d076101d72b9b746bf3c327511b90f66ac1b4b2fced3f8`.
- `once-metrics-refresh/django_dev_metrics_test.db` — worktree metrics fixture; SHA-256 `cc6a958b621cfb4f9531807b2270f95d9ce302c13fac76ce50cc8c491787e110`.
- `ios-brand-pill-locale-overflow/django_dev.db` — iOS worktree development database; SHA-256 `b0acd34b947c0945fc6cc6975ee89e10f3e105c5c56c3e3861b22d117d796356`.
- `ios-brand-pill-locale-overflow/bridgewright-run-receipt.yaml` — worktree runtime receipt; SHA-256 `14906dc3f20c779850c67d276e7cc110fe3249ac05a81bf1e10e8dadfe671a7d`.
- `allen-trash-pre-delete/` plus `allen-trash-pre-delete.sha256` — exact 59-file copy verified equal before Allen deletion.
- `allen-residual-artifacts/` plus `allen-residual-artifacts.sha256` — exact 42-file note/mockup copy verified equal before Allen deletion.

## Allen disposition

The checkout fragments, Claude project note, and Downloads mockups were removed from `allenwlee` only after checksum-matched fuchitalee copies and local preservation commits existed. A post-cleanup search under `/Users/allenwlee` found no path containing `pushin-weight` or `ollija`. Allen remains a keyboard/browser endpoint and is not eligible for authority transfer.

## One-host authority transfer

Host loss does not automatically promote another machine. Until the transfer
is completed, agents may inspect GitHub and Render but must not write project
state, create a checkout, deploy, or restore a database from a proposed host.

1. The owner names a replacement host other than `allenwlee` and confirms that
   `fuchitalee` is unavailable or retired.
2. Rebuild the repository from GitHub and recover only required ignored state
   from the fuchitalee backup set or Render. Never copy a working directory as
   the source of truth.
3. Verify the repository remote, branch ancestry, Render workspace/resource
   IDs, GitHub access, and local secret ownership in read-only mode.
4. Change the canonical-host field in `.ollija/project.yaml` in a reviewed Git
   commit. Until that commit is the accepted project contract, ollija must
   continue rejecting mutations on the proposed host.
5. Run `ollija doctor` and a non-mutating `ollija status`; only then initialize
   fresh local receipt state and permit staging operations.

This procedure will become executable and regression-tested when the project
contract and host guard land in U2-U3. `allenwlee` remains permanently denied
even if it can SSH to `fuchitalee`.

## Secrets disposition

- `.env` and `data/django_dev.db` are runtime-only and removed from Git tracking by this rollout.
- Historical documentation URLs with embedded database passwords are sanitized in the current tree without rewriting Git history.
- The tracked-value audit found one high-confidence live secret family: the current `pushinweight-db-shadow` password, plus a password for the retired predecessor database. Values in the formerly tracked local `.env` were local URLs, development-only values, empty values, or four-character masks; the audit did not identify a live Google, TwitterAPI, Anthropic, or DeepSeek token.
- Render created managed default user `pushinweight_ollija_20260814`. Web, headlines, and harvest now store that managed connection identity and are live at commit `986d7b8`; the production login endpoint returned HTTP 200 after the rotation.
- The former `pushinweight_shadow` credential was retired and its historical password was verified unable to connect. Render retains its original owner role without login privileges, as expected for deletion of an original managed user.
- The first normal Blueprint-triggered deploy did not refresh the existing services' resolved `DATABASE_URL`. Retiring the old credential therefore caused HTTP 500/502 responses from approximately 04:08-04:12 UTC. Recovery injected the new managed internal connection URL directly into all three active services through the Render API and redeployed them. This incident is why ollija must verify resolved service identity rather than treating a green deploy as proof of credential propagation.
- Current-tree redaction and credential invalidation are complete. Git-history rewriting is intentionally deferred until branch consolidation; the invalid historical password remains recoverable only as non-working evidence in old commits and the local preservation refs.
