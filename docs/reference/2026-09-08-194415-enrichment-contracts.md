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
`classifier`, `relevancy`, and `headline`. Metadata contains no keys, prompts,
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

## Evaluation evidence

Fixtures marked `provenance.kind: synthetic` are deterministic transport and
normalization cases. Analyst examples retain provenance and are calibration
material, never gold labels. The 599-post audit has missing judgments; no
accuracy claim or fabricated labels may be derived from it. Held-out real-label
accuracy is deferred until prompts and contracts are frozen.
