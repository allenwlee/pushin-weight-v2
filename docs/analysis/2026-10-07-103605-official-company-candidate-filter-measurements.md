# Official-company candidate filter measurements

Observed on 2026-10-07 against production revision `b13b38b5ff6df06d27531a6665449950e0685355`. This is read-only research. Official-company extraction remains paused; normal harvesting is active. No discovery model or X data calls were made for this study.

The comparison population is the original **91,028 accounts**, frozen by `Account.first_seen_at <= official-company-initial-v1.started_at` (`2026-10-07T01:00:48.600571Z`). There is no post-age cutoff. Measurements describe stored evidence, not complete X timelines or verified real-time badges.

## Settled examples

These accounts are already owner verified; this study does not nominate or reclassify them.

| Account | Stored authored posts | Business badge | Nested bio | Expanded profile website |
| --- | ---: | --- | --- | --- |
| Reflection | 1 | Yes; flat verified/blue booleans are false | Make intelligence open and accessible to all | reflection.ai |
| Aleph Alpha | 1 | No | We create specialized large language models for a sovereign Europe | aleph-alpha.com |
| Bad Theory Labs | 8 | No | making intelligence efficient enough to own | badtheorylabs.com |

Flat `Account.bio`, `Account.description`, and `Post.author_description` are empty for these examples. `Account.profile_bio_text` and nested `Post.author_profile_bio.description` preserve the descriptions. Expanded website URLs live under `author_profile_bio.entities.url.urls[].expanded_url`. Checking only the flat empty fields produces incorrect conclusions.

## Individual filter measurements

Counts overlap; do not add these rows.

| Filter | Accounts retained | Settled examples retained |
| --- | ---: | ---: |
| At least two stored authored posts | 36,384 | 1/3 |
| Gold/business badge alone | 733 | 1/3 |
| AI/model-related bio and external profile website | 9,855 | 3/3 |
| Development language in AI/model-related bio and external profile website | 3,084 | 3/3 |
| AI/model-related bio and website whose name resembles account handle/name | 4,707 | 3/3 |
| AI/model-related evidence; at least 100 followers and follower/following ratio >=20 | 5,405 | 3/3 |
| Model-related release/availability wording in an authored post | 15,443 | 1/3 |
| AI/model-related evidence and organization-style account name | 2,953 | 2/3 |

The owner's binding rule is **gold badge alone admits to evaluation and gets highest queue priority**. Identify it using `verified_type = Business`, not verified/blue booleans. It does not establish AI model development or authorize automatic registration/list addition. Gold is optional for other entrances.

Requiring two stored posts misses Reflection and Aleph Alpha. Name-only and release-only gates also miss positives. Post counts and follower ratios can rank candidates; neither is a universal eligibility requirement. Do not impose follower minimums on gold or profile/development entrances.

## Proposed ordered candidate set

1. **Gold/business badge:** 733 accounts, with no additional requirement.
2. **AI/model-related bio + development language + external profile website:** 3,022 additional accounts after excluding tier 1. First two tiers total **3,755** and retain all three settled examples.
3. **AI/model-related bio + external website + organization-name or domain-name match**, OR **model-release wording + organization-style account name:** 3,955 additional accounts after excluding tiers 1–2.

Combined: **7,710 candidates**, a **91.53% reduction** in accounts receiving model evaluation. All three examples are retained without ID allowlisting in the filter. The 733 gold accounts must stay ahead of the other tiers. The remaining 83,318 are deferred outside the proposed candidate set, not declared non-companies or deleted. Only the gold entrance/priority is explicitly settled; the other tiers are a measured recommendation pending further discussion/implementation. Existing settled official mappings and owner attestations should be reused, not discarded or charged for rediscovery.

A more inclusive variant allowing any AI-related bio with external website, and model-release posts from high follower/following-ratio accounts, retains **12,332**. Adding the follower-ratio release entrance to the stronger set retains **9,098**. These are alternative tradeoffs, not cumulative totals.

## Precision and coverage limits

Three positives demonstrate that those three survive; they cannot establish exhaustive discovery or precision. Yann LeCun's personal account survives the organization/domain alternative: it describes AI research, links to a personal website and mentions lab leadership. This is a concrete reason the subsequent evaluator must distinguish company accounts from staff, founders, reporters, enthusiasts and model users. Do not automatically reject every bio mentioning a founder or engineer: an organization's bio can refer to its team. Do not treat URLs or gold as sufficient evidence to add an account to Call A.

Gold admission retains Luma Labs and MiniMax even when their stored bio lacks these AI terms. Runway, Cohere and Mistral also survive the combined proposal. Stored OpenAI/Anthropic rows have insufficient fetched author evidence in this dataset and do not pass these heuristics; current settled mappings should therefore bypass rediscovery. Missing metadata is not evidence of ineligibility. Badge-free labs with sparse, multilingual or unusual wording may fall outside these candidate sets; add genuine held-out examples and inspect borderline/nonmatching records before claiming broad coverage.

The draft token families cover AI, LLM, models, intelligence, inference, weights, diffusion, robotics, embedding, generative, neural and several Chinese/Japanese equivalents. Development terms include we/our/build/create/make/develop and equivalents; release terms include introducing/announce/launch/release/available/open-source/weights/model-card/download plus model technical terms. These are starter patterns, not a complete language or model-type taxonomy. Non-LLM, closed and pre-release model developers remain eligible. No Hugging Face presence is required.

An external website means a profile expanded URL outside a heuristic social/link-hosting exclusion list. Domain resemblance strips punctuation and compares handle/display name with host-name text. Neither verifies website ownership; personal sites can match. Historical profiles can contain stale identity, so final evaluation must preserve observation dates and inspect contradictions.

## Method and evidence

A repeatable-read, explicitly read-only transaction collected the frozen account population and scanned **300,060 posts with a non-null author** through a bounded database cursor, evaluating text locally to avoid repeated expensive regular-expression work on production. It read 191,526,997 bytes of public post/profile text; account-level features and counts, rather than full post bodies, were saved. A subsequent read-only replay examined **95,486 distinct author/profile pairs**, decoded raw SQL JSON values explicitly, and replaced the preliminary domain metrics. The initial combined SQL-regex aggregate hit its 45-second statement timeout and made no writes; its preliminary domain-zero output is invalid and is not used in this report. Post/count features and profile replay were separate snapshots while ordinary harvesting remained active, so this is not a single simultaneous full-database snapshot.

Machine evidence and reproducible operator scripts remain untracked under `.context/official-co-execution/`: `candidate-filter-research.json`, `candidate-filter-features.json`, `candidate_filter_research.py`, and `profile_filter_replay.py`. They are derived database evidence, not raw provider exports. IDs remain strings. No credentials, provider headers or tokens are saved.

## Pause observation

One-off full scan job `job-db2pk1gm7kps73br6bm0` was canceled at 01:25:54UTC. Harvest environment deploy `dep-db2pv967bikc73aid7sg` is LIVE at the same b13 revision; all three official-company enable/registration/list-sync flags are false. Normal harvest remains `not_suspended`.

Durable initial enumeration stopped at **14,001/91,028**; total state rows include **14,017 pending**, four no-evidence, one registered, one review-needed and one rejected. The scheduled lane completed two paid model decisions (combined actual USD 0.00027198) and one zero-cost owner attestation before pause. Aleph Alpha was registered and its actual Call A addition acknowledged and confirmed at 01:23:13UTC. No full-coverage outcome is claimed; queue/cursors, evidence, credentials, existing additions and /admin remain preserved. No automatic restart is authorized by this research.
