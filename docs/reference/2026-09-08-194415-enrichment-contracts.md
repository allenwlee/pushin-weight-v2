# Enrichment telemetry and evaluation contract

Stage 0 contract, version 1. It specifies observation and fixture semantics;
it adds no database schema, persisted status, scheduler behavior, or provider
call.

## Usage normalization

The normalized shape is nullable `input_tokens`, `output_tokens`,
`cache_read_input_tokens`, `cache_creation_input_tokens`, `reasoning_tokens`,
and `total_tokens`. Preserve provider semantics. `total_tokens` is the
provider-reported total only; it is null when unreported and is never derived
by adding overlapping fields. Unreported usage is not zero. Reserved
`max_tokens` is a limit, never observed usage.

Usage is captured once at the application transport boundary. An event has an
`event_id`, timestamp, role, stage, run, model, provider-host class,
prompt-identity, batch size, attempt ordinal/kind, outcome, safe error class,
elapsed latency, and usage source. The event represents one application
transport invocation; retry, repair, and fallback are represented by their
own invocation with outer context, without helper/wrapper duplicates.

Current role names are `post_translation_synthesis` for translator,
`classification`, `relevancy`, and `headline`. Metadata contains no keys, prompts,
source or post text, raw bodies, full URLs, or exception messages. Reporting is
best effort and cannot alter provider failure or parsed output.

The production post-fetch translator and classifier factories share the
direct-HTTP `x_monitor.attribution.AnthropicClaudeClient`; their explicit
application loops own retries. The separate legacy translator SDK wrapper and
the headline SDK client disable SDK retries.

## Contract boundaries

Future completion identity includes content, context, prompt, model, taxonomy,
and locale versions. Future semantic concepts are `pending`, `failure`,
`context_missing`, `historical_untyped`, and confident `Other`; they must not
be collapsed into one another or implemented as Stage 0 persisted keys.

The product target retains universal collection/classification and literal
translation, AI synthesis by default, and equal EN/ZH-CN/JA policy. The final
post types are Releases & Updates, Hands-On Usage, Results and Evaluations,
Questions & Requests, Advertising & Marketing, Events & Opportunities,
Opinions & Reactions, Research & Explanations, Business & Finance, and Other.
Product labels are Bug, Complaint, Testimonial, Ideas & requests, and
Misinformation. These are documented future contracts; Stage 0 does not
change taxonomy, discourse, nationalism, schema, or visibility.

## Stage 1 classifier contract, version 1

Stage 1 returns one complete result for every already attributed brand. The
ten independent post types are Releases & Updates, Hands-On Usage, Results
and Evaluations, Questions & Requests, Advertising & Marketing, Events &
Opportunities, Opinions & Reactions, Research & Explanations, Business &
Finance, and Other. There is no primary type and no count cap. Other is an
explicit classified residual and is exclusive; it never represents invalid,
missing, pending, failed, context-missing, or historical output.

The five independent product labels are Bug (concrete malfunction), Complaint
(dissatisfaction), Testimonial (praise or endorsement), Ideas & requests
(desired capability, improvement, unmet need, or proposal), and Misinformation
(a potentially misleading claim for review, never an adjudication of falsity).
Zero or several labels are valid. A failure report asking for help can carry
Results and Evaluations, Questions & Requests, Bug, and Complaint.

Each result declares `classified` or `context_missing`, type/product arrays,
sentiment, and China/US nationalism. Classified requires a valid sentiment and
at least one type. Context-missing has no type/product edge and can retain
only independently supported scalars; unknown scalar values are null. Explicit
nationalism `none` is a supported judgment and differs from null unknown.
Malformed fields, unknown keys, missing or duplicate brand results, and an
illegal Other combination fail the transport result rather than being repaired.

The bounded input envelope has source text plus only already stored quote text
and locally persisted parent text, each with provenance. Classification never
fetches a parent, link, or media. New state stores a non-reversible fingerprint
of that envelope, versions, model, source language, outcome, and scalars; it
does not store raw prompt or context. Historical discourse rows remain
read-only. Current state owns scalar nulls; only an absent current state may
read one distinct non-null legacy value, while absent/conflicting legacy values
remain unknown and are reported as conflicts.

Reader currency is defined by the classification contract and taxonomy
versions. Prompt version is retained as provenance and does not by itself make
an otherwise compatible current state historical.

## Evaluation evidence

Fixtures marked `provenance.kind: synthetic` are deterministic transport and
normalization cases. Analyst examples retain provenance and are calibration
material, never gold labels. The 599-post audit has missing judgments; no
accuracy claim or fabricated labels may be derived from it. Held-out real-label
accuracy is deferred until prompts and contracts are frozen.
