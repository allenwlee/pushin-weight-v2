# R97 provider terms and data-use receipt

**Observed at:** 2026-09-14 18:46:50 JST (+09:00)
**Scope:** OpenRouter routing and provider-policy metadata; DeepInfra,
Google Gemini API, and GMICloud terms/privacy.
**Status:** Research receipt only. No inference endpoint was called. No
secrets, owner materials, database-only personal data, or private source data
were inspected.

## Frozen packet boundary

The candidate packet covered by this receipt is **public-X-only**: content
already public on X and the minimum derived fields needed for the Stage 1
classification task. The packet must exclude all of the following:

- owner answers or owner reference material;
- private comments, private messages, or other non-public conversation;
- API keys, credentials, cookies, tokens, or any other secrets; and
- personal data available only in the database rather than in the public X
  post (including account or operational metadata not present in that post).

“Permitted” below means permitted for this frozen packet under these
operational exclusions. It is not a legal opinion about a provider’s complete
terms or about other packet contents.

## OpenRouter controls and live provider table

OpenRouter says that its own prompt/completion retention is opt-in. With the
default settings it stores request metadata (for example, token counts and
latency), not prompt or response content. Its anonymous categorization samples
are detached from the account when the user has not opted into OpenRouter use
of inputs/outputs. See [OpenRouter Data Collection](https://openrouter.ai/docs/guides/privacy/data-collection).

The request-level `provider.data_collection` setting controls whether providers
that may store data can be used; `deny` filters those providers and `allow`
permits them. The request-level `provider.zdr: true` restricts routing to
endpoints OpenRouter marks Zero Data Retention (ZDR). See [Provider
Routing](https://openrouter.ai/docs/guides/routing/provider-selection) and
[Zero Data Retention](https://openrouter.ai/docs/guides/features/zdr). ZDR is
endpoint-specific: OpenRouter says that an unclear policy is conservatively
treated as retaining and training, and a provider’s general policy can differ
from a particular endpoint.

The live [OpenRouter provider-policy feed](https://openrouter.ai/api/frontend/v1/all-providers)
observed at the timestamp above reported:

| Provider | OpenRouter `dataPolicy` observed | Routing implication |
| --- | --- | --- |
| DeepInfra | `training=false`, `retainsPrompts=false` | compatible with `data_collection=deny`; ZDR endpoints are present in the [live ZDR endpoint feed](https://openrouter.ai/api/v1/endpoints/zdr) |
| Google Vertex | `training=false`, `retainsPrompts=false` | paid/Vertex path can satisfy a stricter policy, subject to the selected endpoint |
| Google AI Studio | `training=false`, `retainsPrompts=true`, `retentionDays=55` | free/AI Studio path requires `data_collection=allow`; `zdr=false` |
| GMICloud | `training=false`, `retainsPrompts=true`, no `retentionDays` field | use `data_collection=allow` to match the table’s retaining status; `zdr=false` |

The Google row is a useful warning rather than a substitute for Google’s
terms: Google’s current unpaid-service terms allow content use and human
review, as described below. The GMICloud row similarly governs the OpenRouter
route even where GMICloud’s own public pages describe a narrower prompt-
logging setting.

## Provider findings and decisions

### DeepInfra

DeepInfra’s [Data Privacy documentation](https://docs.deepinfra.com/account/data-privacy)
(page metadata observed with `dateModified` 2026-02-20) says ordinary
inference input exists only in memory while a request is processed, output is
deleted after it is returned, and DeepInfra does not train on submitted API
data. It documents exceptions: image-generation outputs can be held briefly;
Google and Anthropic model calls follow the receiving company’s policy; and
bulk inference may use encrypted disk storage for a short period before
deletion. Its [Privacy Policy](https://deepinfra.com/privacy) also says inputs
and outputs are not stored, sold, or used for training without explicit
consent, while account/personal information can be retained for service or
legal purposes.

The stronger [DeepInfra Terms of Service](https://deepinfra.com/terms),
section 7(b), defines a ZDR commitment for Customer Data: no sale, training,
fine-tuning, improvement use, or retention beyond processing and returning the
request, followed by deletion in the ordinary course. Exceptions include
written support retention (deleted within 30 days after resolution), non-
content operational metadata, and records needed for law, fraud, security, or
abuse. The terms also permit subcontractors, with DeepInfra remaining
responsible for them.

**Decision:** `data_collection=deny`, `zdr=true`. The frozen public-X-only
packet is permitted for the ordinary inference path, subject to the packet
exclusions above. Do not use bulk inference, image generation, or a Google or
Anthropic model when this decision is intended to preserve the DeepInfra
ZDR/data-use boundary.

### Google Gemini API, unpaid/free service

The current [Gemini API Additional Terms of Service](https://ai.google.dev/gemini-api/terms)
are effective **2026-03-23**. They define unpaid services to include direct
Google AI Studio use and unpaid Gemini API quota. For unpaid services, Google
may use submitted content and generated responses to provide, improve, and
develop Google products, services, and machine-learning technologies. Human
reviewers may read, annotate, and process API input and output. The terms
specifically say not to submit sensitive, confidential, or personal
information. The content license extends to prompts, system instructions,
cached content, files, and generated responses. The terms do not promise ZDR
for unpaid use.

Google’s [Gemini logging policy](https://ai.google.dev/gemini-api/docs/logs-policy)
says project logs have a default maximum retention of 55 days (configurable to
7, 14, 28, or 55 days), while datasets can retain selected logs longer. This
is consistent with OpenRouter’s 55-day `retentionDays` value for Google AI
Studio, but it does not turn unpaid use into a ZDR service.

**Decision:** `data_collection=allow`, `zdr=false`, and **free Google is
permitted only for the public-X-only packet**. The required allow policy is
deliberate: it acknowledges Google’s possible retention, downstream quality
review, and product/model improvement use. The packet must contain no
sensitive, confidential, private, or DB-only personal fields. Paid Google
Vertex is a separate policy choice; this receipt does not approve silently
switching the free route to paid or Vertex.

### GMICloud

The current [GMICloud Privacy Policy](https://www.gmicloud.ai/en/legal/privacy)
is marked **Effective Date: February 26, 2025 (Last Updated)**. It says GMI
Cloud collects API usage logs and technical metadata (including IP address,
timestamps, and usage metrics), uses logs for reliability, troubleshooting,
security, analytics, and service improvement, and may share data with service
providers. Its retention section says active-account information, settings,
and usage logs are retained as needed; after cancellation, content and
personal information are scheduled for removal, but no fixed interval is
given. It allows retention for legal, billing, fraud, security, or dispute
purposes and says backups are time-limited without stating the duration.

GMICloud’s [Console Terms of Service](https://www.gmicloud.ai/en/legal/console-terms-of-service)
(effective 2026-07-07) says some underlying AI models may store or train on
inputs under their own model terms. It also says prompt logging is an account
opt-in and, absent that opt-in, the company does not store inputs after
categorization. This page does not provide a fixed retention period for
OpenRouter-routed prompts and leaves underlying model terms in control.

**Decision:** `data_collection=allow`, `zdr=false`, and the frozen public-X-
only packet is permitted. `allow` is required to match OpenRouter’s live
`retainsPrompts=true` status; `zdr=false` records that no ZDR guarantee was
established. Do not infer a fixed GMICloud prompt-retention period from its
public policy. Exclude private, sensitive, secret, and DB-only personal data
even though the packet is public-X-only.

## Limitations and re-check triggers

This receipt records policy pages and OpenRouter’s live metadata at one
observation time. Provider policies, endpoint assignments, retention fields,
and model-specific terms can change. OpenRouter’s provider feed and endpoint
feed are operational metadata, not a contract with the provider. GMICloud’s
public pages are internally incomplete on inference retention, and its
OpenRouter metadata is more conservative than the prompt-logging language in
its Console Terms; the routing decision therefore follows OpenRouter’s
retaining status. Google’s unpaid terms are explicit about training/review but
do not state a universal fixed prompt-retention period. Re-check the feeds and
linked provider terms before changing a candidate packet or routing policy.
