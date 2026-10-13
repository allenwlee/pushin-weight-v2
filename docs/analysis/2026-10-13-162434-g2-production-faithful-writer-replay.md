---
title: G2 production-faithful English writer replay
created_at: "2026-10-13T16:24:34+09:00"
status: completed-one-call-writer-replay
workstream: G2
---

# G2 production-faithful English writer replay

The owner requires writing tests to reproduce the full production conditions.
The replay imports the actual deployed writer/request/transport/source-validation
code on the production headline worker at `db5510ccc94ea326dd5f81e833a9c791e5e84d99`. It rebuilds the
immutable Mistral edition's source snapshot and checks the entire request against
its producing call before making one paid call. It does not publish the result.

| Observation | Value |
| --- | --- |
| Original model and effort | GPT6.0 Sol (`gpt-6-sol`), medium |
| Model returned by replay | `gpt-6-sol` |
| Original published headline | MISTRAL’S ‘LE CHONK’ GOES LARGE, POST SAYS |
| Replay headline | REPORT: MISTRAL’S ‘LE CHONK’ ENTERS THE CHAT |
| Supporting line | The European AI developer reportedly put its massive new model in public preview and plans to release its weights by month’s end. |
| API | Direct OpenAI Chat Completions |
| Completion allowance / socket timeout | 4096 / 90seconds |
| Tier | default |
| HTTP / finish | 200 / stop |
| Calls / retries | 1 / 0 |
| Elapsed | 15.837seconds |
| Input / output / reasoning tokens | 3462 / 1199 / 436 |
| Ledger cost after confirmed usage | USD0.020645 |
| Conservative reservation before send | USD0.113545 |
| Publication | None; original edition preserved |

The complete request and actual transport hash both match the original:
`f6e159434251987385322edf8ff248822a6976b814263936d7e14bcc59fe8094`. Equality covers full instructions, system/user placement,
source/context text, source references and image URLs, schema, exact model,
reasoning, output cap and tier. The test requires the original effective config
and checks the endpoint, voice hash and deployed revision. Original user JSON
serialization is restored only after checking identical contents, because
PostgreSQL JSON storage reorders keys. Source IDs and normalization bindings
remain unchanged; prior headlines are not inserted as examples.

The normal `json_call` transport, global in-flight/accounting guards,
`normalize_reply` and `validate_copy` pass. Four negative controls reject extra
instructions after the matching opening, a changed message role, changed context
and a changed completion allowance before any send. Compile/affected-fileRuff
and the unchanged actual-fixture check pass; no additional paid verification.

This reproduces the writing stage and its saved input. The saved input contains
1 primary post and 0 context posts; it does not invent missing
historical evidence. No factual-editor ranking, fresh context retrieval, picture
work or publication is performed. The same request can yield different wording.
This first replay therefore does not isolate why an earlier CLI result was better,
or demonstrate that instruction length or any individual rule caused the outcome.

Reusable entry point: [production_replay.py](../../tests/editorial_replay/production_replay.py)
and [usage](../../tests/editorial_replay/README.md). Private exact request, source
snapshot, first response and read-only accounting/publication proof are retained
at `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/g2-editorial/.local/g2-production-parity-20261013`. The first report's canonical-call lookup missed the storage bridge's
`legacy-editorial:<assessment>` cycle name; its raw report is preserved. A separate
read-only check resolves the exact producing record and confirms zero publications;
the entry point now uses the project's exact legacy-call identity convention.
No response, accounting or request was changed and no second provider call occurred.

Future comparisons must use the complete production writer contract and frozen
source packet. Intentional prompt/model/input variants must be labeled explicitly;
matching only the short locked opening is insufficient. Earlier headline-only and
CLI trials remain historical outcomes with different conditions. Current model
choices, locked wording, live configuration and published editions stay unchanged.

## Reusable HTML review and publication preparation — 2026-10-13T17:31:11+09:00

The owner requests commit/push plus a fresh browser page for repeated testing.
The dedicated branch `test/g2-production-replay-review` contains the replay
entry point, a portable renderer/template, focused renderer tests and a real
browser checker. Private captured requests/replies and generated HTML remain
in the retained G2 tree. The stable review URL is `http://fuchitalee:58713/`.

The page presents the full selected Chatter article alongside its published
baseline. Tabs show the actual source/context packet, full system/user messages
and the complete saved reply. Source links, copy controls and JSON/HTML downloads
work. Additional saved replies can be appended with repeated `--replay` arguments;
the builder rejects changed conditions, duplicate run IDs and unfinished replies.
No model call is initiated by the page. Current preflight output also captures
the original copy, removing the separate export step for later runs.

Seven pure renderer checks pass with zero skips/errors. The repository's shared
local environment lacks Pillow, so its automatic Django startup failed before
the first renderer-only test attempt. The documented isolated pytest command
runs these pure checks without importing Django or requiring a database; it
passes without warnings. This does not claim an application suite pass.

The real agent-browser checker passes16states:original/replay × fourtabs ×
1440/390px. Exact headline/support/article, full system/user/reply, no horizontal
overflow and selection reload match recorded expectations. Source navigation,
keyboard tabs, clipboard, reply download and portable HTML preserving selection
also pass; zero page errors. Desktop/mobile screenshots were inspected. Updated
self-contained preflight reproduces the same request hash and identical generated
HTML bytes, so this browser evidence remains applicable. No new paid call occurred.
FocusedRuff and syntax checks pass. Remote commit/browser-window receipts follow
in private evidence; this preparation is not a claim of a new production release.
