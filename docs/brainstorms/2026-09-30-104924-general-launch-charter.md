---
title: General Launch Charter
created_at: "2026-09-30T10:49:24+09:00"
status: active-requirements
---

# General Launch Charter

## Plain-English Summary

PushinWeight's general page is a public-facing AI news experience, drawing on
the project's translations, commentary, classifications, and headlines. Before
launch, the owner wants four capabilities: verified researcher identities and
photos, a distinctive multilingual editorial voice, topic histories behind
headlines, and controlled access for external agents through an API and MCP
(Model Context Protocol).

This charter records the shared requirements and open decisions for those four
workstreams. Sessions may work on different tasks and hand them to later
sessions. Use the [General Launch Index](2026-09-30-104924-general-launch-index.md)
to find the current task plans, owners, next steps, and session log.

The charter is maintained in place. Update it as the owner changes requirements;
Git preserves committed history. Distinguish owner requirements from proposed
approaches and unconfirmed findings. Creating these coordination documents does
not authorize collection batches, implementation, external publication, or
deployment. Retain any separate authorization the owner gives a working session.

## Purpose and scope

- **General:** the news experience for general readers; the active launch target.
- **Product:** the paid offering for AI labs; surrounding context, not part of
  these four workstreams unless explicitly added.
- **Dashboard:** primarily administrative use; surrounding context, not a
  redesign target in this charter.
- **Homepage design:** the initial prototype covers the first screen. Its
  proportions and interactions have not yet been accepted by the owner. Final
  URL allocation between general, product, and dashboard remains unresolved.
- **Launch:** all four G items are prelaunch requirements. They are not an order
  of execution. A requirement can be deferred only by a later owner decision.

This is a shared requirements document, not an implementation plan or a claim
about deployed behavior. Detailed task plans belong in `docs/plans/` and follow
the repository's Ollija plan-selection rules. Do not run plan creation merely
to maintain this charter or its index.

## G1 — Researcher identities and images

### Owner requirements

- **G1-R01:** Use the Call A staff-account list as the starting population for a
  comprehensive collection of real, verified researcher photos. The owner
  expects many people in this population to be Chinese nationals; this is
  context, not evidence of any individual's nationality.
- **G1-R02:** Verify each person's identity and name, including their Chinese
  name where applicable. Do not invent Chinese characters from a romanized
  name, or treat an uncertain match as verified.
- **G1-R03:** Persist the verified identity/photo records to the database and
  retain the evidence needed to inspect and correct a match. The storage design
  for image bytes and database references remains to be planned.
- **G1-R04:** These assets must support lighthearted AI-generated illustrations
  accompanying news items. Identity verification and permission/suitability for
  the intended reuse are separate questions that must be recorded.

### Proposed first step and completion evidence

Audit a dated roster before collection so comprehensive coverage has an explicit
denominator. Account for every entry as verified, unresolved, inapplicable, or
otherwise excluded with a reason. Decide the required number and quality of
photos per person. Report name verification, photo verification, and reuse
eligibility separately; a downloaded profile picture does not establish all
three. Demonstrate that an approved identity/photo record can support the
intended illustration workflow.

### Open decisions

Population boundary and roster refresh; acceptable identity evidence; photo
quantity/quality; handling unavailable Chinese names; rights and reuse evidence;
illustration labeling and editorial boundaries; whether any unresolved entry
blocks launch. Do not silently replace the comprehensive requirement with a
convenient subset.

## G2 — General-page editorial voice

### Owner requirements

- **G2-R01:** Develop an English voice combining Variety's insider fluency,
  abbreviations, and industry terminology with the New York Post's irreverence,
  directness, and attention-getting writing, without excessive clickbait.
- **G2-R02:** Use Togetter as a reference for Japanese headlines.
- **G2-R03:** Research an appropriate Chinese voice that triangulates between
  the Variety and New York Post directions. Do not assume a literal translation
  of the English style resolves this requirement.
- **G2-R04:** Make the resulting guidance usable across general-page headlines
  and commentary, including the longitudinal experience.

### Proposed first step and completion evidence

Create a bounded comparison packet using the same underlying stories in English,
Chinese, and Japanese. Research real examples from the named publications and
candidate Chinese references. Let the owner judge rendered examples before
turning them into prompt/style rules. Preserve approved examples, terminology,
and distinctions between fact, allegation, inference, and editorial attitude.

Before open-ended evaluation begins, freeze the sample, evaluation criteria,
iteration limit, and spending limit. Completion requires owner-approved examples
and evidence that the selected guidance reproduces the intended voice on
additional stories without changing their factual meaning.

### Open decisions

Chinese publications/references; how much insider shorthand general readers can
handle; when acronyms need explanation; acceptable irreverence; story/headline
lengths; transliteration and proper-name conventions; tone across languages and
professional/general reading modes.

## G3 — Topic history and longitudinal reporting

### Owner requirements

- **G3-R01:** Each headline on the general page needs an icon through which a
  reader can inspect the longitudinal trend of its topic.
- **G3-R02:** The history must use database evidence. Its generation and serving
  may be dynamic, lazy-loaded, or saved, depending on resource use.
- **G3-R03:** Build on the existing longitudinal research: help readers understand
  how the evidence and explanation of a topic changed over time.

### Proposed first step and completion evidence

Prototype one topic across several headlines. Show the difference between a
discussion-volume chart and an explanation of what changed, when, and why. Make
source support, uncertainty, and insufficient history visible.

A starting proposal is a shared topic history generated on first request, saved
for reuse, and refreshed when relevant evidence changes; popular topics might
be prepared ahead of time. This is an unapproved implementation hypothesis to
measure, not a settled architecture. Completion evidence should cover topic
continuity, supported changes, source traceability, freshness, corrections, and
bounded latency/cost.

### Open decisions

Topic identity and merging/splitting; history time windows; graph versus narrative
presentation; drawer versus separate page; refresh triggers; correction handling;
resource budgets; and behavior when history is unavailable. Final product
decisions belong in the task plan before implementation.

## G4 — Public API and MCP

### Owner requirements

- **G4-R01:** Provide a way for users to connect agents to PushinWeight through
  an API and MCP.
- **G4-R02:** Stay within strict compliance with applicable X and TwitterAPI.io
  terms of service/use. Start from the repository's compliance materials and
  verify relevant current terms before concluding that a proposed output is
  permitted.
- **G4-R03:** External users must not receive actual post text. Author/account
  identity, including usernames, must be obscured.
- **G4-R04:** The intended useful outputs include commentary and classifications.
  Links to underlying X posts are allowed by the owner's requested product
  boundary, subject to the compliance review in G4-R02.
- **G4-R05:** Apply the content boundary to every externally exposed response,
  including generated prose and metadata; removing named database fields is
  insufficient if other output repeats the same prohibited content.

### Proposed first step and completion evidence

Define an explicit permitted-output contract before building the external
interface. Check it against current provider/platform terms. Keep approved
public outputs distinct from internal source records and G1's identity library.
Demonstrate useful agent requests and negative cases that exercise leakage
through commentary, classification evidence, errors, and metadata, alongside
access and resource limits. Define correction/deletion behavior where required.

### Open decisions

An X source link can reveal its author when followed. Clarify the distinction
between omitting identity from our response and promising anonymity; do not
claim both a discoverable source link and guaranteed anonymity. Decide which
classifications and commentary are permitted, at what granularity, and whether
some outputs require aggregation or redaction. Authentication, rate limits,
commercial access, source changes, and permitted use by downstream agents also
remain to be specified. Redaction alone is not a compliance determination.

## Shared boundaries and dependencies

| Shared subject | Coordinating workstream | Other consumers |
| --- | --- | --- |
| Verified person identity and photo provenance | G1 | Personnel news and illustration workflow; G4 must enforce its own output boundary |
| Editorial voice and terminology | G2 | Chatter, headlines, G3 history, and permitted G4 commentary |
| Continuing topic identity and supporting evidence | G3 | Headlines, history UI, and any approved G4 topic tools |
| Permitted external content | G4 | G3 if histories are agent-accessible; any other externally exposed content |

G1's identity records must not automatically become agent-accessible because they
exist in the database. Similarly, an editorial treatment approved for a named
person's news article does not automatically satisfy G4's obscured-identity rule.

Proposed sequence: investigate G1 coverage and G4's permitted-output boundary
early; research G2 alongside them; then exercise one G3 story with the emerging
voice and public-output constraints. Independent progress is allowed. Do not
invent a dependency merely because two tasks share a branch, environment, or
session.

## Homepage context carried forward

The owner supplied a first-screen sketch with Chatter on the left, a chart and
scrolling news area on the right, then Calendar, Free Stuff/Jobs, and Who's Moving
below. The design references Polymarket's rounded white frames, borders, chart
colors, transitions, and automatic headline scrolling. Each major section needs
sharing. Images and video surfaces need rounded edges; personnel images should
be full bleed, as in the supplied Facebook reference. Chatter should wrap text
around the changing transparent silhouette of a generated image; the prototype
uses a conceptual Meta Muse illustration.

These are owner design instructions. The prototype uses illustrative data and
sample personnel; it is not a source for production facts or a selected final
design. Language controls currently demonstrate navigation labels only.

## Maintaining this charter

- Keep requirement IDs stable. New requirements receive new IDs. Explicitly mark
  withdrawn or replaced requirements and link to their replacement where needed.
- Update this document in place; no frozen-version or immutable-file procedure
  is required. Never turn an agent suggestion into an owner decision silently.
- Record material shared-scope changes in the index log with their authority and
  affected G items. Update the affected task plans without copying this whole
  charter into them.
- Current explicit owner instructions take precedence. Recording an instruction
  is not an additional authorization gate.
- Commit, push, collection, deployment, and production activation require the
  applicable session authorization; a readiness checkbox supplies none.

## Source map

- [General Launch Index](2026-09-30-104924-general-launch-index.md)
- [Longitudinal and agentic-media research](../research/2026-09-28-111844-agentic-ai-media-advantages.md), especially section 4 and Appendix A.
- [TwitterAPI.io compliance materials](../external_vendors/twitterapi_docs/compliance/)
- [X compliance materials](../external_vendors/x_twitter/compliance/)
- [Prototype decisions and limitations](../../.context/compound-engineering/ce-prototype/2026-09-29-general-homepage/decisions.md) — local, ignored artifact on fuchitalee.
- [First-screen prototype](../../.context/compound-engineering/ce-prototype/2026-09-29-general-homepage/01-above-the-fold/screens/index.html) — local, ignored artifact; a preview server may need restarting.
