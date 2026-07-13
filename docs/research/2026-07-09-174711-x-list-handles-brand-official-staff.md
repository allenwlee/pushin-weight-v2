# X list handles → brand + official/staff (Table 6)

### written by Grok 4.3

**Date:** 2026-07-09 (JST)  
**Source list members:** selected handles from X list export  
**Brand registry:** `docs/reference/lookup-tables.md` §6 (`brands` / `companies`, enabled models + other registered rows)  
**Method:** assign brand **solely from public X bios** (and handle name for official vs staff). Brand ids use table-6 `nickname`.

---

## Summary table

| handle | brand | official/staff |
|--------|-------|----------------|
| `alexandr_wang` | `llama` | staff |
| `BytePlusGlobal` | `seed` | official |
| `CunxiangWang` | `glm` | staff |
| `echojuliett` | `upstage` | staff |
| `EileenTal` | `stepfun` | staff |
| `liulicheng10` | `stepfun` | staff |
| `louszbd` | `glm` | staff |
| `Meituan_LongCat` | — *(not in table 6)* | official |
| `mertunsal2020` | `mistral` | staff |
| `PaddlePaddle` | `ernie` | official |
| `robbyant_brain` | — *(not in table 6)* | official |
| `ShunyuYao12` | — *(bio insufficient)* | staff *(personal handle; brand unknown)* |
| `sophiamyang` | `mistral` | staff |
| `Stefania_druga` | `sakana_ai` | staff |
| `xiong_hui_chen` | `qwen` | staff |
| `xuanmingzhangai` | `qwen` | staff |
| `Zai_org` | `glm` | official |
| `ZhihuFrontier` | — *(not in table 6)* | official |
| `ZixuanLi_` | `glm` | staff |
| `zRdianjiao` | `glm` | staff |

---

## Bio → decision notes

| handle | Bio signal (excerpt) | Why brand / type |
|--------|----------------------|------------------|
| `alexandr_wang` | “chief ai officer **@meta**, founder @scale_ai…” | Meta → enabled brand `llama`; personal name + title → **staff** |
| `BytePlusGlobal` | “Official API access to **Seedance, Seedream, Seed**… powered by **ByteDance**” | Seed family → `seed` (table 6 other rows / migration 030); product org handle → **official** |
| `CunxiangWang` | “Researcher **@Zai_org**… Core contributor to **GLM** series” | `glm`; personal → **staff** |
| `echojuliett` | “Chief Product Officer **@upstageai**” | `upstage`; **staff** |
| `EileenTal` | “GM, Developer Business **@StepFun**” | `stepfun`; **staff** |
| `liulicheng10` | “Post Train **@StepFun_ai** … Opinions are my own” | `stepfun`; **staff** |
| `louszbd` | “Code with **GLM @Zai_org**” | `glm`; **staff** |
| `Meituan_LongCat` | “**Official account** of Meituan LongCat LLM” | Meituan/LongCat **not** in table 6; wording → **official** |
| `mertunsal2020` | “Training Formal Math AI **@MistralAI**…” | `mistral`; **staff** |
| `PaddlePaddle` | “Powering the **ERNIE** model family” | `ernie`; product platform name → **official** |
| `robbyant_brain` | “**@AntGroup** Affiliate \| Building Practical Embodied AI” | Ant/Robbyant **not** in table 6; org brand → **official** |
| `ShunyuYao12` | only “Language agents” | **No company/brand** in bio; personal-style handle → staff-ish, brand **—** |
| `sophiamyang` | “Head of Developer Relations **@MistralAI**” | `mistral`; **staff** |
| `Stefania_druga` | “Staff Research Scientist **@SakanaAILabs**…” | `sakana_ai`; **staff** |
| `xiong_hui_chen` | “**Qwen** team researcher… lead **qwen-robot** project” | `qwen`; **staff** |
| `xuanmingzhangai` | “**@Alibaba_Qwen** Prev.@Stanford…” | `qwen`; **staff** |
| `Zai_org` | “The AI Lab behind **GLM** models…” | `glm`; lab org handle → **official** |
| `ZhihuFrontier` | “Powered by **知乎**/zhihu…” | Zhihu **not** in table 6; org media → **official** |
| `ZixuanLi_` | “Lead … **@Zai_org**” | `glm`; **staff** |
| `zRdianjiao` | “Algorithm Engineer **@Zai_org** — **GLM** model research…” | `glm`; **staff** |

---

## Counts

| category | n |
|----------|--:|
| Mapped to a table-6 brand | 15 |
| No matching table-6 brand | 3 (`Meituan_LongCat`, `robbyant_brain`, `ZhihuFrontier`) |
| Bio insufficient for brand | 1 (`ShunyuYao12`) |
| official | 5 |
| staff | 15 |

### By brand (`nickname`)

| brand | handles |
|-------|---------|
| `glm` | `Zai_org` (official), `CunxiangWang`, `louszbd`, `ZixuanLi_`, `zRdianjiao` |
| `stepfun` | `EileenTal`, `liulicheng10` |
| `mistral` | `mertunsal2020`, `sophiamyang` |
| `qwen` | `xiong_hui_chen`, `xuanmingzhangai` |
| `llama` | `alexandr_wang` |
| `seed` | `BytePlusGlobal` (official) |
| `ernie` | `PaddlePaddle` (official) |
| `upstage` | `echojuliett` |
| `sakana_ai` | `Stefania_druga` |
| — | `Meituan_LongCat`, `robbyant_brain`, `ZhihuFrontier`, `ShunyuYao12` |

---

## Caveats

1. **`BytePlusGlobal`:** If restricted to the 20 *enabled* nicknames only (excluding migration-030 rows), closest ByteDance-enabled brand is `doubao`, not `seed`. Bio names Seed products explicitly, so `seed` is the better table-6 row.
2. **`PaddlePaddle`:** Brand is ERNIE via “Powering the ERNIE model family”; handle is Baidu’s DL platform, not the `ernie` product name.
3. **`Meituan_LongCat` / `robbyant_brain` / `ZhihuFrontier`:** Clear orgs, but **no table-6 brand**.
4. **`ShunyuYao12`:** Cannot assign a brand from bio alone.
5. Classification **official vs staff** uses bio wording (“Official account…”, org product handle) vs personal names + job titles; not X’s verified-organization badge.

---

## Full bios used (from list export)

| handle | name | bio |
|--------|------|-----|
| `alexandr_wang` | Alexandr Wang | chief ai officer @meta, founder @scale_ai. rational in the fullness of time |
| `BytePlusGlobal` | BytePlus | Official API access to Seedance, Seedream, Seed and more. Enterprise AI and cloud, powered by ByteDance. Built for businesses scaling with AI. |
| `CunxiangWang` | Cunxiang Wang | Researcher @Zai_org, Postdoc @thukeg, working with @jietang. Core contributor to GLM series. Focusing on real long-horizon agentic tasks, self-evolving LLMs |
| `echojuliett` | Lucy Park | Chief Product Officer @upstageai |
| `EileenTal` | Ailing Teng | GM, Developer Business @StepFun |
| `liulicheng10` | Licheng Liu | Post Train @StepFun_ai \| incoming Phd @WisconsinCS Opinions are my own |
| `louszbd` | Lou | Code with GLM @Zai_org |
| `Meituan_LongCat` | Meituan LongCat | Official account of Meituan LongCat LLM |
| `mertunsal2020` | Mert Ünsal | Training Formal Math AI @MistralAI, prev. founding engineer @browser_use (YC W25), Kimina Prover @ProjectNumina @ETH_en |
| `PaddlePaddle` | PaddlePaddle | The first independent R&D and Open-Source deep learning platform in China. Powering the ERNIE model family. |
| `robbyant_brain` | Robbyant | @AntGroup Affiliate \| Building Practical Embodied AI. Intelligence in Action, Benefits for Everyone. |
| `ShunyuYao12` | Shunyu Yao | Language agents |
| `sophiamyang` | Sophia Yang, Ph.D. | Head of Developer Relations @MistralAI \| Board of @NumFOCUS |
| `Stefania_druga` | Stefania Druga | Staff Research Scientist @SakanaAILabs RSI Lab, alumni @GoogleDeepMind @mit |
| `xiong_hui_chen` | xiong-hui (barry) chen | Qwen team researcher. focus on rl algorithm and robotics. lead qwen-robot project |
| `xuanmingzhangai` | xuanming zhang | @Alibaba_Qwen Prev.@Stanford @PKU1898 @UWMadison Interested in AI Theory, Quantitative Theory. |
| `Zai_org` | Z.ai | The AI Lab behind GLM models, dedicated to inspiring the development of AGI to benefit humanity. |
| `ZhihuFrontier` | Zhihu Frontier | Bringing China's AI & tech trends, voices and perspectives to the global stage. Powered by 知乎, China's leading knowledge community. |
| `ZixuanLi_` | Zixuan Li | Lead … @Zai_org. |
| `zRdianjiao` | zR | Algorithm Engineer @Zai_org — GLM model research & OSS adaptation · Issues & PRs welcome |
