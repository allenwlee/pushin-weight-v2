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

The explicit English launch profile is
[`config/editorial-english-launch.yaml`](../../config/editorial-english-launch.yaml).
It configures generation/public story reading and headline derivatives with a
combined $5/day reservation ceiling. `EDITORIAL_CONFIG_PATH` selects the file
for all processes; its resolved path must be under the repository's `config/`
directory. `EDITORIAL_ENABLED` and `EDITORIAL_PUBLIC_ENABLED` accept only
`true`/`false`; `EDITORIAL_DAILY_USD` may lower the selected profile's daily cap.
Selecting the default file disables generation, public reading and all pictures.
The configured launch profile does not prove that a service has activated it.

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

The editor's instructions carry the owner's reviewed newsworthiness rules:
spotlight model releases from quieter tracked brands, prioritize major agent or
application providers entering model competition, and reserve personnel-change
headlines for well-known people or very key roles. Ordinary moves belong in
Who's Moved. Unproven allegations require multiple supporting posts with their
provenance distinguished from copies of one claim. The writer identifies
unfamiliar people and companies, preserves the actual product category and
explains why the development matters using supplied evidence. These are runtime
instructions; the saved human judgments do not train a model or establish that
a live model followed them.

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
240,000 UTF-8 bytes. Hourly sampling prevents a burst in the final minute from
using every slot. Trimming reserves up to one quarter of the byte allowance for
background, instead of discarding it all first. Coverage records recent inclusion,
context inclusion/trimming and sampling. This is bounded discovery, not an exhaustive news scan. Original
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

Selection and writing share source-reading rules with the existing headline
generator through [`monitor/headline_grounding.py`](../../monitor/headline_grounding.py).
These rules preserve the actor, action, target, uncertainty and ownership of
figures, and distinguish a report or promotion from a developer announcement.
Sharing those rules does not impose the older generator's per-brand eligibility
or translation policy on Chatter and Pulse.

[`monitor/editorial/grounding.py`](../../monitor/editorial/grounding.py) assigns
short model-facing labels such as `S001` and exact named passages. Passage fields
distinguish the original post, stored quoted text and locally available reply
context; available quoted/parent identities are supplied separately. Unknown
identity stays unknown. The source's raw quote flag is preserved even when the
quoted post is absent from the local database.

Returned editor decisions and writer responses must include a `source_check`
with actor/action/target, claim status and number ownership. Each claim's wire
`support` object binds one source label, one field (original/quote/parent),
passages owned by that field, and brands collected for that source. Complete
schema alternatives preserve those relationships; packet-wide lists of valid
brands and sources would permit invalid combinations. Code repeats the ownership
checks locally and derives the final source-ID list, event brands and audit actor
from validated support. The actor is the original author, quoted speaker or
parent author for that exact field; an unavailable identity stays unknown.
The model does not generate duplicate source lists or audit actor names. Code
restores canonical post IDs before saving the response.
A brand mentioned in text but absent from that post's collected matches cannot
be added by the model. A grouped story can still combine separately supported
brands and posts. Empty brand choices are valid for an untracked subject.

After selection, `context.story_packet` resolves original anchor posts and
searches stored original/quoted text for distinctive names and phrases. Recent
recall covers seven days; one expanded query covers 180 days and samples up to
eight candidates per month. A phrase introduced near an anchor name and a
relationship cue (such as a nickname or meme) can extend the search; its source
post, field, exact offsets and text are saved. At most two terms are added.
Repeated distinctive names can also extend recall. Direct parent/quote links
can recover unnamed teasers. A shared brand/author alone cannot link a teaser
to a release, and an earlier model version is not evidence of this version's
availability. The initial extractor targets Latin-script names, including those
embedded in Chinese/Japanese posts; it does not provide general multilingual
entity recognition or semantic relevance guarantees.

Each lookup returns at most 80 candidates and has a 1,500ms statement timeout.
The stored `story_context` reports query timeouts and candidate/omission counts.
The concurrent migration `0069_editorial_context_search` adds one multi-column
pg_trgm index on uppercase original and quoted post text; it adds no columns or
tables. Reversing this migration removes the index but retains the potentially
shared extension. Apply the migration before judging historical-query latency.

A writer bundle preserves anchors and adds at most 24 context posts within
96,000 evidence bytes, reserving up to eight slots for older history. Identical
text and duplicate IDs are deduplicated. A source too large for remaining space
is omitted; an oversized anchor set produces an explicit hold. Manual anchor
IDs absent from discovery use the same collector and cutoff checks. The service
freezes the bundle in the assessment before writing and reuses it across tracks
and locales. Retrieval does not change story identity, priority age or unchanged
story checks. It cannot recover a story the editor never selected.

The writer receives selected sources, eligible background, their identifiers and chart context. It
does not receive the editor's summary, reasons, claim prose or inferred subject
kind. After its source checks it produces `supported_copy`, then copies those
headline/byline/article strings into the final fields; validation rejects any
disagreement. Editions retain source checks and supported copy privately.
Each new edition also saves `evidence.attribution.post_count` and
`evidence.attribution.posts` (distinct IDs and every URL), derived from the
writer's validated citations. `cited_post_ids` and `sources` contain only used
support; `post_ids` retains editorial anchors for unchanged-story compatibility.
Retrieved candidates are not automatically citations or independent reports.
Reader payloads expose `source_count` and complete source links, and the permanent
story page displays both. Historical saved contracts remain readable. These checks establish reference
ownership and consistency, not that every sentence follows from its evidence.
The editor schema also binds absent chart evidence to `unavailable` and empty
fact IDs, absent people to empty person IDs, and an empty existing-story list to
`change=new` with a null story ID. `not_supported` still requires a supplied
chart measurement; it is not a synonym for unavailable.

The request also lists repeated-author groups and explicitly marks independent
confirmation as unassessed. A narrow local guard rejects the observed wording
claiming multiple independent reports/sources/accounts. Numeric prose with an
all-empty number-ownership audit is held; this detects an audit contradiction,
not all possible numeric or semantic errors. Three October 7 live iterations
reached pipeline completion once but did not qualify the final candidate;
see the [iteration report](../analysis/2026-10-07-122329-g2-source-contract-iterations.md).

The launch editor/Pulse routes send the schema through DeepInfra's strict
`json_schema` response format, without duplicating it in prompt text. Every
object is closed to extra fields and requires explicit values for its properties.
Other routes retain the prompt schema, JSON-object mode and the same local
ownership validation. The schema has a separate 120,000-byte default cap; the
serialized request cap is evidence allowance + schema allowance + 30,000 bytes.
The full request still counts toward the pre-send monetary reservation. An
oversized schema or request fails before reserving/sending; it does not silently
remove sources. A rebuilt October 4 discovery packet retained 128 recent/22 background posts
at 237,724 bytes; its direct editor request was 347,225 bytes with a 94,337-byte
schema, within the 390,000-byte total cap. Offline size checks do not establish
provider acceptance or model quality.

When the source does not supply an event date, `occurred_at` is instructed to
use first-observed posting time for priority aging. It must not be presented as
a verified launch date. Missing context or unseen source images still limit
what the editor can infer; supplying URLs alone does not inspect their pixels.

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
truncated/invalid response is held. Rejected replies persist a fixed failure code,
HTTP status, model-match Boolean, standard finish reason and integer token counts
when available. Success/failure diagnostics include the exact serialized request's
SHA-256 hash, request profile, socket timeout and elapsed seconds. Bounded
provider request IDs, recognized service tiers, reported reasoning-token counts
and finite estimated cost are retained when supplied. A transport timeout has no
invented HTTP status or network phase. Raw rejected text and credentials are
excluded. Uncertain stages
retain their reservation and cannot resend. No guessed model, key or price is
supplied.
OpenRouter requests also cap the permitted provider input/output prices at the
configured reservation rates.

The English launch profile routes editor and Pulse directly to DeepInfra as
`deepseek-ai/DeepSeek-V4-Flash-0731`, using `DEEPINFRA_API_KEY` and
`reasoning_effort: none`. The `editorial_editor_v1` and `editorial_writer_v1`
profiles in [`x_monitor/deepinfra.py`](../../x_monitor/deepinfra.py) share the
existing headline settings: priority tier, strict JSON schema, top_p 0.95 and
seed 42. Editor temperature is 0.2; Pulse temperature is 0. The socket timeout
is 300 seconds. It is not a whole-assessment deadline: the 15-minute assessment
lease still prevents stale publication and further calls after expiry.
The shared adapter requires the exact served model, priority tier, a request ID,
nonnegative input/output token counts, a finite nonnegative estimated cost and
zero or absent reported reasoning tokens. It rejects truncated/empty completions
and duplicate JSON keys. It sends no OpenRouter provider or price-cap fields on
those routes.
Chatter uses direct OpenAI Chat Completions at
`https://api.openai.com/v1/chat/completions`, model `gpt-6-sol`, with
`reasoning_effort: medium`, `max_completion_tokens: 4096`, image input and
`service_tier: default`. It sends no OpenRouter routing fields. See the
[OpenAI request contract](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
and [model pricing](https://developers.openai.com/api/docs/models/gpt-6-sol).
The configured $2.50/M input reservation includes the published cache-write
rate; output reserves $10/M. Existing combined daily limits still apply.

The launch credential is `OPENAI_API_KEY`, sourced from fuchitalee's
`/Users/fuchitalee/.env.secrets`. Delivery must parse only that literal assignment
without executing the file and provision its value in the intended editorial
worker's Render environment. Runtime reads the process environment and fails
before reserving/sending if the selected key is absent; it never falls back to
OpenRouter. Neither selecting the profile nor passing offline checks provisions
a Render credential or activates scheduled generation.

The English launch profile allows **65,536 total output tokens** per DeepSeek
editor/Pulse call, including reasoning; the Chatter writer has its independent
4,096-token allowance. The route validator permits configured allowances up to
65,536. These are application request limits, not claims about the provider's
maximum capability. Each request reserves the full configured output allowance
before sending; increasing that allowance does not increase the combined $5/day
ceiling. At the factual route's $2/M reservation rate, output alone reserves
$0.131072 per call, plus its bounded input reservation.

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

The story asset route checks public/staff access, the exact edition/picture
association, current source verification and picture mode before delivering a
file. Filesystem storage streams through Django. For shared S3-compatible
storage it checks object existence, asks the adapter for a signed URL with a
300-second lifetime, and redirects the client directly to storage. The URL must
use HTTPS, contain a signature and expire within 300 seconds; unsigned or
unbounded links are rejected. The redirect is `private, no-store`, and temporary
URLs are never saved as object identifiers. Disabling a binding prevents new
links immediately; a previously issued link can remain usable until expiry.
Object expiry, range requests and real video playback require live shared-
storage verification; local fake-backend tests do not establish those results.

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
