# Post commentary

PushinWeight generates analyst commentary separately from literal translation.
The commentary explains what a post means and what the visible evidence
establishes; it is not a translation, classification label, or broad trend
interpretation. Literal translation is documented in
[`translator-output.md`](translator-output.md). Both use the shared artifact
storage and read lifecycle in
[`post-content-artifacts.md`](post-content-artifacts.md).

## Input and output

The synthesis context has three separately attributed strings: the author's
post (`source`), a stored quoted post (`stored_quote`), and a locally available
parent post (`local_parent`). Missing context is empty. Source strings are
untrusted data, never instructions. Provenance records distinguish the source,
quoted post, and parent post.

The model returns commentary for the same post in English, Simplified Chinese,
and Japanese, plus the exact post identifier. Each locale must be nonempty and
distinct from the others. The active tagged-text prompt requires one short
line per locale, in the fixed order EN, ZH-CN, JA. The explanation should use
only supplied evidence, preserve attribution and uncertainty, and avoid
inventing identity, intent, background, or wider market significance. It may
omit secondary details but must not change the claims.

The parser checks the exact post identifier, field order and boundaries,
nonempty locale values, and locale duplication. A malformed, partial, or
identity-mismatched response is rejected. Provider response bodies are not
part of the public read contract.

## Artifact and demand behavior

Successful synthesis is stored as an immutable locale-complete artifact tied
to its source-context fingerprint, prompt version, model, and output schema
version. A changed post, quote, or available parent context produces a
different artifact identity. Failed attempts are recorded safely and do not
replace the current successful artifact. Legacy commentary columns are
compatibility projections, not the normalized source of truth.

Readers create bounded demand records rather than waiting for a provider call
inside the page request. Demand is deduplicated by post, context fingerprint,
prompt version, model, and schema. Repeated demand can raise priority; expired
work is cancelled. A worker leases due requests, reserves configured daily
capacity, makes the provider call, and publishes the result only if the lease
still owns the work. These boundaries prevent duplicate work and stale workers
from overwriting newer results.

The PostgreSQL-backed worker runs `python manage.py run_synthesis_worker` as a
separate Render worker. It is not a scheduler, does not harvest posts, and
does not use Twitter credentials or the headline queue. Provider calls and
activation are controlled independently through synthesis configuration.
The configured production worker uses DeepInfra's OpenAI-compatible endpoint
with `google/gemma-4-31B-it-turbo`, tagged-text output, and a versioned prompt;
the active settings are in `config.yaml` and `render.yaml`.

## Source map

| Responsibility | Source |
| --- | --- |
| Prompt, provider call, response validation | `x_monitor/synthesis.py` |
| Context assembly and durable demand/worker | `monitor/post_synthesis.py` |
| Artifact fingerprints, publication, and reads | `monitor/post_artifacts.py` |
| Artifact and demand schema | `core/models.py` and ordered migrations |
| Runtime limits and model settings | `config.yaml` |
| Production worker declaration | `render.yaml` |
| Shared user-facing artifact behavior | [`post-content-artifacts.md`](post-content-artifacts.md) |
