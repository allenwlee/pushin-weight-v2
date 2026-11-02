# Product-release verification pilot: staging results

Reviewed October30,2026. Staging job `job-dbi56coae00c73b8ug0g` succeeded at08:26:45UTC (17:26:45JST). Runtime `0a974d779e6caa0318bb7c6572e4bafb06c76f90`; no application deployment was needed.

[Updated sortable 35-entry report](2026-10-30-172900-product-release-verification-pilot.html) · [Persisted results and verification](2026-10-30-172900-product-release-verification-pilot.json)

Five existing dossiers received new reviews. The cohort now has **4 confirmed and 31 provisional** entries, up from 2 confirmed. Zero new dossiers were created, all five previous reviews remain available, and the other 30 current reviews stayed unchanged. This is a session-reviewed evidence update, not proof of unattended publisher verification.

| Entry | Current staging result | What changed |
| --- | --- | --- |
| GLM5.3 | Confirmed; access available | Official site links the announcing X account. Announcement is August14 05:17:49UTC. The next post, one second later, asserts Coding Plan/ZCode access; general API/weights were future. |
| GLM5.3Flash | Confirmed; access available | Publisher/account verified. August26 announcement retains its time; API and weight availability now have separate claims. |
| MiniMax Music3 | Provisional | Official blog corroborates the release and August13 date. The website's two-underscore X handle versus the stored one-underscore handle still needs stable-account/history reconciliation. Local access and future cloud access remain distinct. |
| DeepSeek1017 | Provisional in current importer; primary-site corroboration retained | Official documentation identifies October17 and availability. The selected third-party post's08:57:11UTC time is no longer treated as the release time. Primary web research is retained but needs a collected primary-source milestone path. |
| Nanbeige4.3-33B | Provisional; publisher-repository corroboration retained | The repository identifies33B as the released teacher and3B as future work. The profile links Nanbeige on X and zhipin.com. The selected third-party post time is no longer a release anchor; issuer/source registration remains unresolved. |

## Source checks

- [Z.ai GLM5.3 announcement](https://z.ai/blog/glm-5.3), [Flash announcement](https://z.ai/blog/glm-5.3-flash), and [official documentation](https://docs.z.ai/guides/overview/overview) establish the models and link the selected Zai_org account. The initial blog HTML is a JavaScript shell; browser-rendered text and outgoing links were captured. A confirmed existing-company/account relationship for Zhipu was registered in staging through the shared publisher service, with proof retained in the dossier review.
- [MiniMax's Music3 announcement](https://www.minimax.io/blog/minimax-music-3-0-next-generation-open-weights-production-ready-versatile-music-model) supports the release; it does not resolve the X-account discrepancy.
- [DeepSeek's dated1017 announcement](https://api-docs.deepseek.com/news/news261017/) supports the release date and channels. The Post-only study assessment cannot turn this research document into an independently collected primary announcement.
- [Nanbeige's repository](https://huggingface.co/Nanbeige/Nanbeige4.3-33B) and [publisher profile](https://huggingface.co/Nanbeige) support product identity and publisher links. Current repository availability is not proof of its first historical availability time.

## Verification and storage

The complete five-case import first passed in a rolled-back transaction. The committed import then passed exact repeat checks: same identities/results and no extra rows on replay. Old reviews were preserved. Announcing-source text, primary-page observations and retained capture hashes support the assessed changes. No stored Post was altered.

Three dated cases each reused 186 existing discussion windows: **558uses, zero new numerical snapshots, and zero new snapshots on repeat**. New links attach those existing calculations to the new reviews. Historical measurements for the two corrected third-party anchors remain tied to their old reviews and are not treated as current release-aligned evidence.

Observed row changes:

| Table | Added rows |
| --- | --- |
| `brand_discovery_candidates` | 0 |
| `collection_evidence_archives` | 5 |
| `companies_accounts` | 1 |
| `discussion_window_counts` | 0 |
| `discussion_window_snapshots` | 0 |
| `event_dossier_claims` | 15 |
| `event_dossier_discussion_windows` | 558 |
| `event_dossier_intake_decisions` | 0 |
| `event_dossier_reviews` | 5 |
| `event_dossier_sources` | 0 |
| `event_dossiers` | 0 |
| `product_release_details` | 5 |

End-to-end native-job time was about 6m41s, including startup, rollback validation, two imports, three 186-window studies repeated and export. This is not an isolated TN request latency. Reuse reduced stored rows; verifying reuse still costs computation. The data remains incomplete staging history, unsuitable as a population-wide attention baseline.

## Next integration work

1. Let the evidence-intake path collect and attach primary website/model-card documents as actual sources, with publisher identity and source clocks. The current study imports Post evidence and retains external research in assessment archives; it does not create those independent source observations. Reuse existing collection/dossier storage after inspecting the real writers. A company website may be found through existing account/post/official-company evidence; no Company.url dependency is required.
2. Resolve stable account identity across handle differences and support verified individual creators without inventing Companies.
3. Extend the access-channel vocabulary deliberately for hosted applications/Coding Plans; the current seeded values are only api/weights. GLM5.3's hosted access therefore retains a null channel with exact source wording, not an incorrectapi label.
4. Repeat this evidence-driven correction on the remaining cohort, keeping source candidacy, publisher confirmation, availability, dates and popularity distinct.

No production data, scheduler, live harvester, application code or schema was changed. No new inference/API-model call or paid provider collection was made. The local Company.url revert6257cdf2 remains unpushed; the old staging column is still present and unused by this pilot. Earlier read-only probes failed on collation and an incorrect physical column name; both were corrected before any write, and the final preflight succeeded. No success is claimed for those failed probes.

Private evidence is on fuchitalee under `.local/2026-10-30-release-verification-pilot/`; native-job receipts and downloaded result packets remain under `.local/2026-10-29-product-release-lfg/`. The primary capture manifest distinguishes six direct page fetches from three browser-rendered pages; browser assets are additional requests. Public-source summaries here were reviewed in the session; the study is not an automated external verifier.

Browser verification passed at 1280px and 390px: all 35 rows, four confirmed/31 provisional, filtering, sorting, expanded claims and no document overflow. The exported report was visually inspected.
