# Chatter, Pulse and the picture editor

G2 turns collected posts into saved stories that readers can share and revisit.
Chatter covers AI human interest, memes and insider news with an English
New York Post style headline and supporting line. Pulse reports factual news.
An important event can qualify for both. A single source post remains the
atomic unit; its own commentary preserves its meaning and tone.

This reference describes the candidate implementation through migration 0068.
Generation, public access and picture bindings ship **off** in
[`config/editorial.yaml`](../../config/editorial.yaml). Deployment and a fresh
human quality evaluation are separate from the local implementation tests.

Staging refresh treats the editorial tables as environment-local, like the
existing per-brand headline work. It excludes their data from the source dump
and clears the full graph in staging, including accepted editions and assets,
so staging cannot resume source provider jobs or use source-only storage paths.
Original posts remain copied. See the [staging refresh runbook](../operations/staging-data-refresh.md)
for optional-source migration handling and the required source-reader grants.

## Normal flow

1. A committed harvest completion queues one editorial assessment on the
   existing `trend-narratives` queue. G2 activation is independent of the older
   headline generator; there is no new scheduler or collection call.
2. The **editor-in-chief** receives original posts from the preceding 24 hours,
   relevant seven-day context, existing headline leads, current staff roles and
   recent story identities. It groups developments and judges Chatter and Pulse
   separately. Missing chart evidence never excludes major news.
3. Code validates source, person, brand and chart references, removes exact
   repeats, and compares a worthy Chatter challenger with the incumbent.
4. A shared writer applies the selected track/locale profile directly to the
   same original evidence. Accepted editions contain a headline, supporting
   line (called `byline`), full article and source links. A byline is not an
   invented journalist's name.
5. The optional **picture editor** selects an eligible source image. `derive`
   adds an asynchronous MiniMax H3 video; the verified source image can display
   while that task is pending. Missing imagery does not discard valid text.

Each quarter-hour permits at most one new Chatter story, including a meaningful
revision of an existing story. Locale variants belong to that same publication.
The initial Pulse cap is one story per assessment and is configurable separately.

Priority is `importance × 0.5 ** (age_hours / half_life_hours)`. The initial
six-hour half-life and five-point replacement margin are engineering defaults,
not human-approved scoring thresholds. Aging starts at the meaningful
development time, not the time of each reassessment. No worthy challenger keeps
the existing hero. An unchanged evidence packet skips model calls altogether.

## Source coverage and grouping

The default packet has at most 160 recent posts, 40 older context posts and
120,000 UTF-8 bytes. Hourly sampling prevents a burst in the final minute from
using every slot. Coverage includes the eligible and included counts and a
sampling flag. This is bounded discovery, not an exhaustive news scan. Original
post images are included as URLs, with at most three images attached to a
vision request. A visually essential story requires a vision-capable writer
and the selected original image. Unseen URLs are not visual verification.

Existing approved brand/window headlines serve as leads, never as independent
proof. The latest eligible one-day chart dossier supplies measurement context;
an event records `supported`, `not_supported` or `unavailable`. Claims of support
must reference actual facts for its brands. This does not prove causation.

The model receives existing story IDs and decides whether a development is new,
updated or unchanged. Code coalesces exact source-set/key matches, but does not
merge on mere post overlap. Later product versions can have separate stories.
Semantic grouping remains a model judgment requiring human evaluation.

Creation and fetch timestamps exclude later posts from saved-cutoff packets.
Staff roles are explicitly labeled as observed now; this is not a historical
reconstruction of the staff directory. Headline leads whose original sources
are outside the packet cannot independently ground a new publication.

## Voices and routing

[`config/editorial_voices/`](../../config/editorial_voices/) holds immutable JSON
profiles. Each has `id`, `version`, `track`, `locale`, `available` and instructions.
Changing a voice means adding a version and changing the binding in
`editorial.yaml`; no copied generation script is needed. Saved editions retain
the profile ID, version and content hash. Existing shared editions remain intact.

`chatter-en-v1` follows the successful bare-prompt direction without the five
prior example headlines. Chinese and Japanese Chatter profiles are explicitly
unavailable until crafted and evaluated. Pulse has factual profiles for all
three locales; only English is bound by default. All active bindings are
validated before paid work, including track/locale agreement. Each locale uses
original evidence independently; it does not translate an English draft.

The `editor`, `chatter` and `pulse` routes require explicit model identifiers,
endpoint, matching credential variable, output cap and token prices. Supported
endpoints are OpenRouter and direct DeepInfra. `vision` is an explicit capability;
OpenRouter provider fallback is disabled. A mismatched returned model or
truncated/invalid response is held. No guessed model, key or price is supplied.

Atomic commentary uses its existing model and the versioned
`post-synthesis-direct-source-v3` prompt, with no editorial profile.
See [Post commentary](commenter.md). Existing brand/window headline generation
keeps its own interfaces and uses the shared bounded HTTP transport.

## Picture bindings and selection

| Binding | Purpose | Default |
| --- | --- | --- |
| `atomic`, optionally `atomic:x` | One source post's commentary | `off` |
| `current_headline` | Existing brand/window headline | `off` |
| `chatter` | Saved Chatter edition | `off` |
| `pulse` | Saved Pulse edition | `off` |

Each binding accepts `off`, `select_only` or `derive`. An atomic platform override
does not change any headline binding. The same selector and derivative service
serve all four callers. Only X adapters are wired; this does not add other
platform collectors. G5 chooses where attachments appear in existing surfaces.

The editor's subject classification and named-person IDs feed deterministic
selection: named subject first; identifiable author when no subject is named;
leadership for company direction; the agent team for an agent release; a
researcher for a model release; then founder. Current headlines and atomic
adapters use known authors and founder fallback when richer subject metadata is
unavailable. No additional picture-selection model call is required. The writer
can include a visual brief in its existing request when pictures are enabled.

G1 affiliations must be current, confirmed, not superseded, date-relevant and
for a subject brand. Portraits require verified attribution, individual portrait
status, approved suitability, available source bytes and an allowed reuse state.
At most 500 roles are considered, prioritizing named people, authors and founders
before the remaining roles. A missing researcher photo falls through to the next
eligible candidate or founder. Fallback identity is stored separately from the
article's named subject; no eligible image is an explicit `missing` result.

An image-dependent story retains its actual post image instead of substituting
a portrait. Post-image reuse is `unknown`; using it requires an explicit policy
allowing that state. The default allows only `permitted`. `restricted` is never
allowed. Identity verification and reuse permission remain separate facts.

Affiliation/photo corrections are checked again at reading and generation time.
Re-selection creates a new assignment when the eligible source changes. Original
bytes, provenance and prior derivative receipts are retained. `off` hides existing
attachments without deleting them.

H3 uses only `PUSHINWEIGHT_MINIMAX_API_KEY` in the worker's environment. It never
falls back to shared MiniMax keys or executes a secret file. Both `staff_media`
and `editorial_media` storage must be configured as durable and readable by
worker and web processes before video creation. `EDITORIAL_MEDIA_STORAGE_BACKEND`,
`EDITORIAL_MEDIA_STORAGE_OPTIONS`, `EDITORIAL_MEDIA_ROOT` and
`EDITORIAL_MEDIA_DURABLE` configure the derivative namespace.

The initial adapter produces 768P video, six seconds by default (configurable
four to fifteen). It verifies source hashes and minimum dimensions, persists a
provider task ID, polls that task, validates a bounded MP4 container and stores
the derivative separately. Humorous treatment belongs to Chatter; Pulse/current
headlines use restrained illustration, atomic commentary faithful illustration.
Actual generated motion and likeness still require a funded visual trial.

## Spending and recovery

Daily dollar, daily call, per-assessment dollar/call and media call/cost ceilings
are required before paid work. Text reserves a conservative UTF-8-byte token
bound plus configured image/output bounds. Media reserves the operator's full
cost ceiling. These are application reservations based on supplied rates, not
a provider billing guarantee. Failed/uncertain requests remain fully charged;
reported token usage is kept separately. GET readers never initiate generation.

PostgreSQL claims and fencing prevent stale publication. Requests reserve spend
before network I/O; database locks are released during provider calls. There is
at most one active G2 create/text request globally. An expired worker's uncertain
send is marked `ambiguous`, leaving room for later intervals without retrying it.
A video's create stage is unique across assessments: a later worker recovers
the saved task ID instead of paying again.

Polling has a persisted lease and maximum attempt count (40 by default). Duplicate
poll deliveries do not create additional polling chains. Already-sent tasks can
be collected after a binding is disabled, while readers continue to hide them.
Headline jobs recover due polls; picture-only operation can use the explicit
poll command after broker loss. Unknown sends need operator investigation;
there is no automatic refund, reset or blind resubmit command.

Read-only commands:

```bash
python manage.py editorial preview --cutoff 2026-10-05T00:00:00+00:00
python manage.py editorial status
python manage.py editorial replay --assessment 123 --cutoff 2026-10-05T06:00:00+00:00
```

`preview` exposes a private source packet to the operator. `replay` re-scores
saved decisions with current decay settings; it does not ask a model to make
new judgments. Provider-capable commands require configuration and `--execute`:

```bash
python manage.py editorial run --execute
python manage.py editorial picture --kind current_headline --content-id 123 --execute
python manage.py editorial poll --picture-id UUID --execute
```

## Reader and integration contracts

`/stories/<story UUID>/` opens the newest accepted edition for the requested
track/locale. Share links include `edition=<edition UUID>`, pinning exactly the
saved copy the reader shared. `/stories/` is a cursor-paginated archive; both
surfaces link back to current General. Missing locale copy falls back to English
with a visible label. X sharing uses an intent link and Open Graph/Twitter card
metadata. Instagram/Facebook publishing is not implemented.

`/api/v2/editorial-stories/?track=chatter&lang=en` returns saved `hero`, up to five
distinct previous stories, `items` and `next_cursor`. Pulse uses the same API
without a hero and orders accepted editions newest first. Meaningful updates
create a new edition; earlier versions remain in the archive and at pinned links.
The projection excludes raw post text, review notes, decision packets and costs.
Asset routes check that the assignment belongs to the accepted edition and is
still eligible. Anonymous access requires `public_enabled`; normal authenticated
staff can preview while it is off. These views perform no writes or provider calls.

G5 can include `monitor/editorial/chatter.html` with the shared feed payload and
load `monitor/editorial/editorial.css` and `.js`. The hero stays stationary while
the five-item history scrolls, with pause, focus/hover and reduced-motion support.
Final General placement and styling remain G5's responsibility.

G3 consumes `longitudinal_subject(edition)` from
[`readers.py`](../../monitor/editorial/readers.py): story/edition IDs, brand keys,
source-post IDs, evidence cutoff and development time. Its later longitudinal
angle does not change the G2 editorial decision.

Implementation: [`monitor/editorial/`](../../monitor/editorial/).
Schema: [editorial tables](db-schema.md#editorial).
Verification: `tests/test_editorial*.py`; provider responses are fixtures, not a
claim that live models reproduced the owner's preferred headlines. The saved
54-case owner fixture preserves explicit judgments and the owner's instruction
to treat remaining blanks as negative.
