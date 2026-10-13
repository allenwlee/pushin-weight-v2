# Replay a production Chatter writer request

This test reproduces the complete request that created a published Chatter
edition. It helps distinguish an actual production result from a headline trial
that changed the instructions, context, output task or API route.

The script runs on the production headline worker and imports its deployed
request builder, provider transport, accounting guards and validators. The
default operation checks the saved request without making a provider call.
An explicit `--execute` permits one call and saves a test result without
publishing an edition. A run ID cannot be dispatched twice.

From the retained G2 worktree on fuchitalee, run the English Mistral preflight:

```sh
ssh -T -o BatchMode=yes -o ConnectTimeout=20 \
  srv-d9ufj4e417fc73d93g20@ssh.oregon.render.com \
  "python -c 'import os,sys; os.environ.setdefault(\"DJANGO_SETTINGS_MODULE\",\"project.settings\"); import django; django.setup(); exec(sys.stdin.read())' --edition 65a88027-6bb0-429f-85f6-6af8bad5d732 --expected-revision db5510ccc94ea326dd5f81e833a9c791e5e84d99" \
  < tests/editorial_replay/production_replay.py \
  > .local/g2-production-parity-20261013/preflight.json
```

For an authorized fresh replay, add `--execute --run-id <unique-test-id>` to
the remote Python arguments and save stdout to a new private JSON file. The
recorded `20261013-mistral-en-01` run is complete: do not redispatch it.

The test requires equality for the full request and its recorded wire hash:

- full system and user text, message roles, source passages, included historical
  context, image URLs and JSON schema;
- effective configuration, resolved voice instructions, API endpoint, exact
  model, reasoning effort, service tier, completion allowance and socket timeout;
- the original source-to-passage bindings used by normal response validation.

PostgreSQL can reorder JSON object keys when saving the source snapshot. The
test first proves the rebuilt payload has identical contents, then restores the
recorded user text serialization. Its final request hash must match the actual
producing call. This preserves the original input tokens rather than quietly
accepting a differently serialized prompt.

Before a paid send, negative checks confirm that changed instructions, message
roles, context or completion limits are rejected even if the locked opening
still matches. A fresh send uses `json_call`, its normal transport, the shared
single-request guard and ordinary daily/assessment accounting. It then runs
the existing source normalizer and copy validator. The test's conservative
reservation may not exceed USD0.25; ordinary global limits also apply. A held,
failed or incomplete request is recorded without automatic retry.

The private result includes the exact request, source snapshot, hashes of the
deployed writer modules, diagnostics, first reply and accounting identifiers.
It never includes credentials. No editor-ranking replay, fresh context
retrieval, picture generation or publication is performed. Historical context
is reproduced only to the extent it was actually included in the saved writer
packet. The request is identical; a generated response can still differ.

## Keep a review page for repeated tests

The preflight also records the original published copy, so it is a complete
review fixture. Build a standalone HTML from that fixture and one or more
saved replays:

```sh
python tests/editorial_replay/build_review.py \
  --fixture /absolute/private/path/preflight.json \
  --replay /absolute/private/path/replay-01.json \
  --replay /absolute/private/path/replay-02.json \
  --output /absolute/private/path/preview/index.html
```

The page shows Chatter copy on the left and baseline comparison, source context,
exact request and full reply on the right. Adding another `--replay` adds a saved
run without replacing earlier results. The builder rejects different request
hashes, model settings or unfinished replies. The page makes no provider calls.
Its dropdown and tabs retain selection across reloads and in downloaded HTML.
The stylesheet uses the same Newsreader and DM Sans families as General, with
local fallback fonts when the external font service is unavailable.

Older preflight fixtures did not include the published copy. For those fixtures,
pass `--original /absolute/private/path/original-copy.json`. Keep fixture/result
JSON and generated HTML in an ignored private directory; commit the entry points
and template. Serve only the generated preview directory to the owner's browser.

For the current G2 notebook, the owned local URL is
`http://fuchitalee:58713/`. Its generated HTML and first-call evidence remain in
the retained G2 tree's `.local/g2-production-parity-20261013/` directory. Rebuild
the same `preview/index.html` and refresh that URL after another authorized run.

Check the browser with recorded expectations:

```sh
python tests/editorial_replay/check_review_browser.py \
  --url http://fuchitalee:58713/ \
  --fixture /absolute/private/path/preflight.json \
  --replay /absolute/private/path/replay-01.json \
  --evidence /absolute/private/path/browser-evidence
```

This exercises every run and tab on desktop/mobile, exact copy and request text,
selection reload, source navigation, keyboard tabs, clipboard and portable
downloads. The small renderer tests require no Django/database startup:

```sh
python -m pytest -p no:django -c /dev/null --rootdir=. \
  --confcutdir=tests/editorial_replay tests/editorial_replay/test_review.py -q
```
