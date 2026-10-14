# Prodsimtest: test production Chatter writing

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

## Simulate earlier stories from the database

The database-scenario mode selects the original Wang wardrobe correction or
first official Mistral announcement and uses the deployed `build_packet`,
`post_evidence` and `story_packet` collectors. It imports the actual deployed
writer, transport, accounting and validation code on the headline worker.
The local launcher streams the test harness over authenticated SSH; it changes
no deployed application file and saves private evidence only on fuchitalee.

Prepare a read-only fixture before a newly authorized test:

```sh
python tests/editorial_replay/run_database_scenario.py \
  --case wang \
  --expected-revision db5510ccc94ea326dd5f81e833a9c791e5e84d99 \
  --run-id new-wang-en-test \
  --output /absolute/private/path/wang-preflight.json
```

Use `--case mistral-first` for the official announcement. Inspect the frozen
packet and request before sending. Add `--fixture <preflight-path> --execute`
and use a new result output path for the authorized first call. The output must
not already exist; a recorded run ID cannot be dispatched again. Global
production guards and the USD0.25 test reservation cap apply. Test assessment
time is today; the evidence cutoff remains historical. No publication occurs.

Wang's cutoff is September24 14:45UTC, after the source was fetched at14:31.
Mistral's cutoff is October6 13:30UTC, after its13:15 fetch. Both source posting
and collection times must precede the cutoff. This uses today's stored database
rows; old profile/classification revisions and archived image pixels are not
recovered. Story nomination is the owner's choice, and the fixture records
whether the anchor appeared in the ordinary dispatch sample. It does not test
automatic editor ranking, queue delivery or publication. Normal retrieval
limits, query timeouts and omissions remain visible rather than being repaired
with manually supplied context. Writer facts come from its projected evidence,
not editor metadata retained in the preparation snapshot.

## Compare the one-sentence prompt variant

The owner-selected variant adds exactly this sentence from
`config/editorial_voices/chatter-en-v1.json`:

> Write a catchy, punny, tongue-in-cheek print headline and supporting byline.

Prepare it from an existing unmodified database preflight with
`--fixture <baseline-preflight> --prepare-variant --output <new-variant-preflight>`.
Execute that inspected variant fixture with a unique run ID. This reuses the
same packet and user message; no new database history query runs. The harness
proves the original full-wire hash before adding the sentence, then checks the
complete variant request before sending. All other instructions, images, schema,
model settings and guards remain fixed. The live production voice is unchanged.
Earlier CLI examples used different conditions and are labelled separately.

The authorized6.1/high model variant starts from that catchy/punny preflight:
use `--fixture <6.0-style-preflight> --prepare-model-variant --output <new-preflight>`.
It preserves the complete prompt and packet and changes the request's model
and reasoning effort. Rates come from the deployed6.1 route; endpoint,
credential, output allowance and timeout retain the English route's settings.
The test checks the entire prior request after restoring the two changed fields.
Execute the inspected fixture once with a unique run ID. This does not change
the deployed English model selection.

## Test evidence repair and headline attribution

The owner-approved repair variant adds two reviewed evidence records to Wang:
the source image's transcribed labels and a dated official identity excerpt.
They have `platform: supplemental_evidence`, their own source URL/date, an
explicit `evidence_role` and a hash of the reviewed text. They are not new X
posts. The image record also retains the original post ID and image hash.
Production's existing generic source projection and `original_text` passage
binding represent the text of these supplemental records; the original X post
text and attached image remain unchanged. This tests a sourced packet repair,
not an automatic production collection or a historical database snapshot.

The repair changes exactly one system-prompt sentence. Faithful attribution
continues in the supporting line and article, and the headline must preserve
attribution/uncertainty whenever omitting it would mislead. The catchy/punny
sentence and6.1/high route/settings remain fixed. Mistral receives no additional
evidence, so its variant changes only that attribution sentence.

Prepare with `--prepare-repair --fixture <6.1-preflight>
--supplements <reviewed-records.json> --output <new-repair-preflight>`, then
execute that inspected fixture once with a unique run ID. No deployed source
module, live voice, source database row, provider transport or copy validator
is patched. Add the new results to the same review manifest and label the
comparison as evidence/attribution changes. The writer sees no prior model copy
or suggested target headline. First results and supplemental receipts remain
private; preserve every earlier fixture and response.

To compare that exact repair on6.0/medium, prepare with
`--prepare-repair-model --fixture <successful-6.1-repair-preflight>
--output <new-6.0-repair-preflight>`. This restores the configured English6.0
model/effort/rates while retaining every message, evidence record, image, schema
and other request parameter. The full request must equal the6.1 reference after
restoring only model and reasoning. Execute the inspected fixture once using a
unique run ID and retain the6.1 copy as its same-prompt comparison.

## Keep several cases in one review

Use a private JSON manifest to retain each case's own inputs and comparisons:

```json
{
  "cases": [
    {
      "kind": "exact_replay",
      "fixture": "review-preflight.json",
      "replays": ["result.json"]
    },
    {
      "kind": "database_scenario",
      "fixture": "wang-preflight.json",
      "result": "wang-result.json",
      "comparison": "wang-comparison.json"
    }
  ]
}
```

Paths resolve relative to the manifest. A comparison file contains `label` and
`copy` with `headline` and `byline`; it is reference copy, not a new model run.
Build with `build_review.py --manifest <path> --output <preview/index.html>`.
Verify with `check_review_browser.py --manifest <path> --url <preview-url>
--evidence <new-evidence-directory>`. Case switching must update copy, packet,
exact request, hash and comparison together. The same selection survives a
reload or portable HTML download. Keep every first fixture/reply unchanged and
add new manifest entries when another test is authorized.
