---
title: "General round two — G1–G5 scope and carry-forward register"
created_at: "2026-10-09T11:01:45+09:00"
status: open-for-planning
round: 2
proposed_version: "0.2.0b2"
predecessor: docs/analysis/2026-10-09-110145-general-round-one-closeout.md
---

# General round two — G1–G5 scope and carry-forward register

## Plain-English Summary

Round two starts with the useful work already completed and the unfinished
requirements accepted by the owner. G1 handles assets, G2 editorial choices and
voices, G3 charts and inherited analysis, G4 sharing and inherited API work, and
G5 the General experience. Keep these five labels for concurrent sessions.

The [round-one closeout](../analysis/2026-10-09-110145-general-round-one-closeout.md)
preserves earlier outcomes. This document is the fresh scope/ownership register;
the [charter](2026-09-30-104924-general-launch-charter.md) still holds detailed
owner requirements. The proposed next beta is `0.2.0b2`, tagged
`v0.2.0-beta.2`; no version has been changed by this record.

## How the rollover works

- Round one is **closed with carry-forward** as an owner decision. Completed
  receipts, research, local code and unresolved checkboxes remain intact.
- Every unmet, non-superseded owner requirement in the prior charter/plans
  transfers to the corresponding round-two stream. The rows below group that
  work; they do not discard an unlisted detail. Prior proposals stay proposals,
  and previously excluded or waived work does not become required again.
- A carry-forward row means **accepted into round-two planning**, not already
  implemented. Implementation sequencing and the bounded beta release scope
  belong to the next stream plans. No new deadline or paid allowance is inferred.
- Use IDs `B2-G1-01` etc. Keep the original requirement/unit IDs as provenance.
  Avoid `G1-R2`: existing requirement IDs and Cloudflare R2 already use that form.
- Existing root index/charter remain the shared entry points. New session claims
  identify **round 2**, G item, bounded files and current plan. New detailed
  execution logs belong in the round-two plan, not appended to the closed plan.
- On selecting an implementation plan, follow Ollija in the intended branch/
  worktree and use its returned path. Reuse existing code/context, preserve dirty
  work, and avoid selecting a closed round-one plan as a fresh execution target.
  This register is coordination, not a parallel implementation plan.

## G1 — Assets and graphicsed

**Starting assets:** delivered staff identity/media foundation and shared R2;
saved DeepSeek/MiniMax research and explicit coverage gaps.

| ID | Origin | Round-two work | State |
| --- | --- | --- | --- |
| B2-G1-01 | New owner priorities; G1-R04; existing G2 picture editor | Every content item receives image/video. Apply relevant-person picture → source author profile picture → company logo; record why the asset fits. Resolve multiple authors and all-fallbacks-missing cases. | **Owner-assigned October12:** requirements/guide now owned by retained `g2-round2-20261009` session in existing `.worktrees/feat/g2-editorial`; actual module editing ownership must be checked before implementation. G1 staff/acquisition/storage work preserved. No implementation/paid-generation/release claim |
| B2-G1-02 | New graphicsed guide; G2-R48 picture modularity | Selection/creation/treatment guidance, reuse/caching, attribution and delivery/export variants. Explicitly hand off G2-owned picture/media files before changes; coordinate with G4 exports and G5 presentation. | **Owner-assigned October12:** requirements/guide now owned by retained `g2-round2-20261009` session in existing `.worktrees/feat/g2-editorial`; actual module editing ownership must be checked before implementation. G1 staff/acquisition/storage work preserved. No implementation/paid-generation/release claim |
| B2-G1-03 | Unfinished G1 identity/acquisition scope and saved dossiers | Remaining portraits, names/roles and wrong-company corrections; remaining selected brands and broader Call A/database staff population; ongoing acquisition/worker activation, budget and coverage decisions. Review/import saved research only within its actual evidence and authority. | Carried forward |

**Apply round-one lessons:** named-block image attribution, separate people/file/
portrait counts, and real consumer access to shared media. An author avatar
fallback does not imply the depicted subject has been identity-verified.

### October 12 graphics-editor ownership

The owner selects B2-G1-01/02 for the retained G2 session, while working on
Pulse/chart decisions in G3. Use the existing G2 worktree/plan and preserve its
locked writing choices and local evidence; no handoff swap is needed. G1's
active roster/orientation claim remains in place for identity/acquisition and
shared foundation. This session owns graphics-editor requirements and guide,
with module-level editing coordination before code changes. Read both existing
handoffs for their factual asset/storage/context boundaries. The October9
“ready to plan” statements below are historical, superseded for B2-G1-01/02.

**Selected default-image direction:** portrait + brand logo + small bilingual name/role inscription; the subject adopts the current meme, with playful and generous treatment. One variant splits portrait-left/logo-right50/50 with an airbrushed transition and a small PushinWeight watermark. First Yan Junjie/MiniMax camouflage-T-shirt image and prompt/record are [saved in the retained G2 worktree](../analysis/2026-10-12-112151-g2-graphics-editor/README.md). One built-in imagegen call, no repairs; actual sourced portrait/logo references,1536×1024 PNG, visual/English-OCR/browser byte checks. Chinese name checked visually. Generated illustration does not replace verified staff photographs; no staff/runtime/release changes.

**Compact companion requested:** owner approves wide graphic and requests face+brand only for a small betting-post thumbnail. Enlarged logo overlaps the face edge, with softened blending and partial logo visibility acceptable. [400×400 PNG and actual48/64/80px square/circle preview](../analysis/2026-10-12-112151-g2-graphics-editor/compact.html) delivered:one further built-in imagegen edit, zero repairs;12browser cases and visual small-size checks pass. Original landscape preserved; no application/betting feature or release change.

### G1 session-clear handoff — October 9

Owner requested this supplement before clearing the staff-roster session.
This is the existing G1 continuity record for B2-G1-03. It does not start
B2-G1-01 or B2-G1-02, create an execution plan, or select a collection,
production write, commit, or release.

**What exists and where**

- Collector: `/Users/fuchitalee/development/collect-chinese-workers`, branch
  `main`, HEAD and `origin/main` both `b7b9f86`. The skill symlink is
  `~/.agents/skills/collect-chinese-workers`. The tree is dirty and
  uncommitted. New files: `company_collect/filings.py`,
  `tests/test_filings.py`. Filing wiring is in `company_collect/command.py`,
  `SKILL.md`, `README.md`, `references/company-website-run.md`, and
  `tests/test_command.py`. Also dirty, and not to be reverted while saving
  the filing work: `company_collect/dossier.py`,
  `references/china-connection.md`, `references/chinese-source-access.md`.
  The prior session recorded 55 passed on `tests/test_baidu.py`,
  `tests/test_command.py`, `tests/test_pages.py`, and `tests/test_filings.py`
  using `/Users/fuchitalee/development/face-matcher/.venv` with `PYTHONPATH=.`.
  This handoff did not re-run that suite. Tests stay offline: no live
  SerpApi, Apify, or CNINFO.
- pymupdf is installed in that Face Matcher venv (`import pymupdf`). A
  missing import records an error and falls back to the website walk.
  Download cap 80MB. Accept only URLs built as `https://static.cninfo.com.cn/`
  plus the relative `adjunctUrl`. Filing reads do not spend SerpApi.
- This coordination checkout is `docs/general-launch-coordination` at
  `33f20b97`, already dirty. The round-two register is untracked. Do not
  commit this supplement unless asked. Production staff import stays a
  separate explicit step. Only the DeepSeek dossier has been written to
  production.
- The older machine-local note
  `/tmp/compound-engineering-501/ce-handoff/pushin-weight-v2-aff2eb3769a9/g1-deepseek-minimax-photo-coverage.md`
  is a photo-coverage snapshot in OS temp. It is not this round-two handoff.

**Roster rule**

Input is a company or unit name. Filings are the starting point. They list
founders and C-suite, and rarely the research team.

- Unit of a listed parent: open the parent filing and keep a name only when
  the filing itself ties that person to the unit. Do not copy the parent's
  directors onto the unit.
- Unit of an unlisted parent: skip filings.
- Standalone and listed: open that company's own filing.
- Standalone and private: no filing. Then use (1) database accounts with
  role staff on that brand, (2) the company's own website where the same
  line gives name and role, (3) a paper or technical report the company
  published whose affiliation line names this company.

When a filing list is read, that list plus the database seed is the staff
list the shipped command collects. Do not add Baidu news-sentence fragments.
When no filing matches, keep the website and Baidu walk.

The filing step runs after the database seed and before any photo or Baidu
search. Source is CNINFO (巨潮资讯网), which also hosts Hong Kong PDFs. Use
the latest annual report, or the prospectus when no annual report exists.
Hong Kong chapter: 董事及高级管理人员. Mainland chapter:
董事、监事、高级管理人员和员工情况. Do not vendor ah-disclosure-kit.
`choose_management_document` must not treat 半年度报告 as the annual report.
Prefer Chinese over an English copy, annual over prospectus, and the latest
announcement time.

Keep founders and C-suite, including a founder who is also a non-executive
director, an executive chairman, and the board secretary named in the
senior-management biographies (肖磊-type 董事會秘書). Keep the filing's own
characters. Do not convert 劉 to 刘 or invent pinyin. Drop independent
directors, supervisors (监事), an outside company secretary at a
corporate-services firm, and an executive director whose only office is
director (职工董事 / 張笑涵). "創立" of a different company later in a bio is
not founder of this company. Only the title clause through the first 。
counts. A later sentence must not revive a dropped person (鄭程傑).

Issuer versus unit is in `filing_forms`: a supplied name that matches the
company row searches company names; a supplied name that matches a linked
brand and not the company searches only that brand. A `qwen` request must
not open Alibaba's management chapter. A unit with status `not_listed` gets
the reason "this unit is not the listed issuer, so the parent company's
management chapter is not its staff list". Latin issuer keys strip a trailing
`-W` or `-SW`, casefold, and require length at least 4, so MINIMAX-W matches
MiniMax and 阿里巴巴-W matches neither Alibaba nor Qwen. Do not translate
Alibaba into 阿里巴巴. Cache a successful `filing.json` and reuse it on
resume. Do not cache status `error` as final.

Zhipu live read, prior session, not repeated after the parser landed: HK
02513, orgId 9920000016, short name 智谱, 2025年度报告, announcement
2026-04-19, adjunctUrl `finalpage/2026-04-19/1225124333.PDF`. Kept 劉德兵,
張鵬, 李涓子, 王紹蘭, 肖磊, 唐傑. Dropped 張笑涵, 李家慶, 王盟, 楊強, 謝德仁,
唐穎, 鄭程傑. Parser tests pin the keep/drop behavior; they do not replace
that live name list. MiniMax is HK 00100, MINIMAX-W, orgId 9920000022.
Alibaba on CNINFO is 09988 from the keyword 阿里巴巴 (orgId 9900042435);
the keyword Alibaba, and Qwen / 通义千问 / Inclusion, returned no listing.

**Next source, described and not built**

After filings, take one report per lab: the latest report the lab published
that prints individual names. Keep a person when the name is printed and the
affiliation line names this lab. A byline that is only "Qwen Team" or
"Gemini Team" adds nobody. Walk back to the newest earlier report that still
prints names. The role is "author of this report" unless the report states a
title. Alphabetical order is not a ranking. Examples already checked:
arXiv 2309.16609 and 2407.10671 print Qwen Team, Alibaba Group authors;
2412.15115 and 2505.09388 open as "Qwen Team" only; DeepSeek-V3 2412.19437
prints a long named list. Staff-role X accounts come after that, to attach
handles to people the report already named. They are not how the research
team is discovered.

**Categories recorded 2026-10-08. Recheck a listing before opening a filing.**

| Lab | Shape | Filing to open |
| --- | --- | --- |
| MiniMax | Standalone, listed | Own annual report. HK 00100 |
| Zhipu GLM (`glm`) | Standalone, listed | Own annual report. HK 02513 |
| Qwen | Unit of Alibaba | Parent filing only where it names Qwen. HK 9988 / NYSE BABA |
| ERNIE | Unit of Baidu | Parent filing only where it names the unit. HK 9888 / Nasdaq BIDU |
| Hunyuan | Unit of Tencent | Parent filing only where it names the unit. HK 0700 |
| MiMo | Unit of Xiaomi | Parent filing only where it names MiMo. HK 1810. The database also links `mimo` to Meituan; treat that as a bad link |
| SenseChat | Unit of SenseTime | Parent filing only where it names the unit. HK 0020 |
| KwaiYii (`kuaishou`) | Unit of Kuaishou | Parent filing only where it names the unit. HK 1024 |
| DeepMind | Unit of Alphabet | Alphabet filing only where it names DeepMind. Nasdaq GOOGL. Still inside Alphabet as of the 2026-08-05 Hassabis appointment (Alphabet chief scientist and DeepMind chairman); Koray Kavukcuoglu runs the lab day to day. Isomorphic Labs is a spinout |
| SpaceXAI | Unit of SpaceX | SpaceX S-1 and later reports, only where they name the unit. Formerly xAI; acquired 2026-02-02; renamed around 2026-07-06. SpaceX listed June 2026, Nasdaq SPCX |
| Doubao | Unit of ByteDance | None. ByteDance is private |
| dots | Unit of Xiaohongshu | None while unlisted. June 2026 reporting described a confidential Hong Kong filing being prepared |
| InclusionAI | Public pages call it Ant Group's lab | None. Ant is not listed and is not the listed Alibaba company. The database stores `inclusion_ai` and `inclusionai` as their own companies. `SKILL.md` still says Qwen and Inclusion are part of Alibaba. Do not silently rewrite that sentence |
| DeepSeek | Standalone, private | None until a public prospectus. Began inside High-Flyer. Two company nicknames, `deepseek` and `deepseek_co` |
| Moonshot Kimi | Standalone, private | None until a public prospectus |
| StepFun | Standalone, private | None until a public prospectus |
| Yi / 01.AI (`yi`, `01ai`) | Standalone, private | None until a public prospectus |
| OpenAI | Standalone, private | None. Microsoft is an investor. Do not read Microsoft's 10-K as OpenAI's staff list |
| Anthropic | Standalone, private | None until a public prospectus. Amazon and Google are investors. Do not read their filings as Anthropic's staff list |
| Mistral | Standalone, private, already tracked | None. French |

Tracked brands are `config.yaml` `enabled_models` (21). Llama, NeMo, EXAONE,
Sakana, and Upstage were not put through this roster pass.

**Accounts, finished runs, and leads**

- Qwen staff-role rows from the prior read-only check, brand `qwen`, role
  `staff`: `@xuanmingzhangai`, `@ChujieZheng`, `@xiong_hui_chen`. Only
  `@xuanmingzhangai` had a person row and a pending Qwen employment
  affiliation. The company command still seeds employment and founder rows
  joined through `brands_companies`. A `qwen` request therefore seeds
  Alibaba. Do not switch the seed to `brands_accounts` role staff unless
  asked.
- The 29 seed-not-staff accounts in run `qwen.ai/2026-10-07T061107Z` came
  from `profile-affiliation-rules-v1` and one
  `profile-affiliation-extraction-v2` row. They are pending affiliations,
  not the staff list. Call A (list `2067062923525275922`) is the tweet
  harvester fan-in.
- Do not rerun that Qwen dossier. It used the wrong roster and made no
  personal photo search. Path:
  `~/.local/state/collect-chinese-workers/runs/qwen.ai/2026-10-07T061107Z`.
- Do not resume the finished Zhipu run
  `~/.local/state/collect-chinese-workers/runs/zhipu/20261008T051014Z`
  (`research_status` partial, `production_import` not_run). It predates the
  filing step. It held 8 X-account staff plus five junk fragments (张鹏在电,
  递网证实, 王玥婷已, 近期, 数据官胡). 张鹏 himself was not among the eight.
  Do not retry Cunxiang Wang page 3 or Acer page 1. A Mac copy is
  `/Users/allenwlee/Desktop/2026-10-08-155220-zhipu-dossier/index.html`.
- Tyler Folkman (`@tfolkman`) remains in the Zhipu seed and that dossier.
  The stored row is a pending employment on brand `glm` with no filing tie.
  The owner said he has no Zhipu tie. Removing him was not authorized.
  Do not drop him unless asked again.
- Search default, uncommitted in `clue_from_profile`: search a staff account
  unless the account states a birthplace or hometown outside mainland China,
  Hong Kong, Macau, or Taiwan and the name is not Chinese or a pinyin
  surname. An English name or a city such as Utah or London is not that
  statement. The clue is not an ethnicity label. `origin` stays empty unless
  a source states a birthplace.
- Hugging Face org members are access seats. A public seat is a lead until a
  filing or the lab's own report already names that person. Do not add those
  members unless asked. Do not call the HF API again from this work; the
  address was rate-limited after a large profile fetch. Valid unauthenticated
  counts from 2026-10-08, zero errors: Qwen 193, StepFun 113, DeepSeek 37,
  Z.ai 36, MiniMax 12. Later orgs' bucket counts from that same run are
  invalid. inclusionAI, moonshotai, and Anthropic member lists returned 403.
- News articles, GitHub contributor lists, job ads, and fan accounts stay in
  a lead file. A self-written "ex lab" line on 脉脉, LinkedIn, or alphaXiv
  becomes a staff row only when a filing or the lab's own report also names
  that person. Leavers stay in a former pile.
- No third-party catalog checked sells a 脉脉 profile database. SerpApi's
  published engine list has no 脉脉 engine. Apify store search for 脉脉
  returned zero actors; a "maimai" hit was a Thailand logistics actor.
  Arcade-game 舞萌 APIs are the wrong product. Bright Data's public scraper
  catalog had no maimai.cn entry. People Data Labs' published social-network
  list has no 脉脉. No public 脉脉 profile product was found at
  PhantomBuster, Octoparse, Coresignal, Apollo, ZoomInfo, 探迹, 励销云, or
  典枢. `https://maimai.cn/robots.txt` allows a narrow public set (home,
  articles, some company and community pages, brand, SEO) and then disallows
  the rest. Member career lines are outside that set. 脉脉 itself requires a
  registered mainland mobile number. Do not build a scraper, replay cookies
  or access tokens, or recommend an SMS farm or an unofficial client.
- IT桔子, 烯牛, 鲸准, and 企名片 track companies, rounds, investors, and a
  short current team. They do not hold the departed-engineer list, and the
  ones checked ask for a mobile number. 猎聘 and Boss直聘 are phone-signup
  resume sites. 天眼查 and 企查查 terms refuse overseas access. Do not use
  those registry sites from outside China, and do not suggest a VPN or a
  fake phone to get around the terms. Usable without a Chinese number, as
  leads only: alphaXiv alumni pages and public LinkedIn headlines.

**Round-two starting point**

B2-G1-01 and B2-G1-02 stay ready to plan. This session did not select assets
or edit G2-owned picture files. B2-G1-03 continues from the roster rule
above. The technical-report pass and a seed switch from company
employment/founder to brand staff-role accounts are described here and are
not implemented. Agree the shared content reference and asset selection with
G2, G4, and G5 before implementations diverge. GLM-5.3 is the shared
integration case. G1 supplies media.

## G2 — Editorial decisions and voices

**Starting assets:** delivered English writing, source-grounding/context repair,
shared packet preparation and OriginalContent readers/storage.

| ID | Origin | Round-two work | State |
| --- | --- | --- | --- |
| B2-G2-01 | Unfinished ja/zh_cn voice scope; new explicit priority | Japanese and Simplified Chinese house voices with source-faithful copy, reviewed examples and bounded evaluation. Use the actual story evidence delivered to the writer. | Initial and fully target-language Wang/Le Chonk trials delivered: ja 東スポ/RocketNews24; zh-cn metro dailies/Zimeiti; two requested model settings. New pages opened in new owner Chrome window, compact explanation/image verified; actual drafts compared with mixed outcomes. Native house-voice acceptance remains pending. Owner-selected V4 Pro/high fully native continuation delivered:three drafts and a Rocket refusal, plus one preserved token-cap failure/recovery, five physical calls total. JA36/CN18 browser cases pass; updated owner review tabs loaded and prior GPT results retained. DeepSeek comparison complete; Claude Fable5.1/Opus5.5 xhigh fully native JA/CN/EN continuation delivered:10normal replies, zero retries/refinements, final exact CO2_NEW/workspace selected by owner. Additive five-model JA/CN and two-model EN pages/browser verified; JA60/CN30combinations+60stories/EN12 checks pass, raw/media/compact-purpose/preservation intact. No release; native acceptance pending. Owner-requested Claude evaluation/all-model picks complete across28selected replies: agent overall GPT6.1 Sol/high both languages; earlier ToSpo both/native Rocket Wang/earlier Rocket Chonk, earlier Chinese6.1 Metro Wang/WeMedia both and earlier6Sol medium Metro Chonk. Chinese WeMedia Wang headline needs correction before final use. Detailed assessments linked in same plan; zero new generation/copy/page/browser edits, originals unchanged. Owner-requested combined HTML now delivered with30original JA/zh-cn/EN replies, EN/mixed/local toggle, explicit untested settings and eight best picks;252desktop/phone, URL/reload/media/portable checks pass,64protected inputs unchanged. Observed active in new owner Chrome tab919891953, four existing tabs/URLs preserved. No new generation or earlier-page/application/release edits; same plan links combined receipt. Owner-selected V4.1 Flash/max mostly-English continuation delivered:five exact-alias replies, JA/CN both stories, EN Wang only with explicit Chonk omission. Combined35replies/six models;306browser states, unchanged best picks, media/portable Flash downloads pass.30old replies/media and64old protected inputs preserved; existing owner review tab refreshed to CN Metro/Flash/Chonk with six other tabs unchanged. Zero retries/refinements; native quality/ranking remains pending; no release. Flash comparison now complete:better Pro attribution/coverage but existing JA/CN favorites unchanged; Chinese framing drops naming qualification, EN Wang readable but current Opus preferred/Flash Chonk omitted.35reply hashes/page/eight picks unchanged; zero new generation, draft/page/browser edits or release; native acceptance pending. **October12 owner choices locked:** future JA/zh-cn writing defaultsGPT6.1 Sol/high; English NYPost Opus5.5/xhigh based on current Wang preference. Existing eight JA/CN examples remain selected, including earlier6Sol/medium Chinese Metro Chonk exception. Known factual repairs required before final use. Reference families remain ToSpo/Rocket and metro/WeChat; native-reader certification not claimed. Actual locale bindings/live configuration not changed by decision capture. [Round-two plan](../plans/2026-10-09-064803-feat-g2-round2-voices-plan.md) |
| B2-G2-02 | New chart-editor/chart-setter priority; superseding prediction-led Pulse and audited-learning direction | Define editorial prediction selection/origin, measurable target/deadline and requested evidence/chart settings; retain frozen cutoff and maximum two preselected comparisons. G2 owns interpretation/writing; G3 validates/calculates/forecasts/renders; later auditor compares actual outcome with the original prediction. | **Owner clarification October12:** Pulse/chart-editor work is already in the G3 session; retired as next task for this retained G2 session, which moves to graphics editor. Preserve G3 current work/plan and existing charts. |
| B2-G2-03 | G2 U15 and explicit exclusions after U16 | Retire obsolete storage/aliases and evaluate any remaining rename/reference work only under a selected scope. Reconcile 24-hour owner rollback decision with seven-day report behavior; preserve native consumers, restore proof and records until cleanup is authorized and justified. | Carried forward |
| B2-G2-04 | G2/G5 published-history dependency | Define durable publication/history retention for permanent content and share links. Coordinate old editions, source lists, media and selection pointers with G4/G5. | Carried forward |
| B2-G2-05 | Remaining G2 quality/coverage decisions | Preserve open live-quality qualification, discovery/unnamed-teaser coverage, image-claim evidence and earlier undecided editorial choices. Reconcile old prototype checkboxes against delivered behavior before choosing work; no repeat of completed experiments. | Carried forward |

**Apply round-one lessons:** [verify evidence delivery before voice evaluation](../solutions/workflow-issues/2026-10-09-110145-editorial-evidence-delivery-before-voice-evaluation.md);
keep anchors, background and actual cited support distinct. Publication and
storage changes preserve saved locale/version and selected-story identity.

### G2 session continuity — October 9

The owner requests this addition before clearing the G2 session. It supplements
the existing handoff/register; it does not reopen round one, create a new
implementation plan, or select a round-two release. This capture uses saved
release receipts and local source inspection, not a fresh production audit.

**Read first and preserve:** the authoritative root charter/index above; the
[closed G2 plan](../plans/2026-09-30-051835-docs-g2-voices-corpus-plan.md),
especially its round-one closeout, current rollback decision and October 8
compatible/physical-name receipts; and the evidence-delivery learning linked
above. The plan's historical unchecked boxes and delivery metadata are evidence
of the prior round, not instructions to rerun it. New detailed execution belongs
in a selected round-two plan through Ollija, in its intended branch/worktree.

**Delivered baseline and remaining dependencies**

- The last G2-observed production application is
  `00d7311754cf0837004c859e73c65c740aebab4d`, core migration
  `0079_original_content_physical_names`, on web, headlines, synthesis, harvest
  and jobs. Feature HEAD `1743234aa95e8b31d0613f313a88a4e9c60115b5` is a later
  documentation receipt. The October 9 coordination audit/local `origin/main`
  points to `671e9682`, which adds the independent HF-clock correction. These
  identities have different evidence scopes; verify the actual current target
  before future delivery and preserve intervening work.
- The six real tables are `original_content`, `original_content_texts`,
  `original_content_runs`, `original_content_calls`,
  `original_content_selections` and `content_pictures`.
  `original_content_sources` is the shared cited-Post join for headlines,
  Chatter and Pulse. Six old-name views point at those same base rows; they do
  not duplicate content. The obsolete editorial tables remain separately.
  U16 changed no physical columns and deleted no table/view.
- “Existing writing engine” means the **OriginalContent-integrated** deployed
  path. `monitor/packet_maker.py` freezes bounded preparation without provider
  work; `monitor/editorial/service.py`, `writing.py`, `grounding.py` and
  `persistence.py` select/write/check/save through shared storage and accounting.
  Compatible legacy writes remain for rollback and some orchestration inputs.
  Their presence does not mean the cutover is absent. Keep producing workflow
  identity separate from display names: `social-brief` is Chatter,
  `development-report` is Pulse, and `brand-window` is the trend workflow.
  Rank/editor/critic calls were preserved; a universal single-final-call engine
  and further call savings have not been demonstrated.
- Saved language/version copy and citations belong to
  `OriginalContentText`/`OriginalContentSource`. Displayed source count means
  distinct **cited Posts**, with every URL snapshot; retrieved context is not
  automatically cited. Existing editorial readers delegate to
  `monitor/original_content_readers.py`. Preserve story UUID, saved-edition
  `public_id`, revision and chosen locale; the integer database primary key is
  not a replacement for an existing public edition URL. Page/feed reads do not
  generate stories or reserve paid calls.

**B2-G2-01/05 — voices, evidence and quality**

- **October12 current writing selection:** owner locks GPT6.1 Sol/high for JA/zh-cn and Opus5.5/xhigh for English NYPost (current Wang comparison). The eight saved JA/CN picks and their variants remain exact; earlier GPT6 Sol/medium Metro Chonk is a saved-story exception. Known factual corrections remain required; raw examples are not rewritten. This supersedes pending owner choice, while native-reader certification and actual locale-binding activation are different observations. The configuration description below is the historical delivered baseline, not evidence that these new defaults are already wired into production.
- English voice bindings are the delivered baseline. Files for Japanese and
  Simplified Chinese already exist under `config/editorial_voices/`:
  `chatter-ja-v1`/`chatter-zh-cn-v1` are marked `available: false`, while
  `pulse-ja-v1`/`pulse-zh-cn-v1` are marked available with generic factual
  instructions. Neither file presence nor Pulse's available flag proves a
  qualified house voice. The delivered bindings select only English, and
  ja/zh-cn readers explicitly fall back to saved English. Round two needs
  independently reviewed
  house voices and examples, rather than treating fallback as localized copy.
  Public locale spelling is `zh-cn`; the charter also uses `zh_cn` as shorthand.
  Keep original-content house voice separate from factual third-party Post
  commentary and literal source translation.
- Freeze the actual selected story/writer input before comparing voices. The
  repaired collector in `monitor/editorial/context.py` retrieves relevant shared
  brands/recent material plus bounded older named/meme history, and
  `writer_request` in `writing.py` receives anchors and included context.
  The old Ajax/PewDiePie trace was 49 DB keyword matches → 2 editor inputs →
  1 writer input; those counts were matches, not independent confirmations.
  Chonk/LECHONK months-old relevance and GLM tease/update/launch are useful
  retrieval fixtures, with dates/uncertainty preserved. Do not mistake a lookup
  time-window setting for evidence that actually reached the writer.
- Current collector defaults are 240,000 packet bytes/160 recent posts,
  96,000 selected-story bytes/24 context posts, a 180-day historical lookup and
  1,500 ms optional-query timeout. Actual provider input also contains prompt
  and schema bytes. Inspect effective configuration and saved wire coverage;
  larger input alone does not establish recall or quality.
- Keep source/actor/brand/number ownership tied to validated source spans;
  counts, chart facts, denominators and comparisons are calculated in code.
  Images being attached or described does not establish a usable image-claim
  citation. Unnamed/unlinked teaser nomination, image-claim evidence and live
  numeric/semantic quality remain open qualification work.
- Iteration counts are separate: the October 7 source-contract loop exhausted
  **three live iterations/five model calls** and remained **not quality-qualified**;
  the context/attribution repair had **seven local implementation passes** and
  118 passing tests plus a separate saved-source replay. Compatible production
  took **three application deployment iterations**, correcting snapshot-query
  disk exhaustion and citation-alias recovery from original saved excerpts.
  U16 took **two implementation rounds/one release candidate**. Its 580 tests,
  five subtests, 328 required PostgreSQL cases and 36 Ollija checks prove their
  stated regression/migration scope, not live voice quality. Reuse the detailed
  logs in the closed plan; do not invent a combined iteration count or revive
  exhausted trial allowances. New evaluation needs a frozen acceptance set,
  rubric, iteration/spend ceiling and current owner-selected scope.

**B2-G2-03/04 — rollback review and lasting publication**

- Owner decision: **24 hours**, measured from the unchanged production cutover
  `2026-10-08T07:37:56.303216+00:00`; reevaluate **October 9, 16:37:56 JST**.
  The session recorded that checkpoint without scheduling a background review;
  it has not performed the reevaluation. Seven-day/October 15 dates in older
  receipts are superseded. `monitor/original_content_cutover.py::retirement_status`
  still computes seven days and always reports `ready: false`; reconcile the
  implementation and boundary/management-command regressions before cleanup.
  Passing the checkpoint does not authorize automatic removal or stop mirroring.
- Remaining legacy consumers include `monitor.editorial.service`,
  `monitor.editorial.persistence` and `monitor.editorial.evidence`. Destructive
  retirement requires selected scope, native replacements, no remaining
  consumers, reconciled preservation and proven encrypted backup restoration.
  Removing old-name views, deleting obsolete editorial tables and renaming
  physical columns are distinct changes. Keep rollback within the compatible
  storage/claim contract; pre-compatibility provider writers or an old database
  snapshot can lose overlap or duplicate sends.
- Published-history retention is a separate G2/G5 dependency. Review
  `monitor/trend_narrative_lifecycle.py` and the G5 plan's KTD11: preserve every
  genuinely published OriginalContent version/locale/source list and permanent
  link after feed/hero turnover, including approved trend output belonging to
  an activated active/superseded run. Approval alone is not publication evidence.
  Preserve media and selected pointers too; page reads must not create pins or
  publication events. The schema rename did not certify this retention policy.

**B2-G2-02 — agreements with G1/G3/G4/G5**

- **October12 session allocation:** the owner handles editorial/chart requests in G3. The editorial role decides whether a chart supports a content claim and its requested evidence/settings; the calculation role validates metrics and renders. G4 owns the exact
  shared view/language; G5 owns placement and interaction. Use the register's
  shared content/chart agreements, one GLM5.3 item and a second configuration,
  exercising both Post and OriginalContent. Benchmark/usage collection and
  readers are already deployed; do not recreate them. The independent metric
  window PR #56 (`be0489e8`) has verified-PR evidence only, with migrations
  0080/0081 reserved; its schema is not yet claimed deployed. Coordinate actual
  integration/migration state instead of allocating those numbers again.
- **October12 ownership update:** graphics-editor B2-G1-01/02 requirements/guide now belong to this retained G2 session; G1 staff/media foundation remains separately owned. Existing G2
  implementation candidates include `monitor/editorial/pictures.py`,
  `media.py`, `bindings.py`, picture configuration and
  `tests/test_editorial_pictures.py`. Agree a bounded file handoff before
  overlapping edits; this record alone does not transfer ownership. Preserve
  shared `ContentPicture`, source/subject attribution and media-call accounting.
  At U16 verification the 19 saved picture rows were intact but their files
  were already unavailable through both readers (404); do not report that as
  successful deployed image-byte delivery or a new rename loss.
- G5 has **already completed** local real published Chatter/Pulse integration
  on October 9 via the existing shared readers/access gate. Its :58418 preview
  uses a fresh isolated core0079 snapshot with 306,938 Posts and 19 approved
  editions, generation disabled. Exact saved headline/byline/full body,
  source counts and 96 displayed URLs were checked across desktop/mobile and
  three locales. The :58011/:58417 previews and dirty G5 code remain retained.
  Its 279-test affected result includes one existing Japanese geography-seed
  failure; broader retention/release preparation remains open. This supersedes
  this session's earlier suggestion that G5 still needed to refresh its old
  snapshot; it does not establish fresh-story generation or a production
  General release. Use the G5 plan/index receipt for the evidence boundary.

**Machine-local continuity and operating boundaries**

The retained G2 checkout is
`/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/g2-editorial`
on **fuchitalee**. Its closed-plan amendments remain uncommitted and protected
private/untracked artifacts remain; do not reset, clean or remove this worktree
when clearing chat. Links into it require that machine-local checkout. Private
evidence is under its `.local/g2-physical-names-20261008/` (full-row preservation,
reader/citation checks, final tests and restored service settings) and
`.local/g2-original-content-20261008/` (import/cutover receipts). Neither set is
guaranteed present in another clone. The earlier coordination snapshot was
published on `docs/general-round-two-records` at `7babf022` and subsequently
merged through PR #57 to main `60181a88be8c0887ca20033d6f9a9d24eb89152f`,
verified after the owner's pause/resume. That merge carries `[skip render]` and
does not establish a new deployed application. These later G2 handoff notes and
the other sessions' newer local supplements are separate from that snapshot;
their presence in another clone must not be assumed. Resume from the current
authoritative root file on fuchitalee while they remain unpublished.

At G2 completion writing was resumed and harvesting/synthesis/jobs continued;
no deployment/schema hold remains. Harvest stayed every 15 minutes and jobs at
`17 */6 * * *`; headline worker remains queue-only. The owner's temporary
two-hour-cadence idea was withdrawn. Budget/provider/cadence changes and a new
paid quality run are not implied by clearing the session or closing round one.
Future diagnostics resolve the database from each current service's
`DATABASE_URL`; the old static DB pointer in memory was stale during U16.
Never print connection strings/keys. The owner selected the OpenAI key in
fuchitalee's untracked `~/.env.secrets` for launch; resolve only its literal
`OPENAI_API_KEY` assignment without executing/dumping the file. Preserve all
other project credentials and independently owned benchmark/company operations.

## G3 — Chart engine and inherited analysis

**Starting assets:** deployed independent benchmark/usage collection and charts,
G3 evidence/forecast research and the GLM/DeepSeek comparison example.

| ID | Origin | Round-two work | State |
| --- | --- | --- | --- |
| B2-G3-01 | New chart-engine priority | Flexible settings for the Pulse editor's article: release spikes, 90-day predecessor buzz, 7-day brand post comparisons and classification percentages. Reuse chart/data/calculation behavior; define scopes, filters, grouping, units, windows, baselines and annotations. Reader exploration is not the reason for this flexibility. | Implemented and verified locally; four hypothetical examples ready for owner review. No production activation |
| B2-G3-02 | New share-settings priority; G4/G5 handoff | Validated saved chart state, locale and data-as-of identity; explicit frozen snapshot versus live-updating behavior. Supply the same state to editor, browser and share/export consumers. | Implemented locally: immutable edition snapshots, JS serialize/restore, numeric-export permission and explicit separate live refresh. G4 distribution and G5 embedding remain separate |
| B2-G3-03 | Unimplemented G3 design, G3-R12 and later statistical/market requirements | Historical analysis, qualified forecast target/baselines/uncertainty, reader scenario questions, prediction record and market-candidate/support workflow. Reassess the old benchmark dependency using delivered evidence; retain unresolved statistical/threshold/submission/notification choices. | Carried forward; decisions remain |

**Apply round-one lessons:** rolling downloads, exact-model usage, raw score and
rank keep their separate meanings. A post-release comparison baseline cannot
leak into a pre-release forecast. Chart implementation and forecast qualification
have separate completion evidence; this rollover does not claim the old hold
was a completed forecast implementation.

**October 9 requirements drill-down:** owner rejects an iterative
draft/chart/rewrite agreement loop because of refusals, timeouts and queue
growth. Proposed Pulse truth-reconciler flow is newsworthy item → assembled
chart evidence → reporting that claims matched or were refuted by our evidence.
Inconsistency supplies the story rather than forcing another rewrite cycle.
Owner selects publishing missing/mixed evidence findings with explicit limits,
including what was checked and what remains unresolved. Owner selects one
upfront evidence plan with at most two predefined comparisons per claim,
considering its results without result-driven recuts. Further owner answers:
reevaluate Pulse's lead subject every 15-minute editorial cycle with a
preceding-hour lookback; retain a leading subject with possible content
updates rather than forcing a new topic each cycle. Percentages use all
collected relevant posts, including unclassified posts. Failed comparisons
finish with available evidence and a stated gap; the main chart is visible
and the second comparison openable. Owner adds a distinct announcement event
layer: official model-release announcements and genuine first-breaking
other-account reports get prominent vertical lines and annotations so singular
posts retain visibility amid discussion volume. First-report/confirmation
handling and announcement counting in volume remain open, alongside time
budgets and writer-failure policy. Owner selects model editorial judgment
from evidence with a short major-news-organization role prompt; exact wording
is preserved in the charter and G3 plan. Evidence packet design is next.
G2 editorial and G3
calculation ownership remain distinct.

**Final owner decisions, October 9:** labelled credible unconfirmed breaking
reports may run; publish only meaningful news/finding changes after quarter-hour
reassessment; dated updates/corrections preserve accessible earlier wording.
G3 completed B2-G3-01/02 for a working local review version in its selected
worktree. Forecast/market work remains carried forward; no deployment selected.

**Local receipt, 2026-10-09T19:03:47+09:00:** [review index](http://100.102.74.50:8767/pulse/)
shows four hypothetical scenarios and dated/pinned earlier wording in en/ja/zh-cn.
One chart plan, maximum two comparisons, terminal gaps, original/official release
markers and full frozen data now reach the real saved-edition browser path.
[Selected plan and exact checks](/Users/fuchitalee/.codex/worktrees/ec5a/pushin-weight-v2/docs/plans/2026-10-09-063417-feat-g3-round2-chart-engine-plan.md):110 tests/8 subtests pass;
one unchanged homepage filter test fails in isolation;67 required PostgreSQL
tests execute with zero skips/errors. Twelve review pages and desktop/mobile
screenshots pass with no JS errors/overflow. Fixture copy is not a native voice
evaluation. Feature remains disabled by default. No provider calls, harvest or
scheduler changes, commit, push or deployment occurred.

Resume G3 in the same dirty worktree/branch/base. Its isolated `.venv`, task-owned
`pw_g3_round2_20261009` database and port8767 server remain for review; other
sessions' resources are preserved. The initial shared environment link was
replaced locally after a missing-Pillow failure. Active file claim is released.
Existing G2 voices, benchmark semantics and General homepage remain preserved.

**Superseding owner amendment, October 9 evening:** Pulse should make predictions
from news/evidence; Chatter reports actual events. The chart engine must track
observed variables and forecast them forward. A later auditor must release
an actual-outcome-versus-original-prediction report. Whether Pulse editor or
chart editor originates the hypothesis remains a brainstorm question.
The existing G3 plan now records that exploration, retaining the completed
local charts as a foundation. Forecasting portions of B2-G3-03 inform this
direction; reader scenarios/market workflows are not automatically brought into
implementation. G5's accepted blue/white DM Sans/Newsreader prototype remains
the requested visual baseline. No presentation code changed before this turn
of discussion; no forecast implementation or release is selected.

**Owner learning amendment, October 10:** Add recursive learning from audited
Pulse forecasts; the owner suggests classification buckets and normalized/
abstracted lessons and explicitly requests Firecrawl open-source research.
The [research report](/Users/fuchitalee/.codex/worktrees/ec5a/pushin-weight-v2/docs/analysis/2026-10-10-084801-g3-pulse-learning-open-source-research.md)
and existing G3 plan recommend an ACE-style versioned lesson playbook with
separate numerical learning, using Metaculus resolved-forecast calibration as a
reference and GEPA for later bounded offline evaluation. LangMem's structured
memory primitives are an optional dependency. Bucket taxonomy/framework choices
are proposals; actual outcomes, compatible units, cutoff eligibility, unresolved
states and independent release counts govern learning. Firecrawl research used
55 observed credits; no candidate code/model trial, learner, runtime job, new
collection or release was executed. Preserve all completed local charts, G5
visual target, worktree/environment/preview and other stream ownership.

**Owner data-readiness priority, October 11:** verify model-release capture and
categorization before learning experiments, and investigate historical collection
loss. [Bounded read-only audit](/Users/fuchitalee/.codex/worktrees/ec5a/pushin-weight-v2/docs/analysis/2026-10-11-062415-g3-x-post-coverage-and-release-readiness.md)
finds major UTC authored-date gaps through August 16; August 17 is only a steadier
count boundary, with later attribution/intraday/recall gaps retained. July/August
have no versioned classification states; structured release evidence begins
September 25 and 155 extracted records remain pending review. The existing G3 plan
now prioritizes verified releases plus a brand/interval coverage-repair map.
Actual backfill horizon, collection/repair work and qualifying forecast cohort
remain unexecuted; preserve both saved library research reports and local charts.

**Owner route, October 12:** use a practical 21-brand → current product-family
→ verified release approach, with MiniMax M, GLM and DeepSeek V4 as initial
examples. The existing G3 plan records this starting scope in place of a universal
all-data release detector. The first deliverable is a reviewable family/source
register; old candidate rows support checking capture and duplicates. Runtime
catalog repair, paid recovery and release remain separate work.
The [starting family register](/Users/fuchitalee/.codex/worktrees/ec5a/pushin-weight-v2/docs/analysis/2026-10-12-091100-g3-tracked-brand-family-register.md)
now covers all 21 brands as draft candidates, with source-qualified official
accounts and primary identity checks for the three owner seeds. The same plan's
U6 next curates expected launch groups/milestones; U7 retains future caller-path
regressions. No production grouping, release confirmation or recall qualification
was performed by the starting pass.

**Current owner scope and research result, October 12:** build release dates for
the twelve named companies over the past sixty days, including models, agents,
harnesses and other AI products. This replaces the interrupted all-release-tagged-
post scan and three-family pilot cap. Anonymous community tests and quiet artifact
publication belong in staged histories, with attribution/date uncertainty and
later identity knowledge retained.
[Working canonical inventory](/Users/fuchitalee/.codex/worktrees/ec5a/pushin-weight-v2/docs/research/2026-10-12-093516-g3-sixty-day-product-releases.md) and linked JSON/CSV record159 dated
entries, including8 qualified artifact revisions and2 boundary-day cases, plus
16 pending decisions and44 exclusions. No complete release-recall certificate,
classification taxonomy change or production repair. U6 next compares the
source-backed milestones against existing Posts/releases and resolves gaps;
U7 implementation remains evidence-dependent, and the proposed five-way product
categories are recorded as later work.

### G3 session-clear handoff — October 9

Owner requested this supplement before clearing g3-longitudinal-20260930.
Round one stays closed; the [G3 design](2026-10-05-163237-g3-evidence-forecasts-markets.md)
preserves its detailed requirements/proposals. Round two prioritizes reusable
charts under B2-G3-01/02, with the unbuilt statistical prediction, reader
scenario and market-candidate functions carried under B2-G3-03. The initial
request selected continuity documentation. The owner's later October 9 request
authorizes committing and pushing this handoff and its workspace instructions
to main; it does not select G3 implementation or application deployment.

#### Round-two working directory — owner decision

The owner confirms that G3's dedicated round-two worktree is its default
working directory, including after consulting shared knowledge. The October 9
startup request created a registered worktree through the harness's native
worktree tool, based on then-current main `7c426c3a4d76630b17243ac5b8a3451d77efab74`:

- **Session:** `g3-round2-20261009`.
- **Default working directory:**
  `/Users/fuchitalee/.codex/worktrees/ec5a/pushin-weight-v2` on fuchitalee.
- **Branch:** `feat/g3-round2-chart-engine`.
- **Round-two plan:**
  [reusable chart engine and saved state](/Users/fuchitalee/.codex/worktrees/ec5a/pushin-weight-v2/docs/plans/2026-10-09-063417-feat-g3-round2-chart-engine-plan.md),
  selected by `ollija annotate-plan`. Orientation and read-only reuse audit
  are complete; next is the bounded B2-G3-01/02 settings contract and two
  integration examples. No shared implementation-file claim or release
  endpoint has been selected. B2-G3-03 remains carried forward.

The native workspace is separate from the repository's `.worktrees` delivery
area. Use this registered path for current G3 work; any later delivery
placement follows the selected plan's guidance. Other worktrees and private
evidence remain preserved. The shared `.venv` is linked for local tools;
no database, secret file or other session's preview was attached.

- When round-two work starts, locate the assigned G3 worktree or create it
  through the repository's worktree workflow. Record its exact path, branch and
  selected round-two plan here and in the authoritative index. Give that path
  to every fresh G3 session.
- Start and resume implementation there. Confirm `pwd`,
  `git branch --show-current` and `git status --short` before editing. Keep G3
  code changes, tests, implementation plans and new task artifacts in that
  worktree; return there after reading material elsewhere.
- Read shared knowledge from the authoritative root on fuchitalee:
  `/Users/fuchitalee/development/pushin-weight-v2`. This includes its current
  charter, index, round-two register, prior G3 research and documented lessons.
  Older coordination copies in worktrees may be stale.
- Shared coordination updates go into the authoritative index, charter and
  relevant handoff section. Keep G3 implementation in its assigned worktree.
  The benchmark collector and other streams retain their own ownership;
  coordinate overlapping changes with their owners.
- Preserve the old shared checkout, other worktrees and local research,
  prototypes and evidence when clearing conversations. Untracked or ignored
  material does not automatically appear in a newly created worktree; consult
  its recorded source location before assuming it is missing.

**Authoritative reading and delivered inputs:**

- [Index](2026-09-30-104924-general-launch-index.md#current-round--round-two)
  and [charter intake](2026-09-30-104924-general-launch-charter.md#october-9-next-round-intake):
  current ownership, chart-engine priority and shared interfaces. G3-R01–R28
  retain owner requirements; design proposals remain proposals.
- [Closed G3 design](2026-10-05-163237-g3-evidence-forecasts-markets.md):
  measurement/chart semantics, statistical pilot, reader questions, Jev and
  Kalshi support/submission/notification contracts. Its staging-only, pending
  U22/U23 and benchmark-wait statements are historical; use later receipts.
- [Independent benchmark plan](../../.worktrees/feat/benchmark-download-collector/docs/plans/2026-10-05-070106-feat-benchmark-download-collector-plan.md):
  identities, reviewed mappings, metrics, calculation/read contracts, source-use
  permissions and actual delivery. Reuse its data/readers rather than collecting
  again. Collection permission does not automatically permit forecasts,
  API/export distribution or exchange use.
- [Round-one closeout](../analysis/2026-10-09-110145-general-round-one-closeout.md)
  and [evidence-delivery learning](../solutions/workflow-issues/2026-10-09-110145-editorial-evidence-delivery-before-voice-evaluation.md):
  completed research differs from implemented features; inspect the inputs that
  actually reach each consumer before judging its output.

All four selected sources—**Arena, Hugging Face, OpenRouter and OpenCode**—are
active in production. Initial reviewed comparisons are GLM 5.3 Flash and
DeepSeek V4.1 Flash, with DeepSeek V4 Flash as Arena predecessor context.
The October 8 [activation receipt](../../.worktrees/feat/benchmark-download-collector/docs/analysis/2026-10-08-141922-benchmark-production/2026-10-08-181800-activation.md)
records real scheduled collection and database-backed chart/browser checks.
The October 9 HF-clock receipt records web/benchmark cron at
671e968290780813bdbbfb9cd0d37bb74f601c6a, core leaf
0079_original_content_physical_names: **HF daily at 10:00 UTC**, OpenCode hourly,
OpenRouter/Arena daily. These are saved receipts, not new deployment checks.
HF's collection clock does not establish its counter's effective cutoff.

The independently owned generated-window change reached
[PR #56](https://github.com/allenwlee/pushin-weight-v2/pull/56), revision
be0489e88a505ccbb7509247a73aad34f357f41b, leaf
0081_measurement_window_index; **that schema change is not deployed in these
receipts**. It adds finite [start, end) window_range for complete intervals;
incomplete intervals retain known timestamps and a NULL range. Existing
timestamp fields remain usable. Coordinate integration and reserved 0080/0081
migration numbers with its owner, without treating this as a deployed field.

No G3 implementation plan, fitted/qualified statistical forecast, scenario
service, collected support ledger, exchange application/submission or
notification service was built here. The owner's earlier reference to an
existing prediction engine did not identify a verified implementation entry
point; inspect and reuse any actual producer before designing another.
Reassess the old benchmark hold against delivered inputs when selecting new
work; the rollover is not evidence of a trained prediction engine.

**Chart contracts to preserve:**

- G2 selects the editorial comparison; G3 validates, calculates and renders;
  G4 preserves/distributes the state; G5 embeds it. Agree product/release,
  source metrics/series, units, window, baseline/transform, annotations, locale
  and data cutoff, including **frozen snapshot versus live update**. Use a
  GLM-5.3 integration case and a second configuration, exercising both Post and
  OriginalContent. Transfer shared chart/editor file ownership before overlapping
  edits. Preserve provenance and unavailable-data states through every consumer.
- The release-response chart has **three percentage-change lines**: collected
  brand posts, exact-product OR daily tokens and HF adjacent rolling-counter
  change. Each uses its own mean over the same first complete seven-day
  post-release interval. Default display is a trailing three-day mean; the daily
  toggle retains the denominator. Preserve gaps and negative changes. Zero means
  the reference average; this is not an outcome probability.
- Arena is a separate **raw score/confidence/battles panel**, with rank context,
  actual publication dates and the reviewed text/overall configuration without
  style control. Score and rank differ; battles are not unique people. The
  predecessor proxy is rank only and ends at the successor's first valid
  evaluation; it does not invent successor scores/battles.
- OR is provider-scoped exact-model traffic; absent top-50 rows are unavailable,
  not zero. HF downloads are a rolling 30-day request counter; adjacent changes
  are not daily new downloads or unique users. OpenCode describes its hosted
  Go/free-model scope, with hourly revisions of daily UTC totals, not exact
  hourly usage. Provider user counts cannot be added into a global audience.
- [Cutoff-aware numeric reader](../../.worktrees/feat/benchmark-download-collector/core/benchmark_forecast_inputs.py):
  observation/import and mapping/contract availability must precede the forecast.
  Filter by cutoff before resolving revisions; pin source value/run/contract
  identities. Retrospective archives remain labeled as not past-known evidence.
  Native posts and unmapped OR denominator context are excluded: cutoff-aware
  post features and same-scope share denominators need coordinated adapters.
  Current code reads methodology key "comparisons"; the plan also describes
  "comparison_presets". Verify the delivered writer/validator before generalizing;
  preserve immutable contracts rather than silently renaming them.
- Owner-selected histories are **15 minutes, 1 day, 7 days, 30 days and
  360 days**: first two saved/pre-generated, longer windows asynchronous.
  Scope may be exact model, reviewed family/predecessor or audience topic such
  as local LLMs. History windows, chart viewport and forecast horizon differ.

**Inherited statistical engine and reader scenarios:**

The owner requires statistics across verified releases and their following
30 days, including post classifications and a qualitative account of discussion
changes. Publisher/X evidence and HF weights/repository metadata triangulate
actual releases; repository creation alone is insufficient. Same-launch variants
are dependent groups. Large post/measurement counts do not create independent
release samples. The October 7 local coverage check in the design used a partial
database projection; its empty release/classification tables do not prove that
production is empty.

The proposed pilot audits the true cohort and target coverage, then compares a
historical baseline, one regularized model and one Bayesian model sharing
information across publishers, with at most five substantive predictors in one
fixed evaluation round. OR 30-day usage is a proposed first target; attention,
usage, Arena rank/score and release timing remain separate. SQL/Django, pandas,
SciPy, scikit-learn, PyMC and ArviZ were proposed tools, not selected/installed
or used for fitting. The first numeric target and qualification standard remain
open.

Train only on outcomes already resolved at each forecast cutoff and test later
releases with launch siblings together. Today's classifications/corrections
cannot become historical features. The future reference week used in a release
chart cannot enter a pre-release estimate. Calendar, weekday, holidays, company
HQ and evidenced researcher work locations are candidate factors; retain unknown
coverage and publisher confounding. No country/holiday effect was established.
Report broad uncertainty or withhold a probability when unsupported.

Owner requires **2–5 questions** and a separate **0–100% personal probability
line** updating with answers. Jev may assess supplied factor questions
concurrently; a learned, evaluated statistical method combines them. Do not
add probabilities, multiply dependent factors or fabricate holiday effects.
Crossing 50% indicates a Yes/No lean; price and fees also determine a trade's
value. Keep canonical forecast, personal scenario, outcome vote, support for
creation, optional trading interest and actual orders distinct.

**Kalshi workflow and open operating choices:**

Kalshi is the owner's selected first venue. The
[partnership assessment](/Users/fuchitalee/development/pushin-weight-v2/docs/analysis/2026-10-07-104452-g3-market-partnership-selection/README.md)
supports a first builder/market-suggestion conversation, not an acceptance-rate
claim, approved partnership or permission to create markets. Latest owner flow:
**"Vote to make a market on Kalshi" → enough distinct support → versioned packet
→ confirmed-submission notification**, followed by verified decision/listing
updates. Support for creation is not a Yes prediction, bet or commitment to trade.

G3-R28 and the design's
[candidate section](2026-10-05-163237-g3-evidence-forecasts-markets.md#forecast-to-kalshi-market-candidate-request)
preserve the detailed contract: one active support per account/question version;
renewed support after material rule changes; resolution/eligibility review and
existing-market check before arming a trigger; exact model, cutoff, deadline/
timezone, source/configuration, edge rules and frozen aggregate demand. Private
scenario answers/contact details are not sent by default. Use a verified
suggestion or agreed partner route; no create-market API was established.
Prepared/queued is not sent. Unknown delivery needs reconciliation before retry;
notifications/live links require receipts and exact listed-rule matching.
No reply means pending, not rejection.

Open choices include support threshold/abuse policy, review owner, submission
route/automation and notification channel. In-app first was proposed, not
selected. Earlier supporter counts were internal ideas, not a published Kalshi
acceptance minimum. Source-use permissions and exact non-release/not-listed/
tie/correction outcome rules remain prerequisites for qualifying each question.
Liquidity provision is later business research, not an authorized capital task.

Legal research found **no disclaimer guaranteeing immunity from user losses**.
Forecast claims, hypothetical trading results, referrals, personalized advice
and execution have different implications; review the actual future workflow
and US/EU/Japan audience. Retain dated primary research pointers:
[CFTC intermediary guidance](https://www.cftc.gov/IndustryOversight/Intermediaries/index.htm),
[17 CFR 4.14](https://www.ecfr.gov/current/title-17/chapter-I/part-4/subpart-A/section-4.14),
[17 CFR 4.41](https://www.ecfr.gov/current/title-17/chapter-I/part-4/subpart-D/section-4.41)
and [Kalshi developer agreement](https://kalshi.com/developer-agreement).
The inspected developer agreement's facilitation restrictions and developer
indemnity need assessment before later trading integration. These are research
pointers, not counsel-approved terms or an approval gate for this document task.

**Settlement-source research from October 8:**

These primary market/rule checks were performed in the preceding conversation,
not rechecked October 9. Verify the exact contract version before a new proposal.
Settled precedent differs from a catalogue entry, fallback or market summary.

| Source | Confirmed example and limit |
| --- | --- |
| OpenRouter | Kalshi [KXOPENSHARE-26OCT05-21.5](https://external-api.kalshi.com/trade-api/v2/markets/KXOPENSHARE-26OCT05-21.5), finalized with OpenAI token share 18.2. Provider-specific weekly share with specified observation time/rounding, not global AI usage. |
| Vercel AI Gateway | Kalshi [KXDEEPVREQ-04OCT26-T9P0](https://external-api.kalshi.com/trade-api/v2/markets/KXDEEPVREQ-04OCT26-T9P0), finalized with DeepSeek request share 13.3. Usage-source precedent; Vercel remains an unselected collector candidate. |
| Artificial Analysis | Kalshi [KXOPENINTAI-26OCT02-XIAO](https://external-api.kalshi.com/trade-api/v2/markets/KXOPENINTAI-26OCT02-XIAO), finalized open-source Intelligence Index leader Xiaomi; speech settlement also found. AA remains a disabled collector candidate. |
| DeepSWE / Datacurve | Kalshi [KXCODEAI-26SEP30-MIMO](https://external-api.kalshi.com/trade-api/v2/markets/KXCODEAI-26SEP30-MIMO), finalized with ChatGPT as leader. Exact evaluation/identity/tie rules matter; mentions are not scores. |
| Humanity's Last Exam | Polymarket [Claude by June 30, 2026](https://polymarket.com/event/anthropic-claude-score-on-humanitys-last-exam-by-june-30?marketSlug=will-an-anthropic-claude-model-score-at-least-50-on-humanitys-last-exam&outcomeIndex=1), resolved thresholds using Scale's HLE leaderboard. Later contracts can specify agi.safe.ai; preserve the exact source. |
| ARC Prize / ARC-AGI-2 | Polymarket [2025 ARC-AGI-2 thresholds](https://polymarket.com/event/how-high-will-ai-score-on-arc-agi-2), resolved using ARC Prize public confirmation of private-evaluation scores. |
| Carbon Arc | Kalshi [KXGPTAPP-26SEP07-T95](https://external-api.kalshi.com/trade-api/v2/markets/KXGPTAPP-26SEP07-T95), finalized ChatGPT app-download index 112.4: 12.4% year-over-year growth, not 112.4 million downloads or HF weights requests. |
| Ornn | Kalshi [B200 August 7](https://kalshi.com/markets/kx/m/kxb200ws-26aug07), paid out at $5.76/hour. Infrastructure-price precedent, not model performance. |
| Publisher announcements | Polymarket [GPT-5 release in 2024](https://polymarket.com/event/will-openai-release-gpt-5-in-2024), resolved No under its public-release evidence rules. |

SWE-bench was confirmed as Kalshi series
[KXSWEBENCH](https://external-api.kalshi.com/trade-api/v2/series/KXSWEBENCH);
no settled instance was confirmed in this check. Epoch AI/LiveBench appeared as
fallback/tiebreak sources in a future contract, not verified past settlement
sources. No HF download-counter or OpenCode usage settlement precedent was
verified in this bounded search. A leaderboard hosted on HF is not an HF
download market. None of this research selects another collector.

**Earlier evidence and fragile local state:**

- [Headline sample/history](/Users/fuchitalee/development/pushin-weight-v2/docs/analysis/2026-10-05-142212-g3-headline-sample/README.md):
  varied stored examples and the activity-summary to editorial-news change.
  Version counts are not unique stories. Headline-generator cloning/refashioning
  belongs with G2; it was not implemented in this G3 pass.
- [Benchmark mentions](/Users/fuchitalee/development/pushin-weight-v2/docs/analysis/2026-10-05-144309-g3-benchmark-mentions/README.md),
  [concentration](/Users/fuchitalee/development/pushin-weight-v2/docs/analysis/2026-10-05-144309-g3-benchmark-mentions/concentration.md),
  [trends](/Users/fuchitalee/development/pushin-weight-v2/docs/analysis/2026-10-05-144309-g3-benchmark-mentions/trends.md) and
  [legitimacy/traffic audit](/Users/fuchitalee/development/pushin-weight-v2/docs/analysis/2026-10-05-144309-g3-benchmark-mentions/legitimacy-audit.md):
  CursorBench is unusually account-concentrated; DeepSWE has promotional
  contamination alongside real discussion. Arena domain visits include its
  interactive product; bot share was not established. DeepSWE traffic was
  unknown, not proven low. Mentions are not quality or independent endorsements.
- [Audience geography](/Users/fuchitalee/development/pushin-weight-v2/docs/analysis/2026-10-05-195203-g3-audience-geography/README.md):
  country coverage 31.4% of source authors, not website readers, eligible
  traders or historical researcher work locations.
- [Listing versus order parameters](/Users/fuchitalee/development/pushin-weight-v2/docs/analysis/2026-10-05-170409-g3-market-listing-and-order-parameters.md)
  and [builder/liquidity research](/Users/fuchitalee/development/pushin-weight-v2/docs/analysis/2026-10-05-210519-g3-builder-and-liquidity-programs/README.md):
  proposal review, builder access, referrals and liquidity are separate.
  No external application, submission or market making occurred.
- [Interest analytics](/Users/fuchitalee/development/pushin-weight-v2/docs/analysis/2026-10-06-123349-g3-interest-analytics/README.md)
  and [PostHog/GA4 review evidence](/Users/fuchitalee/development/pushin-weight-v2/docs/analysis/2026-10-06-124136-posthog-ga4-recent-reviews/skill-output/report.md):
  separate clicks, explicit support and agent calls. Later owner-requested
  **PostHog initial setup is an independent session**, recorded in G4's handoff
  below; progress was not checked here. Do not restart vendor selection as a G3
  prerequisite. Prediction/support/scenario events remain future integration;
  canonical operation counts belong in the database.

Machine-local capture: dirty authoritative root
/Users/fuchitalee/development/pushin-weight-v2, branch
docs/general-launch-coordination, inspected HEAD
33f20b971b01dbb8d90939f975e5dbbd987a3d86. The owner reports the charter/index
merged to main; remote main was observed at
60181a88be8c0887ca20033d6f9a9d24eb89152f during that earlier handoff pass.
This supplement was local-only at that capture; the authoritative index records
later publication. The old root checkout lists the G3 design and research
directories as untracked even when a snapshot has since been published.
Preserve local research and private evidence; the handoff publication does not
include every linked machine-local artifact. Resolve those links from the
authoritative root when they are absent from a fresh worktree.

The ignored, isolated G5-conforming prototype remains at
/Users/fuchitalee/development/pushin-weight-v2/.context/compound-engineering/ce-prototype/2026-10-05-g3-poll-to-market/.
Its 01-headline-poll-proposal/screens/index.html, verification.json, decisions.md
and sample-edited-market-proposal.md preserve the design and 34 saved browser/
asset checks. It uses illustrative probabilities and browser-local votes,
predates the latest creation-support wording and is not the statistical engine
or a production demand ledger. The preview was temporary; current process/port
availability was not checked. Preserve prototype-agent /root/g3_poll_prototype
ownership and the independent dirty G5 worktree.

**Round-two orientation:** agree the shared chart example/state and bounded
engine scope; audit actual cohort coverage before choosing forecast execution.
On an owner-selected implementation, use Ollija in the intended round-two branch/
worktree and enrich its returned plan. Keep the closed G3 design and root's
historical G1 coordination plan as source material, not new execution targets.
Reading this supplement alone grants no collection, package installation,
database writes, external contact, further Git publication, cleanup or release
authority; follow the current owner's selected task.

## G4 — Sharing, X and inherited API work

**Starting assets:** API/MCP discovery/draft, public-output restrictions and
October 9 X research in the shared index.

**Current successor — October 9:** [G4 homepage/Pulse snapshot-sharing plan](../../.worktrees/feat/g4-mcp/docs/plans/2026-10-09-091151-feat-g4-round2-sharing-plan.md),
selected by Ollija on `feat/g4-round2-sharing` at main `7c426c3a` in the existing
`.worktrees/feat/g4-mcp` directory. G4-R08–R34 are consolidated, with fixed
acceptance cases and upstream file-handoff boundaries. The owner selected U1/U2
continuation: an [isolated local prototype](http://fuchitalee:60423) now compares
Pulse with chart below/beside, plus homepage/Chatter/Post variants, using labelled
example data. Prototype browser checks cover sliders, Reset, exact sample links,
source/classification details, scrolling, languages and static SVG download.
Owner layout judgment remains pending. Real site integration, durable sharing,
GIF/video encoding, paid calls, X actions and delivery have not started; no
Django/PostgreSQL/application assurance is claimed from these prototype checks.
The earlier local Round 1 draft is byte-preserved (SHA-256
`5a7c69a6574b84e809edee92a724d0798f7da94322e13664d391c743a15d6bbf`)
and now appears modified because current main tracks a different published
version; exclude that preservation-only change from successor code commits.
The historical handoff below retains its original branch/state observations;
current snapshot, anonymous access, optional X connection and shortening-only
decisions take precedence over its earlier open options.

**U1 integration findings:** G2 saved edition/source readers currently include
named byline/source labels, and G5's Post projection includes raw source text;
G4 must select an explicit allowed projection. G3's evolving `ChartSpec` and
saved `edition.evidence["pulse"]` are integration inputs, not frozen schemas.
Its current `refresh_chart` recalculates saved absolute bounds under explicit
`latest_stored_evidence`; moving/rolling the bounds still needs a validated
upstream operation. Public chart, numeric-export and media-export permissions
are distinct. G1 approved subject assets and G5 component-file handoff remain
required before product integration. The example projection and exact file/
evidence locations are in the selected G4 plan; no shared module was changed.

| ID | Origin | Round-two work | State |
| --- | --- | --- | --- |
| B2-G4-01 | New sharing priority; G4-R08–R13/R18–R34 | First implementation: homepage charts and Pulse units. Saved snapshot URLs with anonymous creation/opening and link-only discoverability. Story/chart are one Pulse-style shared unit; homepage charts can stand alone. Both chart types support movable/resizable historical windows, exploration/reset and Live mode that pauses on historical navigation, respecting source resolution. First-version share links open snapshots only; recipient exploration does not alter the original shared view. Later corrections add a notice/link without silently replacing the original chart. Reusable content-unit variants follow the sketch, with a different Pulse layout where needed and image/video/chart support. Expandable per-source author metadata omits names/handles and does not sum followers. Photos follow the subject, with profile photos for self-subject posts only. Atomic classifications and dominant aggregate percentage with click-through detail omit product type. Long text is visually bounded with complete text available by scrolling. | Owner requirements consolidated in selected successor draft; U1/U2 integration/layout work next; not implemented |
| B2-G4-02 | Owner’s X sharing/login option; G4-R14–R17/R22/R23/R25/R30 | Chart media plus interactive link, preferring GIF/video. Lines draw progressively, then hold on the complete chart. Users optionally connect X when posting, review/edit and explicitly confirm inside PushinWeight; media download is also available. Editable captions use DeepInfra dsv4-0731 (`deepseek-ai/DeepSeek-V4-Flash-0731`). Limit new anonymous caption/video generation and reuse exports. X post text uses saved atomic commentary or the established Chatter/Pulse voice. Reuse text when it fits; DeepInfra only shortens longer copy while preserving its voice. Verify actual access/cost/permissions; define caption/animation/budget details. | Owner requirements consolidated in selected successor draft; actual account/provider access, limits and renderer choices untested |
| B2-G4-03 | Unimplemented G4 API/MCP draft | Retain saved-output API/MCP, auth/disclosure, possible private scenario writes, analytics and integration work. Current public content/identity restrictions still apply. The sample server is a prototype; final MCP integration follows actual upstream capability availability. | Carried forward; decisions remain |

**Apply round-one lessons:** exact saved outputs and permissions must survive
every consumer path. Browser JSON and a loopback mock server do not establish a
public API contract. Native posting permission and login remain separate.

**X media research checkpoint — October 9:** Official [media best practices](https://docs.x.com/x-api/media/quickstart/best-practices) document animated GIF and video attachments. The [v2 upload guide](https://docs.x.com/x-api/media/quickstart/media-upload-chunked) returns media IDs for [post creation](https://docs.x.com/x-api/posts/create-post). Native media upload and publishing are distinct from sharing a URL or expecting an animated link preview. Format support is verified documentation, not proof of our account access or an implemented flow. No account connection, upload, paid provider call or post occurred. G4-R14–R17 select GIF/video-preferred media, progressive drawing/final hold, reviewed connected publishing plus download, and the DeepInfra caption model. Actual account access and cost remain untested.

**Owner sketch — October 9:** Original operator-supplied image on allenwlee: `/Users/allenwlee/Desktop/Screenshots/Screenshot 2026-10-09 at 5.28.41 PM.png`. [Machine-local G4 review copy](../../.worktrees/feat/g4-mcp/.context/g4-round2/owner-sketch-2026-10-09-172841.png), SHA-256 `d71c77bf944a89d0ea48c84734252aa37cf7a4126a05126358cddf5fd0fd6d3f`. Inspected directly: author rail left, Asset/Content side by side, share/download top right, post details below. G4-R25–R29 clarify that author details are unnamed metadata, Asset may include image/video/chart, footer details are atomic classifications or aggregate percentages without product type, and reusable variants can give Pulse a different layout. G4-R30–R34 further select shortening-only DeepInfra use, expandable anonymous per-source metadata, dominant-percentage bar with full detail, subject-based photos/profile use for self-subject posts, and visually bounded full-text scrolling. Detailed sizes, provenance binding and responsive geometry remain implementation choices. No GUI automation or UI implementation occurred.

### G4 session-clear handoff — October 9

Owner requested this supplement before clearing `g4-mcp-scaffold-20261006`.
This is the existing G4 continuity record, not a new implementation plan. Start
round two with B2-G4-01/02 sharing/X and carry the unfinished MCP work under
B2-G4-03. The full prediction/MCP offering is not automatically part of the next
beta. No new implementation, account connection, posting or delivery endpoint
was selected by this handoff request.

**What exists and where:**

- [Closed round-one MCP/API draft](../plans/2026-10-07-053244-feat-g4-mcp-plan.md):
  requirements R1–R10, architecture KTD1–KTD5, proposed tools/events, open
  decisions O1–O7 and future units U1–U6. The draft-planning pass completed;
  none of those implementation units was executed in this session. Formal
  implementation-readiness review and application tests were not performed.
- [Offering discovery](2026-10-06-210526-g4-mcp-offering-and-scaffold.md):
  offering/transport options and initial disclosure questions. Its technical
  recommendations are proposals, not owner selections or current SDK guarantees.
- Retained machine-local worktree:
  `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/g4-mcp`, branch
  `feat/g4-mcp`, inspected at `d66d8508`. A repository copy of the closed draft is already published at `docs/plans/2026-10-07-053244-feat-g4-mcp-plan.md`; retain that published reference alongside the local working copy. The draft is untracked there; there is
  no G4 runtime implementation, dependency installation, provider call,
  database change, live analytics or deployed MCP server from this session.
  Preserve the worktree. The authoritative root is also a dirty coordination
  checkout; neither checkout is the current deployed application. This G4
  supplement was published through its owner-authorized handoff commit; later
  local round-two additions remain separately recorded.

**Technical recommendations worth retaining:** use a shared approved-output
layer behind HTTP and a maintained Python MCP SDK, with hosted Streamable HTTP
as the recommended offering. Keep the existing production WSGI process intact
while evaluating a separate local MCP entry point. G5's handwritten loopback
sample is design evidence only. Choose released SDK/protocol versions against
the actual first clients when implementation starts.

Saved reads and status polling should never start paid computation. If private
scenarios are selected, explicitly request work through G3-owned operations,
with authenticated ownership, idempotency and separate read/write permissions.
Do not duplicate G3's calculations, jobs, forecast storage or cost ledger.
Return explicit public projections rather than internal reader/database rows;
apply current disclosure/source-use rules on cached delivery as well as creation.

**Unresolved choices:** agents reading forecasts versus also submitting private
scenario answers was asked but never answered. OAuth provider/first supported
clients, quotas and deployment topology remain open. Distinguish omission of
author identity from guaranteed anonymity: a source link can reveal the author.
Named subjects, media and generated prose still need an explicit output decision.
The inherited MCP restrictions cover metadata, errors and cached results too.
Do not silently apply an MCP identity restriction to all website sharing, or
assume a website-approved export is automatically MCP-approved; reconcile each
surface with the charter. Agent support/interest writes remain a separate choice
from reads or scenario requests; consume G3's later support-vote contract rather
than treating the old draft event names as settled.

**PostHog is a separate initial-setup task.** On October 8 the owner requested
another session outside G1–G5 for initial setup, wanting to enter account/billing
details once and let the agent handle routine integration and dashboards. Do not
reopen the earlier vendor comparison as a G4 prerequisite. The scoped proposal
was browser pageviews, stable logged-in identity, ordinary Django events and a
starter dashboard. No PostHog installation or account access occurred here;
another session's subsequent progress has not been checked. Its temporary
handoff is machine-local at
`/tmp/compound-engineering-501/ce-handoff/pushin-weight-v2-aff2eb3769a9/2026-10-08-121446-posthog-initial-setup.md`;
it may be cleared by the OS, so this paragraph preserves the essential boundary.
G3/G4-specific prediction/MCP events remain future integration. PostHog's
management MCP/API for creating dashboards is distinct from its optional MCP
analytics wrapper; ordinary browser/server events do not require that wrapper.

Retain these measurement distinctions: trusted `web`/`mcp`/`api` channel and
authenticated account identity are separate; a tool call does not prove human
viewing or intent. Count polls/retries separately from accepted operations and
explicit support. Use bounded metadata without private scenario answers or raw
content. Canonical interest, computation and cost counts belong in the database,
not an analytics delivery queue. The closed draft's detailed event names and
visibility thresholds remain proposals.

**Round-two starting point:** agree the shared content/edition/locale, chart
state/cutoff and media-variant example with G2/G3/G5 and G1 before overlapping
edits. G4 preserves and distributes that state; G3 validates/calculates/renders
it. Fixed snapshots versus live charts, durable publication retention and
recipient language behavior need explicit contracts. Reuse the October 9 X
research in the index, then verify actual access/permissions and current rules
within the selected work; mandatory X login remains an option, and login is
separate from permission to publish a user-reviewed post. Recheck current
OriginalContent and benchmark contracts: the old MCP draft predates their later
delivery. Source-use approval for public forecasts/API/export is distinct from
collection availability. G4-R06 still governs final MCP integration; it does not
create a blanket wait for independent sharing design or PostHog setup.

When a bounded implementation is selected, use Ollija in the intended round-two
branch/worktree and enrich its returned plan. Keep this closed draft as source
material and new execution in that successor. Preserve other sessions' files,
services and G5's dirty implementation; claim only the selected G4 surfaces.

## G5 — General-page integration and release preparation

**Starting assets:** accepted General design, real lower feeds, permanent Post
pages/navigation, locally verified published Chatter/Pulse integration and saved
browser evidence. Preserve `.worktrees/feat/g5-general-page` and its dirty code.

| ID | Origin | Round-two work | State |
| --- | --- | --- | --- |
| B2-G5-01 | New chart/asset/voice/sharing priorities; current local General work | Integrate G1/G2/G3/G4 components incrementally into the accepted layout and detail pages; verify desktop/mobile, all supported locales and Human/Agent geometry. | Ready to plan |
| B2-G5-02 | Unfinished G5 release/readiness scope | Resolve the recorded Japanese geography-seed failure, durable published-history/link behavior with G2, actual candidate assurance/performance and remaining General navigation/source-display decisions. Reuse valid earlier evidence. | Independent readiness pass complete locally: geography fixture and aging-clock regressions fixed; real-data timings recorded. Retention, exact candidate assurance/performance and page decisions remain carried forward |
| B2-G5-03 | Existing local-only endpoint; future launch | Preserve and reconcile local work onto the eventual chosen candidate. Record any later commit/push/deployment endpoint explicitly. Default landing/domain routing, including the recorded pushinweight.si purchase, remains a selected-scope decision. | Carried forward; delivery unselected |

**Apply round-one lessons:** check database → shared reader → page → recipient
with real saved content; keep prototype, local browser and production receipts
separate. Closing round one is not permission to remove its dirty worktree.

### G5 session handoff — October 9

Captured **2026-10-09 14:49 JST** for the owner's requested session reset.
This expands G5's existing round-two record; it does not reopen round one or
select a new implementation/release. The next session's focus is B2-G5-01–03.

#### Where the work lives

- **Authoritative coordination:** this register and the root
  [charter](2026-09-30-104924-general-launch-charter.md) /
  [index](2026-09-30-104924-general-launch-index.md) on fuchitalee. Worktree
  copies can be older. The index carries current cross-stream ownership.
- **G5 checkout, machine-local:**
  `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/g5-general-page`,
  branch `feat/g5-general-page`, HEAD
  `00d7311754cf0837004c859e73c65c740aebab4d`. Its modified and untracked files
  contain the implementation; a fresh checkout of the branch does not contain
  those changes. No G5 implementation commit/push or production release occurred.
  At capture, cached `origin/main` was `671e9682`, four commits ahead of this
  base. Refresh/reconcile that comparison when a later implementation is selected;
  the earlier “current main” receipt means the October 9 morning integration.
- **Closed plan:** [published round-one G5 plan](https://github.com/allenwlee/pushin-weight-v2/blob/main/docs/plans/2026-10-02-060108-feat-g5-general-page-plan.md)
  preserves decisions, requirements and U1–U8 scope. Its closeout transfers
  unfinished work here. Keep that historical body/checkboxes intact; detailed
  new execution belongs in the later Ollija-selected round-two plan.
- **Implementation map:** [General reader/URL reference](../../.worktrees/feat/g5-general-page/docs/reference/general-page.md)
  explains current feed rules, publication access, URLs and preferences.
  [Local implementation tracker](../../.worktrees/feat/g5-general-page/todos/2026-10-08-150837-g5-general-page-local-implementation.md)
  holds the dated tests, corrections and snapshot history. These are retained
  local files, not proof of remote availability.
- **Main code in that checkout:** `monitor/general_readers.py` reads the four
  lower feeds; `monitor/general_views.py` adapts those and the shared editorial
  readers. `monitor/content_readers.py` / `content_views.py` serve individual
  Posts. General's templates are `monitor/templates/monitor/general.html` and
  `general/`; its browser behavior/styles are `monitor/static/monitor/general.js`
  and `general.css`. `tests/test_general_*.py`, `test_content_detail.py` and
  `tests/ui_assurance/general.py` cover the changed behavior.

#### Implemented behavior and owner decisions to retain

- **Four lower feeds work independently of G2 generation.** Calendar, Free
  stuff, Jobs and Who's moving read actual classified Posts, saved commentary
  and linked facts. Missing commentary uses the labeled source/literal-translation
  fallback; unknown dates stay unknown. Each Open-weight panel displayed 20
  real initial Posts in the last browser verification. Identity/extraction
  behavior remains owned by its upstream stream.
- **Chatter/Pulse now contain published OriginalContent.** They reuse
  `monitor.editorial.views.access` and
  `monitor.editorial.readers.feed_payload`, with shared storage selected in
  the preview. Chatter uses the shared featured edition and prior distinct
  stories; Pulse shows six saved editions. Full headline, byline and body,
  distinct cited-Post count and every source URL are present. Sources and
  Chatter history expand within the fixed panel; headline/archive links work.
  These are global editorial selections, independent of lower-feed weights or
  brand filters. Chinese/Japanese disclose English fallback in this snapshot.
  This implementation does not add the round-two chart engine to Pulse.
- **Atomic URLs:** `/general/` is General and `/` remains Pro.
  `/posts/<tweet_id>/?lang=<locale>&commentary=<artifact-id>` pins saved Post
  commentary when available. OriginalContent links use G2's existing
  `/stories/<story-uuid>/?track=<track>&lang=<locale>&edition=<edition-uuid>`.
  The planned `/content/` adapter is not implemented. Published-history/edition
  retention remains B2-G2-04 plus B2-G5-02; do not describe saved story URLs as
  proven permanent across future cleanup. The owner raised obscuring original
  Post text for compliance but did not select a policy; source text is currently
  accessible. G4's output restrictions and public web policy stay distinct.
- **Accepted visual baseline:**
  [DeepSeek/context prototype](http://100.102.74.50:58417/index.html?product=deepseek&window=context).
  The owner rejected the ChatGPT warm-gray/font substitution at `:56887` and
  retained the prior styling. Keep earlier `:58011` and accepted `:58417`
  prototypes separate from the wired `:58418` page. The weight-themed heading
  brainstorm was tabled; no replacement H2 names were selected. The research
  journeys remain [agentic products](/Users/fuchitalee/development/pushin-weight-v2/docs/research/2026-10-07-214739-agentic-product-design-patterns.html)
  and [prediction graphs](/Users/fuchitalee/development/pushin-weight-v2/docs/research/2026-10-08-095045-prediction-graph-visual-journey.html);
  `make-visual-style-doc` is installed at user level on fuchitalee.
- **Navigation and controls:** collapsible left navigation, login/settings,
  locale/timezone/audience preferences, independent Open/Closed controls and
  mobile handling are implemented. The Closed trigger deliberately displays
  the owner's exact **“Open Weights Coming Soon!”** message, then deselects
  Closed while preserving Open, cards and URL. Its popup sits 8px from the
  invoking header/sidebar toggle and follows the visible control after resize.
  Do not silently “correct” the owner-selected wording. Human/Agent retain
  identical six outer panel rectangles; Agent capability and the masthead
  assistant remain explicitly unavailable pending their actual integration.
- **Domain:** the owner confirmed purchasing **pushinweight.si through
  Namecheap** on October 9. [Registration record](../reference/domains.md).
  DNS/Cloudflare configuration, renewal details and launch/default routing
  remain unconfirmed or unselected; purchase is not a deployment receipt.

#### Preview, isolated data and local evidence

The [wired General preview](http://100.102.74.50:58418/general/?lang=en&weights=open&audience=human)
returned HTTP 200 during this handoff, with eight saved-edition cards in the
HTML. Its owned listener was PID `12147`, running the G5 private `.venv` and
`manage.py runserver 0.0.0.0:58418 --noreload`. A PID is a capture-time fact;
verify the command, directory and port before any later restart. Other sessions'
servers and the earlier prototypes remain separate resources.

The database is **`pw_g5_collected_20261009`**, local PostgreSQL 18 on
`127.0.0.1:55436`, restored through core migration `0079`. The October 9
06:37 JST snapshot has 306,938 Posts (last fetch 06:33:50 JST) and 19 approved
English editions: two Chatter and 17 Pulse. It is not an automatically refreshing
production connection. Runtime uses `ORIGINAL_CONTENT_STORAGE=shared`,
`EDITORIAL_PUBLIC_ENABLED=true`, `EDITORIAL_ENABLED=false`; viewing does not
generate content. The older G5 snapshot and source rehearsal database remain.
Tests used a separate disposable PostgreSQL 17 database on the default local
port (`pw_g5_general_20261008`, with Django's `test_` database); populated
snapshot databases are not test targets.

**Machine-local evidence directory**, relative to the G5 checkout:
`.context/g5-original-content-20261009/`.

| File | What it establishes |
| --- | --- |
| `render-export-receipt.json`, `data-source.json` | Successful fresh isolated restore and the frozen data counts above. The slower direct dump was canceled after this restore and its partial archive removed. Do not rerun either snapshot helper merely to resume the session. |
| `shared-readers.json`, `live-browser.json` | Exact reader-to-page headline/byline/full-body/source/edition-link parity across 1280px/390px and EN/ZH-CN/JA; 96 displayed citation links matched, four lower feeds populated, Human/Agent rectangles equal, no overflow or JavaScript errors. |
| `live-en-1280.png`, `live-mobile-top.png` | Visually inspected real-data desktop/mobile presentation. |
| `affected-gate.log`, `general-assessment.json`, `local-review.json` | Code-test result, 49-obligation General browser assessment and scoped inline review. The review was not independent/external. |
| `start_preview.py`, `preview-server.pid`, `preview-server.log` | Existing starter, captured listener and runtime log; restart only if needed under the next task's scope. |
| `before-main-wip.tar.gz`, `before-main.patch`, `before-main-manifest.json` | Preserved G5 work before the morning main sync. The named Git stash `g5-preserve-before-current-main-20261009` was applied successfully and retained; applying it again would duplicate old work. |

The unchanged product identity, recomputed during this handoff, is
`worktree-sha256:9884c875aba3a4fedf78dfc5557cd304f2a45220aff8ae933f5e368281c01338`.
Its affected gate recorded **279 passed, one failed, 59 subtests passed**;
115 required PostgreSQL tests executed, with zero skips/errors. The remaining
failure is
`tests/test_feed_geography.py::test_japanese_geography_seed_covers_every_existing_country_and_region`
(missing seed rows), carried into B2-G5-02 and not waived. The earlier Account
UUID fixture failure was fixed by the morning base update. All **49 General
browser obligations** passed. Scoped Ruff, JavaScript syntax and whitespace
checks passed. This handoff reuses those receipts; it did not rerun the suite.
An exact committed release candidate and representative performance verification
remain outstanding. Earlier four-fixture timing measurements do not satisfy them.

#### Round-two continuation boundary

The owner's next-round direction is integration of G1 assets/graphicsed, G2
Japanese/Chinese voices and chart editorial decisions, G3 reusable charts/state,
and G4 sharing/API contracts. G5 owns their page/detail/mobile placement, not
new copies of those upstream pipelines. The existing shared agreements below
use one GLM-5.3 content item plus a second chart configuration and both Post and
OriginalContent paths. Source counts must use actual cited support, not every
retrieved/background item; retain the linked evidence-delivery lesson above.

A suitable next planning step is to select a bounded B2-G5-01 integration using
those interfaces while retaining B2-G5-02's regression/retention/performance
work. This is a continuation recommendation, not a newly selected implementation.
The index also records the independent HF-clock update and metric-window PR #56;
recheck their actual code/schema status before consuming them. Do not assume the
local snapshot contains later migrations or that the pending metric-window
release is deployed.

The owner subsequently selected **commit-and-push of this G5 documentation to
main** on October 9. That endpoint covers this handoff, its charter/index links
and the domain record. G5 application delivery remains unselected; DNS changes,
deployment, paid generation and external posting are outside this request.
Clearing chat leaves these files/databases on fuchitalee, but another host/clone
will not automatically have them. Preserve the checkout, its private artifacts
and the owned preview.
New execution should use the current charter/index and an Ollija-selected
round-two plan rather than reopening the closed plan.

**Post-merge check, October 9 at 14:56 JST:** fetched and inspected remote main
`60181a88be8c0887ca20033d6f9a9d24eb89152f` after PR #57 merged the earlier
documentation snapshot. That revision contains the round-two baseline and
B2-G5-01–03, but not this later G5 handoff or its charter/index discovery links.
The domain-purchase note and its link are present there, but
`docs/reference/domains.md` is not; at that revision, the link resolved only in
the local authoritative checkout. All eight file links in this local handoff
were checked and resolve. No handoff content was lost in the merge. This later
owner-authorized documentation change supplies the G5 supplement, its two discovery links and
the missing domain record. The G5 implementation remains uncommitted, at the
source identity captured above. References into `.worktrees/` and the research
journeys point to machine-local artifacts on fuchitalee; publishing this handoff
does not publish those underlying files.

#### Round-two session start — October 9

`g5-round2-20261009` resumed at the owner's request in the existing canonical
G5 checkout, `.worktrees/feat/g5-general-page`, on `feat/g5-general-page` at
`00d7311754cf0837004c859e73c65c740aebab4d`. Read the authoritative index,
charter, this handoff, the closed plan, local reader reference/tracker and the
evidence-delivery learning. The modified/untracked application files remain
preserved. General's recomputed product identity still matches the handoff:
`worktree-sha256:9884c875aba3a4fedf78dfc5557cd304f2a45220aff8ae933f5e368281c01338`.
All ten checked snapshot, reader/browser, gate/review and before-main evidence
files are present. No test suite was rerun during orientation.

The owned preview returned HTTP 200 at `/general/?lang=en&weights=open&audience=human`;
port 58418 still belongs to PID 12147, whose command uses this G5 checkout's
private `.venv` and `manage.py runserver 0.0.0.0:58418 --noreload`.
These are read-only availability observations, not new browser acceptance or
production receipts. A fresh main fetch resolves `origin/main` to `7c426c3a`
(12 commits ahead of G5's base); the application-path difference is the independent
HF daily-clock command and its tests, with no new core migration in that comparison.

`ollija annotate-plan` confirms this exact worktree and returns the closed
round-one plan unchanged, with `delivery_target: on-request`. Preserve it as
history; no round-two execution plan was selected or created in this orientation.
The next proposed bounded B2-G5-01 step is the page/detail integration contract
for G1 assets, G2 localized writing, G3 validated chart state and G4 share views.
Use the agreed GLM-5.3 example plus a second chart configuration, exercise both
Post and OriginalContent, and retain exact cited support, revision/edition,
locale and snapshot/live meaning at the rendered page and recipient boundaries.
G5 owns placement, responsive behavior and shared Human/Agent geometry; upstream
generation, chart calculation and sharing implementation remain with their owners.
B2-G5-02 retains the Japanese geography-seed failure, G2 publication-retention
proof and representative candidate assurance/performance. Application delivery
and domain routing remain unselected. Orientation is complete; detailed new
execution belongs in the later selected round-two plan.

#### Independent G5 readiness — October 9

Owner selected “ok go” on the G5 work that needs no new G1–G4 output.
The [Ollija-selected round-two readiness plan](../../.worktrees/feat/g5-general-page/docs/plans/2026-10-09-081712-feat-g5-round2-readiness-plan.md)
records the completed local pass. The same existing G5 worktree now uses local
branch `feat/g5-round2-readiness`, still based on `00d73117`; all pre-existing
dirty implementation and the closed round-one plan remain preserved.
The branch change selected new round-two execution without reopening round one.
The owner-required existing path overrides branch-derived relocation guidance.

The geography failure was test setup: normal Django test flushes remove the
data-migration taxonomy, and the label command correctly skips missing base
keys. The test now restores frozen prerequisites and still checks all 249
countries, 31 regions and repeatability. The broader run exposed a second
aging-fixture test; its server/browser clocks are now pinned and its real-route
assertions prove timer suspension, restoration and resumed ticking. Only those
two test files changed; General's product identity remains `9884c875…c01338`.
Final affected checks pass: **280 tests, 59 subtests, 115 required PostgreSQL
tests executed, zero skips/errors; all 49 General browser obligations clean**.

Read-only measurements on the retained 306,938-Post snapshot cover 20 reader
and 12 Django route cases. Open feed-route warm medians are **14–20 ms**;
General in EN/JA/ZH-CN is **101–102 ms**. Actual :58418 browser navigation/readiness
warm medians are **178 ms desktop / 176 ms mobile**, with all four feeds populated,
matching Human/Agent panel geometry, no overflow or JavaScript errors. These are
local unsealed timings, not production latency or committed candidate assurance.
No measured bottleneck justified a query rewrite. Future asset/chart/sharing
insertion points and existing unavailable states are mapped in the selected plan;
no upstream implementation is claimed.

Private evidence remains in the existing G5 checkout's
`.context/g5-round2-readiness-20261009/`. The populated snapshot and PID 12147
preview remain intact; tests use a separate dedicated local PostgreSQL 17 database.
G2 published-history retention, candidate assurance/performance, page/source
decisions and actual upstream integration remain open. No commit, push, release,
domain routing, provider, production or snapshot mutation occurred.

## Shared agreements for parallel work

Agree these interfaces before overlapping code edits. G1/G2/G3/G4 own their
outputs; G5 owns page integration. A shared module has one editing owner at a
time, with an explicit handoff when ownership changes.

| Agreement | Required meaning | Lead / consumers |
| --- | --- | --- |
| Content reference | Post or OriginalContent, stable identity, saved revision/edition and locale | G2 + G5 / all |
| Asset selection | Selected image/video, source/subject evidence, fallback reason, reusable variants | G1 / G2, G4, G5 |
| Chart request/state | Source metrics/series, units, window, baseline/transform, annotations, locale, cutoff/as-of and snapshot/live choice | G3 session: editorial intent + validation (owner October12 allocation) / G4, G5 |
| Share view | Exact content reference, chart state, chosen language and asset variant; recipient locale must not silently replace shared language | G4 / G3, G5 |

Start with one GLM5.3 content item carried through all applicable components,
then a second configuration proving chart reuse. Exercise both a third-party
Post and OriginalContent. No global “finish G1 before G2” ordering is introduced;
only concrete interface, shared-file, migration or runtime conflicts constrain
concurrent work.

## Round-two completion records

Each bounded plan records delivered behavior, evidence scope, actual endpoint,
remaining items and their destination. Relevant regression checks cover changed
existing behavior; earlier checks are reused while their assumptions still hold.
When a subtask finishes, close it without reopening round one. When the owner
closes round two, produce the same explicit outcome/transfer record for any
unfinished scope.

No implementation plan or active implementation owner is created by this
register. Use the authoritative [index](2026-09-30-104924-general-launch-index.md)
for current claims and ON/OFF entries. The retained branches/worktrees are source
material, not an instruction to reset, delete or deploy them.
