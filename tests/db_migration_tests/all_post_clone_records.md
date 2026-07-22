# All records inserted or changed in `data/staging.db` after the production-clone

## Method

Diffed `data/staging.db` (current) against `data/staging.db.pre-030-apply.20260706T082037Z.bak` (a v23-era snapshot at 2026-07-06 08:20:37 UTC, taken right after the staging.db was cloned from production and before any 024+ migration ran). All records below were either absent in the pre-clone snapshot, or were row-UPDATEd in place by migration 030.

Excluded:
- `posts` (5,890 rows; pre-clone count = 5,890, no change — pre-existing data)
- Lookup-table families (`roles`, `post_type_keys`, `discourse_keys`, `nationalism_keys`, `sentiment_keys` and their `_labels` siblings) — none grew post-clone
- Pre-existing rows in changed tables (`brands` 1-11, `companies` 1-11, `accounts` 1-1522, `hf_orgs` 1-11, `brand_search_terms` none, `brand_keywords` 88 rows)

## Per-table delta

| Table | Pre-clone | Now | Δ | Source |
|---|---|---|---|---|
| brands | 12 | 27 | **+15** | 1 UPDATE + 14 INSERTs (9 from migration 024, 6 from migration 030) |
| companies | 11 | 20 | **+9** | migration 030 INSERTs |
| accounts | 1522 | 1571 | **+49** | U4 CLI seed-port |
| brands_accounts | 0 | 62 | **+62** | U4 CLI seed-port |
| brands_companies | 11 | 11 | **0** | no-op |
| hf_orgs | 11 | 22 | **+11** | U4 CLI seed-port |
| brand_search_terms | 0 | 72 | **+72** | U4 CLI seed-port |
| brand_keywords | 88 | 90 | **+2** | migration 029 (llama regex keywords) |

Total post-clone row count: **222 rows** (1 UPDATE + 221 INSERTs) across 8 tables.

---

## Section 1 — `brands` (1 UPDATE + 14 INSERTs)

### Row UPDATE (id = 12)

Before: `nickname = 'xiaomi_mimo'`. After (current state in staging.db):

| id | nickname | display_name | accent_color | is_sentinel | created_at | display_name_en | display_name_zh_cn |
|---|---|---|---|---|---|---|---|
| 12 | mimo | Xiaomi MiMo | #eab308 | 0 | 2026-06-19T00:00:00+00:00 | NULL | NULL |

### All post-clone brands (15 rows)

Includes the 1 UPDATEd row plus the 14 INSERTed rows. Schema columns become the table columns.

| id | nickname | display_name | accent_color | is_sentinel | created_at | display_name_en | display_name_zh_cn |
|---|---|---|---|---|---|---|---|
| 12 | mimo | Xiaomi MiMo | #eab308 | 0 | 2026-06-19T00:00:00+00:00 | NULL | NULL |
| 13 | llama | Meta Llama | #1877f2 | 0 | 2026-07-06 08:21:08 | Meta Llama | NULL |
| 14 | nemo_megatron | NVIDIA NeMo | #76b900 | 0 | 2026-07-06 08:21:08 | NVIDIA NeMo | NULL |
| 15 | doubao | ByteDance Doubao | #000000 | 0 | 2026-07-06 08:21:08 | ByteDance Doubao | 豆包 |
| 16 | yi | 01.AI Yi | #7c3aed | 0 | 2026-07-06 08:21:08 | 01.AI Yi | 零一万物 |
| 17 | sensechat | SenseTime SenseChat | #ff6b00 | 0 | 2026-07-06 08:21:08 | SenseTime SenseChat | 商汤日日新 |
| 18 | exaone | LG EXAONE | #a50034 | 0 | 2026-07-06 08:21:08 | LG EXAONE | NULL |
| 19 | kuaishou | Kuaishou KwaiYii | #ff4906 | 0 | 2026-07-06 08:21:08 | Kuaishou KwaiYii | 快意 |
| 20 | sakana_ai | Sakana AI | #1e40af | 0 | 2026-07-06 08:21:08 | Sakana AI | サカナAI |
| 21 | upstage | Upstage Solar | #22c55e | 0 | 2026-07-06 08:21:08 | Upstage Solar | 업스테이지 |
| 22 | chatglm | ChatGLM | #9ca3af | 0 | 2026-07-06 08:23:57 | ChatGLM | ChatGLM |
| 23 | sensenova | SenseNova | #9ca3af | 0 | 2026-07-06 08:23:57 | SenseNova | 日日新 |
| 24 | step | Step | #9ca3af | 0 | 2026-07-06 08:23:57 | Step | Step |
| 25 | kwaiyii | KwaiYii | #9ca3af | 0 | 2026-07-06 08:23:57 | KwaiYii | 快意 |
| 26 | wenxin | Wenxin / Wenxin | #9ca3af | 0 | 2026-07-06 08:23:57 | Wenxin | 文小言 |
| 27 | seed | Seed | #9ca3af | 0 | 2026-07-06 08:23:57 | Seed | Seed |

---

## Section 2 — `companies` (9 INSERTs)

| id | nickname | display_name | hq_country | created_at | display_name_en | display_name_zh_cn |
|---|---|---|---|---|---|---|
| 12 | meta | Meta | US | 2026-07-06 08:23:57 | Meta | Meta（元） |
| 13 | nvidia | NVIDIA | US | 2026-07-06 08:23:57 | NVIDIA | 英伟达 |
| 14 | bytedance | 字节跳动 | CN | 2026-07-06 08:23:57 | ByteDance | 字节跳动 |
| 15 | sensetime | 商汤科技 | CN | 2026-07-06 08:23:57 | SenseTime | 商汤科技 |
| 16 | lg_ai | LG AI연구원 | KR | 2026-07-06 08:23:57 | LG AI Research | LG AI研究院 |
| 17 | sakana | サカナAI | JP | 2026-07-06 08:23:57 | Sakana AI | Sakana AI |
| 18 | kuaishou_co | 快手科技 | CN | 2026-07-06 08:23:57 | Kuaishou Technology | 快手科技 |
| 19 | upstage_co | 업스테이지 | KR | 2026-07-06 08:23:57 | Upstage | Upstage |
| 20 | 01ai | 零一万物 | CN | 2026-07-06 08:23:57 | 01.AI | 零一万物 |

---

## Section 3 — `accounts` (49 INSERTs)

Note: every newly-ported account row has all of `display_name`, `bio`, `bio_fetched_at`, `source_query_ids`, `notes`, `bio_en`, `bio_zh_cn` empty/`NULL` — those columns were dropped by the U4 CLI script per the migration plan (the source's `bio`, `notes_raw_payload` were discarded at write time; `bio_en`/`bio_zh_cn` were set to `NULL`).

| id | accounts_id | handle | display_name | bio | bio_fetched_at | verified | bio_contains_brand | first_seen_at | last_seen_at | source_query_ids | notes | bio_en | bio_zh_cn |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1523 | 1034844617261248512 | AIatMeta | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1524 | 615818451 | alexandr_wang | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1525 | 1667249535519805451 | MistralAI | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1526 | 51091819 | arthurmensch | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1527 | 1148669001406529540 | sophiamyang | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1528 | 877952584333410305 | NVIDIAAIDev | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1529 | 740238495952736256 | NVIDIAAI | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1530 | 1753339277386342400 | Alibaba_Qwen | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1531 | 1899009772961357824 | Ali_TongyiLab | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1532 | 1513878350611238912 | xiong_hui_chen | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1533 | 1939556424906100736 | ErnieforDevs | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1534 | 1575735743502172162 | Paddlepaddle | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1535 | 1810933558703493120 | TencentHunyuan | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1536 | 1271552707464032256 | ShunyuYao12 | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1537 | 1856750484977324034 | DoubaoAI | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1538 | 1943470572450762752 | BytePlusGlobal | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1539 | 1714580962569588736 | deepseek_ai | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1540 | 1726486879456096256 | Zai_org | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1541 | 1931962509596246016 | ZhihuFrontier | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1542 | 1998992680332963840 | louszbd | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1543 | 1896810733423493120 | ZixuanLi_ | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1544 | 2023288069005422592 | cara_catowner | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1545 | 1158334988993142788 | CunxiangWang | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1546 | 1863959670169501696 | Kimi_Moonshot | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1547 | 1875078099538423808 | MiniMax_AI | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1548 | 2020841805148041217 | MiniMaxAgent | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1549 | 1831522735819771904 | VictorSuOrtiz | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1550 | 1926868815683497984 | RyanLeeMiniMax | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1551 | 1879314108723658752 | SkylerMiao7 | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1552 | 50940456 | kaifulee | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1553 | 1720108056871317504 | 01AI_Yi | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1554 | 1906594230002503680 | TheInclusionAI | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1555 | 1909081835776413696 | AntLingAGI | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1556 | 2013222786630914048 | robbyant_brain | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1557 | 1019503378517200897 | SenseTime_AI | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1558 | 40042569 | lindahua | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1559 | 1888791214864072705 | StepFun_ai | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1560 | 1404781008 | EileenTal | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1561 | 1914997266890579968 | XiaomiMiMo | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1562 | 2066799363746340864 | XiaomiMiMoDevs | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1563 | 1721721873095155712 | _LuoFuli | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1564 | 1513396084197928961 | LG_AI_Research | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1565 | 730823445752258562 | honglaklee | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1566 | 218811492 | SakanaAILabs | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1567 | 2895499182 | hardmaru | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1568 | 14223925 | Stefania_druga | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1569 | 1799294856822673408 | Kling_ai | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1570 | 1307324353894215682 | upstageai | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |
| 1571 | 94735585 | echojuliett | NULL | NULL | NULL | 0 | NULL | 2026-07-01 15:06:46.248525+09 | 2026-07-01 15:06:46.248525+09 | NULL | NULL | NULL | NULL |

---

## Section 4 — `brands_accounts` (62 INSERTs)

All 62 rows have `added_at = 2026-07-01 15:06:46.248525+09`. Pre-clone snapshot had 0 rows. Role columns: `1=community`, `2=official`, `3=staff`. Brand/account FK columns are INTEGER surrogate ids — full slug/handle resolution lives in Sections 1 and 3.

| brand_id | accounts_id | role_id | added_at |
|---|---|---|---|
| 2 | 1539 | 2 | 2026-07-01 15:06:46.248525+09 |
| 3 | 1533 | 2 | 2026-07-01 15:06:46.248525+09 |
| 3 | 1534 | 2 | 2026-07-01 15:06:46.248525+09 |
| 4 | 1540 | 2 | 2026-07-01 15:06:46.248525+09 |
| 4 | 1541 | 2 | 2026-07-01 15:06:46.248525+09 |
| 4 | 1542 | 3 | 2026-07-01 15:06:46.248525+09 |
| 4 | 1543 | 3 | 2026-07-01 15:06:46.248525+09 |
| 4 | 1544 | 3 | 2026-07-01 15:06:46.248525+09 |
| 4 | 1545 | 3 | 2026-07-01 15:06:46.248525+09 |
| 5 | 1535 | 2 | 2026-07-01 15:06:46.248525+09 |
| 5 | 1536 | 3 | 2026-07-01 15:06:46.248525+09 |
| 6 | 1554 | 2 | 2026-07-01 15:06:46.248525+09 |
| 6 | 1555 | 2 | 2026-07-01 15:06:46.248525+09 |
| 6 | 1556 | 2 | 2026-07-01 15:06:46.248525+09 |
| 7 | 1547 | 2 | 2026-07-01 15:06:46.248525+09 |
| 7 | 1548 | 2 | 2026-07-01 15:06:46.248525+09 |
| 7 | 1549 | 3 | 2026-07-01 15:06:46.248525+09 |
| 7 | 1550 | 3 | 2026-07-01 15:06:46.248525+09 |
| 7 | 1551 | 3 | 2026-07-01 15:06:46.248525+09 |
| 8 | 1525 | 2 | 2026-07-01 15:06:46.248525+09 |
| 8 | 1526 | 3 | 2026-07-01 15:06:46.248525+09 |
| 8 | 1527 | 3 | 2026-07-01 15:06:46.248525+09 |
| 9 | 1546 | 2 | 2026-07-01 15:06:46.248525+09 |
| 10 | 1530 | 2 | 2026-07-01 15:06:46.248525+09 |
| 10 | 1531 | 2 | 2026-07-01 15:06:46.248525+09 |
| 10 | 1532 | 3 | 2026-07-01 15:06:46.248525+09 |
| 11 | 1559 | 2 | 2026-07-01 15:06:46.248525+09 |
| 11 | 1560 | 3 | 2026-07-01 15:06:46.248525+09 |
| 12 | 1561 | 2 | 2026-07-01 15:06:46.248525+09 |
| 12 | 1562 | 2 | 2026-07-01 15:06:46.248525+09 |
| 12 | 1563 | 3 | 2026-07-01 15:06:46.248525+09 |
| 13 | 1523 | 2 | 2026-07-01 15:06:46.248525+09 |
| 13 | 1524 | 3 | 2026-07-01 15:06:46.248525+09 |
| 14 | 1528 | 2 | 2026-07-01 15:06:46.248525+09 |
| 14 | 1529 | 2 | 2026-07-01 15:06:46.248525+09 |
| 15 | 1537 | 2 | 2026-07-01 15:06:46.248525+09 |
| 15 | 1538 | 2 | 2026-07-01 15:06:46.248525+09 |
| 16 | 1552 | 3 | 2026-07-01 15:06:46.248525+09 |
| 16 | 1553 | 2 | 2026-07-01 15:06:46.248525+09 |
| 17 | 1557 | 2 | 2026-07-01 15:06:46.248525+09 |
| 17 | 1558 | 3 | 2026-07-01 15:06:46.248525+09 |
| 18 | 1564 | 2 | 2026-07-01 15:06:46.248525+09 |
| 18 | 1565 | 3 | 2026-07-01 15:06:46.248525+09 |
| 19 | 1569 | 2 | 2026-07-01 15:06:46.248525+09 |
| 20 | 1566 | 2 | 2026-07-01 15:06:46.248525+09 |
| 20 | 1567 | 3 | 2026-07-01 15:06:46.248525+09 |
| 20 | 1568 | 3 | 2026-07-01 15:06:46.248525+09 |
| 21 | 1570 | 2 | 2026-07-01 15:06:46.248525+09 |
| 21 | 1571 | 3 | 2026-07-01 15:06:46.248525+09 |
| 22 | 1540 | 2 | 2026-07-01 15:06:46.248525+09 |
| 22 | 1541 | 2 | 2026-07-01 15:06:46.248525+09 |
| 22 | 1542 | 3 | 2026-07-01 15:06:46.248525+09 |
| 22 | 1543 | 3 | 2026-07-01 15:06:46.248525+09 |
| 22 | 1544 | 3 | 2026-07-01 15:06:46.248525+09 |
| 22 | 1545 | 3 | 2026-07-01 15:06:46.248525+09 |
| 23 | 1557 | 2 | 2026-07-01 15:06:46.248525+09 |
| 23 | 1558 | 3 | 2026-07-01 15:06:46.248525+09 |
| 25 | 1569 | 2 | 2026-07-01 15:06:46.248525+09 |
| 26 | 1533 | 2 | 2026-07-01 15:06:46.248525+09 |
| 26 | 1534 | 2 | 2026-07-01 15:06:46.248525+09 |
| 27 | 1537 | 2 | 2026-07-01 15:06:46.248525+09 |
| 27 | 1538 | 2 | 2026-07-01 15:06:46.248525+09 |

---

## Section 5 — `brands_companies` (UNCHANGED — 11 rows, no-op)

Pre-clone had these 11 rows; current `data/staging.db` has the same 11 rows verbatim. No post-clone insert/update; included here for completeness so the doc is exhaustive.

| brand_id | company_id | ownership_pct |
|---|---|---|
| 10 | 1 | 1.0 |
| 3 | 2 | 1.0 |
| 2 | 3 | 1.0 |
| 6 | 4 | 1.0 |
| 7 | 5 | 1.0 |
| 8 | 6 | 1.0 |
| 9 | 7 | 1.0 |
| 11 | 8 | 1.0 |
| 5 | 9 | 1.0 |
| 12 | 10 | 1.0 |
| 4 | 11 | 1.0 |

---

## Section 6 — `hf_orgs` (22 rows total; 11 unchanged pre-clone + 11 INSERTs)

Pre-clone had 11 rows (ids 1-11); 11 new rows (ids 12, 14, 18, 19, 21, 24, 26, 29, 30, 31, 32) were inserted post-clone. Listed together so the doc is exhaustive.

| id | namespace | company_id | confirmed | discovered_via | added_at |
|---|---|---|---|---|---|
| 1 | MiniMaxAI | 5 | 1 | curated | 2026-06-22T18:58:00+00:00 |
| 2 | Qwen | 1 | 1 | curated | 2026-06-22T18:58:00+00:00 |
| 3 | THUDM | 11 | 1 | curated | 2026-06-22T18:58:00+00:00 |
| 4 | XiaomiMiMo | 10 | 1 | curated | 2026-06-22T18:58:00+00:00 |
| 5 | baidu | 2 | 1 | curated | 2026-06-22T18:58:00+00:00 |
| 6 | deepseek-ai | 3 | 1 | curated | 2026-06-22T18:58:00+00:00 |
| 7 | inclusionAI | 4 | 1 | curated | 2026-06-22T18:58:00+00:00 |
| 8 | mistralai | 6 | 1 | curated | 2026-06-22T18:58:00+00:00 |
| 9 | moonshotai | 7 | 1 | curated | 2026-06-22T18:58:00+00:00 |
| 10 | stepfun-ai | 8 | 1 | curated | 2026-06-22T18:58:00+00:00 |
| 11 | tencent | 9 | 1 | curated | 2026-06-22T18:58:00+00:00 |
| 12 | meta-llama | 12 | 0 | csv_seed | 2026-07-01 15:21:05.034933+09 |
| 14 | nvidia | 13 | 0 | csv_seed | 2026-07-01 15:21:05.034933+09 |
| 18 | bytedance | 14 | 0 | csv_seed | 2026-07-01 15:21:05.034933+09 |
| 19 | bytedance-research | 14 | 0 | csv_seed | 2026-07-01 15:21:05.034933+09 |
| 21 | zai-org | 11 | 0 | csv_seed | 2026-07-01 15:21:05.034933+09 |
| 24 | 01-ai | 20 | 0 | csv_seed | 2026-07-01 15:21:05.034933+09 |
| 26 | SenseTime | 15 | 0 | csv_seed | 2026-07-01 15:21:05.034933+09 |
| 29 | LGAI-EXAONE | 16 | 0 | csv_seed | 2026-07-01 15:21:05.034933+09 |
| 30 | SakanaAI | 17 | 0 | csv_seed | 2026-07-01 15:21:05.034933+09 |
| 31 | Kuaishou | 18 | 0 | csv_seed | 2026-07-01 15:21:05.034933+09 |
| 32 | upstage | 19 | 0 | csv_seed | 2026-07-01 15:21:05.034933+09 |

---

## Section 7 — `brand_search_terms` (72 INSERTs)

All 72 rows have `added_at = 2026-06-30 21:34:08.919355+09`. Pre-clone snapshot had 0 rows.

| brand_id | term | added_at |
|---|---|---|
| 2 | DeepSeek-R1 | 2026-06-30 21:34:08.919355+09 |
| 2 | DeepSeek-V3 | 2026-06-30 21:34:08.919355+09 |
| 2 | R1 | 2026-06-30 21:34:08.919355+09 |
| 2 | RAG | 2026-06-30 21:34:08.919355+09 |
| 2 | deepseek | 2026-06-30 21:34:08.919355+09 |
| 2 | deepseek-coder | 2026-06-30 21:34:08.919355+09 |
| 2 | deepseek-v2 | 2026-06-30 21:34:08.919355+09 |
| 2 | 推理 | 2026-06-30 21:34:08.919355+09 |
| 2 | 深度求索 | 2026-06-30 21:34:08.919355+09 |
| 4 | ChatGLM | 2026-06-30 21:34:08.919355+09 |
| 4 | CodeGeeX | 2026-06-30 21:34:08.919355+09 |
| 4 | CogAgent | 2026-06-30 21:34:08.919355+09 |
| 4 | CogVLM | 2026-06-30 21:34:08.919355+09 |
| 4 | CogVideoX | 2026-06-30 21:34:08.919355+09 |
| 4 | GLM | 2026-06-30 21:34:08.919355+09 |
| 4 | GLM-130B | 2026-06-30 21:34:08.919355+09 |
| 4 | GLM-4 | 2026-06-30 21:34:08.919355+09 |
| 4 | GLM-4V | 2026-06-30 21:34:08.919355+09 |
| 4 | GLM-Z1 | 2026-06-30 21:34:08.919355+09 |
| 4 | glm-4b | 2026-06-30 21:34:08.919355+09 |
| 4 | 智谱 | 2026-06-30 21:34:08.919355+09 |
| 6 | InclusionAI | 2026-06-30 21:34:08.919355+09 |
| 6 | Yi | 2026-06-30 21:34:08.919355+09 |
| 6 | Yi-34B | 2026-06-30 21:34:08.919355+09 |
| 6 | yi-1.5 | 2026-06-30 21:34:08.919355+09 |
| 6 | yi-lightning | 2026-06-30 21:34:08.919355+09 |
| 6 | yi-vision | 2026-06-30 21:34:08.919355+09 |
| 6 | 万知 | 2026-06-30 21:34:08.919355+09 |
| 6 | 零一万物 | 2026-06-30 21:34:08.919355+09 |
| 7 | Hailuo | 2026-06-30 21:34:08.919355+09 |
| 7 | M2.5 | 2026-06-30 21:34:08.919355+09 |
| 7 | M2.7 | 2026-06-30 21:34:08.919355+09 |
| 7 | M3 | 2026-06-30 21:34:08.919355+09 |
| 7 | M3.0 | 2026-06-30 21:34:08.919355+09 |
| 7 | minimax | 2026-06-30 21:34:08.919355+09 |
| 7 | minimax-agent | 2026-06-30 21:34:08.919355+09 |
| 7 | minimax-coding | 2026-06-30 21:34:08.919355+09 |
| 7 | minimax-work | 2026-06-30 21:34:08.919355+09 |
| 7 | 智能 | 2026-06-30 21:34:08.919355+09 |
| 7 | 海螺 | 2026-06-30 21:34:08.919355+09 |
| 7 | 海螺ai | 2026-06-30 21:34:08.919355+09 |
| 9 | Kimi K2 | 2026-06-30 21:34:08.919355+09 |
| 9 | Kimi k1.5 | 2026-06-30 21:34:08.919355+09 |
| 9 | Kimi-Audio | 2026-06-30 21:34:08.919355+09 |
| 9 | Moonshot AI | 2026-06-30 21:34:08.919355+09 |
| 9 | kimi | 2026-06-30 21:34:08.919355+09 |
| 9 | kimi-k2 | 2026-06-30 21:34:08.919355+09 |
| 9 | kimi-researcher | 2026-06-30 21:34:08.919355+09 |
| 9 | kimi-vision | 2026-06-30 21:34:08.919355+09 |
| 9 | moonshot | 2026-06-30 21:34:08.919355+09 |
| 9 | moonshot-v1 | 2026-06-30 21:34:08.919355+09 |
| 9 | 月之暗面 | 2026-06-30 21:34:08.919355+09 |
| 10 | QwQ | 2026-06-30 21:34:08.919355+09 |
| 10 | Qwen-Audio | 2026-06-30 21:34:08.919355+09 |
| 10 | Qwen-Code | 2026-06-30 21:34:08.919355+09 |
| 10 | Qwen2-VL | 2026-06-30 21:34:08.919355+09 |
| 10 | Qwen2.5-VL | 2026-06-30 21:34:08.919355+09 |
| 10 | qwen | 2026-06-30 21:34:08.919355+09 |
| 10 | qwen-vl | 2026-06-30 21:34:08.919355+09 |
| 10 | qwen2 | 2026-06-30 21:34:08.919355+09 |
| 10 | qwen2.5 | 2026-06-30 21:34:08.919355+09 |
| 10 | qwen3 | 2026-06-30 21:34:08.919355+09 |
| 10 | 千问 | 2026-06-30 21:34:08.919355+09 |
| 10 | 通义 | 2026-06-30 21:34:08.919355+09 |
| 10 | 通义千问 | 2026-06-30 21:34:08.919355+09 |
| 12 | Xiaomi | 2026-06-30 21:34:08.919355+09 |
| 12 | Xiaomi MiMo | 2026-06-30 21:34:08.919355+09 |
| 12 | XiaomiMiMo | 2026-06-30 21:34:08.919355+09 |
| 12 | mimo | 2026-06-30 21:34:08.919355+09 |
| 12 | mimo-7b | 2026-06-30 21:34:08.919355+09 |
| 12 | mimo-vl | 2026-06-30 21:34:08.919355+09 |
| 12 | 小米 | 2026-06-30 21:34:08.919355+09 |

> **Caveat on `added_at`**: every `brand_search_terms.added_at` reads `2026-06-30 21:34:08.919355+09`, which is 6 days **before** the 2026-07-06 08:20:37 UTC clone moment. The pre-clone snapshot has 0 rows in this table — pre-clone by set difference these are all post-clone rows. The `added_at` likely came from the U4 seed-port script which carried forward a `seeded_at` value from the source-of-truth's earlier seed batch.

---

## Section 8 — `brand_keywords` (2 INSERTs)

Pre-clone had 88 rows (excluded); these 2 new rows were added by migration 029.

| brand_id | pattern | is_regex | added_at |
|---|---|---|---|
| llama | Open[- ]source[- ]Llama | 1 | 2026-07-06 08:21:08 |
| llama | open[- ]weights[- ]Llama | 1 | 2026-07-06 08:21:08 |

---

## Excluded: `posts` (5,890 rows, pre-clone data)

The 5,890 rows in `posts` exist pre-clone (5,890 → 5,890, no change) and were excluded per your direction.

## Excluded: pre-existing rows in changed tables

- `brands` ids 1-11 (12 brands) — unchanged.
- `companies` ids 1-11 (11 companies) — unchanged.
- `accounts` ids 1-1522 (1,522 accounts) — unchanged.
- `brands_accounts` — pre-clone had 0 rows.
- `brands_companies` — same 11 rows pre/post clone (listed in Section 5).
- `hf_orgs` ids 1-11 (11 rows) — unchanged (listed in Section 6 alongside the 11 new rows).
- `brand_search_terms` — pre-clone had 0 rows.
- `brand_keywords` — 88 pre-existing rows excluded (new rows are the 2 listed in Section 8).

## Excluded: lookup-table families

The 5 lookup-table families (`roles`, `post_type_keys`, `discourse_keys`, `nationalism_keys`, `sentiment_keys` and their `_labels` siblings) were unchanged post-clone. Pre-clone row counts are intact.

---

## Provenance

Records in this file were diffed from `data/staging.db` (current) against `data/staging.db.pre-030-apply.20260706T082037Z.bak` (the v23-era pre-clone snapshot). The staging DB was a one-shot research artifact; it was **retired 2026-07-07** after the production rollout in `docs/plans/2026-07-07-001-feat-push-staging-changes-to-production-plan.md` brought `data/x_monitoring.db` to the same row state. The archived DB and the v23-era baseline snapshot live at `data/staging_archive/` (see `data/staging_archive/RETIRED.md`).
