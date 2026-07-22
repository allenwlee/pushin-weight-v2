# Migration 030 — `030_brand_rename_to_pushin_weight_slugs.sql`

> Dumped directly from `data/staging.db` on 2026-07-07 via `sqlite3 -header`.
> 18 records touched in total: **3 brand renames in place** (UPDATE), **6 new brand rows** (INSERT), **9 new company rows** (INSERT).
> The migration script itself lives at `x_monitor/migrations/030_brand_rename_to_pushin_weight_slugs.sql`.

> **Note on relationship tables**: migration 030 only touches `brands` and `companies`. The 3 relationship tables below — `brands_companies` (11 rows), `brands_accounts` (62 rows), `hf_orgs` (22 rows) — were populated by **U4 (CLI seed-port script)**, not 030. They live here because the staging.db state reflects U4's effective output and they're the join tables that connect everything 030 created. Listed verbatim with FK labels resolved.

## Section 1 — 3 brand renames in place (UPDATE)

Schema: `brands(id, nickname, display_name, accent_color, is_sentinel, created_at, display_name_en, display_name_zh_cn)`

Source `staging.db` snapshot — these are the post-rename rows:

```
id=12   nickname="mimo"           display_name="Xiaomi MiMo" accent_color="#eab308" is_sentinel=0 created_at="2026-06-19T00:00:00+00:00" display_name_en=NULL             display_name_zh_cn=NULL
id=14   nickname="nemo_megatron"  display_name="NVIDIA NeMo" accent_color="#76b900" is_sentinel=0 created_at="2026-07-06 08:21:08"          display_name_en="NVIDIA NeMo"  display_name_zh_cn=NULL
id=20   nickname="sakana_ai"      display_name="Sakana AI"   accent_color="#1e40af" is_sentinel=0 created_at="2026-07-06 08:21:08"          display_name_en="Sakana AI"    display_name_zh_cn="サカナAI"
```

Pre-rename values (for context — these are what the column held BEFORE migration 030 ran):

```
id=12   nickname="xiaomi_mimo"    display_name="Xiaomi MiMo" accent_color="#eab308" is_sentinel=0 created_at="2026-06-19T00:00:00+00:00" display_name_en=NULL             display_name_zh_cn=NULL
id=14   nickname="nvidia_nemo"    display_name="NVIDIA NeMo" accent_color="#76b900" is_sentinel=0 created_at="2026-07-06 08:21:08"          display_name_en="NVIDIA NeMo"  display_name_zh_cn=NULL
id=20   nickname="sakana"         display_name="Sakana AI"   accent_color="#1e40af" is_sentinel=0 created_at="2026-07-06 08:21:08"          display_name_en="Sakana AI"    display_name_zh_cn="サカナAI"
```

## Section 2 — 6 new brand rows (INSERT OR IGNORE)

Schema: `brands(id, nickname, display_name, accent_color, is_sentinel, created_at, display_name_en, display_name_zh_cn)`

Source `staging.db` snapshot — these are the 6 newly inserted rows:

```
id=22   nickname="chatglm"    display_name="ChatGLM"          accent_color="#9ca3af" is_sentinel=0 created_at="2026-07-06 08:23:57" display_name_en="ChatGLM"   display_name_zh_cn="ChatGLM"
id=23   nickname="sensenova"  display_name="SenseNova"        accent_color="#9ca3af" is_sentinel=0 created_at="2026-07-06 08:23:57" display_name_en="SenseNova" display_name_zh_cn="日日新"
id=24   nickname="step"       display_name="Step"             accent_color="#9ca3af" is_sentinel=0 created_at="2026-07-06 08:23:57" display_name_en="Step"      display_name_zh_cn="Step"
id=25   nickname="kwaiyii"    display_name="KwaiYii"          accent_color="#9ca3af" is_sentinel=0 created_at="2026-07-06 08:23:57" display_name_en="KwaiYii"   display_name_zh_cn="快意"
id=26   nickname="wenxin"     display_name="Wenxin / Wenxin"  accent_color="#9ca3af" is_sentinel=0 created_at="2026-07-06 08:23:57" display_name_en="Wenxin"    display_name_zh_cn="文小言"
id=27   nickname="seed"       display_name="Seed"             accent_color="#9ca3af" is_sentinel=0 created_at="2026-07-06 08:23:57" display_name_en="Seed"      display_name_zh_cn="Seed"
```

## Section 3 — 9 new company rows (INSERT OR IGNORE)

Schema: `companies(id, nickname, display_name, hq_country, created_at, display_name_en, display_name_zh_cn)`

Source `staging.db` snapshot — these are the 9 newly inserted rows:

```
id=12   nickname="meta"        display_name="Meta"              hq_country="US" created_at="2026-07-06 08:23:57" display_name_en="Meta"                     display_name_zh_cn="Meta（元）"
id=13   nickname="nvidia"      display_name="NVIDIA"            hq_country="US" created_at="2026-07-06 08:23:57" display_name_en="NVIDIA"                   display_name_zh_cn="英伟达"
id=14   nickname="bytedance"   display_name="字节跳动"          hq_country="CN" created_at="2026-07-06 08:23:57" display_name_en="ByteDance"                display_name_zh_cn="字节跳动"
id=15   nickname="sensetime"   display_name="商汤科技"          hq_country="CN" created_at="2026-07-06 08:23:57" display_name_en="SenseTime"                display_name_zh_cn="商汤科技"
id=16   nickname="lg_ai"       display_name="LG AI연구원"       hq_country="KR" created_at="2026-07-06 08:23:57" display_name_en="LG AI Research"           display_name_zh_cn="LG AI研究院"
id=17   nickname="sakana"      display_name="サカナAI"          hq_country="JP" created_at="2026-07-06 08:23:57" display_name_en="Sakana AI"                display_name_zh_cn="Sakana AI"
id=18   nickname="kuaishou_co" display_name="快手科技"          hq_country="CN" created_at="2026-07-06 08:23:57" display_name_en="Kuaishou Technology"      display_name_zh_cn="快手科技"
id=19   nickname="upstage_co"  display_name="업스테이지"        hq_country="KR" created_at="2026-07-06 08:23:57" display_name_en="Upstage"                  display_name_zh_cn="Upstage"
id=20   nickname="01ai"        display_name="零一万物"          hq_country="CN" created_at="2026-07-06 08:23:57" display_name_en="01.AI"                     display_name_zh_cn="零一万物"
```

## Lookup maps (for FK resolution in sections 4–6)

### brands id → nickname

```
id=1  _unattributed     id=14 nemo_megatron    (renamed by 030)
id=2  deepseek          id=15 doubao
id=3  ernie             id=16 yi
id=4  glm               id=17 sensechat
id=5  hunyuan           id=18 exaone
id=6  inclusionai       id=19 kuaishou
id=7  minimax           id=20 sakana_ai        (renamed by 030)
id=8  mistral           id=21 upstage
id=9  moonshot_kimi     id=22 chatglm          (new from 030)
id=10 qwen              id=23 sensenova        (new from 030)
id=11 stepfun           id=24 step             (new from 030)
id=12 mimo              (renamed by 030)       id=25 kwaiyii         (new from 030)
id=13 llama             id=26 wenxin           (new from 030)
                       id=27 seed             (new from 030)
```

### companies id → nickname

```
id=1  alibaba         id=11 zhipu
id=2  baidu           id=12 meta          (new from 030)
id=3  deepseek_co     id=13 nvidia        (new from 030)
id=4  inclusion_ai    id=14 bytedance     (new from 030)
id=5  minimax         id=15 sensetime     (new from 030)
id=6  mistral_ai      id=16 lg_ai         (new from 030)
id=7  moonshot        id=17 sakana        (new from 030)
id=8  stepfun_inc     id=18 kuaishou_co   (new from 030)
id=9  tencent         id=19 upstage_co    (new from 030)
id=10 xiaomi          id=20 01ai          (new from 030)
```

### roles id → key

```
id=1 community  id=2 official  id=3 staff
```

## Section 4 — `brands_companies` (11 rows)

Schema: `brands_companies(brand_id INTEGER FK→brands.id, company_id INTEGER FK→companies.id, ownership_pct REAL)`

Source `staging.db` snapshot:

```
brand_id=10  (qwen)         → company_id=1   (alibaba)         ownership_pct=1.0
brand_id=3   (ernie)        → company_id=2   (baidu)           ownership_pct=1.0
brand_id=2   (deepseek)     → company_id=3   (deepseek_co)     ownership_pct=1.0
brand_id=6   (inclusionai)  → company_id=4   (inclusion_ai)    ownership_pct=1.0
brand_id=7   (minimax)      → company_id=5   (minimax)         ownership_pct=1.0
brand_id=8   (mistral)      → company_id=6   (mistral_ai)      ownership_pct=1.0
brand_id=9   (moonshot_kimi)→ company_id=7   (moonshot)        ownership_pct=1.0
brand_id=11  (stepfun)      → company_id=8   (stepfun_inc)     ownership_pct=1.0
brand_id=5   (hunyuan)      → company_id=9   (tencent)         ownership_pct=1.0
brand_id=12  (mimo)         → company_id=10  (xiaomi)          ownership_pct=1.0
brand_id=4   (glm)          → company_id=11  (zhipu)           ownership_pct=1.0
```

## Section 5 — `brands_accounts` (62 rows)

Schema: `brands_accounts(brand_id INTEGER FK→brands.id, accounts_id INTEGER FK→accounts.id, role_id INTEGER FK→roles.id, added_at TEXT)`

Source `staging.db` snapshot — 62 rows, ordered by `brand_id, accounts_id`:

```
brand_id=2   (deepseek)         accounts_id=1539  handle=deepseek_ai       role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=3   (ernie)            accounts_id=1533  handle=ErnieforDevs      role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=3   (ernie)            accounts_id=1534  handle=Paddlepaddle      role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=4   (glm)              accounts_id=1540  handle=Zai_org           role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=4   (glm)              accounts_id=1541  handle=ZhihuFrontier     role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=4   (glm)              accounts_id=1542  handle=louszbd           role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=4   (glm)              accounts_id=1543  handle=ZixuanLi_         role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=4   (glm)              accounts_id=1544  handle=cara_catowner     role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=4   (glm)              accounts_id=1545  handle=CunxiangWang      role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=5   (hunyuan)          accounts_id=1535  handle=TencentHunyuan    role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=5   (hunyuan)          accounts_id=1536  handle=ShunyuYao12       role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=6   (inclusionai)      accounts_id=1554  handle=TheInclusionAI    role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=6   (inclusionai)      accounts_id=1555  handle=AntLingAGI        role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=6   (inclusionai)      accounts_id=1556  handle=robbyant_brain    role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=7   (minimax)          accounts_id=1547  handle=MiniMax_AI        role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=7   (minimax)          accounts_id=1548  handle=MiniMaxAgent      role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=7   (minimax)          accounts_id=1549  handle=VictorSuOrtiz     role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=7   (minimax)          accounts_id=1550  handle=RyanLeeMiniMax    role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=7   (minimax)          accounts_id=1551  handle=SkylerMiao7       role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=8   (mistral)          accounts_id=1525  handle=MistralAI         role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=8   (mistral)          accounts_id=1526  handle=arthurmensch      role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=8   (mistral)          accounts_id=1527  handle=sophiamyang       role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=9   (moonshot_kimi)    accounts_id=1546  handle=Kimi_Moonshot     role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=10  (qwen)             accounts_id=1530  handle=Alibaba_Qwen      role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=10  (qwen)             accounts_id=1531  handle=Ali_TongyiLab     role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=10  (qwen)             accounts_id=1532  handle=xiong_hui_chen    role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=11  (stepfun)          accounts_id=1559  handle=StepFun_ai        role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=11  (stepfun)          accounts_id=1560  handle=EileenTal         role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=12  (mimo)             accounts_id=1561  handle=XiaomiMiMo        role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=12  (mimo)             accounts_id=1562  handle=XiaomiMiMoDevs    role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=12  (mimo)             accounts_id=1563  handle=_LuoFuli           role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=13  (llama)            accounts_id=1523  handle=AIatMeta           role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=13  (llama)            accounts_id=1524  handle=alexandr_wang     role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=14  (nemo_megatron)    accounts_id=1528  handle=NVIDIAAIDev       role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=14  (nemo_megatron)    accounts_id=1529  handle=NVIDIAAI          role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=15  (doubao)           accounts_id=1537  handle=DoubaoAI          role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=15  (doubao)           accounts_id=1538  handle=BytePlusGlobal    role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=16  (yi)               accounts_id=1552  handle=kaifulee          role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=16  (yi)               accounts_id=1553  handle=01AI_Yi           role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=17  (sensechat)        accounts_id=1557  handle=SenseTime_AI      role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=17  (sensechat)        accounts_id=1558  handle=lindahua          role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=18  (exaone)           accounts_id=1564  handle=LG_AI_Research    role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=18  (exaone)           accounts_id=1565  handle=honglaklee        role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=19  (kuaishou)         accounts_id=1569  handle=Kling_ai          role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=20  (sakana_ai)        accounts_id=1566  handle=SakanaAILabs      role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=20  (sakana_ai)        accounts_id=1567  handle=hardmaru          role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=20  (sakana_ai)        accounts_id=1568  handle=Stefania_druga    role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=21  (upstage)          accounts_id=1570  handle=upstageai         role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=21  (upstage)          accounts_id=1571  handle=echojuliett       role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=22  (chatglm)          accounts_id=1540  handle=Zai_org           role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=22  (chatglm)          accounts_id=1541  handle=ZhihuFrontier     role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=22  (chatglm)          accounts_id=1542  handle=louszbd           role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=22  (chatglm)          accounts_id=1543  handle=ZixuanLi_         role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=22  (chatglm)          accounts_id=1544  handle=cara_catowner     role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=22  (chatglm)          accounts_id=1545  handle=CunxiangWang      role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=23  (sensenova)        accounts_id=1557  handle=SenseTime_AI      role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=23  (sensenova)        accounts_id=1558  handle=lindahua          role_id=3  (staff)     added_at="2026-07-01 15:06:46.248525+09"
brand_id=25  (kwaiyii)          accounts_id=1569  handle=Kling_ai          role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=26  (wenxin)           accounts_id=1533  handle=ErnieforDevs      role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=26  (wenxin)           accounts_id=1534  handle=Paddlepaddle      role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=27  (seed)             accounts_id=1537  handle=DoubaoAI          role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
brand_id=27  (seed)             accounts_id=1538  handle=BytePlusGlobal    role_id=2  (official)  added_at="2026-07-01 15:06:46.248525+09"
```

## Section 6 — `hf_orgs` (22 rows)

Schema: `hf_orgs(id TEXT PRIMARY KEY, company_id INTEGER FK→companies.id, confirmed INTEGER, discovered_via TEXT, added_at TEXT)`

Source `staging.db` snapshot:

```
id=1   (HF_org)         → company_id=5   (minimax)         confirmed=1  discovered_via="curated"   added_at="2026-06-22T18:58:00+00:00"
id=2   (HF_org)         → company_id=1   (alibaba)         confirmed=1  discovered_via="curated"   added_at="2026-06-22T18:58:00+00:00"
id=3   (HF_org)         → company_id=11  (zhipu)           confirmed=1  discovered_via="curated"   added_at="2026-06-22T18:58:00+00:00"
id=4   (HF_org)         → company_id=10  (xiaomi)          confirmed=1  discovered_via="curated"   added_at="2026-06-22T18:58:00+00:00"
id=5   (HF_org)         → company_id=2   (baidu)           confirmed=1  discovered_via="curated"   added_at="2026-06-22T18:58:00+00:00"
id=6   (HF_org)         → company_id=3   (deepseek_co)     confirmed=1  discovered_via="curated"   added_at="2026-06-22T18:58:00+00:00"
id=7   (HF_org)         → company_id=4   (inclusion_ai)    confirmed=1  discovered_via="curated"   added_at="2026-06-22T18:58:00+00:00"
id=8   (HF_org)         → company_id=6   (mistral_ai)      confirmed=1  discovered_via="curated"   added_at="2026-06-22T18:58:00+00:00"
id=9   (HF_org)         → company_id=7   (moonshot)        confirmed=1  discovered_via="curated"   added_at="2026-06-22T18:58:00+00:00"
id=10  (HF_org)         → company_id=8   (stepfun_inc)     confirmed=1  discovered_via="curated"   added_at="2026-06-22T18:58:00+00:00"
id=11  (HF_org)         → company_id=9   (tencent)         confirmed=1  discovered_via="curated"   added_at="2026-06-22T18:58:00+00:00"
id=12  (HF_org)         → company_id=12  (meta)            confirmed=0  discovered_via="csv_seed"  added_at="2026-07-01 15:21:05.034933+09"
id=14  (HF_org)         → company_id=13  (nvidia)          confirmed=0  discovered_via="csv_seed"  added_at="2026-07-01 15:21:05.034933+09"
id=18  (HF_org)         → company_id=14  (bytedance)       confirmed=0  discovered_via="csv_seed"  added_at="2026-07-01 15:21:05.034933+09"
id=19  (HF_org)         → company_id=14  (bytedance)       confirmed=0  discovered_via="csv_seed"  added_at="2026-07-01 15:21:05.034933+09"
id=21  (HF_org)         → company_id=11  (zhipu)           confirmed=0  discovered_via="csv_seed"  added_at="2026-07-01 15:21:05.034933+09"
id=24  (HF_org)         → company_id=20  (01ai)            confirmed=0  discovered_via="csv_seed"  added_at="2026-07-01 15:21:05.034933+09"
id=26  (HF_org)         → company_id=15  (sensetime)       confirmed=0  discovered_via="csv_seed"  added_at="2026-07-01 15:21:05.034933+09"
id=29  (HF_org)         → company_id=16  (lg_ai)           confirmed=0  discovered_via="csv_seed"  added_at="2026-07-01 15:21:05.034933+09"
id=30  (HF_org)         → company_id=17  (sakana)          confirmed=0  discovered_via="csv_seed"  added_at="2026-07-01 15:21:05.034933+09"
id=31  (HF_org)         → company_id=18  (kuaishou_co)     confirmed=0  discovered_via="csv_seed"  added_at="2026-07-01 15:21:05.034933+09"
id=32  (HF_org)         → company_id=19  (upstage_co)      confirmed=0  discovered_via="csv_seed"  added_at="2026-07-01 15:21:05.034933+09"
```


---

## Provenance

Records in this file were dumped directly from `data/staging.db` (snapshot at 2026-07-07). The staging DB was a one-shot research artifact cloned from production to develop and validate migration 030 + the U4 pushin_weight seed-port script. It was **retired 2026-07-07** after the production rollout in `docs/plans/2026-07-07-001-feat-push-staging-changes-to-production-plan.md` brought `data/x_monitoring.db` to the same row state. The archived DB lives at `data/staging_archive/staging.db` for inspection (see `data/staging_archive/RETIRED.md`).
