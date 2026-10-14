---
title: Tracked-brand family register for release verification
date: 2026-10-12
status: draft-family-register
session: g3-round2-20261009
execution: read-only-evidence-and-planning
---

# Tracked-brand family register for release verification

The owner selects a practical starting point: **21 tracked brands → current
product families → release verification**. MiniMax M, Z's GLM and DeepSeek V4
are the first seeds. This replaces a universal all-data release-detector starting
scope. The family register defines where to look and what identities need
review; it does not automatically confirm a launch.

[Machine-readable register](2026-10-12-091100-g3-tracked-brand-family-register.json)
holds the observed catalog examples, source-qualified official accounts,
confirmed/unconfirmed publisher namespaces, primary checks and draft event
fields. Its entries are **candidate product lines**, not a certified complete
or current active lineup. Primary identity support was checked for the three
owner seeds; most other entries still need publisher review.

## What exists now

Read-only production observations on October 12:

- **21 tracked brands**, with **1,578 directly brand-linked Product rows**.
  All selected rows fit the 3,000-row read ceiling. These are repositories/
  products, not independent releases. Unassigned Products and Products linked
  to other brands are outside this selected count.
- **No populated ProductGroup records** in the inspected database. The schema
  supports groups and memberships; no competing runtime catalog was created.
- The fresh release read observes **159 extracted release records**, rather
  than the October 11 audit's dated 155. A bounded supporting packet contains
  14 records and 15 evidence rows for MiniMax preview, GLM 5.3 and Mistral Large 4.
- Official account seeds were read again with an explicit source qualifier.
  HF namespaces and X handles share the Account table and must not be confused.

Products/catalog observations are at 00:14:18 UTC; role observations are at
00:16:38 UTC; the supporting release packet is at 00:12:06 UTC. These are
separate observations, not a single database snapshot. No database write,
classification/model call, paid X batch, backfill or deployment occurred.

## Initial register

The stored official X roles are source lookup seeds, not proof that every
account represents every product line or that every post is an announcement.
Confirmed HF publisher ownership does not make every hosted derivative an
original model by that publisher. Counts do not measure active lineup size.

| Tracked brand | Candidate product lines to review | Stored Products | Stored official X account seeds |
| --- | --- | ---: | --- |
| minimax | M text, H video, Music | 21 | @Hailuo_AI, @MiniMaxAgent, @MiniMax_AI |
| qwen | Qwen text, Qwen Coder, Qwen VL, Qwen Image | 468 | @Ali_TongyiLab, @Alibaba_Qwen, @Alibaba_Wan |
| deepseek | V4 / V4.1 text and multimodal | 105 | @deepseek_ai |
| glm | GLM text and multimodal | 61 | @Zai_org, @ZhihuFrontier |
| mimo | MiMo V | 28 | @Xiaomi, @XiaomiMiMo, @XiaomiMiMoDevs |
| moonshot_kimi | Kimi K, Kimi Linear | 19 | @Kimi_Moonshot |
| inclusionai | Ling, Ring, Ming | 212 | @AntLingAGI, @TheInclusionAI, @robbyant_brain |
| mistral | Large, Medium, Small, Codestral, Magistral, Ministral, Voxtral | 75 | @MistralAI |
| stepfun | Step, Step Audio, Step Video | 45 | @StepFun_ai, @stepfunai |
| ernie | ERNIE text, ERNIE Image | 30 | @ErnieforDevs, @PaddlePaddle |
| hunyuan | Hunyuan / Hy text, Hunyuan Image, Hunyuan Video, Hunyuan 3D / World | 160 | @TencentHunyuan |
| llama | Llama, Llama Guard / Prompt Guard | 70 | @AIatMeta |
| nemo_megatron | Nemotron | 100 | @NVIDIAAI, @NVIDIAAIDev, @NVIDIARTXSpark, @nvidia |
| doubao | Doubao / Seed: primary lineup check required | 0 | @BytePlusGlobal, @bytedanceoss, @doubaoAi |
| yi | Yi, Yi Coder, Yi VL | 28 | @01AI_Yi |
| sensechat | SenseChat / SenseNova: primary lineup check required | 0 | @SenseTime_AI |
| exaone | EXAONE, K-EXAONE | 50 | @LG_AI_Research |
| kuaishou | KAT, HiPO, KwaiYii / Kling: primary lineup check required | 14 | @Kling_ai |
| sakana_ai | TinySwallow, Additional research model lines: review required | 49 | @SakanaAILabs |
| upstage | Solar / Solar Pro / Solar Open | 26 | @upstageai |
| dots | dots note, dots OCR, dots TTS, dots LLM / VLM | 17 | @dotsstudioai |

A missing Product catalog is not absence of a model family: Doubao and SenseChat
need their official website/API lineup checked. Broad publishers such as NVIDIA,
Tencent and inclusionAI need origin/derivative separation. Catalog repositories
include quantizations, tokenizers, experiments and republished models.

## Three starting families and primary evidence

| Owner seed | Primary check | What it establishes | Still needed |
| --- | --- | --- | --- |
| MiniMax M | [Official M Plan](https://www.minimax.io/m-plan) | Publisher advertises M3.1 Flash Preview access | Exact announcement anchor/date, previous M generations and preview/API/weight milestones |
| GLM | [Publisher model card](https://huggingface.co/zai-org/GLM-5.3-Flash) | GLM-5.3-Flash identity in the GLM-5 series | Announcement timing, predecessor and sibling/BF16 relationships |
| DeepSeek V4 | [Official change log](https://api-docs.deepseek.com/updates/) | Dated API release/update milestones and changing API aliases | Match exact builds/milestones to our Posts, Products and mappings |

The model card links [GLM's release blog](https://z.ai/blog/glm-5.3-flash), but this
reader returned no blog text. Its URL alone is not a verified release date.
MiniMax's present access page also does not establish an original launch date.
No model files/weights were downloaded.

DeepSeek supplies a useful first expected-event list, with **day precision**:

| Publisher date | Milestone |
| --- | --- |
| 2026-04-24 | V4-Pro and V4-Flash API availability |
| 2026-07-31 | V4-Flash public-beta/post-training update |
| 2026-08-13 | V4-Pro general availability |
| 2026-08-21 | V4-Flash-Vision-Exp API availability |
| 2026-09-10 | V4.1-Flash API release |

These are publisher-dated milestones, not five independent model generations.
Exact instants/timezones remain unverified. The same change log says legacy
Flash aliases route to V4.1-Flash: a continuing API name is not proof of a fixed
historical model. This fact does not change PushinWeight's pinned third-party
classifier route. [Source](https://api-docs.deepseek.com/updates/).

## How one family becomes a usable release history

Use the same small record shape for the three seeds, then the other brands:

1. **Brand and line:** MiniMax → M; GLM → GLM; DeepSeek → V4/V4.1 scope.
2. **Generation and exact variant:** M3.1 / Flash; GLM5.3 / Flash;
   DeepSeekV4.1 / Flash. Keep official spelling, exact repo/API identifiers,
   observed aliases, source and review state.
3. **Milestone:** announcement, preview availability, general/API availability,
   weight publication or a supported model/build update. Availability on an
   unrelated reseller or a price/feature change is not automatically a new
   underlying model.
4. **Evidence and time:** original official source, credible first-known report,
   source-stated precision, exact source-post time where available and actual
   local observation/review times. Unknown values stay unknown.
5. **Capture check:** was the announcement collected, correctly linked to the
   model/family and assigned the right event kind? Keep missing, incorrect,
   duplicate and unresolved outcomes separate.

A preview and later weight publication can have separate chart markers while
belonging to one launch group. FP8/BF16/GGUF packages and multiple recap Posts
must not silently inflate independent-launch counts. Whether a substantive
variant/build is its own event depends on publisher evidence and the defined
outcome; the family register is not a blanket rule to collapse everything.

Names are curated review inputs, not universal regex guesses. In particular,
the M text line requires a numeric generation: a loose “MiniMax-M” prefix can
also match Music. Publisher namespaces can contain foreign-model quantizations,
so namespace/name matching alone is insufficient.

## What the supporting packet already shows

- MiniMax has four same-named M3.1-Flash-Preview rows with different version
  representations, plus one abbreviated M3.1-Flash beta row. They are candidates
  for source-backed grouping, not five independent launches. Several sources
  quote the same announcement text. Quote context must lead back to the original
  account/Post rather than being treated as independent confirmation.
- GLM candidate **64** is supported by a Post announcing Rogue DeepThink Preview
  built on GLM5.3. That source does not by itself announce a new GLM5.3 release.
  The family map lets us distinguish the underlying model from a third-party
  product using it.
- Mistral Large4/“Large4” appears across eight rows with other/preview/stable
  channels and mostly unknown dates. The source packet describes API preview
  separately from planned later weights. Treat these as review cases until
  primary milestone/date evidence resolves them.
- All 15 selected evidence rows have top-level authors that fail the current
  matching official-role query. Some retain quoted announcement context. This
  does not mean official announcements are absent from the overall corpus.

These are scoped source-reading findings, not a measured full-corpus classifier
error rate or a completed recall study. No existing release was marked confirmed,
merged or rejected in production.

The current extractor also explains a duplicate mechanism worth checking later:
when a version is missing, its release identity hash includes the source URL;
version spelling and channel also enter the hash. Separate Posts can therefore
produce separate candidate records. That is a code finding, not authority to
merge rows without evidence.

## Next bounded verification unit

The first unit should fully establish one generation/variant event list and
its immediate predecessors for M, GLM and DeepSeek V4, using explicit primary
sources. This allows a concrete comparison of expected releases against
collection, exact model linking, event category, time precision and grouping.
Dates, formats and retired API aliases remain source-specific.

Then apply that record/check shape to the remaining tracked brands. Do not
require a single naming convention or an open HF repository from every vendor.
Unlisted or newly named models go to review rather than being assumed false or
assigned an invented family.

Reuse existing Product/ProductGroup relationships and ModelRelease/Evidence.
The JSON is a review artifact, not a second production source of truth.
Runtime storage/integration and historical recovery belong to later concrete
work; apply family-specific windows when repairing announcement and full
discussion coverage. The original chart/audit/learning priority remains.

## Evidence and limits

Ignored receipts: `.context/g3-release-pilot-20261012-091100/` contains bounded
read-only SQL, raw/parsed results, catalog summaries, source-qualified roles and
saved web results. Five web tool results cover six targeted queries, primary
opening/finding and one linked blog check; search pages that happened to expose
weight-file links were not downloaded. Primary checks here are narrow seed
identity/milestone checks, not an external review of every line in the table.

This register uses G3 at `7c426c3a4d76630b17243ac5b8a3451d77efab74`, with existing
dirty application changes preserved. The same
[G3 plan](../plans/2026-10-09-063417-feat-g3-round2-chart-engine-plan.md) records the
owner's route and next unit. Its retained library/forecast research does not
verify these releases. Numerical reconciliation, 21-brand scope, source
qualification, links, JSON and whitespace were checked; no application tests
were run for this read-only/document task.

