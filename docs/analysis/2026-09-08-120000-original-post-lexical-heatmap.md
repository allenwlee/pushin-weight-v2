# Original-post corpus lexical heatmap

Generated 2026-09-08 from the authoritative corpus snapshot. Snapshot: 2026-09-08T02:07:50.27153+00:00; SHA-256: 2b84af439fcf087d8313636e8563e18313a0207a443983627ec07ad04e5dbfba. Source artifacts: `/Users/fuchitalee/development/pushin-weight-v2/.context/corpus-heatmap-20260908-vqlrFk/`. This preserves the original-post lexical analysis; the commentary-field semantic heatmap is included in a separate section below.

## Scope and method

- Census: **204,579 distinct posts**, **66,937 authors**. EN/ZH/JA slices: 142,324 / 18,071 / 16,955 posts.
- Raw post text only; commentary fields were not included. URLs/handles and configured stopwords/generic terms were filtered. Each post counts at most once per term; terms can overlap in one post. Spelling variants remain separate and their counts must not be summed.
- Weekly cells are normalized prevalence percentages within language (underlying values are per 1,000 posts divided by 10). Weeks: Jul 20, Jul 27, Aug 3, Aug 10, Aug 17, Aug 24, Aug 31, Sep 7* (*partial).
- Heat: `· <0.25%`, `░ 0.25–1%`, `▒ 1–3%`, `▓ 3–10%`, `█ ≥10%`.

## English (142,324 posts)

```text
Term                         Posts       %      A  B  C  D  E  F  G  H
api                          11,427     8.03     █  ▓  ▓  ▓  ▓  ▓  ▓  █
coding                       10,070     7.08     █  ▓  ▓  ▓  ▓  ▓  ▓  ▓
tokens                        8,798     6.18     ▓  ▓  ▓  ▓  ▓  ▓  ▓  ▓
cost                          8,749     6.15     ▓  ▓  ▓  ▓  ▓  ▓  ▓  ▓
local                         8,630     6.06     ▓  ▓  ▓  ▓  ▓  ▓  ▓  ▓
harness                       6,676     4.69     ▒  ▒  ▒  ▓  ▓  ▓  ▓  ▓
prompt                        6,103     4.29     ▓  ▓  ▓  ▓  ▓  ▓  ▓  ▓
reasoning                     5,916     4.16     ▓  ▓  ▒  ▓  ▓  ▓  ▓  ▓
inference                     5,851     4.11     ▓  ▓  ▒  ▒  ▓  ▓  ▓  ▓
pricing                       4,615     3.24     ▓  ▒  ▓  ▓  ▒  ▒  ▒  ▒
benchmark                     4,310     3.03     ▓  ▒  ▒  ▒  ▒  ▒  ▒  ▓
open-source                   3,892     2.73     ▓  ▒  ▒  ▒  ▒  ▒  ▒  ▒
open source                   3,797     2.67     ▓  ▒  ▒  ▒  ▒  ▒  ▒  ▒
open weights                  2,944     2.07     ▓  ▒  ▒  ▒  ░  ▒  ▒  ▒
frontier models               2,345     1.65     ▓  ▒  ▒  ▒  ▒  ▒  ▒  ▒
ai agents                     2,257     1.59     ▒  ░  ░  ▒  ▒  ▒  ▒  ▒
context window                1,794     1.26     ▒  ▒  ░  ░  ░  ▒  ▒  ▒
local ai                      1,437     1.01     ▒  ░  ░  ▒  ▒  ▒  ▒  ▒
api key                       1,343     0.94     ▒  ░  ░  ░  ▒  ░  ▒  ▓
coding agent                    800     0.56     ░  ░  ░  ░  ░  ░  ░  ░
video generation                784     0.55     ░  ░  ░  ░  ░  ░  ░  ▒
```

## Chinese (18,071 posts)

```text
Term                         Posts       %      A  B  C  D  E  F  G  H
开源                           2,955    16.35     █  █  █  █  █  █  █  █
成本                           2,215    12.26     █  █  █  ▓  █  █  █  █
部署                           1,356     7.50     █  ▓  ▓  ▓  ▓  ▓  ▓  ▓
工作流                           987     5.46     ▓  ▓  ▓  ▓  ▓  ▓  ▓  ▓
开源模型                         696     3.85     █  ▓  ▓  ▒  ▒  ▓  ▓  ▒
提示词                           515     2.85     ▓  ▒  ▒  ▒  ▓  ▓  ▓  ▓
智能体                           514     2.84     ▓  ▒  ▒  ▒  ▓  ▒  ▒  ▓
模型能力                         482     2.67     █  ▒  ▒  ▒  ▒  ▒  ▒  ▒
写代码                           468     2.59     ▓  ▓  ▒  ▒  ▒  ▓  ▒  ▓
工具调用                         443     2.45     ▓  ▓  ▒  ▒  ▒  ▒  ▒  ░
视频生成                         322     1.78     ▓  ▒  ▒  ░  ▒  ▒  ▓  ▒
长上下文                         259     1.43     ▓  ░  ░  ░  ▒  ▒  ▒  ▒
```

## Japanese (16,955 posts)

```text
Term                         Posts       %      A  B  C  D  E  F  G  H
動画生成                       1,264     7.46     ▒  ▒  ▓  ▓  ▓  ▓  ▓  ▓
生成AI                         1,055     6.22     ▓  ▓  ▓  ▓  ▓  ▓  ▓  ▓
検証                             959     5.66     █  ▓  ▓  ▓  ▓  ▓  ▓  ▓
トークン                         742     4.38     █  ▓  ▓  ▓  ▓  ▓  ▓  ▓
日本語                           555     3.27     ▓  ▒  ▒  ▓  ▓  ▒  ▓  ▒
AIエージェント                   459     2.71     ▓  ▓  ▒  ▒  ▒  ▒  ▒  ▒
ローカルLLM                      454     2.68     ▓  ▒  ▒  ▒  ▒  ▒  ▓  ▓
量子化                           441     2.60     ▓  ▓  ▒  ▒  ▒  ▒  ▒  ▒
ワークフロー                     430     2.54     ▒  ░  ▒  ▒  ▓  ▒  ▓  ▒
最適化                           388     2.29     ▓  ▒  ▒  ▒  ▒  ▒  ▒  ▒
オープンソース                   351     2.07     █  ▒  ▒  ▒  ▒  ▒  ▒  ▒
画像生成                         302     1.78     ▒  ░  ▒  ▒  ▒  ▒  ▒  ▒
```

## Literal phrase probes

EN: `because` 6,917; `I think` 3,088; `how to` 1,719; `according to` 939; `I tried` 634; `for example` 602; `I tested` 393; `I wish` 154; `in my experience` 106; `doesn't work` 93.

ZH: `因为` 1,177 (because); `比如` 544 (for example); `我觉得` 475 (I think); `希望` 389 (hope/wish); `我认为` 154 (I believe); `报错` 132 (error); `实测` 598 (actual testing).

JA: `と思います` 375 (I think); `と思う` 357 (I think); `試してみた` 160 (tried it); `欲しい` 132 (want); `使ってみた` 101 (used it); `例えば` 85 (for example).

These are literal document-frequency probes, not semantic labels or classifier proportions.

## Interpretation and caveats

- Practical vocabulary clusters around APIs, coding, tokens/cost, local deployment, harnesses, prompting, reasoning, inference, open weights, agents, context and generation. These are candidate subject signals, not evidence that a post is useful or defensible to repost.
- Corpus noise: Malaysian highway updates used **LLM** as a highway-authority acronym; Japanese **量子化** was concentrated in one author (25.2% of matching posts); Portuguese “gate de qualidade” appeared in 21 posts from one author.
- This is a persisted corpus snapshot, not a claim about the currently served feed. Language/collection mix, author concentration, partial final week and duplicate/syndicated material can distort prevalence.
- A commentary semantic heatmap should cluster functions such as evidence, mechanism, comparison, uncertainty, actionability, attribution and disagreement from commentary text, then validate clusters against sampled originals; it must not be inferred from lexical counts.

## Commentary-field semantic heatmap

This is a separate semantic analysis of commentary fields, not a keyword count. Canonical artifacts: `/Users/fuchitalee/development/pushin-weight-v2/.context/commentary-semantic-20260908-XFga3U/`. Commentary snapshot: **2026-09-08T02:41:18.861299+00:00**, SHA-256 **4d529df33b699fc9f5db9bed62781d5ac578bb7ade8bfdced223f46d822580ff**. The read-only commentary snapshot has **42,266 available English commentaries** (plus 4,965 Chinese-only records excluded from this English semantic coding); the directly coded sample is **500 records from 477 authors**. English commentaries describe originals in multiple languages; paired EN/ZH fields were not doubled.

Method: each complete English commentary in a deterministic 500-record sample was read and assigned one dominant communicative function using the codebook. A 5,000-post exploratory embedding pass informed the codebook but was not directly labeled and must not be interpreted as semantic-function frequencies. Clustering diagnostics were weak (silhouette **0.0319**, alternate-seed ARI **0.4234**), so this is **single-LLM-analyst coding**, not a validated classifier, human annotation, second-coder agreement, or a claim about original-post truth, sincerity, or verified evidence.

```text
Function                                      n/500   Heat (coarse; ~1 percentage point/block)
Endorses/recommends/prefers/switches             62   ████████████  12.4%
Argues/challenges/corrects/interprets            60   ████████████  12.0%
Method/mechanism/setup                           59   ███████████   11.8%
Test/comparison/measured outcome                 53   ██████████    10.6%
Marketing/offer/paid attention                   46   █████████      9.2%
Joke/reaction/thanks/social                      38   ███████        7.6%
Release/update/availability                      34   ██████         6.8%
Question/practical help                          30   ██████         6.0%
Friction/disappointment/failure                 28   █████          5.6%
Shows made/accomplished                          27   █████          5.4%
Corporate/market/financial development           15   ███            3.0%
Anticipation/speculation/plan to try             15   ███            3.0%
Curates news/links/reading                       12   ██             2.4%
Other/insufficiently specified                   11   ██             2.2%
Requests/proposes capability                      6   █              1.2%
Invites participation/collaboration               4   █              0.8%
```

The numeric percentages are authoritative and exact within the 500 coded records; bars are coarse visual approximations of roughly one percentage point per block. These are sampling estimates for the 42,266-record English-commentary population, not percentages of the original-post lexical snapshot (204,579 posts) or the later commentary snapshot's 204,615 all-post rows. The primary-function convention forces the displayed categories to sum to 100%, although commentary can contain multiple functions.

Reader-facing examples are paraphrased function templates, not exact recurring phrases: “I recommend/switch to this” (endorsement); “the important distinction is…” (argument); “run it with this setup” (method); “I tested it and observed…” (evaluation); “free credits/subscribe here” (marketing); “lol/thanks” (social); “version X is now available” (release); “how do I…?” (question); “the output fails/latency is unacceptable” (friction); “I built this” (showcase); “the lab raised funding” (business); “I expect the next release…” (anticipation); “roundup/read this thread” (curation); “please add capability Y” (idea); and “join/help benchmark” (collaboration).

The 11 `Other` cases were retained rather than forced into a category. They included off-topic Malaysian highway advisories where LLM means the highway authority, hashtag-only/link-only posts, opaque or conspiratorial posts, unrelated Turkish finance, and spam. This reinforces that semantic coding describes commentary function and collection noise; it does not independently verify the underlying post or claim.
